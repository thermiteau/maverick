"""Tests for H5 — automatic report-interval bookkeeping.

Covers `report end --auto`, phase inheritance, the generate-time flush of
dangling intervals, and the subagent_report hook's decision table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from maverick import report_cli
from maverick.runtime_hooks import subagent_report
from maverick.runtime_hooks.adapters import ClaudeAdapter

# ---------------------------------------------------------------------------
# CLI: end --auto / phase inheritance / flush
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
    return tmp_path


def _begin(issue: int, action: str, **ids) -> None:
    args = argparse.Namespace(
        action=action,
        issue=issue,
        phase=ids.pop("phase", None),
        agent=ids.pop("agent", None),
        skill_name=ids.pop("skill_name", None),
        topic=ids.pop("topic", None),
        llm=None,
    )
    assert report_cli._report_begin(args) == 0


def _end_auto(issue: int, outcome: str = "success", **guards) -> int:
    args = argparse.Namespace(
        action=None,
        auto=True,
        issue=issue,
        outcome=outcome,
        if_action=guards.pop("if_action", None),
        if_agent=guards.pop("if_agent", None),
        phase=None,
        agent=None,
        skill_name=None,
        topic=None,
        notes=None,
        llm=None,
    )
    return report_cli._report_end(args)


def _events(issue: int, repo_root: Path):
    return report_cli.load_timeline(report_cli.timeline_path(issue, repo_root=repo_root))


class TestEndAuto:
    def test_closes_most_recent_interval(self, repo_root):
        _begin(7, "agent-dispatch", agent="agent-issue-analyst", phase="design")
        _begin(7, "skill-dispatch", skill_name="do-code", phase="implement")
        assert _end_auto(7, "success") == 0
        rows = _events(7, repo_root)
        assert len(rows) == 1
        assert rows[0]["action"] == "skill-dispatch"
        assert rows[0]["dispatched_skill"] == "do-code"
        assert rows[0]["outcome"] == "success"
        # The older interval is still pending
        pending = report_cli._read_pending(report_cli.pending_path(7, repo_root=repo_root))
        assert list(pending) == ["agent-dispatch:agent-issue-analyst"]

    def test_if_agent_guard(self, repo_root):
        _begin(7, "agent-dispatch", agent="agent-code-reviewer", phase="review")
        assert _end_auto(7, if_agent="agent-tech-docs-writer") == 1  # no match: no-op
        assert _end_auto(7, if_agent="agent-code-reviewer") == 0
        rows = _events(7, repo_root)
        assert rows[0]["maverick_agent"] == "agent-code-reviewer"

    def test_if_action_guard(self, repo_root):
        _begin(7, "skill-dispatch", skill_name="do-code", phase="implement")
        assert _end_auto(7, if_action="agent-dispatch") == 1
        assert _end_auto(7, if_action="skill-dispatch") == 0

    def test_no_pending_is_warning_noop(self, repo_root):
        assert _end_auto(7) == 1
        assert _events(7, repo_root) == []


class TestPhaseInheritance:
    def test_begin_inherits_phase_from_timeline(self, repo_root):
        # A phase-boundary row establishes the current phase.
        boundary = {
            "schema_version": report_cli.SCHEMA_VERSION,
            "action": "phase-boundary",
            "start_ts": "2026-07-02T10:00:00Z",
            "instance_id": "i-x",
            "issue": 7,
            "maverick_version": "0.0.0",
            "phase": "implement",
            "llm": "test-llm",
        }
        assert report_cli.append_event(boundary, repo_root=repo_root)
        _begin(7, "skill-dispatch", skill_name="do-code")  # no --phase
        assert _end_auto(7, "success") == 0
        rows = _events(7, repo_root)
        interval = [r for r in rows if r["action"] == "skill-dispatch"][0]
        assert interval["phase"] == "implement"


class TestGenerateFlush:
    def test_dangling_intervals_flushed_as_unknown(self, repo_root):
        _begin(7, "agent-dispatch", agent="agent-tech-docs-writer", phase="docs")
        args = argparse.Namespace(issue=7, llm=None)
        flushed = report_cli._flush_dangling_intervals(7, args)
        assert flushed == 1
        rows = _events(7, repo_root)
        assert rows[0]["outcome"] == "unknown"
        assert rows[0]["maverick_agent"] == "agent-tech-docs-writer"
        # Pending is now empty; a second flush is a no-op.
        assert report_cli._flush_dangling_intervals(7, args) == 0


# ---------------------------------------------------------------------------
# Hook decision table
# ---------------------------------------------------------------------------

class _ClaudeHook:
    """The subagent-report handler as Claude Code drives it."""

    @staticmethod
    def handle(payload: dict, env: dict, registry: Path) -> list[str] | None:
        event = ClaudeAdapter().normalize(payload)
        return subagent_report.report_args(
            event, env, registry, id_path=registry.parent / "no-instance-id"
        )


@pytest.fixture(scope="module")
def hook():
    return _ClaudeHook()


@pytest.fixture
def one_claim(tmp_path):
    registry = tmp_path / "active-claims.json"
    registry.write_text(
        json.dumps(
            {"claims": [{"repo": "o/r", "issue": 42, "instance_id": "i-hook"}]}
        )
    )
    return registry


ENV = {"MAVERICK_INSTANCE_ID": "i-hook"}


class TestHookDecisions:
    def test_subagent_start_begins_interval(self, hook, one_claim):
        cmd = hook.handle(
            {"hook_event_name": "SubagentStart", "agent_type": "agent-code-reviewer"},
            ENV,
            registry=one_claim,
        )
        assert cmd == [
            "begin", "agent-dispatch", "--issue", "42", "--agent", "agent-code-reviewer",
        ]

    def test_subagent_stop_auto_ends(self, hook, one_claim):
        cmd = hook.handle(
            {"hook_event_name": "SubagentStop", "agent_type": "agent-issue-analyst"},
            ENV,
            registry=one_claim,
        )
        assert cmd is not None
        assert cmd[:2] == ["end", "--auto"]
        assert "--if-agent" in cmd and "agent-issue-analyst" in cmd
        assert "--if-action" in cmd and "agent-dispatch" in cmd

    def test_namespaced_agent_name_stripped(self, hook, one_claim):
        """Plugin agents report as maverick:agent-x — the namespace must
        not defeat the agent- guard (live-run regression)."""
        cmd = hook.handle(
            {
                "hook_event_name": "SubagentStart",
                "agent_type": "maverick:agent-code-reviewer",
            },
            ENV,
            registry=one_claim,
        )
        assert cmd is not None
        assert "agent-code-reviewer" in cmd
        assert not any("maverick:" in part for part in cmd)

    def test_non_maverick_agent_ignored(self, hook, one_claim):
        cmd = hook.handle(
            {"hook_event_name": "SubagentStart", "agent_type": "Explore"},
            ENV,
            registry=one_claim,
        )
        assert cmd is None

    def test_tracked_skill_begins_dispatch(self, hook, one_claim):
        cmd = hook.handle(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": "do-code"},
            },
            ENV,
            registry=one_claim,
        )
        assert cmd == [
            "begin", "skill-dispatch", "--issue", "42", "--skill-name", "do-code",
        ]

    def test_namespaced_skill_matches(self, hook, one_claim):
        cmd = hook.handle(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": "maverick:do-cybersecurity-review"},
            },
            ENV,
            registry=one_claim,
        )
        assert cmd is not None
        assert "do-cybersecurity-review" in cmd

    def test_untracked_skill_ignored(self, hook, one_claim):
        cmd = hook.handle(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": "do-issue-solo"},
            },
            ENV,
            registry=one_claim,
        )
        assert cmd is None

    def test_no_claim_is_silent(self, hook, tmp_path):
        registry = tmp_path / "missing.json"
        cmd = hook.handle(
            {"hook_event_name": "SubagentStart", "agent_type": "agent-code-reviewer"},
            ENV,
            registry=registry,
        )
        assert cmd is None

    def test_multiple_claims_is_silent(self, hook, tmp_path):
        registry = tmp_path / "active-claims.json"
        registry.write_text(
            json.dumps(
                {
                    "claims": [
                        {"repo": "o/r", "issue": 1, "instance_id": "i-hook"},
                        {"repo": "o/r", "issue": 2, "instance_id": "i-hook"},
                    ]
                }
            )
        )
        cmd = hook.handle(
            {"hook_event_name": "SubagentStart", "agent_type": "agent-code-reviewer"},
            ENV,
            registry=registry,
        )
        assert cmd is None

    def test_other_instances_claim_is_silent(self, hook, tmp_path):
        registry = tmp_path / "active-claims.json"
        registry.write_text(
            json.dumps({"claims": [{"repo": "o/r", "issue": 1, "instance_id": "other"}]})
        )
        cmd = hook.handle(
            {"hook_event_name": "SubagentStart", "agent_type": "agent-code-reviewer"},
            ENV,
            registry=registry,
        )
        assert cmd is None


# ---------------------------------------------------------------------------
# Multi-claim attribution (do-epic holds the epic + every in-flight story)
# ---------------------------------------------------------------------------


@pytest.fixture
def epic_claims(tmp_path):
    """An epic session: epic #100 plus stories #101 and #102 in flight."""
    registry = tmp_path / "active-claims.json"
    registry.write_text(
        json.dumps(
            {
                "claims": [
                    {"repo": "o/r", "issue": n, "instance_id": "i-hook"}
                    for n in (100, 101, 102)
                ]
            }
        )
    )
    return registry


def _agent_call(event: str, prompt: str, cwd: Path, **extra) -> dict:
    return {
        "hook_event_name": event,
        "tool_name": "Agent",
        "cwd": str(cwd),
        "tool_input": {
            "subagent_type": "maverick:agent-code-reviewer",
            "prompt": prompt,
            **extra,
        },
    }


class TestMultiClaimAttribution:
    def test_marker_in_agent_prompt_attributes_dispatch(self, hook, epic_claims, tmp_path):
        cmd = hook.handle(
            _agent_call("PreToolUse", "Review this.\nmaverick-issue: 102\n", tmp_path),
            ENV,
            registry=epic_claims,
        )
        assert cmd == [
            "begin", "agent-dispatch", "--issue", "102", "--agent", "agent-code-reviewer",
        ]

    def test_post_tool_use_closes_the_same_interval(self, hook, epic_claims, tmp_path):
        cmd = hook.handle(
            _agent_call("PostToolUse", "maverick-issue: #101", tmp_path),
            ENV,
            registry=epic_claims,
        )
        assert cmd is not None
        assert cmd[:2] == ["end", "--auto"]
        assert cmd[cmd.index("--issue") + 1] == "101"
        assert cmd[cmd.index("--if-agent") + 1] == "agent-code-reviewer"

    def test_background_dispatch_not_closed_at_launch(self, hook, epic_claims, tmp_path):
        cmd = hook.handle(
            _agent_call(
                "PostToolUse", "maverick-issue: 101", tmp_path, run_in_background=True
            ),
            ENV,
            registry=epic_claims,
        )
        assert cmd is None

    def test_marker_for_unclaimed_issue_ignored(self, hook, epic_claims, tmp_path):
        cmd = hook.handle(
            _agent_call("PreToolUse", "maverick-issue: 999", tmp_path),
            ENV,
            registry=epic_claims,
        )
        assert cmd is None  # several claims, no usable marker, no story branch

    def test_marker_in_skill_args(self, hook, epic_claims, tmp_path):
        cmd = hook.handle(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "cwd": str(tmp_path),
                "tool_input": {"skill": "do-code", "args": "add x (maverick-issue: 101)"},
            },
            ENV,
            registry=epic_claims,
        )
        assert cmd == [
            "begin", "skill-dispatch", "--issue", "101", "--skill-name", "do-code",
        ]

    def test_story_branch_attributes_when_no_marker(
        self, hook, epic_claims, tmp_path, monkeypatch
    ):
        seen: list[Path] = []

        def fake_branch(cwd: Path) -> int | None:
            seen.append(cwd)
            return 101

        monkeypatch.setattr(subagent_report, "branch_issue", fake_branch)
        cmd = hook.handle(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "cwd": str(tmp_path),
                "tool_input": {"skill": "do-cybersecurity-review"},
            },
            ENV,
            registry=epic_claims,
        )
        assert cmd is not None and cmd[cmd.index("--issue") + 1] == "101"
        assert seen == [tmp_path]

    def test_single_claim_needs_no_marker(self, hook, one_claim, tmp_path):
        cmd = hook.handle(
            _agent_call("PreToolUse", "no marker here", tmp_path),
            ENV,
            registry=one_claim,
        )
        assert cmd is not None and cmd[cmd.index("--issue") + 1] == "42"

    def test_non_maverick_agent_tool_ignored(self, hook, epic_claims, tmp_path):
        payload = _agent_call("PreToolUse", "maverick-issue: 101", tmp_path)
        payload["tool_input"]["subagent_type"] = "general-purpose"
        assert hook.handle(payload, ENV, registry=epic_claims) is None


class TestBranchIssue:
    def test_reads_issue_from_story_branch(self, tmp_path):
        import subprocess

        subprocess.run(["git", "init", "-q", "-b", "feat/123-add-export", str(tmp_path)], check=True)
        assert subagent_report.branch_issue(tmp_path) == 123

    def test_non_story_branch(self, tmp_path):
        import subprocess

        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
        assert subagent_report.branch_issue(tmp_path) is None

    def test_not_a_repo(self, tmp_path):
        assert subagent_report.branch_issue(tmp_path / "missing") is None


# ---------------------------------------------------------------------------
# Session model detection
# ---------------------------------------------------------------------------


class TestSessionModel:
    def test_transcript_last_assistant_model_wins(self, tmp_path):
        from maverick.runtime_hooks import session_model

        transcript = tmp_path / "t.jsonl"
        rows = [
            {"type": "assistant", "message": {"model": "claude-sonnet-5-5"}},
            {"type": "user", "message": {"content": "hi"}},
            {"type": "assistant", "message": {"model": "claude-opus-5-5"}},
            {"type": "assistant", "message": {"model": "<synthetic>"}},
        ]
        transcript.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        assert session_model.model_from_transcript(transcript) == "claude-opus-5-5"

    def test_missing_transcript(self, tmp_path):
        from maverick.runtime_hooks import session_model

        assert session_model.model_from_transcript(tmp_path / "nope.jsonl") is None

    def test_hook_records_session_start_model(self, tmp_path, monkeypatch):
        from maverick.runtime_hooks import session_model

        registry = tmp_path / "session-models.json"
        monkeypatch.setattr(session_model, "registry_path", lambda: registry)
        event = ClaudeAdapter().normalize(
            {"hook_event_name": "SessionStart", "model": "claude-opus-5-5"}
        )
        subagent_report.record_model(event, ENV)
        assert session_model.lookup("i-hook", registry) == "claude-opus-5-5"

    def test_hook_records_model_from_transcript(self, tmp_path, monkeypatch):
        from maverick.runtime_hooks import session_model

        registry = tmp_path / "session-models.json"
        monkeypatch.setattr(session_model, "registry_path", lambda: registry)
        transcript = tmp_path / "t.jsonl"
        transcript.write_text(
            json.dumps({"type": "assistant", "message": {"model": "claude-fable-5-2"}}) + "\n"
        )
        event = ClaudeAdapter().normalize(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": "do-code"},
                "transcript_path": str(transcript),
            }
        )
        subagent_report.record_model(event, ENV)
        assert session_model.lookup("i-hook", registry) == "claude-fable-5-2"

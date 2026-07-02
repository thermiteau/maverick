"""Tests for H5 — automatic report-interval bookkeeping.

Covers `report end --auto`, phase inheritance, the generate-time flush of
dangling intervals, and the subagent_report hook's decision table.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from maverick import report_cli

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

HOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "maverick"
    / "hooks"
    / "subagent_report.py"
)


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("subagent_report_hook", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


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

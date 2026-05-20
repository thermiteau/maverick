"""Unit tests for the v1 Maverick workflow report CLI surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from maverick import report_cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    report_cli.build_subparsers(sub)
    return parser.parse_args(list(argv))


def _full_event(**overrides: Any) -> dict[str, Any]:
    """A minimum-viable, schema-valid event. Override fields per test."""
    base: dict[str, Any] = {
        "schema_version": report_cli.SCHEMA_VERSION,
        "action": "phase-boundary",
        "start_ts": "2026-05-19T10:00:00Z",
        "instance_id": "test1234ab",
        "issue": 321,
        "maverick_version": "3.3.2-dev",
        "phase": "design",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


class TestArgparseWiring:
    def test_run_start_parses(self):
        args = _parse("report", "run-start", "do-issue-solo", "--issue", "5")
        assert args._handler is report_cli._report_run_start
        assert args.skill == "do-issue-solo"
        assert args.issue == 5

    def test_phase_parses(self):
        args = _parse("report", "phase", "--issue", "5", "--phase", "design")
        assert args._handler is report_cli._report_phase
        assert args.phase == "design"

    def test_phase_rejects_unknown_value(self):
        with pytest.raises(SystemExit):
            _parse("report", "phase", "--issue", "5", "--phase", "not-a-phase")

    def test_begin_end_parse(self):
        a = _parse("report", "begin", "agent-dispatch", "--issue", "5",
                   "--phase", "design", "--agent", "agent-x")
        assert a._handler is report_cli._report_begin
        b = _parse("report", "end", "agent-dispatch", "--issue", "5",
                   "--outcome", "success", "--agent", "agent-x")
        assert b._handler is report_cli._report_end
        assert b.outcome == "success"

    def test_end_outcome_required_and_validated(self):
        with pytest.raises(SystemExit):
            _parse("report", "end", "agent-dispatch", "--issue", "5", "--agent", "agent-x")
        with pytest.raises(SystemExit):
            _parse("report", "end", "agent-dispatch", "--issue", "5",
                   "--outcome", "winning", "--agent", "agent-x")

    def test_commit_parses(self):
        args = _parse("report", "commit", "--issue", "5", "--phase", "implement",
                      "--sha", "abc1234", "--subject", "feat: a thing")
        assert args._handler is report_cli._report_commit
        assert args.sha == "abc1234"

    def test_note_parses(self):
        args = _parse("report", "note", "--issue", "5", "--phase", "design",
                      "--text", "narrative")
        assert args._handler is report_cli._report_note

    def test_generate_and_verify(self):
        g = _parse("report", "generate", "owner/repo", "42")
        assert g._handler is report_cli._report_generate
        v = _parse("report", "verify", "42")
        assert v._handler is report_cli._report_verify


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_minimal_event_passes(self):
        report_cli._validate(_full_event())  # does not raise

    def test_wrong_schema_version_rejected(self):
        with pytest.raises(report_cli.SchemaError, match="schema_version"):
            report_cli._validate(_full_event(schema_version=2))

    def test_unknown_action_rejected(self):
        with pytest.raises(report_cli.SchemaError, match="action"):
            report_cli._validate(_full_event(action="invent-something"))

    def test_unknown_phase_rejected(self):
        with pytest.raises(report_cli.SchemaError, match="phase"):
            report_cli._validate(_full_event(phase="bogus"))

    def test_start_ts_must_be_z_suffixed(self):
        with pytest.raises(report_cli.SchemaError, match="start_ts"):
            report_cli._validate(_full_event(start_ts="2026-05-19T10:00:00+00:00"))

    def test_atomic_action_must_not_carry_end_ts(self):
        with pytest.raises(report_cli.SchemaError, match="must not carry end_ts"):
            report_cli._validate(_full_event(action="phase-boundary",
                                             end_ts="2026-05-19T10:01:00Z"))

    def test_interval_action_requires_end_ts(self):
        with pytest.raises(report_cli.SchemaError, match="requires end_ts"):
            report_cli._validate(_full_event(action="agent-dispatch",
                                             outcome="success", end_ts=None))

    def test_interval_action_requires_outcome(self):
        with pytest.raises(report_cli.SchemaError, match="requires outcome"):
            report_cli._validate(_full_event(action="agent-dispatch",
                                             end_ts="2026-05-19T10:01:00Z"))

    def test_unknown_outcome_rejected(self):
        with pytest.raises(report_cli.SchemaError, match="outcome"):
            report_cli._validate(_full_event(action="agent-dispatch",
                                             end_ts="2026-05-19T10:01:00Z",
                                             outcome="meh"))

    def test_commit_requires_sha_and_subject(self):
        with pytest.raises(report_cli.SchemaError, match="commit action requires sha"):
            report_cli._validate(_full_event(action="commit", phase="implement"))
        with pytest.raises(report_cli.SchemaError, match="subject"):
            report_cli._validate(_full_event(action="commit", phase="implement", sha="abc"))

    def test_note_requires_text(self):
        with pytest.raises(report_cli.SchemaError, match="notes text"):
            report_cli._validate(_full_event(action="note"))

    def test_run_start_requires_skill(self):
        with pytest.raises(report_cli.SchemaError, match="run-start.*maverick_skill"):
            report_cli._validate(_full_event(action="run-start", phase="claimed"))

    def test_missing_required_system_field_rejected(self):
        e = _full_event()
        del e["instance_id"]
        with pytest.raises(report_cli.SchemaError, match="instance_id"):
            report_cli._validate(e)

    def test_skill_dispatch_requires_dispatched_skill(self):
        with pytest.raises(report_cli.SchemaError, match="skill-dispatch.*dispatched_skill"):
            report_cli._validate(_full_event(
                action="skill-dispatch", phase="security",
                end_ts="2026-05-19T10:01:00Z", outcome="success",
            ))

    def test_agent_dispatch_dispatched_skill_optional(self):
        # An agent that operates under a skill: valid
        report_cli._validate(_full_event(
            action="agent-dispatch", phase="docs",
            end_ts="2026-05-19T10:01:00Z", outcome="success",
            maverick_agent="agent-tech-docs-writer",
            dispatched_skill="do-docs",
        ))
        # An agent dispatched without an associated skill: also valid
        report_cli._validate(_full_event(
            action="agent-dispatch", phase="design",
            end_ts="2026-05-19T10:01:00Z", outcome="success",
            maverick_agent="agent-issue-analyst",
        ))


# ---------------------------------------------------------------------------
# append_event + load_timeline
# ---------------------------------------------------------------------------


class TestAppendEvent:
    def test_round_trip(self, tmp_path: Path):
        event = _full_event(action="phase-boundary", phase="design")
        ok = report_cli.append_event(event, repo_root=tmp_path)
        assert ok is True
        path = report_cli.timeline_path(321, repo_root=tmp_path)
        assert path.exists()
        loaded = json.loads(path.read_text().strip())
        assert loaded["action"] == "phase-boundary"
        assert loaded["phase"] == "design"

    def test_invalid_event_returns_false_writes_nothing(self, tmp_path: Path):
        bad = _full_event(action="phase-boundary", end_ts="2026-05-19T11:00:00Z")
        ok = report_cli.append_event(bad, repo_root=tmp_path)
        assert ok is False
        path = report_cli.timeline_path(321, repo_root=tmp_path)
        assert not path.exists()

    def test_failure_returns_false_does_not_raise(self, tmp_path: Path, monkeypatch):
        from pathlib import Path as P

        def boom(self, *a, **kw):
            raise PermissionError("nope")

        monkeypatch.setattr(P, "mkdir", boom)
        ok = report_cli.append_event(_full_event(), repo_root=tmp_path)
        assert ok is False


class TestLoadTimeline:
    def test_skips_invalid_rows_with_warning(self, tmp_path: Path, capsys):
        path = tmp_path / "t.jsonl"
        good = _full_event(start_ts="2026-05-19T10:00:00Z")
        bad = _full_event(start_ts="2026-05-19T10:01:00Z", action="invent-something")
        path.write_text(
            "\n".join([
                json.dumps(good),
                "{not json",
                json.dumps(bad),
                json.dumps(_full_event(start_ts="2026-05-19T10:02:00Z", phase="tasks")),
            ])
        )
        events = report_cli.load_timeline(path)
        assert len(events) == 2
        assert [e["phase"] for e in events] == ["design", "tasks"]
        captured = capsys.readouterr()
        assert "warning" in captured.err

    def test_sorts_by_start_ts(self, tmp_path: Path):
        path = tmp_path / "t.jsonl"
        path.write_text("\n".join([
            json.dumps(_full_event(start_ts="2026-05-19T10:02:00Z", phase="tasks")),
            json.dumps(_full_event(start_ts="2026-05-19T10:01:00Z", phase="design")),
        ]))
        events = report_cli.load_timeline(path)
        assert [e["phase"] for e in events] == ["design", "tasks"]


# ---------------------------------------------------------------------------
# begin/end pairing via the pending sidecar
# ---------------------------------------------------------------------------


class TestBeginEnd:
    def _setup(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "test1234ab")

    def test_round_trip_writes_one_interval_row(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        # begin
        begin_args = _parse("report", "begin", "agent-dispatch", "--issue", "321",
                            "--phase", "design", "--agent", "agent-x")
        report_cli._report_begin(begin_args)
        # end
        end_args = _parse("report", "end", "agent-dispatch", "--issue", "321",
                          "--outcome", "success", "--agent", "agent-x")
        report_cli._report_end(end_args)

        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert len(events) == 1
        e = events[0]
        assert e["action"] == "agent-dispatch"
        assert e["maverick_agent"] == "agent-x"
        assert e["outcome"] == "success"
        assert e["start_ts"].endswith("Z")
        assert e["end_ts"].endswith("Z")
        assert e["start_ts"] <= e["end_ts"]
        # pending file should be empty (or absent of this key)
        pending = report_cli._read_pending(report_cli.pending_path(321, repo_root=tmp_path))
        assert "agent-dispatch:agent-x" not in pending

    def test_agent_dispatch_skill_name_persists_as_dispatched_skill(
        self, tmp_path: Path, monkeypatch
    ):
        """`--skill-name` on agent-dispatch lands on the row as `dispatched_skill`."""
        self._setup(tmp_path, monkeypatch)
        report_cli._report_begin(_parse(
            "report", "begin", "agent-dispatch", "--issue", "321",
            "--phase", "docs", "--agent", "agent-tech-docs-writer",
            "--skill-name", "do-docs",
        ))
        report_cli._report_end(_parse(
            "report", "end", "agent-dispatch", "--issue", "321",
            "--agent", "agent-tech-docs-writer", "--outcome", "success",
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert events[0]["dispatched_skill"] == "do-docs"
        assert events[0]["maverick_agent"] == "agent-tech-docs-writer"

    def test_skill_dispatch_skill_name_persists(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        report_cli._report_begin(_parse(
            "report", "begin", "skill-dispatch", "--issue", "321",
            "--phase", "security", "--skill-name", "do-cybersecurity-review",
        ))
        report_cli._report_end(_parse(
            "report", "end", "skill-dispatch", "--issue", "321",
            "--skill-name", "do-cybersecurity-review", "--outcome", "success",
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert events[0]["dispatched_skill"] == "do-cybersecurity-review"
        assert events[0].get("maverick_agent") is None


class TestLLMResolution:
    """The fallback chain in `_current_llm`:
    explicit → env → config.agents → config.skills → config.default →
    run-start lookup → FALLBACK_LLM.
    """

    def _setup(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "test1234ab")
        monkeypatch.delenv("MAVERICK_LLM", raising=False)

    def _patch_config(self, monkeypatch, **overrides):
        """Replace `read_llm_config` with a fixture that returns the given values."""
        from maverick import config

        defaults = {
            "default": overrides.get("default", "claude-opus-4-7"),
            "agents": overrides.get("agents", {}),
            "skills": overrides.get("skills", {}),
        }
        monkeypatch.setattr(config, "read_llm_config", lambda path=None: defaults)

    def test_falls_back_to_literal_when_config_read_fails(
        self, tmp_path: Path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        # Force the config loader to raise so the resolution falls through.
        from maverick import config

        def boom(path=None):
            raise RuntimeError("config unreadable")

        monkeypatch.setattr(config, "read_llm_config", boom)
        assert report_cli._current_llm() == report_cli.FALLBACK_LLM
        assert report_cli.FALLBACK_LLM == "claude-code"

    def test_config_default_used_when_no_explicit_or_env(
        self, tmp_path: Path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        self._patch_config(monkeypatch, default="claude-opus-4-7")
        assert report_cli._current_llm() == "claude-opus-4-7"

    def test_explicit_wins_over_env_and_config(
        self, tmp_path: Path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("MAVERICK_LLM", "claude-sonnet-4-6")
        self._patch_config(monkeypatch, default="claude-opus-4-7")
        assert report_cli._current_llm(explicit="claude-haiku-4-5") == "claude-haiku-4-5"

    def test_env_wins_over_config(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("MAVERICK_LLM", "claude-sonnet-4-6")
        self._patch_config(monkeypatch, default="claude-opus-4-7")
        assert report_cli._current_llm() == "claude-sonnet-4-6"

    def test_config_per_agent_override(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        self._patch_config(
            monkeypatch,
            default="claude-opus-4-7",
            agents={"agent-tech-docs-writer": "claude-sonnet-4-6"},
        )
        # Same agent as the per-agent rule → Sonnet
        assert (
            report_cli._current_llm(agent="agent-tech-docs-writer")
            == "claude-sonnet-4-6"
        )
        # Different agent → falls through to default (Opus)
        assert (
            report_cli._current_llm(agent="agent-issue-analyst") == "claude-opus-4-7"
        )

    def test_config_per_skill_override(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        self._patch_config(
            monkeypatch,
            default="claude-opus-4-7",
            skills={"do-test": "claude-sonnet-4-6"},
        )
        assert report_cli._current_llm(skill_name="do-test") == "claude-sonnet-4-6"
        assert report_cli._current_llm(skill_name="do-code") == "claude-opus-4-7"

    def test_per_agent_beats_per_skill_when_both_apply(
        self, tmp_path: Path, monkeypatch
    ):
        """agent-tech-docs-writer dispatched under do-docs: agent rule wins."""
        self._setup(tmp_path, monkeypatch)
        self._patch_config(
            monkeypatch,
            default="claude-opus-4-7",
            agents={"agent-tech-docs-writer": "claude-haiku-4-5"},
            skills={"do-docs": "claude-sonnet-4-6"},
        )
        assert (
            report_cli._current_llm(
                agent="agent-tech-docs-writer", skill_name="do-docs"
            )
            == "claude-haiku-4-5"
        )

    def test_run_start_inherited_when_no_other_source(
        self, tmp_path: Path, monkeypatch
    ):
        """If config raises and nothing else applies, fall back to the latest
        run-start's llm before the literal."""
        self._setup(tmp_path, monkeypatch)
        from maverick import config

        monkeypatch.setattr(
            config, "read_llm_config", lambda path=None: (_ for _ in ()).throw(RuntimeError())
        )
        report_cli.append_event(
            _full_event(action="run-start", phase="claimed",
                        maverick_skill="do-issue-solo", llm="claude-opus-4-7"),
            repo_root=tmp_path,
        )
        assert report_cli._current_llm(issue=321, repo_root=tmp_path) == "claude-opus-4-7"

    def test_writer_auto_populates_llm_on_every_row(
        self, tmp_path: Path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("MAVERICK_LLM", "claude-opus-4-7")
        report_cli._report_run_start(_parse(
            "report", "run-start", "do-issue-solo", "--issue", "321"
        ))
        report_cli._report_commit(_parse(
            "report", "commit", "--issue", "321", "--phase", "implement",
            "--sha", "abc1234", "--subject", "feat: x"
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert all(e.get("llm") == "claude-opus-4-7" for e in events)

    def test_per_row_llm_override_for_subagent(self, tmp_path: Path, monkeypatch):
        """Multi-model: orchestrator runs Opus, one subagent runs Sonnet."""
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("MAVERICK_LLM", "claude-opus-4-7")
        report_cli._report_run_start(_parse(
            "report", "run-start", "do-issue-solo", "--issue", "321"
        ))
        # Subagent dispatch with explicit override
        report_cli._report_begin(_parse(
            "report", "begin", "agent-dispatch", "--issue", "321",
            "--phase", "design", "--agent", "agent-issue-analyst",
            "--llm", "claude-sonnet-4-6",
        ))
        report_cli._report_end(_parse(
            "report", "end", "agent-dispatch", "--issue", "321",
            "--agent", "agent-issue-analyst", "--outcome", "success",
            "--llm", "claude-sonnet-4-6",
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        by_action = {e["action"]: e for e in events}
        assert by_action["run-start"]["llm"] == "claude-opus-4-7"
        assert by_action["agent-dispatch"]["llm"] == "claude-sonnet-4-6"

    def test_render_surfaces_per_row_llm(self):
        """Rendered table's LLM column reflects the row's llm, not a default."""
        events = [
            _full_event(action="run-start", phase="claimed",
                        maverick_skill="do-issue-solo", llm="claude-opus-4-7",
                        start_ts="2026-05-20T10:00:00Z"),
            _full_event(action="agent-dispatch", phase="design",
                        start_ts="2026-05-20T10:01:00Z",
                        end_ts="2026-05-20T10:02:00Z",
                        maverick_agent="agent-issue-analyst",
                        outcome="success", llm="claude-sonnet-4-6"),
            _full_event(action="phase-boundary", phase="design",
                        start_ts="2026-05-20T10:02:00Z",
                        llm="claude-opus-4-7"),
            _full_event(action="phase-boundary", phase="complete",
                        start_ts="2026-05-20T10:03:00Z",
                        llm="claude-opus-4-7"),
        ]
        md = report_cli.render(issue=321, events=events)
        # Metadata block lists both distinct LLMs
        assert "- LLMs: claude-opus-4-7, claude-sonnet-4-6" in md
        # The agent-dispatch row in the table shows Sonnet
        design_row = next(ln for ln in md.splitlines()
                          if "| Phase 1-2 |" in ln and "agent-dispatch" in ln)
        assert "claude-sonnet-4-6" in design_row
        assert "claude-opus-4-7" not in design_row

    def test_end_without_begin_writes_warning_no_row(self, tmp_path: Path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        end_args = _parse("report", "end", "agent-dispatch", "--issue", "321",
                          "--outcome", "success", "--agent", "agent-x")
        rc = report_cli._report_end(end_args)
        assert rc == 1
        path = report_cli.timeline_path(321, repo_root=tmp_path)
        assert not path.exists()
        assert "no matching open begin" in capsys.readouterr().err

    def test_concurrent_begins_for_different_agents_keep_separate_intervals(
        self, tmp_path: Path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        for agent in ("agent-a", "agent-b"):
            report_cli._report_begin(
                _parse("report", "begin", "agent-dispatch", "--issue", "321",
                       "--phase", "design", "--agent", agent)
            )
        for agent in ("agent-a", "agent-b"):
            report_cli._report_end(
                _parse("report", "end", "agent-dispatch", "--issue", "321",
                       "--outcome", "success", "--agent", agent)
            )
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        agents = sorted(e["maverick_agent"] for e in events)
        assert agents == ["agent-a", "agent-b"]


# ---------------------------------------------------------------------------
# Atomic actions via CLI
# ---------------------------------------------------------------------------


class TestAtomicCommands:
    def _setup(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "test1234ab")

    def test_run_start_writes_skill(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _parse("report", "run-start", "do-issue-solo", "--issue", "321")
        report_cli._report_run_start(args)
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert events[0]["maverick_skill"] == "do-issue-solo"
        assert events[0]["action"] == "run-start"

    def test_fmt_ts_includes_date(self):
        # _fmt_ts renders the date so cross-day rows are obvious instead of
        # looking like time running backwards.
        assert report_cli._fmt_ts("2026-01-01T08:17:35Z") == "2026-01-01 08:17:35"

    def test_commit_writes_sha_and_subject(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        report_cli._report_commit(_parse(
            "report", "commit", "--issue", "321", "--phase", "implement",
            "--sha", "abc1234", "--subject", "feat: x"
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert events[0]["sha"] == "abc1234"
        assert events[0]["subject"] == "feat: x"
        assert events[0].get("end_ts") is None

    def test_note_writes_text(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        report_cli._report_note(_parse(
            "report", "note", "--issue", "321", "--phase", "design",
            "--text", "the analyst returned a clean design"
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        assert events[0]["notes"] == "the analyst returned a clean design"

    def test_run_start_inherited_by_later_calls(self, tmp_path: Path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        report_cli._report_run_start(_parse(
            "report", "run-start", "do-issue-solo", "--issue", "321"
        ))
        report_cli._report_commit(_parse(
            "report", "commit", "--issue", "321", "--phase", "implement",
            "--sha", "deadbeef", "--subject", "feat: y"
        ))
        events = report_cli.load_timeline(report_cli.timeline_path(321, repo_root=tmp_path))
        commit_row = next(e for e in events if e["action"] == "commit")
        assert commit_row["maverick_skill"] == "do-issue-solo"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def _pass_path_events() -> list[dict[str, Any]]:
    """A minimal but representative PASS-path timeline."""
    e = []
    e.append(_full_event(
        action="run-start", start_ts="2026-05-19T10:00:00Z",
        phase="claimed", maverick_skill="do-issue-solo",
    ))
    e.append(_full_event(
        action="agent-dispatch", phase="design",
        start_ts="2026-05-19T10:01:00Z",
        end_ts="2026-05-19T10:04:00Z",
        maverick_agent="agent-issue-analyst",
        outcome="success",
    ))
    e.append(_full_event(
        action="phase-boundary", phase="design",
        start_ts="2026-05-19T10:05:00Z",
    ))
    e.append(_full_event(
        action="phase-boundary", phase="branch",
        start_ts="2026-05-19T10:06:00Z",
    ))
    e.append(_full_event(
        action="commit", phase="implement",
        start_ts="2026-05-19T10:10:00Z",
        sha="abc1234567", subject="feat: a thing",
    ))
    e.append(_full_event(
        action="phase-boundary", phase="implement",
        start_ts="2026-05-19T10:12:00Z",
    ))
    e.append(_full_event(
        action="agent-dispatch", phase="docs",
        start_ts="2026-05-19T10:13:00Z",
        end_ts="2026-05-19T10:14:30Z",
        maverick_agent="agent-tech-docs-writer",
        dispatched_skill="do-docs",
        outcome="success",
    ))
    e.append(_full_event(
        action="commit", phase="docs",
        start_ts="2026-05-19T10:14:45Z",
        sha="def4567890", subject="docs: that thing",
    ))
    e.append(_full_event(
        action="phase-boundary", phase="docs",
        start_ts="2026-05-19T10:15:00Z",
    ))
    e.append(_full_event(
        action="skill-dispatch", phase="security",
        start_ts="2026-05-19T10:15:30Z",
        end_ts="2026-05-19T10:16:00Z",
        dispatched_skill="do-cybersecurity-review",
        outcome="success",
    ))
    e.append(_full_event(
        action="phase-boundary", phase="security",
        start_ts="2026-05-19T10:16:30Z",
    ))
    e.append(_full_event(
        action="phase-boundary", phase="complete",
        start_ts="2026-05-19T10:20:00Z",
    ))
    e.append(_full_event(
        action="note", phase="implement",
        start_ts="2026-05-19T10:19:00Z",
        notes="pushed in one shot after vitest green",
    ))
    return e


class TestRender:
    def test_empty_events_returns_stub(self):
        md = report_cli.render(issue=42, events=[])
        assert "Maverick workflow report" in md
        assert "No timeline events" in md

    def test_pass_path_renders_metadata_and_outcome(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        assert "# Maverick workflow report" in md
        assert "- Issue: #321" in md
        assert "- Skill: do-issue-solo" in md
        assert "- Outcome: PASS" in md
        assert "- Maverick: 3.3.2-dev" in md

    def test_total_time_emits_seconds(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        # 10:00:00 to last phase-boundary at 10:20:00 = 1200s
        assert "## Total Time" in md
        assert "seconds: 1200" in md

    def test_phase_rows_carry_all_columns(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        # Header includes the four-way identity split + timing
        assert (
            "| Phase | LLM | Maverick Root Skill | Maverick Sub Agent | "
            "Maverick Skill | Start | End | Duration | Maverick Action |"
        ) in md
        # Phase 6 row carries the docs agent in Sub Agent, the inner
        # skill in Maverick Skill, claude-code as LLM, do-issue-solo as
        # the Root Skill.
        docs_rows = [ln for ln in md.splitlines() if "| Phase 6 |" in ln]
        agent_row = next(r for r in docs_rows if "agent-dispatch" in r)
        assert "agent-tech-docs-writer" in agent_row
        assert "do-docs" in agent_row
        assert "claude-code" in agent_row
        assert "do-issue-solo" in agent_row

    def test_phase_boundary_row_only_when_no_dispatch(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        lines = md.splitlines()
        # Phase 5 in this fixture has no dispatches (only commits) — it
        # gets a phase-boundary row plus commit rows.
        impl_rows = [ln for ln in lines if "| Phase 5 |" in ln]
        assert any("phase-boundary — execute tasks" in r for r in impl_rows)
        # Phase 6 has an agent-dispatch — no separate phase-boundary row.
        docs_rows = [ln for ln in lines if "| Phase 6 |" in ln]
        assert not any("phase-boundary" in r for r in docs_rows)

    def test_commit_rows_render_under_their_phase(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        lines = md.splitlines()
        # Phase 5's commit shows the sha + subject in the Action column,
        # with `—` placeholders in Start/Duration (commit is atomic).
        impl_rows = [ln for ln in lines if "| Phase 5 |" in ln]
        commit_rows = [r for r in impl_rows if "commit abc1234" in r]
        assert commit_rows, f"no commit row found in: {impl_rows}"
        assert "feat: a thing" in commit_rows[0]

    def test_docs_commit_lands_under_docs_phase(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        lines = md.splitlines()
        docs_rows = [ln for ln in lines if "| Phase 6 |" in ln]
        assert any("commit def4567" in r and "docs: that thing" in r for r in docs_rows)

    def test_notes_render_in_analysis_section_with_split_phase_label(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        assert "## Analysis" in md
        # Notes section labels each note with `Phase N — <descriptor>`
        # (the combined label), reconstructed from the split dicts.
        assert "- Phase 5 — execute tasks: pushed in one shot after vitest green" in md

    def test_durations_in_seconds(self):
        """Phase rows show whole-second durations, no `1m 30s` form."""
        md = report_cli.render(issue=321, events=_pass_path_events())
        # The design row's agent-dispatch was 3 minutes = 180 seconds.
        # Phase column is just "Phase 1-2" (descriptor moved to Action).
        design_lines = [
            ln for ln in md.splitlines()
            if "| Phase 1-2 |" in ln and "agent-dispatch" in ln
        ]
        assert design_lines
        # Duration column carries the integer 180
        assert " 180 |" in design_lines[0]
        # Descriptor sits in the Action column
        assert "agent-dispatch — understand + design" in design_lines[0]

    def test_eject_path_renders_fail(self):
        events = _pass_path_events()
        # Swap the trailing complete phase for ejected
        events = [e for e in events if e["phase"] != "complete"]
        events.append(_full_event(
            action="phase-boundary", phase="ejected",
            start_ts="2026-05-19T10:21:00Z",
        ))
        md = report_cli.render(issue=321, events=events)
        assert "- Outcome: FAIL-eject" in md

    def test_pipe_in_commit_subject_is_escaped(self):
        events = _pass_path_events()
        for e in events:
            if e.get("action") == "commit" and e.get("phase") == "implement":
                e["subject"] = "feat: a|b helper"
        md = report_cli.render(issue=321, events=events)
        assert "a\\|b" in md


# ---------------------------------------------------------------------------
# verify command
# ---------------------------------------------------------------------------


class TestVerify:
    def test_clean_timeline_returns_zero(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        path = report_cli.timeline_path(321, repo_root=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_full_event()) + "\n")
        rc = report_cli._report_verify(argparse.Namespace(issue=321))
        assert rc == 0
        assert "ok" in capsys.readouterr().out

    def test_schema_violations_return_nonzero_and_print_location(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        path = report_cli.timeline_path(321, repo_root=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([
            json.dumps(_full_event()),
            json.dumps(_full_event(phase="nonsense")),
            "{not json",
        ]))
        rc = report_cli._report_verify(argparse.Namespace(issue=321))
        assert rc == 1
        out = capsys.readouterr().out
        assert "schema violation" in out
        assert "malformed JSON" in out

    def test_dangling_pending_intervals_surfaced(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        path = report_cli.timeline_path(321, repo_root=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_full_event()) + "\n")
        pending = report_cli.pending_path(321, repo_root=tmp_path)
        report_cli._write_pending(pending, {
            "agent-dispatch:agent-x": {"start_ts": "2026-05-19T10:00:00Z"},
        })
        report_cli._report_verify(argparse.Namespace(issue=321))
        out = capsys.readouterr().out
        assert "dangling" in out
        assert "agent-dispatch:agent-x" in out

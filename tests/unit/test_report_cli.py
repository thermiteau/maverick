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

    def test_phase_rows_carry_action_and_agent_columns(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        assert "| Maverick Action | Maverick Agent |" in md
        # The docs phase has an agent-dispatch row carrying the agent name
        docs_rows = [ln for ln in md.splitlines() if "Phase 6 — documentation review" in ln]
        assert any("agent-dispatch" in r and "agent-tech-docs-writer" in r for r in docs_rows)

    def test_one_row_per_action_within_a_phase(self):
        """Phase 6 has BOTH a docs agent-dispatch and (in this fixture) no skill-dispatch.
        The implement phase has commit sub-rows but no action row of its own
        (no agent or skill ran inside it).
        """
        md = report_cli.render(issue=321, events=_pass_path_events())
        lines = md.splitlines()
        impl_rows = [ln for ln in lines if "Phase 5 — execute tasks" in ln]
        # No agent ran in implement, so the phase row is a phase-boundary
        assert any("phase-boundary" in r for r in impl_rows)

    def test_commit_subrows_render_under_their_phase(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        lines = md.splitlines()
        impl_idx = next(i for i, ln in enumerate(lines) if "Phase 5 — execute tasks" in ln)
        # The implement commit sub-row appears soon after the phase row
        window = "\n".join(lines[impl_idx:impl_idx + 4])
        assert "↳ commit" in window
        assert "abc1234" in window
        assert "feat: a thing" in window

    def test_docs_commit_lands_under_docs_phase(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        lines = md.splitlines()
        docs_idx = next(i for i, ln in enumerate(lines) if "Phase 6 — documentation review" in ln)
        next_phase_idx = next(
            i for i, ln in enumerate(lines[docs_idx + 1:], start=docs_idx + 1)
            if "Phase 7" in ln
        )
        window = "\n".join(lines[docs_idx:next_phase_idx])
        assert "def4567" in window
        assert "docs: that thing" in window

    def test_notes_render_in_analysis_section(self):
        md = report_cli.render(issue=321, events=_pass_path_events())
        assert "## Analysis" in md
        assert "pushed in one shot" in md

    def test_durations_in_seconds(self):
        """Phase rows show whole-second durations, no `1m 30s` form."""
        md = report_cli.render(issue=321, events=_pass_path_events())
        # The design row's agent-dispatch was 3 minutes = 180 seconds
        design_lines = [
            ln for ln in md.splitlines()
            if "Phase 1-2 — understand + design" in ln and "agent-dispatch" in ln
        ]
        assert design_lines
        # Last column is duration in seconds — should be the number 180
        assert " 180 |" in design_lines[0]

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

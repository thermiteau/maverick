"""Unit tests for the `maverick report` CLI surface (#83)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from maverick import report_cli


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    report_cli.build_subparsers(sub)
    return parser.parse_args(list(argv))


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


class TestArgparseWiring:
    def test_log_subcommand_parses(self):
        args = _parse(
            "report", "log", "subagent-start",
            "--issue", "123", "--name", "agent-issue-analyst",
        )
        assert args._handler is report_cli._report_log
        assert args.issue == 123
        assert args.event_type == "subagent-start"
        assert args.name == "agent-issue-analyst"

    def test_generate_subcommand_parses(self):
        args = _parse(
            "report", "generate", "owner/repo", "42",
            "--branch", "feat/42-foo",
        )
        assert args._handler is report_cli._report_generate
        assert args.repo == "owner/repo"
        assert args.issue == 42
        assert args.branch == "feat/42-foo"

    def test_path_subcommand_parses(self):
        args = _parse("report", "path", "42")
        assert args._handler is report_cli._report_path
        assert args.issue == 42


# ---------------------------------------------------------------------------
# append_event
# ---------------------------------------------------------------------------


class TestAppendEvent:
    def test_round_trip_writes_jsonl(self, tmp_path: Path):
        ok = report_cli.append_event(
            42,
            {"type": "phase-checkpoint", "phase": "design"},
            repo_root=tmp_path,
        )
        assert ok is True
        path = report_cli.timeline_path(42, repo_root=tmp_path)
        assert path.exists()
        line = path.read_text().strip()
        record = json.loads(line)
        assert record["type"] == "phase-checkpoint"
        assert record["phase"] == "design"
        assert record["issue"] == 42
        assert record["ts"].endswith("Z")

    def test_creates_parent_directories(self, tmp_path: Path):
        report_cli.append_event(
            7,
            {"type": "subagent-start", "name": "agent-x"},
            repo_root=tmp_path,
        )
        path = report_cli.timeline_path(7, repo_root=tmp_path)
        assert path.parent.exists()

    def test_appends_not_overwrites(self, tmp_path: Path):
        for phase in ("claimed", "design", "tasks"):
            report_cli.append_event(
                1,
                {"type": "phase-checkpoint", "phase": phase, "ts": f"2026-01-01T00:00:0{['claimed','design','tasks'].index(phase)}Z"},
                repo_root=tmp_path,
            )
        path = report_cli.timeline_path(1, repo_root=tmp_path)
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 3

    def test_failure_returns_false_does_not_raise(self, tmp_path: Path, monkeypatch):
        # Force mkdir to raise — append_event must swallow the error.
        from pathlib import Path as P

        def boom(self, *a, **kw):
            raise PermissionError("nope")

        monkeypatch.setattr(P, "mkdir", boom)
        ok = report_cli.append_event(
            1, {"type": "phase-checkpoint", "phase": "design"}, repo_root=tmp_path
        )
        assert ok is False


# ---------------------------------------------------------------------------
# Validation + loading
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        "evt",
        [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "design"},
            {"ts": "2026-01-01T00:00:00Z", "type": "subagent-start", "name": "x"},
        ],
    )
    def test_valid(self, evt):
        assert report_cli._validate_event(evt)

    @pytest.mark.parametrize(
        "evt",
        [
            None,
            "not a dict",
            {"type": "phase-checkpoint"},  # missing ts
            {"ts": "not-iso", "type": "phase-checkpoint"},  # ts not Z-suffixed
            {"ts": "2026-01-01T00:00:00Z"},  # missing type
            {"ts": "2026-01-01T00:00:00Z", "type": 42},  # type not str
        ],
    )
    def test_invalid(self, evt):
        assert not report_cli._validate_event(evt)

    def test_load_skips_malformed_lines(self, tmp_path: Path, capsys):
        path = tmp_path / "t.jsonl"
        path.write_text(
            "\n".join(
                [
                    json.dumps({"ts": "2026-01-01T00:00:01Z", "type": "phase-checkpoint", "phase": "design"}),
                    "{not json",
                    json.dumps({"type": "phase-checkpoint"}),  # invalid
                    json.dumps({"ts": "2026-01-01T00:00:02Z", "type": "phase-checkpoint", "phase": "tasks"}),
                    "",
                ]
            )
        )
        events = report_cli.load_timeline(path)
        assert len(events) == 2
        assert [e["phase"] for e in events] == ["design", "tasks"]
        captured = capsys.readouterr()
        assert "warning" in captured.err

    def test_load_sorts_by_ts(self, tmp_path: Path):
        path = tmp_path / "t.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(e)
                for e in [
                    {"ts": "2026-01-01T00:00:02Z", "type": "phase-checkpoint", "phase": "tasks"},
                    {"ts": "2026-01-01T00:00:01Z", "type": "phase-checkpoint", "phase": "design"},
                ]
            )
        )
        events = report_cli.load_timeline(path)
        assert [e["phase"] for e in events] == ["design", "tasks"]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestPairIntervals:
    def test_pairs_subagents_with_phase_attribution(self):
        events = [
            {"ts": "2026-01-01T00:00:01Z", "type": "phase-checkpoint", "phase": "claimed"},
            {"ts": "2026-01-01T00:00:02Z", "type": "subagent-start", "name": "agent-x"},
            {"ts": "2026-01-01T00:00:05Z", "type": "subagent-end", "name": "agent-x"},
            {"ts": "2026-01-01T00:00:06Z", "type": "phase-checkpoint", "phase": "design"},
        ]
        pairs = report_cli._pair_intervals(events, "subagent-start", "subagent-end", "name")
        assert pairs == [
            ("agent-x", "2026-01-01T00:00:02Z", "2026-01-01T00:00:05Z", "claimed"),
        ]

    def test_unmatched_start_gets_zero_duration(self):
        events = [
            {"ts": "2026-01-01T00:00:01Z", "type": "phase-checkpoint", "phase": "design"},
            {"ts": "2026-01-01T00:00:02Z", "type": "subagent-start", "name": "agent-x"},
        ]
        pairs = report_cli._pair_intervals(events, "subagent-start", "subagent-end", "name")
        assert len(pairs) == 1
        assert pairs[0][1] == pairs[0][2]


class TestPhaseIntervals:
    def test_anchors_first_phase_to_claim_time(self):
        events = [
            {"ts": "2026-01-01T00:01:00Z", "type": "phase-checkpoint", "phase": "claimed"},
            {"ts": "2026-01-01T00:05:00Z", "type": "phase-checkpoint", "phase": "design"},
        ]
        intervals = report_cli._phase_intervals(events, "2026-01-01T00:00:00Z")
        assert intervals == [
            ("claimed", "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"),
            ("design", "2026-01-01T00:01:00Z", "2026-01-01T00:05:00Z"),
        ]

    def test_no_claim_falls_back_to_first_event(self):
        events = [
            {"ts": "2026-01-01T00:01:00Z", "type": "phase-checkpoint", "phase": "claimed"},
        ]
        intervals = report_cli._phase_intervals(events, None)
        assert intervals[0][1] == "2026-01-01T00:01:00Z"

    def test_empty_returns_empty(self):
        assert report_cli._phase_intervals([], None) == []


class TestFormatters:
    @pytest.mark.parametrize(
        "secs,expected",
        [
            (0, "<1s"),
            (1, "1s"),
            (59, "59s"),
            (60, "1m"),
            (90, "1m 30s"),
            (3600, "1h 0m"),
            (3700, "1h 1m"),
        ],
    )
    def test_fmt_duration(self, secs, expected):
        assert report_cli._fmt_duration(secs) == expected

    def test_fmt_time(self):
        # #91: include the date so cross-day rows are obvious instead of
        # looking like time running backwards.
        assert report_cli._fmt_time("2026-01-01T08:17:35Z") == "2026-01-01 08:17:35"

    def test_fmt_time_invalid_passes_through(self):
        assert report_cli._fmt_time("garbage") == "garbage"


class TestRender:
    def test_empty_events_returns_stub(self):
        md = report_cli.render(issue=42, events=[])
        assert "Issue #42" in md
        assert "No timeline events" in md

    def test_minimal_run_renders_table_and_summary(self):
        events = [
            {"ts": "2026-01-01T00:00:30Z", "type": "phase-checkpoint", "phase": "claimed"},
            {"ts": "2026-01-01T00:00:31Z", "type": "subagent-start", "name": "agent-issue-analyst"},
            {"ts": "2026-01-01T00:04:04Z", "type": "subagent-end", "name": "agent-issue-analyst"},
            {"ts": "2026-01-01T00:05:00Z", "type": "phase-checkpoint", "phase": "design"},
            {"ts": "2026-01-01T00:06:00Z", "type": "phase-checkpoint", "phase": "complete"},
        ]
        md = report_cli.render(
            issue=42,
            events=events,
            claim_created_at="2026-01-01T00:00:00Z",
        )
        # Header
        assert "# Issue #42 — time breakdown" in md
        assert "Wall-clock:" in md
        # Phase rows
        assert "Phase 0 — coordination" in md
        assert "Phase 1-2 — understand + design" in md
        assert "Phase 10 — complete" in md
        # PLACEHOLDER prefix
        assert "PLACEHOLDER" in md
        # Subagent fact rendered into the design row
        assert "agent-issue-analyst" in md
        # Summary table
        assert "Subagent compute" in md
        assert "Coordination" in md

    def test_implement_phase_renders_commit_subrows(self):
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:10:00Z", "type": "phase-checkpoint", "phase": "implement"},
        ]
        commits = [
            {"sha": "abc1234567", "committed_at": "2026-01-01T00:03:00Z", "subject": "feat: add helper"},
            {"sha": "def4567890", "committed_at": "2026-01-01T00:07:00Z", "subject": "test: cover helper"},
        ]
        md = report_cli.render(
            issue=99,
            events=events,
            commits=commits,
            claim_created_at="2026-01-01T00:00:00Z",
        )
        assert "↳ commit" in md
        assert "abc1234" in md
        assert "feat: add helper" in md
        assert "def4567" in md

    def test_pipe_in_commit_subject_is_escaped(self):
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:10:00Z", "type": "phase-checkpoint", "phase": "implement"},
        ]
        commits = [
            {"sha": "abc1234", "committed_at": "2026-01-01T00:01:00Z", "subject": "feat: a|b helper"},
        ]
        md = report_cli.render(issue=1, events=events, commits=commits)
        assert "a\\|b" in md


class TestCommitEvents:
    """Event-sourced commit rows replace `git log <base>..<branch>` (#91).

    `_fetch_commits` had a hardcoded `origin/main` base that over-counted
    on Gitflow-style repos. Reading commits from the JSONL timeline gives
    us deterministic, in-issue-scoped rows that travel with the timeline.
    """

    def test_commit_events_render_under_implement_phase(self):
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:03:00Z", "type": "commit", "sha": "abc1234567",
             "subject": "feat: add helper"},
            {"ts": "2026-01-01T00:07:00Z", "type": "commit", "sha": "def4567890",
             "subject": "test: cover helper"},
            {"ts": "2026-01-01T00:10:00Z", "type": "phase-checkpoint", "phase": "implement"},
        ]
        md = report_cli.render(
            issue=99,
            events=events,
            claim_created_at="2026-01-01T00:00:00Z",
        )
        assert "↳ commit" in md
        assert "abc1234" in md
        assert "feat: add helper" in md
        assert "def4567" in md
        # Preamble reflects the event-driven source.
        assert "commit events in the timeline JSONL" in md

    def test_event_commits_route_to_their_owning_phase(self):
        """A Phase 6 `docs:` commit should land under the docs row, not implement."""
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:05:00Z", "type": "commit", "sha": "aaa1111",
             "subject": "feat: thing"},
            {"ts": "2026-01-01T00:10:00Z", "type": "phase-checkpoint", "phase": "implement"},
            {"ts": "2026-01-01T00:12:00Z", "type": "commit", "sha": "bbb2222",
             "subject": "docs: explain the thing"},
            {"ts": "2026-01-01T00:15:00Z", "type": "phase-checkpoint", "phase": "docs"},
        ]
        md = report_cli.render(
            issue=42,
            events=events,
            claim_created_at="2026-01-01T00:00:00Z",
        )
        lines = md.splitlines()
        impl_idx = next(i for i, ln in enumerate(lines) if "Phase 5 — execute tasks" in ln)
        docs_idx = next(i for i, ln in enumerate(lines) if "Phase 6 — documentation review" in ln)
        # The implement-phase commit appears between its phase row and the next phase row.
        impl_window = "\n".join(lines[impl_idx:docs_idx])
        docs_window = "\n".join(lines[docs_idx:])
        assert "aaa1111" in impl_window
        assert "aaa1111" not in docs_window
        assert "bbb2222" in docs_window
        assert "bbb2222" not in impl_window

    def test_empty_commit_events_falls_back_to_git_log_commits(self):
        """Legacy timelines with no commit events still render via the `commits` arg."""
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:10:00Z", "type": "phase-checkpoint", "phase": "implement"},
        ]
        commits = [
            {"sha": "legacy01", "committed_at": "2026-01-01T00:03:00Z",
             "subject": "feat: legacy"},
        ]
        md = report_cli.render(
            issue=7,
            events=events,
            commits=commits,
            claim_created_at="2026-01-01T00:00:00Z",
        )
        assert "legacy0" in md
        assert "feat: legacy" in md
        assert "git-log fallback (legacy timeline)" in md

    def test_commit_events_take_priority_over_legacy_commits_arg(self):
        """When both are present, event-sourced commits win."""
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:03:00Z", "type": "commit", "sha": "newev01",
             "subject": "feat: new path"},
            {"ts": "2026-01-01T00:10:00Z", "type": "phase-checkpoint", "phase": "implement"},
        ]
        commits = [
            {"sha": "legacy01", "committed_at": "2026-01-01T00:03:00Z",
             "subject": "feat: legacy"},
        ]
        md = report_cli.render(
            issue=7,
            events=events,
            commits=commits,
            claim_created_at="2026-01-01T00:00:00Z",
        )
        assert "newev01" in md
        assert "legacy01" not in md

    def test_log_commit_subcommand_writes_event(self, tmp_path: Path, monkeypatch):
        """The `report log commit --sha --subject` form round-trips through the JSONL."""
        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        report_cli.build_subparsers(sub)
        args = parser.parse_args([
            "report", "log", "commit",
            "--issue", "55",
            "--sha", "abc1234",
            "--subject", "feat: log the commit",
        ])
        rc = args._handler(args)
        assert rc == 0
        events = report_cli.load_timeline(report_cli.timeline_path(55, repo_root=tmp_path))
        commit_events = [e for e in events if e["type"] == "commit"]
        assert len(commit_events) == 1
        assert commit_events[0]["sha"] == "abc1234"
        assert commit_events[0]["subject"] == "feat: log the commit"


class TestCommitRowsHelper:
    def test_extracts_commit_events_in_order(self):
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:01:00Z", "type": "commit", "sha": "111",
             "subject": "feat: a"},
            {"ts": "2026-01-01T00:02:00Z", "type": "phase-checkpoint", "phase": "implement"},
            {"ts": "2026-01-01T00:03:00Z", "type": "commit", "sha": "222",
             "subject": "feat: b"},
        ]
        rows = report_cli._commit_rows(events)
        assert rows == [
            ("111", "2026-01-01T00:01:00Z", "feat: a"),
            ("222", "2026-01-01T00:03:00Z", "feat: b"),
        ]

    def test_ignores_non_commit_events(self):
        events = [
            {"ts": "2026-01-01T00:00:00Z", "type": "phase-checkpoint", "phase": "branch"},
            {"ts": "2026-01-01T00:01:00Z", "type": "subagent-start", "name": "x"},
        ]
        assert report_cli._commit_rows(events) == []

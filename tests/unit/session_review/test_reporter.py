"""Tests for maverick.session_review.reporter — report generation."""

from __future__ import annotations

from pathlib import Path

from maverick.session_review.analyzers import MAVERICK_GAP, USER_BEHAVIOR, Finding
from maverick.session_review.parser import SessionData
from maverick.session_review.reporter import (
    _duration,
    _format_session_ids,
    _project_slug,
    _severity_badge,
    _tool_counts,
    generate_batch_summary,
    generate_report,
    write_report,
)


class TestDuration:
    def test_less_than_minute(self):
        assert _duration("2026-01-15T10:00:00Z", "2026-01-15T10:00:30Z") == "<1 minute"

    def test_minutes(self):
        assert _duration("2026-01-15T10:00:00Z", "2026-01-15T10:25:00Z") == "25 minutes"

    def test_hours(self):
        assert _duration("2026-01-15T10:00:00Z", "2026-01-15T12:30:00Z") == "2h 30m"

    def test_invalid_timestamps(self):
        assert _duration("bad", "data") == "unknown"

    def test_empty_strings(self):
        assert _duration("", "") == "unknown"


class TestToolCounts:
    def test_counts(self, empty_session: SessionData):
        from maverick.session_review.parser import ToolCall

        empty_session.tool_calls = [
            ToolCall(timestamp="t", tool_name="Read", input_data={}),
            ToolCall(timestamp="t", tool_name="Read", input_data={}),
            ToolCall(timestamp="t", tool_name="Bash", input_data={}),
        ]
        counts = _tool_counts(empty_session)
        assert counts["Read"] == 2
        assert counts["Bash"] == 1

    def test_sorted_by_count_desc(self, empty_session: SessionData):
        from maverick.session_review.parser import ToolCall

        empty_session.tool_calls = [
            ToolCall(timestamp="t", tool_name="Bash", input_data={}),
            ToolCall(timestamp="t", tool_name="Read", input_data={}),
            ToolCall(timestamp="t", tool_name="Read", input_data={}),
            ToolCall(timestamp="t", tool_name="Read", input_data={}),
        ]
        counts = _tool_counts(empty_session)
        keys = list(counts.keys())
        assert keys[0] == "Read"  # 3 > 1


class TestSeverityBadge:
    def test_critical(self):
        assert _severity_badge("critical") == "[CRITICAL]"

    def test_warning(self):
        assert _severity_badge("warning") == "[WARNING]"


class TestProjectSlug:
    def test_basic(self):
        assert _project_slug("/home/user/myproject") == "myproject"

    def test_empty(self):
        assert _project_slug("") == "unknown"


class TestFormatSessionIds:
    def test_few_ids(self):
        result = _format_session_ids({"abc", "def"})
        assert "abc" in result
        assert "def" in result

    def test_many_ids(self):
        ids = {f"id{i:02d}" for i in range(10)}
        result = _format_session_ids(ids, limit=3)
        assert "+7 more" in result


class TestGenerateReport:
    def test_report_with_no_findings(self, empty_session: SessionData):
        report = generate_report(empty_session, [])
        assert "# Session Review:" in report
        assert "No issues found." in report

    def test_report_with_findings(self, empty_session: SessionData):
        findings = [
            Finding(
                analyzer="TestAnalyzer",
                severity="critical",
                category=MAVERICK_GAP,
                title="Something bad",
                detail="Details here",
                recommendation="Fix it",
                maverick_component="some-skill",
            ),
        ]
        report = generate_report(empty_session, findings)
        assert "## Maverick Plugin Gaps" in report
        assert "Something bad" in report
        assert "Fix it" in report
        assert "`some-skill`" in report

    def test_report_with_user_behavior_findings(self, empty_session: SessionData):
        findings = [
            Finding(
                analyzer="UserStuff",
                severity="warning",
                category=USER_BEHAVIOR,
                title="User did something",
                detail="Details",
            ),
        ]
        report = generate_report(empty_session, findings)
        assert "## User Behavior" in report

    def test_report_includes_statistics(self, empty_session: SessionData):
        report = generate_report(empty_session, [])
        assert "## Session Statistics" in report
        assert "Tool calls:" in report
        assert "Commits:" in report

    def test_report_with_skill_snapshot(self, empty_session: SessionData):
        meta = [{"topic": "logging", "origin": "upskill-generated"}]
        report = generate_report(empty_session, [], skill_snapshot_meta=meta)
        assert "logging" in report
        assert "upskill-generated" in report

    def test_report_shows_maverick_version(self, empty_session: SessionData):
        empty_session.skills_available = ["maverick:do-issue-solo"]
        empty_session.maverick_version = "0.5.0"
        report = generate_report(empty_session, [])
        assert "**Plugin version:** 0.5.0" in report

    def test_report_shows_unknown_version(self, empty_session: SessionData):
        empty_session.skills_available = ["maverick:do-issue-solo"]
        # No maverick_version set
        report = generate_report(empty_session, [])
        assert "unknown (pre-version plugin)" in report

    def test_report_no_version_without_plugin(self, empty_session: SessionData):
        report = generate_report(empty_session, [])
        assert "Plugin version:" not in report


class TestWriteReport:
    def test_writes_to_disk(self, tmp_path: Path):
        path = write_report("# Report", "myproject", "abc12345xyz", output_dir=tmp_path)
        assert path.exists()
        assert path.read_text() == "# Report"
        assert "myproject" in str(path)
        assert "abc12345" in str(path)

    def test_short_session_id(self, tmp_path: Path):
        path = write_report("# R", "proj", "ab", output_dir=tmp_path)
        assert path.exists()
        assert "ab" in str(path)


class TestGenerateBatchSummary:
    def test_empty_reports(self):
        summary = generate_batch_summary([])
        assert "**Sessions reviewed:** 0" in summary

    def test_no_findings(self, empty_session: SessionData):
        summary = generate_batch_summary([(empty_session, [])])
        assert "No issues found" in summary

    def test_with_findings(self, empty_session: SessionData):
        findings = [
            Finding(
                analyzer="A",
                severity="critical",
                category=MAVERICK_GAP,
                title="Gap",
                detail="D",
                recommendation="R",
                maverick_component="comp",
            ),
            Finding(
                analyzer="B",
                severity="warning",
                category=USER_BEHAVIOR,
                title="Behavior",
                detail="D",
                recommendation="R2",
            ),
        ]
        summary = generate_batch_summary([(empty_session, findings)])
        assert "Maverick Plugin Gaps" in summary
        assert "User Behavior" in summary
        assert "Per-Session Summary" in summary

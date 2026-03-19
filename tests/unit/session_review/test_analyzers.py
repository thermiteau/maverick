"""Tests for maverick.session_review.analyzers — anti-pattern detection."""

from __future__ import annotations

import pytest

from maverick.session_review.analyzers import (
    MAVERICK_GAP,
    USER_BEHAVIOR,
    Finding,
    _bash_commands,
    _maverick_loaded,
    _short_path,
    _versions_compatible,
    _workflow_invoked,
    analyze_commit_without_verification,
    analyze_error_loops,
    analyze_file_churn,
    analyze_maverick_not_used,
    analyze_maverick_partial_use,
    analyze_project_skills_ignored,
    analyze_user_corrections,
    get_current_version,
    run_mechanical_analyzers,
)
from maverick.session_review.parser import SessionData, ToolCall


def make_bash_tool_call(command: str, timestamp: str = "2026-01-15T10:30:00Z") -> ToolCall:
    return ToolCall(timestamp=timestamp, tool_name="Bash", input_data={"command": command})


def make_edit_tool_call(file_path: str, timestamp: str = "2026-01-15T10:30:00Z") -> ToolCall:
    return ToolCall(
        timestamp=timestamp,
        tool_name="Edit",
        input_data={"file_path": file_path, "old_string": "x", "new_string": "y"},
        file_path=file_path,
    )


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_bash_commands_filters(self, empty_session: SessionData):
        empty_session.tool_calls = [
            make_bash_tool_call("ls"),
            ToolCall(timestamp="t", tool_name="Read", input_data={}),
            make_bash_tool_call("pwd"),
        ]
        result = _bash_commands(empty_session)
        assert len(result) == 2
        assert all(tc.tool_name == "Bash" for tc in result)

    def test_maverick_loaded_true(self, session_with_maverick: SessionData):
        assert _maverick_loaded(session_with_maverick) is True

    def test_maverick_loaded_false(self, empty_session: SessionData):
        assert _maverick_loaded(empty_session) is False

    def test_maverick_loaded_with_do_prefix(self, empty_session: SessionData):
        empty_session.skills_available = ["do-task-solo"]
        assert _maverick_loaded(empty_session) is True

    def test_maverick_loaded_with_mav_prefix(self, empty_session: SessionData):
        empty_session.skills_available = ["mav-bp-logging"]
        assert _maverick_loaded(empty_session) is True

    def test_workflow_invoked_returns_matching(self, empty_session: SessionData):
        empty_session.skills_invoked = ["do-task-solo", "other-skill"]
        result = _workflow_invoked(empty_session)
        assert result == {"do-task-solo"}

    def test_workflow_invoked_empty(self, empty_session: SessionData):
        assert _workflow_invoked(empty_session) == set()

    def test_short_path_long(self):
        assert _short_path("/home/user/project/src/main.py") == "project/src/main.py"

    def test_short_path_short(self):
        assert _short_path("src/main.py") == "src/main.py"


# ---------------------------------------------------------------------------
# Analyzer: CommitWithoutVerification
# ---------------------------------------------------------------------------


class TestAnalyzeCommitWithoutVerification:
    def test_no_commits_no_findings(self, empty_session: SessionData):
        assert analyze_commit_without_verification(empty_session) == []

    def test_verified_commit_no_findings(self, empty_session: SessionData):
        empty_session.tool_calls = [
            make_bash_tool_call("uv run pytest"),
            make_bash_tool_call("ruff check ."),
            make_bash_tool_call("git commit -m 'fix'"),
        ]
        assert analyze_commit_without_verification(empty_session) == []

    def test_unverified_commit_no_maverick(self, empty_session: SessionData):
        empty_session.tool_calls = [
            make_bash_tool_call("git commit -m 'yolo'"),
        ]
        findings = analyze_commit_without_verification(empty_session)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].category == USER_BEHAVIOR

    def test_unverified_commit_with_maverick(self, session_with_maverick: SessionData):
        session_with_maverick.tool_calls = [
            make_bash_tool_call("git commit -m 'yolo'"),
        ]
        findings = analyze_commit_without_verification(session_with_maverick)
        assert len(findings) == 1
        assert findings[0].category == MAVERICK_GAP

    def test_unverified_commit_with_workflow(self, session_with_workflow: SessionData):
        session_with_workflow.tool_calls = [
            make_bash_tool_call("git commit -m 'yolo'"),
        ]
        findings = analyze_commit_without_verification(session_with_workflow)
        assert len(findings) == 1
        assert findings[0].category == MAVERICK_GAP
        assert "Workflow" in findings[0].title

    def test_partial_verification_only_test(self, empty_session: SessionData):
        empty_session.tool_calls = [
            make_bash_tool_call("npm test"),
            make_bash_tool_call("git commit -m 'tested'"),
        ]
        findings = analyze_commit_without_verification(empty_session)
        # Missing lint → still flagged
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# Analyzer: FileChurn
# ---------------------------------------------------------------------------


class TestAnalyzeFileChurn:
    def test_no_churn(self, empty_session: SessionData):
        empty_session.tool_calls = [make_edit_tool_call("/src/a.py")]
        assert analyze_file_churn(empty_session) == []

    def test_high_churn_detected(self, empty_session: SessionData):
        empty_session.tool_calls = [make_edit_tool_call("/src/a.py")] * 6
        findings = analyze_file_churn(empty_session)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert findings[0].category == USER_BEHAVIOR

    def test_churn_with_maverick(self, session_with_maverick: SessionData):
        session_with_maverick.tool_calls = [make_edit_tool_call("/src/a.py")] * 6
        findings = analyze_file_churn(session_with_maverick)
        assert len(findings) == 1
        assert findings[0].category == MAVERICK_GAP

    def test_churn_with_workflow(self, session_with_workflow: SessionData):
        session_with_workflow.tool_calls = [make_edit_tool_call("/src/a.py")] * 6
        findings = analyze_file_churn(session_with_workflow)
        assert findings[0].category == MAVERICK_GAP
        assert "workflow" in findings[0].title.lower()

    def test_threshold_is_5(self, empty_session: SessionData):
        empty_session.tool_calls = [make_edit_tool_call("/src/a.py")] * 5
        assert analyze_file_churn(empty_session) == []


# ---------------------------------------------------------------------------
# Analyzer: ErrorLoops
# ---------------------------------------------------------------------------


class TestAnalyzeErrorLoops:
    def test_no_errors(self, empty_session: SessionData):
        assert analyze_error_loops(empty_session) == []

    def test_few_errors_no_loop(self, empty_session: SessionData):
        empty_session.errors = [
            {"error": "something failed", "timestamp": "t1"},
            {"error": "something failed", "timestamp": "t2"},
        ]
        assert analyze_error_loops(empty_session) == []

    def test_error_loop_detected(self, empty_session: SessionData):
        empty_session.errors = [
            {"error": "ModuleNotFoundError: no module named 'foo'", "timestamp": f"t{i}"}
            for i in range(3)
        ]
        findings = analyze_error_loops(empty_session)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert findings[0].category == USER_BEHAVIOR

    def test_error_loop_with_maverick(self, session_with_maverick: SessionData):
        session_with_maverick.errors = [
            {"error": "SyntaxError: invalid syntax", "timestamp": f"t{i}"}
            for i in range(4)
        ]
        findings = analyze_error_loops(session_with_maverick)
        assert len(findings) == 1
        assert findings[0].category == MAVERICK_GAP
        assert "systematic-debugging" in findings[0].maverick_component


# ---------------------------------------------------------------------------
# Analyzer: UserCorrections
# ---------------------------------------------------------------------------


class TestAnalyzeUserCorrections:
    def test_no_corrections(self, empty_session: SessionData):
        empty_session.user_messages = [{"text": "Add a new feature"}]
        assert analyze_user_corrections(empty_session) == []

    def test_single_correction_not_flagged(self, empty_session: SessionData):
        empty_session.user_messages = [{"text": "No, that's wrong"}]
        assert analyze_user_corrections(empty_session) == []

    def test_multiple_corrections_flagged(self, empty_session: SessionData):
        empty_session.user_messages = [
            {"text": "No, that's not what I meant"},
            {"text": "Wrong approach, try again"},
            {"text": "Please fix the import"},
        ]
        findings = analyze_user_corrections(empty_session)
        assert len(findings) == 1
        assert findings[0].category == USER_BEHAVIOR

    def test_short_messages_ignored(self, empty_session: SessionData):
        empty_session.user_messages = [
            {"text": "no"},
            {"text": "no"},
        ]
        assert analyze_user_corrections(empty_session) == []


# ---------------------------------------------------------------------------
# Analyzer: MaverickNotUsed
# ---------------------------------------------------------------------------


class TestAnalyzeMaverickNotUsed:
    def test_no_skills_available(self, empty_session: SessionData):
        assert analyze_maverick_not_used(empty_session) == []

    def test_maverick_loaded_not_invoked(self, session_with_maverick: SessionData):
        findings = analyze_maverick_not_used(session_with_maverick)
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].category == USER_BEHAVIOR

    def test_maverick_loaded_and_invoked(self, session_with_workflow: SessionData):
        # Also add a maverick-prefixed invocation to satisfy the filter
        session_with_workflow.skills_invoked.append("maverick:do-task-solo")
        findings = analyze_maverick_not_used(session_with_workflow)
        assert findings == []


# ---------------------------------------------------------------------------
# Analyzer: MaverickPartialUse
# ---------------------------------------------------------------------------


class TestAnalyzeMaverickPartialUse:
    def test_no_workflow_no_findings(self, empty_session: SessionData):
        assert analyze_maverick_partial_use(empty_session) == []

    def test_workflow_without_review_or_verification(self, session_with_workflow: SessionData):
        findings = analyze_maverick_partial_use(session_with_workflow)
        # Should have 2 findings: no code reviewer, no verification
        assert len(findings) == 2
        assert all(f.category == MAVERICK_GAP for f in findings)

    def test_workflow_with_review_agent(self, session_with_workflow: SessionData):
        session_with_workflow.tool_calls = [
            ToolCall(
                timestamp="t",
                tool_name="Agent",
                input_data={"subagent_type": "maverick:agent-code-reviewer"},
            ),
            make_bash_tool_call("pytest"),
        ]
        findings = analyze_maverick_partial_use(session_with_workflow)
        # Only missing: nothing — both review and verification present
        assert len(findings) == 0

    def test_workflow_with_verification_only(self, session_with_workflow: SessionData):
        session_with_workflow.tool_calls = [
            make_bash_tool_call("npm test"),
        ]
        findings = analyze_maverick_partial_use(session_with_workflow)
        # Missing code reviewer only
        assert len(findings) == 1
        assert "code-reviewer" in findings[0].title


# ---------------------------------------------------------------------------
# Analyzer: ProjectSkillsIgnored
# ---------------------------------------------------------------------------


class TestAnalyzeProjectSkillsIgnored:
    def test_no_project_skills(self, empty_session: SessionData):
        assert analyze_project_skills_ignored(empty_session, []) == []

    def test_all_skills_read(self, empty_session: SessionData):
        paths = ["/p/docs/maverick/skills/logging/SKILL.md"]
        empty_session.project_skills_read = paths
        assert analyze_project_skills_ignored(empty_session, paths) == []

    def test_skills_ignored_no_maverick(self, empty_session: SessionData):
        paths = ["/p/docs/maverick/skills/logging/SKILL.md"]
        findings = analyze_project_skills_ignored(empty_session, paths)
        assert len(findings) == 1
        assert findings[0].category == USER_BEHAVIOR

    def test_skills_ignored_with_maverick(self, session_with_maverick: SessionData):
        paths = ["/p/docs/maverick/skills/logging/SKILL.md"]
        findings = analyze_project_skills_ignored(session_with_maverick, paths)
        assert len(findings) == 1
        assert findings[0].category == MAVERICK_GAP


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------


class TestRunMechanicalAnalyzers:
    def test_clean_session(self, empty_session: SessionData):
        findings = run_mechanical_analyzers(empty_session)
        assert findings == []

    def test_sorted_by_category_then_severity(self, session_with_maverick: SessionData):
        # Trigger commit-without-verification (critical, maverick_gap)
        session_with_maverick.tool_calls = [
            make_bash_tool_call("git commit -m 'x'"),
        ]
        # Trigger user corrections (warning, user_behavior)
        session_with_maverick.user_messages = [
            {"text": "No, that's wrong, try again"},
            {"text": "Wrong, please undo that"},
        ]
        findings = run_mechanical_analyzers(session_with_maverick)
        assert len(findings) >= 2
        # maverick_gap should come first
        categories = [f.category for f in findings]
        gap_indices = [i for i, c in enumerate(categories) if c == MAVERICK_GAP]
        user_indices = [i for i, c in enumerate(categories) if c == USER_BEHAVIOR]
        if gap_indices and user_indices:
            assert max(gap_indices) < min(user_indices)

    def test_includes_project_skills_when_provided(self, empty_session: SessionData):
        paths = ["/p/docs/maverick/skills/logging/SKILL.md"]
        findings = run_mechanical_analyzers(empty_session, project_skill_paths=paths)
        assert any(f.analyzer == "ProjectSkillsIgnored" for f in findings)

    def test_version_mismatch_filters_gap_findings(self, session_with_maverick: SessionData):
        session_with_maverick.tool_calls = [
            make_bash_tool_call("git commit -m 'x'"),
        ]
        session_with_maverick.maverick_version = "0.3.0"
        findings = run_mechanical_analyzers(
            session_with_maverick, current_version="0.5.0"
        )
        # MAVERICK_GAP findings should be filtered out
        assert not any(f.category == MAVERICK_GAP for f in findings)
        # VersionMismatch finding should be present
        assert any(f.analyzer == "VersionMismatch" for f in findings)
        vm_finding = next(f for f in findings if f.analyzer == "VersionMismatch")
        assert "0.3.0" in vm_finding.detail
        assert "0.5.0" in vm_finding.detail

    def test_version_match_keeps_gap_findings(self, session_with_maverick: SessionData):
        session_with_maverick.tool_calls = [
            make_bash_tool_call("git commit -m 'x'"),
        ]
        session_with_maverick.maverick_version = "0.5.0"
        findings = run_mechanical_analyzers(
            session_with_maverick, current_version="0.5.0"
        )
        assert any(f.category == MAVERICK_GAP for f in findings)
        assert not any(f.analyzer == "VersionMismatch" for f in findings)

    def test_unknown_version_filters_gap_findings(self, session_with_maverick: SessionData):
        session_with_maverick.tool_calls = [
            make_bash_tool_call("git commit -m 'x'"),
        ]
        # No maverick_version set (empty string = pre-version plugin)
        findings = run_mechanical_analyzers(
            session_with_maverick, current_version="0.5.0"
        )
        assert not any(f.category == MAVERICK_GAP for f in findings)
        assert any(f.analyzer == "VersionMismatch" for f in findings)
        vm = next(f for f in findings if f.analyzer == "VersionMismatch")
        assert "unknown" in vm.detail

    def test_no_current_version_skips_check(self, session_with_maverick: SessionData):
        session_with_maverick.tool_calls = [
            make_bash_tool_call("git commit -m 'x'"),
        ]
        # No current_version passed — version check skipped
        findings = run_mechanical_analyzers(session_with_maverick)
        assert any(f.category == MAVERICK_GAP for f in findings)

    def test_no_maverick_loaded_skips_version_check(self, empty_session: SessionData):
        empty_session.tool_calls = [
            make_bash_tool_call("git commit -m 'x'"),
        ]
        findings = run_mechanical_analyzers(empty_session, current_version="0.5.0")
        # No version check for sessions without Maverick
        assert not any(f.analyzer == "VersionMismatch" for f in findings)


# ---------------------------------------------------------------------------
# Version compatibility
# ---------------------------------------------------------------------------


class TestVersionsCompatible:
    def test_exact_match(self):
        assert _versions_compatible("0.5.0", "0.5.0") is True

    def test_dev_suffix_compatible(self):
        assert _versions_compatible("0.5.0-dev", "0.5.0") is True

    def test_both_dev(self):
        assert _versions_compatible("0.5.0-dev", "0.5.0-dev") is True

    def test_different_versions(self):
        assert _versions_compatible("0.4.0", "0.5.0") is False

    def test_different_minor(self):
        assert _versions_compatible("0.3.0", "0.5.0") is False

    def test_empty_session_version(self):
        assert _versions_compatible("", "0.5.0") is False

    def test_build_metadata(self):
        assert _versions_compatible("0.5.0+build123", "0.5.0") is True


class TestGetCurrentVersion:
    def test_returns_string(self):
        version = get_current_version()
        assert isinstance(version, str)
        assert len(version) > 0

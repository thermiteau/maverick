"""Shared fixtures for unit tests."""

from __future__ import annotations

import pytest

from maverick.session_review.parser import SessionData, ToolCall


@pytest.fixture
def empty_session() -> SessionData:
    """A minimal SessionData with no activity."""
    return SessionData(
        session_id="test-session-001",
        project_path="/home/user/project",
        git_branch="feat/test",
        created="2026-01-15T10:00:00Z",
        modified="2026-01-15T11:00:00Z",
        model="claude-sonnet-4-20250514",
    )


@pytest.fixture
def session_with_maverick(empty_session: SessionData) -> SessionData:
    """A session where Maverick plugin was loaded but not invoked."""
    empty_session.skills_available = [
        "maverick:do-task-solo",
        "maverick:do-issue-solo",
        "maverick:mav-bp-logging",
    ]
    return empty_session


@pytest.fixture
def session_with_workflow(session_with_maverick: SessionData) -> SessionData:
    """A session where a Maverick workflow was invoked."""
    session_with_maverick.skills_invoked = ["maverick:do-task-solo", "do-task-solo"]
    return session_with_maverick


def make_bash_tool_call(command: str, timestamp: str = "2026-01-15T10:30:00Z") -> ToolCall:
    """Helper to create a Bash ToolCall."""
    return ToolCall(
        timestamp=timestamp,
        tool_name="Bash",
        input_data={"command": command},
    )


def make_edit_tool_call(
    file_path: str, timestamp: str = "2026-01-15T10:30:00Z"
) -> ToolCall:
    """Helper to create an Edit ToolCall."""
    return ToolCall(
        timestamp=timestamp,
        tool_name="Edit",
        input_data={"file_path": file_path, "old_string": "x", "new_string": "y"},
        file_path=file_path,
    )

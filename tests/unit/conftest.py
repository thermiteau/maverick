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
        "maverick:do-issue-solo",
        "maverick:do-issue-guided",
        "maverick:mav-bp-logging",
    ]
    return empty_session


@pytest.fixture
def session_with_workflow(session_with_maverick: SessionData) -> SessionData:
    """A session where a Maverick workflow was invoked."""
    session_with_maverick.skills_invoked = ["maverick:do-issue-solo", "do-issue-solo"]
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


@pytest.fixture(autouse=True)
def _isolate_claims_registry(tmp_path, monkeypatch):
    """Keep the local claims registry out of the developer's real home dir.

    coordinator.claim()/takeover()/release() write to
    ~/.maverick/active-claims.json (the SessionEnd-hook / autonomous-mode
    registry). Any test that exercises them without patching the path
    would pollute — and be polluted by — the machine's real registry.
    Discovered when fake test claims (me/r#42) showed up in the real file.
    """
    from maverick import coordinator

    monkeypatch.setattr(
        coordinator,
        "_claims_registry_path",
        lambda: tmp_path / "active-claims.json",
    )

"""Tests for maverick.session_review.parser — session file parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.session_review.parser import (
    SessionData,
    ToolCall,
    _extract_file_path,
    encode_project_path,
    load_session_index,
    parse_session,
)


class TestEncodeProjectPath:
    def test_basic_path(self):
        assert encode_project_path("/Users/foo/bar") == "-Users-foo-bar"

    def test_root(self):
        assert encode_project_path("/") == "-"

    def test_no_slashes(self):
        assert encode_project_path("myproject") == "myproject"

    def test_trailing_slash(self):
        assert encode_project_path("/home/user/project/") == "-home-user-project-"


class TestExtractFilePath:
    def test_read_tool(self):
        assert _extract_file_path("Read", {"file_path": "/src/main.py"}) == "/src/main.py"

    def test_write_tool(self):
        assert _extract_file_path("Write", {"file_path": "/out.txt"}) == "/out.txt"

    def test_edit_tool(self):
        assert _extract_file_path("Edit", {"file_path": "/f.py"}) == "/f.py"

    def test_glob_tool(self):
        assert _extract_file_path("Glob", {"path": "/src"}) == "/src"

    def test_grep_tool(self):
        assert _extract_file_path("Grep", {"path": "/src"}) == "/src"

    def test_bash_tool(self):
        assert _extract_file_path("Bash", {"command": "ls"}) is None

    def test_missing_key(self):
        assert _extract_file_path("Read", {}) is None


class TestLoadSessionIndex:
    def test_no_index_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = load_session_index("/nonexistent/project")
        assert result == []

    def test_valid_index(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        encoded = encode_project_path("/my/project")
        index_dir = tmp_path / ".claude" / "projects" / encoded
        index_dir.mkdir(parents=True)
        (index_dir / "sessions-index.json").write_text('[{"id": "abc123"}]')

        result = load_session_index("/my/project")
        assert len(result) == 1
        assert result[0]["id"] == "abc123"

    def test_invalid_json_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        encoded = encode_project_path("/my/project")
        index_dir = tmp_path / ".claude" / "projects" / encoded
        index_dir.mkdir(parents=True)
        (index_dir / "sessions-index.json").write_text("not json")

        result = load_session_index("/my/project")
        assert result == []


class TestParseSession:
    def _write_session(self, path: Path, events: list[dict]) -> Path:
        session_file = path / "test-session.jsonl"
        with open(session_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
        return session_file

    def test_empty_session(self, tmp_path: Path):
        session_file = self._write_session(tmp_path, [])
        data = parse_session(session_file)
        assert data.session_id == "test-session"
        assert data.tool_calls == []
        assert data.user_messages == []

    def test_extracts_metadata(self, tmp_path: Path):
        events = [
            {
                "type": "user",
                "timestamp": "2026-01-15T10:00:00Z",
                "cwd": "/home/user/project",
                "gitBranch": "main",
                "message": {"content": "Hello"},
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert data.project_path == "/home/user/project"
        assert data.git_branch == "main"

    def test_extracts_user_text_messages(self, tmp_path: Path):
        events = [
            {
                "type": "user",
                "timestamp": "2026-01-15T10:00:00Z",
                "message": {"content": "Fix the bug"},
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert len(data.user_messages) == 1
        assert data.user_messages[0]["text"] == "Fix the bug"

    def test_extracts_tool_calls(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:01:00Z",
                "message": {
                    "model": "claude-sonnet-4-20250514",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "Read",
                            "input": {"file_path": "/src/main.py"},
                        }
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert len(data.tool_calls) == 1
        assert data.tool_calls[0].tool_name == "Read"
        assert data.tool_calls[0].file_path == "/src/main.py"
        assert data.model == "claude-sonnet-4-20250514"

    def test_tracks_file_modifications(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Edit",
                            "input": {"file_path": "/src/a.py"},
                        },
                        {
                            "type": "tool_use",
                            "id": "t2",
                            "name": "Write",
                            "input": {"file_path": "/src/b.py"},
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert data.files_modified == {"/src/a.py", "/src/b.py"}

    def test_tracks_git_commits(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Bash",
                            "input": {"command": "git commit -m 'fix'"},
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert len(data.commits) == 1

    def test_tracks_skill_invocations(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Skill",
                            "input": {"skill": "do-task-solo"},
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert "do-task-solo" in data.skills_invoked

    def test_tracks_errors(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-err",
                            "name": "Bash",
                            "input": {"command": "false"},
                        },
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2026-01-15T10:02:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-err",
                            "is_error": True,
                            "content": "Command failed",
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert len(data.errors) == 1
        assert data.errors[0]["error"] == "Command failed"

    def test_tracks_project_skills_read(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Read",
                            "input": {
                                "file_path": "/project/docs/maverick/skills/logging/SKILL.md"
                            },
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert len(data.project_skills_read) == 1

    def test_created_modified_from_timestamps(self, tmp_path: Path):
        events = [
            {"type": "user", "timestamp": "2026-01-15T10:05:00Z", "message": {"content": "a"}},
            {"type": "user", "timestamp": "2026-01-15T10:00:00Z", "message": {"content": "b"}},
            {"type": "user", "timestamp": "2026-01-15T10:10:00Z", "message": {"content": "c"}},
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert data.created == "2026-01-15T10:00:00Z"
        assert data.modified == "2026-01-15T10:10:00Z"

    def test_skips_malformed_json_lines(self, tmp_path: Path):
        session_file = tmp_path / "bad.jsonl"
        with open(session_file, "w") as f:
            f.write('{"type": "user", "timestamp": "t1", "message": {"content": "ok"}}\n')
            f.write("not valid json\n")
            f.write('{"type": "user", "timestamp": "t2", "message": {"content": "also ok"}}\n')

        data = parse_session(session_file)
        assert len(data.user_messages) == 2

    def test_extracts_maverick_version(self, tmp_path: Path):
        events = [
            {
                "type": "user",
                "timestamp": "2026-01-15T10:00:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t1",
                            "content": "some text\n<!-- maverick-plugin-version: 0.5.0 -->\nmore",
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert data.maverick_version == "0.5.0"

    def test_no_version_marker(self, tmp_path: Path):
        events = [
            {
                "type": "user",
                "timestamp": "2026-01-15T10:00:00Z",
                "message": {"content": "just a normal message"},
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert data.maverick_version == ""

    def test_version_with_prerelease(self, tmp_path: Path):
        events = [
            {
                "type": "assistant",
                "timestamp": "2026-01-15T10:00:00Z",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "<!-- maverick-plugin-version: 0.5.0-dev -->",
                        },
                    ],
                },
            },
        ]
        session_file = self._write_session(tmp_path, events)
        data = parse_session(session_file)
        assert data.maverick_version == "0.5.0-dev"

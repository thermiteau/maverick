"""Parse .jsonl session files into structured SessionData."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolCall:
    timestamp: str
    tool_name: str
    input_data: dict
    result: str | None = None
    is_error: bool = False
    duration_ms: int | None = None
    file_path: str | None = None


@dataclass
class SessionData:
    session_id: str
    project_path: str
    git_branch: str
    created: str
    modified: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    user_messages: list[dict] = field(default_factory=list)
    assistant_messages: list[dict] = field(default_factory=list)
    skills_invoked: list[str] = field(default_factory=list)
    skills_available: list[str] = field(default_factory=list)
    project_skills_read: list[str] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    files_modified: set[str] = field(default_factory=set)
    errors: list[dict] = field(default_factory=list)


def encode_project_path(project_path: str) -> str:
    """Encode a project path for Claude session directory lookup.

    ``/Users/foo/bar`` → ``-Users-foo-bar``
    """
    return project_path.replace("/", "-")


def find_sessions(project_path: str) -> list[Path]:
    """Find all .jsonl session files for a project."""
    encoded = encode_project_path(project_path)
    session_dir = Path.home() / ".claude" / "projects" / encoded
    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


def load_session_index(project_path: str) -> list[dict]:
    """Read sessions-index.json for a project (if it exists)."""
    encoded = encode_project_path(project_path)
    index_path = Path.home() / ".claude" / "projects" / encoded / "sessions-index.json"
    if not index_path.is_file():
        return []
    try:
        data = json.loads(index_path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _extract_file_path(tool_name: str, input_data: dict) -> str | None:
    """Extract the target file path from a tool call's input."""
    if tool_name in ("Read", "Write", "Edit"):
        return input_data.get("file_path")
    if tool_name == "Glob":
        return input_data.get("path")
    if tool_name == "Grep":
        return input_data.get("path")
    return None


_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_PROJECT_SKILL_RE = re.compile(r"docs/maverick/skills/[^/]+/SKILL\.md")
_MAVERICK_SKILL_RE = re.compile(r"maverick:(\S+)")


def parse_session(path: Path) -> SessionData:
    """Parse a single .jsonl session file into SessionData."""
    events: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    session_id = path.stem
    project_path = ""
    git_branch = ""
    model = ""
    created = ""
    modified = ""
    tool_calls: list[ToolCall] = []
    user_messages: list[dict] = []
    assistant_messages: list[dict] = []
    skills_invoked: list[str] = []
    skills_available: list[str] = []
    project_skills_read: list[str] = []
    commits: list[dict] = []
    files_modified: set[str] = set()
    errors: list[dict] = []

    # Map tool_use_id → ToolCall for linking results back
    pending_tools: dict[str, ToolCall] = {}
    # Track timestamps for created/modified
    timestamps: list[str] = []

    for event in events:
        ts = event.get("timestamp", "")
        if ts:
            timestamps.append(ts)

        etype = event.get("type")

        # Extract metadata from any event with cwd/gitBranch
        if event.get("cwd") and not project_path:
            project_path = event["cwd"]
        if event.get("gitBranch") and not git_branch:
            git_branch = event["gitBranch"]
        if event.get("sessionId") and not session_id:
            session_id = event["sessionId"]

        if etype == "user":
            msg = event.get("message", {})
            content = msg.get("content")

            # Text user messages
            if isinstance(content, str):
                user_messages.append({"text": content, "timestamp": ts})

            # Content array — may contain tool_result entries
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id", "")
                            is_error = block.get("is_error") in (True, "True", "true")
                            result_text = ""
                            rc = block.get("content")
                            if isinstance(rc, str):
                                result_text = rc
                            elif isinstance(rc, list):
                                result_text = " ".join(
                                    b.get("text", "") for b in rc if isinstance(b, dict)
                                )

                            if tool_use_id in pending_tools:
                                tc = pending_tools.pop(tool_use_id)
                                tc.result = result_text
                                tc.is_error = is_error

                            if is_error:
                                errors.append(
                                    {
                                        "tool_use_id": tool_use_id,
                                        "error": result_text[:500],
                                        "timestamp": ts,
                                    }
                                )
                        elif block.get("type") == "text":
                            user_messages.append(
                                {"text": block.get("text", ""), "timestamp": ts}
                            )

                # Scan first user message for available maverick skills
                if not skills_available and isinstance(content, str):
                    skills_available = _MAVERICK_SKILL_RE.findall(content)

        elif etype == "assistant":
            msg = event.get("message", {})
            content = msg.get("content", [])

            # Extract model
            if msg.get("model") and not model:
                model = msg["model"]

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "text":
                        assistant_messages.append(
                            {"text": block.get("text", ""), "timestamp": ts}
                        )

                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        input_data = block.get("input", {})
                        tool_use_id = block.get("id", "")
                        file_path = _extract_file_path(tool_name, input_data)

                        tc = ToolCall(
                            timestamp=ts,
                            tool_name=tool_name,
                            input_data=input_data,
                            file_path=file_path,
                        )
                        tool_calls.append(tc)
                        if tool_use_id:
                            pending_tools[tool_use_id] = tc

                        # Track Skill invocations
                        if tool_name == "Skill":
                            skill_name = input_data.get("skill", "")
                            if skill_name:
                                skills_invoked.append(skill_name)

                        # Track Read of project skills
                        if tool_name == "Read" and file_path:
                            if _PROJECT_SKILL_RE.search(file_path):
                                project_skills_read.append(file_path)

                        # Track file modifications
                        if tool_name in ("Write", "Edit") and file_path:
                            files_modified.add(file_path)

                        # Track git commits
                        if tool_name == "Bash":
                            cmd = input_data.get("command", "")
                            if _GIT_COMMIT_RE.search(cmd):
                                commits.append(
                                    {"command": cmd, "timestamp": ts}
                                )

        # Scan system/user messages for available maverick skills
        if etype in ("user", "assistant") and not skills_available:
            msg = event.get("message", {})
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            if "maverick:" in text:
                skills_available = _MAVERICK_SKILL_RE.findall(text)

    if timestamps:
        timestamps.sort()
        created = timestamps[0]
        modified = timestamps[-1]

    return SessionData(
        session_id=session_id,
        project_path=project_path,
        git_branch=git_branch,
        created=created,
        modified=modified,
        model=model,
        tool_calls=tool_calls,
        user_messages=user_messages,
        assistant_messages=assistant_messages,
        skills_invoked=skills_invoked,
        skills_available=skills_available,
        project_skills_read=project_skills_read,
        commits=commits,
        files_modified=files_modified,
        errors=errors,
    )

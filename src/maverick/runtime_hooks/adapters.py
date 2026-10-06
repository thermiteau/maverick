"""Per-runtime translation between native hook payloads and Maverick's model.

An adapter does two things and nothing else:

- ``normalize(raw)`` turns the runtime's native hook payload into a
  :class:`HookInput` — event kind, working directory, and (for tool calls)
  a :class:`ToolCall` classified by *capability* (shell, write, fetch,
  skill) rather than by the runtime's tool names.
- ``render_tool_decision(decision, reason)`` turns a pre-tool-use decision
  back into the runtime's native response.

Adding a runtime means adding an adapter; handlers do not change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

ToolKind = Literal["shell", "write", "fetch", "skill", "other"]
EventKind = Literal[
    "tool_call", "subagent_start", "subagent_stop", "session_end", "other"
]


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation, classified by capability."""

    kind: ToolKind
    cwd: Path = field(default_factory=lambda: Path("."))
    command: str = ""  # shell
    path: str = ""  # write
    url: str = ""  # fetch
    skill: str = ""  # skill (bare name, namespace stripped)


@dataclass(frozen=True)
class HookInput:
    """A runtime-neutral hook event."""

    event: EventKind
    cwd: Path = field(default_factory=lambda: Path("."))
    tool: ToolCall | None = None
    agent: str | None = None  # subagent name, namespace stripped


@dataclass(frozen=True)
class HookOutput:
    """What the shim relays back to the runtime."""

    stdout: str = ""
    stderr: str = ""


class Adapter(Protocol):
    name: str

    def normalize(self, raw: dict) -> HookInput: ...

    def render_tool_decision(self, decision: str, reason: str) -> HookOutput: ...


def _strip_namespace(value: str) -> str:
    """Plugin skills and agents report namespaced (``maverick:agent-x``)."""
    return value.split(":")[-1]


class ClaudeAdapter:
    """Claude Code hook payloads (PreToolUse, SubagentStart/Stop, SessionEnd)."""

    name = "claude"

    _EVENTS: dict[str, EventKind] = {
        "PreToolUse": "tool_call",
        "SubagentStart": "subagent_start",
        "SubagentStop": "subagent_stop",
        "SessionEnd": "session_end",
    }

    def normalize(self, raw: dict) -> HookInput:
        cwd = Path(raw.get("cwd") or ".")
        event = self._EVENTS.get(raw.get("hook_event_name") or "", "other")
        tool_name = raw.get("tool_name")
        # PreToolUse is the only event that carries a tool. A payload with a
        # tool but no event name is still a tool call (older payloads, tests).
        if tool_name is not None and event == "other":
            event = "tool_call"
        tool = self._tool(tool_name or "", raw.get("tool_input") or {}, cwd)
        return HookInput(
            event=event,
            cwd=cwd,
            tool=tool if event == "tool_call" else None,
            agent=self._agent(raw),
        )

    @staticmethod
    def _tool(name: str, tool_input: dict, cwd: Path) -> ToolCall:
        if name == "Bash":
            return ToolCall("shell", cwd, command=str(tool_input.get("command") or ""))
        if name in ("Edit", "Write", "NotebookEdit"):
            path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            return ToolCall("write", cwd, path=str(path))
        if name == "WebFetch":
            return ToolCall("fetch", cwd, url=str(tool_input.get("url") or ""))
        if name == "Skill":
            skill = _strip_namespace(str(tool_input.get("skill") or ""))
            return ToolCall("skill", cwd, skill=skill)
        return ToolCall("other", cwd)

    @staticmethod
    def _agent(raw: dict) -> str | None:
        for key in ("agent_type", "subagent_type", "agent_name", "agent", "name"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                return _strip_namespace(value)
        return None

    def render_tool_decision(self, decision: str, reason: str) -> HookOutput:
        """Every decision is JSON on stdout with exit 0.

        Deny is expressed as ``permissionDecision: deny`` rather than exit
        code 2 so the shim can treat *any* non-zero exit from the CLI as a
        failure and fail open — an old CLI without ``maverick hook`` exits 2
        from argparse, and must never block every tool call.
        """
        if decision == "allow":
            return HookOutput()
        message = f"maverick scope-guard: {reason}"
        stderr = f"maverick scope-guard: BLOCKED — {reason}\n" if decision == "deny" else ""
        return HookOutput(
            stdout=json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": decision,
                        "permissionDecisionReason": message,
                    }
                }
            ),
            stderr=stderr,
        )


ADAPTERS: dict[str, Adapter] = {"claude": ClaudeAdapter()}

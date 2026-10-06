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
    """What `maverick hook` writes back to the runtime."""

    stdout: str = ""
    stderr: str = ""
    #: Process exit code. 0 unless the runtime expresses a decision through
    #: the exit code itself (Kiro blocks a tool call on exit 2).
    exit_code: int = 0


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




#: Exit code `maverick hook --runtime kiro` uses to mean "block". Kiro itself
#: blocks on exit 2, but argparse in an older CLI also exits 2, which would
#: block every tool call. So the CLI signals a block with a code nothing else
#: produces, and the generated hook command (``kiro_hook_command``) maps only
#: this code to 2 and everything else (old CLI, CLI missing, crash) to 0.
KIRO_BLOCK_EXIT = 42


def kiro_hook_command(handler: str) -> str:
    """The shell command a Kiro hook file runs for *handler* (POSIX sh)."""
    return (
        f"maverick hook {handler} --runtime kiro; s=$?; "
        f'[ "$s" -eq {KIRO_BLOCK_EXIT} ] && exit 2; exit 0'
    )


class KiroAdapter:
    """Kiro hook payloads (PreToolUse, SessionEnd), V3 engine first.

    Shapes verified against Kiro CLI 2.27.1 (Phase 3 spike):

    - V3: PascalCase events; ``execute_bash`` {command, cwd}, ``fs_write``
      {path, text}, ``str_replace`` {path, oldStr, newStr}, ``web_fetch``
      {url}; absolute paths.
    - V2 (legacy, still accepted): camelCase events; ``shell`` {command},
      ``write`` {command, path, content}; workspace-relative paths.

    Kiro hooks are configured without a ``matcher``: in V3 hook files the
    documented ``"*"`` and alias matchers silently stop a hook firing, so
    this adapter does the tool filtering instead.
    """

    name = "kiro"

    _EVENTS: dict[str, EventKind] = {
        "PreToolUse": "tool_call",
        "preToolUse": "tool_call",
        "SessionEnd": "session_end",
        "sessionEnd": "session_end",
    }
    _SHELL = frozenset({"execute_bash", "shell", "execute_cmd"})
    _WRITE = frozenset(
        {"fs_write", "write", "fs_append", "str_replace", "delete_file"}
    )
    _FETCH = frozenset({"web_fetch"})

    def normalize(self, raw: dict) -> HookInput:
        cwd = Path(raw.get("cwd") or ".")
        event = self._EVENTS.get(raw.get("hook_event_name") or "", "other")
        tool = None
        if event == "tool_call":
            tool = self._tool(str(raw.get("tool_name") or ""), raw.get("tool_input") or {}, cwd)
        return HookInput(event=event, cwd=cwd, tool=tool)

    def _tool(self, name: str, tool_input: dict, cwd: Path) -> ToolCall:
        if name in self._SHELL:
            # A shell call may run somewhere other than the session cwd;
            # git checks (protected branch) must look at that directory.
            run_dir = tool_input.get("cwd")
            shell_cwd = cwd / run_dir if isinstance(run_dir, str) and run_dir else cwd
            return ToolCall("shell", shell_cwd, command=str(tool_input.get("command") or ""))
        if name in self._WRITE:
            return ToolCall("write", cwd, path=str(tool_input.get("path") or ""))
        if name in self._FETCH:
            return ToolCall("fetch", cwd, url=str(tool_input.get("url") or ""))
        return ToolCall("other", cwd)

    def render_tool_decision(self, decision: str, reason: str) -> HookOutput:
        """Allow is exit 0; deny and ask both block (``KIRO_BLOCK_EXIT``).

        Kiro hooks can only allow or block — there is no in-session consent
        prompt — so an interactive "ask" verdict blocks too, and says how
        the user can proceed. stderr is returned to the model.
        """
        if decision == "allow":
            return HookOutput()
        message = f"maverick scope-guard: BLOCKED — {reason.rstrip('.')}."
        if decision == "ask":
            message += (
                " Kiro hooks cannot ask for consent in-session, so this is "
                "blocked. Tell the user what you need: they can run it "
                "themselves, or record issue-level authorization with "
                "`maverick coord authorize <repo> <issue> <scope>`."
            )
        return HookOutput(stderr=message + "\n", exit_code=KIRO_BLOCK_EXIT)


ADAPTERS: dict[str, Adapter] = {"claude": ClaudeAdapter(), "kiro": KiroAdapter()}

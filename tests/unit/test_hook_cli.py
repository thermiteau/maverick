"""Tests for `maverick hook`, the Claude adapter, and the plugin hook shim.

The shim and the CLI share one contract: a real decision is always JSON on
stdout with exit 0, so any non-zero exit means "could not run the hook" and
fails open. An older CLI without `maverick hook` exits 2 from argparse —
the code Claude Code reads as "block" — and must never block a tool call.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.runtime_hooks import cli as hook_cli
from maverick.runtime_hooks.adapters import ClaudeAdapter

SHIM_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "maverick" / "hooks" / "run_hook.py"
)


def _run_cli(payload: dict, handler: str = "scope-guard", env: dict | None = None):
    """Run `python -m maverick.cli hook ...` exactly as the shim would."""
    return subprocess.run(
        [sys.executable, "-m", "maverick.cli", "hook", handler, "--runtime", "claude"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", **(env or {})},
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Claude adapter
# ---------------------------------------------------------------------------


class TestClaudeAdapter:
    @pytest.mark.parametrize(
        ("tool_name", "tool_input", "kind", "field", "value"),
        [
            ("Bash", {"command": "ls"}, "shell", "command", "ls"),
            ("Edit", {"file_path": "a.py"}, "write", "path", "a.py"),
            ("Write", {"file_path": "b.py"}, "write", "path", "b.py"),
            ("NotebookEdit", {"notebook_path": "n.ipynb"}, "write", "path", "n.ipynb"),
            ("WebFetch", {"url": "https://x"}, "fetch", "url", "https://x"),
            ("Skill", {"skill": "maverick:do-code"}, "skill", "skill", "do-code"),
        ],
    )
    def test_tool_classified_by_capability(self, tool_name, tool_input, kind, field, value):
        event = ClaudeAdapter().normalize(
            {"hook_event_name": "PreToolUse", "tool_name": tool_name,
             "tool_input": tool_input, "cwd": "/w"}
        )
        assert event.event == "tool_call"
        assert event.tool is not None
        assert event.tool.kind == kind
        assert getattr(event.tool, field) == value
        assert event.tool.cwd == Path("/w")

    def test_unknown_tool_is_other(self):
        event = ClaudeAdapter().normalize({"tool_name": "Glob", "tool_input": {}})
        assert event.tool is not None and event.tool.kind == "other"

    def test_lifecycle_events(self):
        adapter = ClaudeAdapter()
        start = adapter.normalize(
            {"hook_event_name": "SubagentStart", "agent_type": "maverick:agent-x"}
        )
        assert start.event == "subagent_start"
        assert start.agent == "agent-x"
        assert start.tool is None
        assert adapter.normalize({"hook_event_name": "SessionEnd"}).event == "session_end"
        assert adapter.normalize({}).event == "other"

    def test_allow_renders_nothing(self):
        out = ClaudeAdapter().render_tool_decision("allow", "")
        assert out.stdout == "" and out.stderr == ""

    @pytest.mark.parametrize("decision", ["ask", "deny"])
    def test_decisions_render_as_json(self, decision):
        out = ClaudeAdapter().render_tool_decision(decision, "because")
        spec = json.loads(out.stdout)["hookSpecificOutput"]
        assert spec["hookEventName"] == "PreToolUse"
        assert spec["permissionDecision"] == decision
        assert "because" in spec["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# maverick hook (end to end, in a subprocess)
# ---------------------------------------------------------------------------


class TestHookCommand:
    def test_safe_command_allows_silently(self):
        result = _run_cli({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        assert result.returncode == 0
        assert result.stdout == ""

    def test_force_push_asks_interactively(self):
        result = _run_cli(
            {"tool_name": "Bash", "tool_input": {"command": "git push --force"}}
        )
        assert result.returncode == 0
        spec = json.loads(result.stdout)["hookSpecificOutput"]
        assert spec["permissionDecision"] == "ask"

    def test_force_push_denied_autonomously_with_exit_zero(self):
        result = _run_cli(
            {"tool_name": "Bash", "tool_input": {"command": "git push --force"}},
            env={"MAVERICK_AUTONOMOUS": "1"},
        )
        assert result.returncode == 0
        spec = json.loads(result.stdout)["hookSpecificOutput"]
        assert spec["permissionDecision"] == "deny"
        assert "BLOCKED" in result.stderr

    def test_guard_disable_escape_hatch(self):
        result = _run_cli(
            {"tool_name": "Bash", "tool_input": {"command": "AWS_PROFILE=prod aws s3 ls"}},
            env={"MAVERICK_GUARD_DISABLE": "1"},
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_unparseable_payload_fails_open(self):
        result = subprocess.run(
            [sys.executable, "-m", "maverick.cli", "hook", "scope-guard", "--runtime", "claude"],
            input="not json",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_internal_error_fails_open(self, capsys):
        with (
            patch.object(hook_cli, "run", side_effect=RuntimeError("boom")),
            patch.object(sys, "stdin") as stdin,
        ):
            stdin.read.return_value = json.dumps({"tool_name": "Bash"})
            assert hook_cli.main(["scope-guard", "--runtime", "claude"]) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "internal error" in captured.err

    def test_session_release_without_claims_is_silent(self):
        result = _run_cli({"hook_event_name": "SessionEnd"}, handler="session-release")
        assert result.returncode == 0
        assert result.stdout == ""


# ---------------------------------------------------------------------------
# Plugin shim
# ---------------------------------------------------------------------------


@pytest.fixture
def shim():
    spec = importlib.util.spec_from_file_location("run_hook_shim", SHIM_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


class TestShim:
    ARGV = ["scope-guard", "--runtime", "claude"]

    def test_cli_missing_fails_open(self, shim, capsys):
        with (
            patch.object(shim, "_cli_command", return_value=None),
            patch.object(shim.sys, "stdin") as stdin,
        ):
            stdin.read.return_value = "{}"
            assert shim.main(self.ARGV) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "CLI not found" in captured.err

    def test_old_cli_exit_two_fails_open(self, shim, capsys):
        """argparse's exit 2 must not reach the runtime as a block."""
        with (
            patch.object(shim, "_cli_command", return_value=["maverick"]),
            patch.object(shim.subprocess, "run") as run,
            patch.object(shim.sys, "stdin") as stdin,
        ):
            stdin.read.return_value = "{}"
            run.return_value.returncode = 2
            run.return_value.stdout = "usage: maverick ..."
            assert shim.main(self.ARGV) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "predate" in captured.err

    def test_relays_cli_output(self, shim, capsys):
        with (
            patch.object(shim, "_cli_command", return_value=["maverick"]),
            patch.object(shim.subprocess, "run") as run,
            patch.object(shim.sys, "stdin") as stdin,
        ):
            stdin.read.return_value = '{"tool_name": "Bash"}'
            run.return_value.returncode = 0
            run.return_value.stdout = '{"hookSpecificOutput": {}}'
            run.return_value.stderr = "note"
            assert shim.main(self.ARGV) == 0
        assert run.call_args[0][0] == ["maverick", "hook", *self.ARGV]
        assert run.call_args.kwargs["input"] == '{"tool_name": "Bash"}'
        captured = capsys.readouterr()
        assert captured.out == '{"hookSpecificOutput": {}}'
        assert captured.err == "note"

    def test_subprocess_exception_fails_open(self, shim, capsys):
        with (
            patch.object(shim, "_cli_command", return_value=["maverick"]),
            patch.object(shim.subprocess, "run", side_effect=OSError("boom")),
            patch.object(shim.sys, "stdin") as stdin,
        ):
            stdin.read.return_value = "{}"
            assert shim.main(self.ARGV) == 0
        assert "hook skipped" in capsys.readouterr().err

"""Tests for the Kiro runtime: adapter, `maverick hook --runtime kiro`, init.

Payload fixtures mirror what Kiro CLI 2.27.1 actually delivered in the
Phase 3 spike (V3 engine first, V2 still accepted). Kiro blocks a tool call
when the hook exits 2 and returns stderr to the model; there is no "ask".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from maverick import coordinator, init
from maverick.runtime_hooks import claims
from maverick.runtime_hooks.adapters import KIRO_BLOCK_EXIT, KiroAdapter, kiro_hook_command

CWD = "/work/proj"


def _v3(tool_name: str, tool_input: dict) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "cwd": CWD,
        "session_id": "sess_548f1c2e-0000-4000-8000-000000000000",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }


def _bash(command: str, run_cwd: str | None = None) -> dict:
    return _v3(
        "execute_bash",
        {"command": command, "description": "x", "cwd": run_cwd,
         "run_in_background": False, "timeout": None},
    )


def _run(payload: dict, handler: str = "scope-guard", env: dict | None = None):
    return subprocess.run(
        [sys.executable, "-m", "maverick.cli", "hook", handler, "--runtime", "kiro"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", ""), "HOME": "/nonexistent", **(env or {})},
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TestKiroNormalize:
    @pytest.mark.parametrize(
        ("tool_name", "tool_input", "kind", "field", "value"),
        [
            ("execute_bash", {"command": "ls", "cwd": None}, "shell", "command", "ls"),
            ("fs_write", {"path": f"{CWD}/a.py", "text": "x"}, "write", "path", f"{CWD}/a.py"),
            ("str_replace", {"path": f"{CWD}/a.py", "oldStr": "a", "newStr": "b"},
             "write", "path", f"{CWD}/a.py"),
            ("fs_append", {"path": "log.txt", "text": "x"}, "write", "path", "log.txt"),
            ("delete_file", {"path": "Dockerfile"}, "write", "path", "Dockerfile"),
            ("web_fetch", {"url": "https://example.com", "mode": "truncated"},
             "fetch", "url", "https://example.com"),
        ],
    )
    def test_v3_tools(self, tool_name, tool_input, kind, field, value):
        event = KiroAdapter().normalize(_v3(tool_name, tool_input))
        assert event.event == "tool_call"
        assert event.tool is not None
        assert event.tool.kind == kind
        assert getattr(event.tool, field) == value

    @pytest.mark.parametrize(
        ("tool_name", "tool_input", "kind"),
        [
            ("shell", {"command": "ls", "__tool_use_purpose": "p"}, "shell"),
            ("write", {"command": "create", "path": "notes.txt", "content": "x"}, "write"),
        ],
    )
    def test_v2_payloads_still_accepted(self, tool_name, tool_input, kind):
        raw = {"hook_event_name": "preToolUse", "cwd": CWD, "tool_name": tool_name,
               "tool_input": tool_input}
        event = KiroAdapter().normalize(raw)
        assert event.tool is not None and event.tool.kind == kind

    def test_internal_and_mcp_tools_are_other(self):
        for name in ("update_session_information", "@postgres/query", "read_file"):
            event = KiroAdapter().normalize(_v3(name, {}))
            assert event.tool is not None and event.tool.kind == "other"

    def test_shell_cwd_override(self):
        assert KiroAdapter().normalize(_bash("git push", "sub")).tool.cwd == Path(CWD) / "sub"
        assert KiroAdapter().normalize(_bash("git push", "/elsewhere")).tool.cwd == Path(
            "/elsewhere"
        )
        assert KiroAdapter().normalize(_bash("git push")).tool.cwd == Path(CWD)

    def test_lifecycle_events(self):
        adapter = KiroAdapter()
        end = adapter.normalize({"hook_event_name": "SessionEnd", "cwd": CWD, "reason": "x"})
        assert end.event == "session_end" and end.tool is None
        assert adapter.normalize({"hook_event_name": "SessionStart"}).event == "other"

    def test_render(self):
        adapter = KiroAdapter()
        allow = adapter.render_tool_decision("allow", "")
        assert (allow.exit_code, allow.stdout, allow.stderr) == (0, "", "")
        deny = adapter.render_tool_decision("deny", "because")
        assert deny.exit_code == KIRO_BLOCK_EXIT
        assert "because" in deny.stderr and deny.stdout == ""
        ask = adapter.render_tool_decision("ask", "because")
        assert ask.exit_code == KIRO_BLOCK_EXIT
        assert "cannot ask for consent" in ask.stderr


# ---------------------------------------------------------------------------
# maverick hook --runtime kiro (end to end)
# ---------------------------------------------------------------------------


class TestKiroHookCommand:
    def test_safe_command_allows(self):
        result = _run(_bash("echo hello"))
        assert result.returncode == 0
        assert result.stdout == "" and result.stderr == ""

    def test_force_push_blocks_interactively(self):
        """No "ask" in Kiro: an interactive rule hit blocks."""
        result = _run(_bash("git push --force"))
        assert result.returncode == KIRO_BLOCK_EXIT
        assert "cannot ask for consent" in result.stderr

    def test_force_push_blocks_autonomously(self):
        result = _run(_bash("git push --force"), env={"MAVERICK_AUTONOMOUS": "1"})
        assert result.returncode == KIRO_BLOCK_EXIT
        assert "autonomous mode" in result.stderr

    def test_production_blocks(self):
        result = _run(_bash("AWS_PROFILE=prod aws s3 ls"))
        assert result.returncode == KIRO_BLOCK_EXIT

    def test_workflow_write_blocks(self):
        result = _run(_v3("fs_write", {"path": f"{CWD}/.github/workflows/ci.yml", "text": "x"}))
        assert result.returncode == KIRO_BLOCK_EXIT
        assert "infrastructure" in result.stderr

    def test_unknown_handler_fails_open(self):
        """Hook config newer than the CLI: never exit 2 (= block) on bad args."""
        result = subprocess.run(
            [sys.executable, "-m", "maverick.cli", "hook", "future-handler", "--runtime", "kiro"],
            input="{}", capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "hook skipped" in result.stderr

    def test_unparseable_payload_fails_open(self):
        result = subprocess.run(
            [sys.executable, "-m", "maverick.cli", "hook", "scope-guard", "--runtime", "kiro"],
            input="not json", capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0

    def test_session_release_without_claims_is_silent(self):
        result = _run({"hook_event_name": "SessionEnd", "cwd": CWD}, handler="session-release")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# The generated hook command: only the block sentinel becomes Kiro's exit 2
# ---------------------------------------------------------------------------


def _run_wrapper(fake_cli_body: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run kiro_hook_command against a fake `maverick` on PATH (POSIX sh)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "maverick"
    fake.write_text("#!/bin/sh\n" + fake_cli_body + "\n")
    fake.chmod(0o755)
    return subprocess.run(
        ["/bin/sh", "-c", kiro_hook_command("scope-guard")],
        input="{}", capture_output=True, text=True, timeout=30,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
    )


class TestKiroHookCommandWrapper:
    def test_block_sentinel_becomes_exit_2(self, tmp_path):
        result = _run_wrapper(f'echo "blocked" >&2; exit {KIRO_BLOCK_EXIT}', tmp_path)
        assert result.returncode == 2
        assert "blocked" in result.stderr

    def test_allow_stays_0(self, tmp_path):
        assert _run_wrapper("exit 0", tmp_path).returncode == 0

    def test_old_cli_argparse_exit_2_fails_open(self, tmp_path):
        """An old CLI without `maverick hook` exits 2 — must not block."""
        assert _run_wrapper('echo "usage: maverick" >&2; exit 2', tmp_path).returncode == 0

    def test_missing_cli_fails_open(self, tmp_path):
        result = subprocess.run(
            ["/bin/sh", "-c", kiro_hook_command("scope-guard")],
            input="{}", capture_output=True, text=True, timeout=30,
            env={"PATH": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_stdin_reaches_cli(self, tmp_path):
        result = _run_wrapper(f'grep -q payload && exit {KIRO_BLOCK_EXIT}; exit 0', tmp_path)
        assert result.returncode == 0  # input was "{}", no "payload"


# ---------------------------------------------------------------------------
# Instance id: the innermost runtime's session wins
# ---------------------------------------------------------------------------


class TestKiroSessionId:
    def test_claims_prefer_kiro_session(self, tmp_path):
        """Kiro launched from Claude Code inherits CLAUDE_CODE_SESSION_ID."""
        both = {"KIRO_SESSION_ID": "sess_k", "CLAUDE_CODE_SESSION_ID": "claude"}
        kiro_only = {"KIRO_SESSION_ID": "sess_k"}
        missing = tmp_path / "none"
        assert claims.instance_id(both, missing) == claims.instance_id(kiro_only, missing)
        assert claims.instance_id(both, missing) != claims.instance_id(
            {"CLAUDE_CODE_SESSION_ID": "claude"}, missing
        )

    def test_coordinator_matches_hook_mirror(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.setenv("KIRO_SESSION_ID", "sess_k")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude")
        monkeypatch.setattr(coordinator, "_instance_id_path", lambda: tmp_path / "id")
        assert coordinator.runtime_session_id() == "sess_k"
        assert coordinator.instance_id() == claims.instance_id(
            {"KIRO_SESSION_ID": "sess_k"}, tmp_path / "none"
        )
        # Token reporting reads Claude transcripts: it must stay Claude-only.
        assert coordinator.claude_session_id() == "claude"


# ---------------------------------------------------------------------------
# maverick init --runtime kiro / clean
# ---------------------------------------------------------------------------


class TestKiroInit:
    def test_writes_hook_file_without_matchers(self, tmp_path):
        assert init.write_kiro_hooks(tmp_path)
        data = json.loads((tmp_path / init.KIRO_HOOKS_PATH).read_text())
        assert data["version"] == "v1"
        triggers = {h["trigger"]: h for h in data["hooks"]}
        assert set(triggers) == {"PreToolUse", "SessionEnd"}
        assert all("matcher" not in h for h in data["hooks"])
        assert triggers["PreToolUse"]["action"]["command"] == kiro_hook_command("scope-guard")

    def test_idempotent(self, tmp_path):
        assert init.write_kiro_hooks(tmp_path)
        assert not init.write_kiro_hooks(tmp_path)

    def test_foreign_file_left_untouched(self, tmp_path, capsys):
        path = tmp_path / init.KIRO_HOOKS_PATH
        path.parent.mkdir(parents=True)
        path.write_text('{"version": "v1", "hooks": [{"name": "mine"}]}')
        assert not init.write_kiro_hooks(tmp_path)
        assert "mine" in path.read_text()
        assert "not generated by Maverick" in capsys.readouterr().out

    def test_clean_removes_only_maverick_hooks(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        init.write_kiro_hooks(Path("."))
        other = Path(".kiro/hooks/other.json")
        other.write_text("{}")
        init.clean()
        assert not init.KIRO_HOOKS_PATH.exists()
        assert other.exists()

    def test_clean_leaves_foreign_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        init.KIRO_HOOKS_PATH.parent.mkdir(parents=True)
        init.KIRO_HOOKS_PATH.write_text('{"version": "v1", "hooks": [{"name": "mine"}]}')
        init.clean()
        assert init.KIRO_HOOKS_PATH.exists()

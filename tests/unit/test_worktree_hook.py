"""Tests for the worktree_post_create hook surface in maverick.worktree."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from maverick import worktree


def _write_config(root: Path, hook_rel: str) -> None:
    cfg_path = root / ".maverick" / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"hooks": {"worktree_post_create": hook_rel}}))


def _write_hook(
    root: Path, name: str, body: str, executable: bool = True
) -> Path:
    """Write *body* to ``<root>/<name>`` and return the path."""
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


class TestRunPostCreateHook:
    def test_no_hook_configured_is_a_noop(self, tmp_path: Path):
        wt = tmp_path / "wt"
        wt.mkdir()
        worktree._run_post_create_hook(tmp_path, wt, "feat/x", "main")

    def test_hook_receives_path_arg_and_env(self, tmp_path: Path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _write_hook(
            tmp_path,
            "scripts/hook.sh",
            "#!/bin/sh\n"
            "set -e\n"
            'echo "$1" > "$1/.hook-arg"\n'
            'env | grep ^MAVERICK_ | sort > "$1/.hook-env"\n',
        )
        _write_config(tmp_path, "scripts/hook.sh")

        worktree._run_post_create_hook(tmp_path, wt, "feat/x", "develop")

        assert (wt / ".hook-arg").read_text().strip() == str(wt)
        env_lines = (wt / ".hook-env").read_text().splitlines()
        assert f"MAVERICK_WORKTREE_PATH={wt}" in env_lines
        assert "MAVERICK_BRANCH=feat/x" in env_lines
        assert "MAVERICK_BASE_BRANCH=develop" in env_lines
        assert f"MAVERICK_REPO_ROOT={tmp_path}" in env_lines

    def test_missing_hook_file_raises(self, tmp_path: Path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _write_config(tmp_path, "scripts/does-not-exist.sh")
        with pytest.raises(RuntimeError, match="not found"):
            worktree._run_post_create_hook(tmp_path, wt, "b", "main")
        # worktree directory is intentionally left in place
        assert wt.exists()

    def test_non_executable_hook_raises(self, tmp_path: Path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _write_hook(
            tmp_path, "scripts/hook.sh", "#!/bin/sh\nexit 0\n", executable=False
        )
        _write_config(tmp_path, "scripts/hook.sh")
        with pytest.raises(RuntimeError, match="not executable"):
            worktree._run_post_create_hook(tmp_path, wt, "b", "main")
        assert wt.exists()

    def test_non_zero_exit_raises_with_exit_code(self, tmp_path: Path):
        wt = tmp_path / "wt"
        wt.mkdir()
        _write_hook(tmp_path, "scripts/hook.sh", "#!/bin/sh\nexit 7\n")
        _write_config(tmp_path, "scripts/hook.sh")
        with pytest.raises(RuntimeError, match=r"exit 7"):
            worktree._run_post_create_hook(tmp_path, wt, "b", "main")
        assert wt.exists()

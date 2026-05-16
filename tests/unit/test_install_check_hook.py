"""Tests for the SessionStart hook's stale-CLI warning branch.

The auto-install branch is exercised in practice and not covered here.
We focus on the new version-skew warning: it must surface drift to
stderr without aborting the session, and never raise.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "maverick" / "hooks" / "install_check.py"
)


@pytest.fixture
def hook_module():
    """Load the hook as an importable module despite its script layout."""
    spec = importlib.util.spec_from_file_location(
        "install_check_hook", HOOK_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_plugin(tmp_path: Path, version: str) -> Path:
    """Create a plugin layout under *tmp_path* with src/maverick/ available."""
    manifest_dir = tmp_path / ".claude-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": "maverick", "version": version})
    )
    # Point src/ at the real maverick package so version_check importable.
    real_src = Path(__file__).resolve().parents[2] / "src"
    src_link = tmp_path / "src"
    src_link.symlink_to(real_src, target_is_directory=True)
    return tmp_path


class TestWarnIfStale:
    def test_silent_when_ok(self, tmp_path, hook_module, capsys, monkeypatch):
        _write_plugin(tmp_path, "3.1.2-dev")
        from maverick import version_check

        monkeypatch.setattr(
            version_check,
            "check_cli_compatibility",
            lambda *_: version_check.CompatibilityResult(
                ok=True,
                reason="ok",
                installed_version="3.1.2-dev",
                required_version="3.1.2-dev",
                remediation="",
            ),
        )
        hook_module._warn_if_stale(str(tmp_path))
        assert capsys.readouterr().err == ""

    def test_prints_warning_when_stale(
        self, tmp_path, hook_module, capsys, monkeypatch
    ):
        _write_plugin(tmp_path, "3.1.2-dev")
        from maverick import version_check

        monkeypatch.setattr(
            version_check,
            "check_cli_compatibility",
            lambda *_: version_check.CompatibilityResult(
                ok=False,
                reason="cli_older",
                installed_version="2.0.1",
                required_version="3.1.2-dev",
                remediation=(
                    "Installed Maverick CLI v2.0.1 is older than plugin "
                    "v3.1.2-dev. Run /maverick:do-install to upgrade."
                ),
            ),
        )
        hook_module._warn_if_stale(str(tmp_path))
        err = capsys.readouterr().err
        assert "version skew" in err
        assert "v2.0.1" in err
        assert "/maverick:do-install" in err

    def test_swallows_internal_errors(
        self, tmp_path, hook_module, capsys, monkeypatch
    ):
        """A bug in version_check must never abort SessionStart."""
        _write_plugin(tmp_path, "3.1.2-dev")
        from maverick import version_check

        def explode(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(version_check, "check_cli_compatibility", explode)
        hook_module._warn_if_stale(str(tmp_path))
        # No raise; no warning printed because we swallowed the error.
        assert capsys.readouterr().err == ""

    def test_silent_when_module_missing(
        self, tmp_path, hook_module, capsys, monkeypatch
    ):
        """Older plugin checkouts without version_check.py: silent skip."""
        manifest_dir = tmp_path / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "maverick", "version": "1.0.0"})
        )
        # No src/ directory.
        # Also block the real maverick package so the inner import fails.
        with patch.dict(sys.modules, {"maverick.version_check": None}):
            hook_module._warn_if_stale(str(tmp_path))
        assert capsys.readouterr().err == ""

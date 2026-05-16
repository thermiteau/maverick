"""Tests for maverick.version_check — CLI vs plugin version reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from maverick import version_check

# ---------------------------------------------------------------------------
# parse_semver
# ---------------------------------------------------------------------------


class TestParseSemver:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("3.1.1", (3, 1, 1)),
            ("3.1", (3, 1, 0)),
            ("v3.1.1", (3, 1, 1)),
            ("3.1.2-dev", (3, 1, 2)),
            ("3.1.2.dev0", (3, 1, 2)),
            ("3.1.2.dev17", (3, 1, 2)),
            ("3.1.2dev", (3, 1, 2)),
            ("maverick 3.1.1", (3, 1, 1)),
            ("maverick 3.1.2-dev", (3, 1, 2)),
            ("  3.1.1  ", (3, 1, 1)),
        ],
    )
    def test_accepts(self, text: str, expected: tuple[int, int, int]):
        assert version_check.parse_semver(text) == expected

    @pytest.mark.parametrize(
        "text",
        ["", "garbage", "3", "x.y.z", "3.1.1.4.5", "3..1"],
    )
    def test_rejects(self, text: str):
        assert version_check.parse_semver(text) is None


# ---------------------------------------------------------------------------
# _is_compatible (private helper, but covers the comparison contract)
# ---------------------------------------------------------------------------


class TestIsCompatible:
    @pytest.mark.parametrize(
        "installed,required,expected",
        [
            # Same major+minor → ok regardless of patch.
            ((3, 1, 0), (3, 1, 0), True),
            ((3, 1, 5), (3, 1, 0), True),
            ((3, 1, 0), (3, 1, 5), True),
            # Installed minor > required minor → ok.
            ((3, 2, 0), (3, 1, 5), True),
            # Installed minor < required minor → not ok.
            ((3, 0, 99), (3, 1, 0), False),
            # Major mismatch (either direction) → not ok.
            ((2, 9, 9), (3, 0, 0), False),
            ((4, 0, 0), (3, 9, 9), False),
        ],
    )
    def test_matrix(self, installed, required, expected):
        assert version_check._is_compatible(installed, required) is expected


# ---------------------------------------------------------------------------
# check_cli_compatibility — end-to-end branches
# ---------------------------------------------------------------------------


def _make_plugin(tmp_path: Path, version: str) -> Path:
    """Create a minimal plugin root at *tmp_path* with the given version."""
    manifest_dir = tmp_path / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": "maverick", "version": version})
    )
    return tmp_path


class TestCheckCliCompatibility:
    def test_ok_when_versions_match(self, tmp_path: Path, monkeypatch):
        _make_plugin(tmp_path, "3.1.2-dev")

        def fake_which(name):
            return "/usr/bin/maverick" if name == "maverick" else None

        def fake_run(*_args, **_kwargs):
            return CompletedProcess(
                args=["maverick", "--version"],
                returncode=0,
                stdout="maverick 3.1.2-dev\n",
                stderr="",
            )

        monkeypatch.setattr(version_check.shutil, "which", fake_which)
        monkeypatch.setattr(version_check.subprocess, "run", fake_run)
        result = version_check.check_cli_compatibility(tmp_path)
        assert result.ok
        assert result.reason == "ok"
        # `_read_installed_cli_version` strips the `maverick` prog prefix.
        assert result.installed_version == "3.1.2-dev"
        assert result.required_version == "3.1.2-dev"
        assert result.remediation == ""

    def test_ok_when_installed_newer_minor(self, tmp_path: Path, monkeypatch):
        _make_plugin(tmp_path, "3.1.0")
        monkeypatch.setattr(
            version_check.shutil,
            "which",
            lambda name: "/usr/bin/maverick" if name == "maverick" else None,
        )
        monkeypatch.setattr(
            version_check.subprocess,
            "run",
            lambda *a, **k: CompletedProcess(
                args=["maverick", "--version"],
                returncode=0,
                stdout="maverick 3.5.0\n",
                stderr="",
            ),
        )
        result = version_check.check_cli_compatibility(tmp_path)
        assert result.ok and result.reason == "ok"

    def test_fails_when_installed_older(self, tmp_path: Path, monkeypatch):
        _make_plugin(tmp_path, "3.1.2-dev")
        monkeypatch.setattr(
            version_check.shutil,
            "which",
            lambda name: "/usr/bin/maverick" if name == "maverick" else None,
        )
        monkeypatch.setattr(
            version_check.subprocess,
            "run",
            lambda *a, **k: CompletedProcess(
                args=["maverick", "--version"],
                returncode=0,
                stdout="maverick 2.0.1\n",
                stderr="",
            ),
        )
        result = version_check.check_cli_compatibility(tmp_path)
        assert not result.ok
        assert result.reason == "cli_older"
        assert "v2.0.1" in result.remediation
        assert "v3.1.2-dev" in result.remediation
        assert "/maverick:do-install" in result.remediation

    def test_fails_when_cli_missing(self, tmp_path: Path, monkeypatch):
        _make_plugin(tmp_path, "3.1.2-dev")
        monkeypatch.setattr(version_check.shutil, "which", lambda name: None)
        result = version_check.check_cli_compatibility(tmp_path)
        assert not result.ok
        assert result.reason == "cli_missing"
        assert result.installed_version is None
        assert "/maverick:do-install" in result.remediation

    def test_passes_when_plugin_manifest_missing(self, tmp_path: Path, monkeypatch):
        """Defensive: if we can't read the plugin version, don't block work."""
        # No .claude-plugin/plugin.json written.
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "")
        result = version_check.check_cli_compatibility(tmp_path)
        # tmp_path doesn't look like a plugin root, so we fall through to
        # the walk-up resolution. The check defaults to ok on unreadable.
        assert result.reason in ("version_unreadable", "ok")

    def test_passes_when_plugin_version_malformed(
        self, tmp_path: Path, monkeypatch
    ):
        _make_plugin(tmp_path, "totally-not-a-version")
        monkeypatch.setattr(
            version_check.shutil,
            "which",
            lambda name: "/usr/bin/maverick" if name == "maverick" else None,
        )
        result = version_check.check_cli_compatibility(tmp_path)
        assert result.ok
        assert result.reason == "version_unreadable"

    def test_passes_when_cli_version_unparseable(
        self, tmp_path: Path, monkeypatch
    ):
        _make_plugin(tmp_path, "3.1.2")
        monkeypatch.setattr(
            version_check.shutil,
            "which",
            lambda name: "/usr/bin/maverick" if name == "maverick" else None,
        )
        monkeypatch.setattr(
            version_check.subprocess,
            "run",
            lambda *a, **k: CompletedProcess(
                args=["maverick", "--version"],
                returncode=0,
                stdout="custom build, no version\n",
                stderr="",
            ),
        )
        result = version_check.check_cli_compatibility(tmp_path)
        # Don't penalise a user who has a fork/dev build we can't parse.
        assert result.ok
        assert result.reason == "version_unreadable"

    def test_fails_as_missing_when_version_command_errors(
        self, tmp_path: Path, monkeypatch
    ):
        """A CLI on PATH whose `--version` exits non-zero is so broken
        that we treat it as missing — there's no version to compare
        against the plugin floor, and the remediation path is the same.
        """
        _make_plugin(tmp_path, "3.1.2")
        monkeypatch.setattr(
            version_check.shutil,
            "which",
            lambda name: "/usr/bin/maverick" if name == "maverick" else None,
        )
        monkeypatch.setattr(
            version_check.subprocess,
            "run",
            lambda *a, **k: CompletedProcess(
                args=["maverick", "--version"], returncode=1, stdout="", stderr=""
            ),
        )
        result = version_check.check_cli_compatibility(tmp_path)
        assert not result.ok
        assert result.reason == "cli_missing"
        assert "/maverick:do-install" in result.remediation


# ---------------------------------------------------------------------------
# resolve_plugin_root
# ---------------------------------------------------------------------------


class TestResolvePluginRoot:
    def test_explicit_arg_wins(self, tmp_path: Path, monkeypatch):
        _make_plugin(tmp_path, "1.0.0")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/somewhere/else")
        assert version_check.resolve_plugin_root(tmp_path) == tmp_path

    def test_env_var_used_when_no_explicit(self, tmp_path: Path, monkeypatch):
        _make_plugin(tmp_path, "1.0.0")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert version_check.resolve_plugin_root(None) == tmp_path

    def test_falls_through_to_walk_up(self, monkeypatch):
        """Without env or explicit arg, resolve walks up from __file__."""
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        result = version_check.resolve_plugin_root(None)
        # In this repo, the walk-up resolution does find a plugin root.
        assert result is not None
        assert (result / ".claude-plugin" / "plugin.json").exists()

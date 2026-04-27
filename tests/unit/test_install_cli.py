"""Tests for maverick.install_cli — install procedure and settings update."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick import install_cli
from maverick.install_cli import (
    InstallError,
    _check_plugin_root,
    _check_uv_available,
    update_settings_permission,
)


class TestCheckUvAvailable:
    def test_present(self):
        with patch.object(install_cli.shutil, "which", return_value="/usr/bin/uv"):
            _check_uv_available()  # no raise

    def test_missing(self):
        with patch.object(install_cli.shutil, "which", return_value=None):
            with pytest.raises(InstallError, match="uv is required"):
                _check_uv_available()


class TestCheckPluginRoot:
    def test_valid_root(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        _check_plugin_root(tmp_path)  # no raise

    def test_missing_pyproject(self, tmp_path: Path):
        with pytest.raises(InstallError, match="pyproject.toml not found"):
            _check_plugin_root(tmp_path)


class TestUpdateSettingsPermission:
    def test_creates_file_when_missing(self, tmp_path: Path):
        settings = tmp_path / "nested" / "settings.json"
        modified = update_settings_permission(settings, entry="Read(~/foo/**)")
        assert modified is True
        data = json.loads(settings.read_text())
        assert data == {
            "permissions": {
                "allow": ["Read(~/foo/**)"],
                "deny": [],
            }
        }

    def test_appends_to_existing_allow_list(self, tmp_path: Path):
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"permissions": {"allow": ["Existing(*)"], "deny": ["Bad(*)"]}}
            )
        )
        modified = update_settings_permission(settings, entry="Read(~/foo/**)")
        assert modified is True
        data = json.loads(settings.read_text())
        assert data["permissions"]["allow"] == ["Existing(*)", "Read(~/foo/**)"]
        assert data["permissions"]["deny"] == ["Bad(*)"]

    def test_idempotent_when_entry_present(self, tmp_path: Path):
        settings = tmp_path / "settings.json"
        original = {"permissions": {"allow": ["Read(~/foo/**)"], "deny": []}}
        settings.write_text(json.dumps(original))
        modified = update_settings_permission(settings, entry="Read(~/foo/**)")
        assert modified is False
        # File untouched
        assert json.loads(settings.read_text()) == original

    def test_preserves_other_top_level_keys(self, tmp_path: Path):
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps({"theme": "dark", "permissions": {"allow": []}})
        )
        update_settings_permission(settings, entry="Read(~/foo/**)")
        data = json.loads(settings.read_text())
        assert data["theme"] == "dark"
        assert data["permissions"]["allow"] == ["Read(~/foo/**)"]

    def test_writes_trailing_newline(self, tmp_path: Path):
        settings = tmp_path / "settings.json"
        update_settings_permission(settings, entry="Read(~/foo/**)")
        assert settings.read_text().endswith("\n")


class TestMain:
    def test_default_plugin_root_is_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        called_with: list[Path] = []

        def fake_install(root: Path) -> int:
            called_with.append(root)
            return 0

        monkeypatch.chdir(tmp_path)
        with patch.object(install_cli, "install", fake_install):
            rc = install_cli.main([])
        assert rc == 0
        assert called_with == [tmp_path.resolve()]

    def test_explicit_plugin_root(self, tmp_path: Path):
        called_with: list[Path] = []

        def fake_install(root: Path) -> int:
            called_with.append(root)
            return 0

        with patch.object(install_cli, "install", fake_install):
            rc = install_cli.main(["--plugin-root", str(tmp_path)])
        assert rc == 0
        assert called_with == [tmp_path.resolve()]

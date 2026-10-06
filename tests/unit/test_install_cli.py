"""Tests for maverick.install_cli — install procedure and settings update."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick import install_cli
from maverick.install_cli import (
    InstallError,
    _check_gh_available,
    _check_uv_available,
    install_spec,
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


class TestCheckGhAvailable:
    def test_present(self):
        with patch.object(install_cli.shutil, "which", return_value="/usr/bin/gh"):
            _check_gh_available()  # no raise

    def test_missing(self):
        with patch.object(install_cli.shutil, "which", return_value=None):
            with pytest.raises(InstallError, match="GitHub CLI"):
                _check_gh_available()

    def test_missing_message_mentions_gh_auth_login(self):
        with patch.object(install_cli.shutil, "which", return_value=None):
            with pytest.raises(InstallError) as excinfo:
                _check_gh_available()
        assert "gh auth login" in str(excinfo.value)


def _manifest(root: Path, version: str) -> None:
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))


class TestInstallSpec:
    def test_source_checkout_installs_from_path(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        _manifest(tmp_path, "4.1.0")
        assert install_spec(tmp_path) == str(tmp_path)

    def test_released_plugin_pins_pypi_version(self, tmp_path: Path):
        _manifest(tmp_path, "4.1.0")
        assert install_spec(tmp_path) == "maverick-harness==4.1.0"

    def test_v_prefix_stripped(self, tmp_path: Path):
        _manifest(tmp_path, "v4.1.0")
        assert install_spec(tmp_path) == "maverick-harness==4.1.0"

    def test_dev_plugin_without_source_refuses(self, tmp_path: Path):
        _manifest(tmp_path, "4.1.1-dev")
        with pytest.raises(InstallError, match="development build"):
            install_spec(tmp_path)

    def test_no_source_and_no_manifest_refuses(self, tmp_path: Path):
        with pytest.raises(InstallError, match="complete maverick plugin"):
            install_spec(tmp_path)


class TestLegacyTool:
    UV_LIST = "maverick v3.3.10-dev\n- maverick\nruff v0.8.0\n- ruff\n"

    def _uv(self, stdout: str):
        return patch.object(
            install_cli.subprocess, "run",
            return_value=install_cli.subprocess.CompletedProcess([], 0, stdout, ""),
        )

    def test_detects_legacy_tool(self):
        with self._uv(self.UV_LIST):
            assert install_cli._has_legacy_tool()

    def test_new_name_is_not_legacy(self):
        with self._uv("maverick-harness v4.1.0\n- maverick\n"):
            assert not install_cli._has_legacy_tool()

    def test_removed_before_install(self, tmp_path: Path):
        _manifest(tmp_path, "4.1.0")
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            out = self.UV_LIST if cmd[:3] == ["uv", "tool", "list"] else ""
            return install_cli.subprocess.CompletedProcess(cmd, 0, out, "")

        with (
            patch.object(install_cli, "_check_uv_available"),
            patch.object(install_cli, "_check_gh_available"),
            patch.object(install_cli, "_verify_on_path"),
            patch.object(install_cli, "update_settings_permission"),
            patch.object(install_cli.subprocess, "run", side_effect=fake_run),
        ):
            assert install_cli.install(tmp_path) == 0
        assert calls[1:] == [
            ["uv", "tool", "uninstall", "maverick"],
            ["uv", "tool", "install", "--force", "maverick-harness==4.1.0"],
        ]


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

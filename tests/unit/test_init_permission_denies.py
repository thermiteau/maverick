"""Tests for init's permission-deny writer (scope-guard second layer)."""

from __future__ import annotations

import json
from pathlib import Path

from maverick.init import (
    PERMISSION_DENY_RULES,
    _missing_permission_denies,
    write_permission_denies,
)


def _read_settings(project: Path) -> dict:
    return json.loads((project / ".claude" / "settings.json").read_text())


class TestWritePermissionDenies:
    def test_creates_settings_from_scratch(self, tmp_path: Path):
        assert write_permission_denies(tmp_path) is True
        deny = _read_settings(tmp_path)["permissions"]["deny"]
        assert list(PERMISSION_DENY_RULES) == deny

    def test_preserves_existing_content(self, tmp_path: Path):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(
            json.dumps(
                {
                    "env": {"FOO": "bar"},
                    "permissions": {"allow": ["Bash(ls*)"], "deny": ["WebFetch"]},
                }
            )
        )
        assert write_permission_denies(tmp_path) is True
        settings = _read_settings(tmp_path)
        assert settings["env"] == {"FOO": "bar"}
        assert settings["permissions"]["allow"] == ["Bash(ls*)"]
        assert settings["permissions"]["deny"][0] == "WebFetch"
        for rule in PERMISSION_DENY_RULES:
            assert rule in settings["permissions"]["deny"]

    def test_idempotent(self, tmp_path: Path):
        assert write_permission_denies(tmp_path) is True
        assert write_permission_denies(tmp_path) is False
        deny = _read_settings(tmp_path)["permissions"]["deny"]
        assert len(deny) == len(PERMISSION_DENY_RULES)

    def test_unparseable_settings_left_untouched(self, tmp_path: Path, capsys):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        original = "{invalid json"
        (settings_dir / "settings.json").write_text(original)
        assert write_permission_denies(tmp_path) is False
        assert (settings_dir / "settings.json").read_text() == original
        assert "Warning" in capsys.readouterr().out

    def test_non_object_settings_left_untouched(self, tmp_path: Path):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("[1, 2]")
        assert write_permission_denies(tmp_path) is False


class TestMissingPermissionDenies:
    def test_all_missing_when_no_settings(self, tmp_path: Path):
        assert _missing_permission_denies(tmp_path) == list(PERMISSION_DENY_RULES)

    def test_partial(self, tmp_path: Path):
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(
            json.dumps({"permissions": {"deny": [PERMISSION_DENY_RULES[0]]}})
        )
        missing = _missing_permission_denies(tmp_path)
        assert PERMISSION_DENY_RULES[0] not in missing
        assert len(missing) == len(PERMISSION_DENY_RULES) - 1

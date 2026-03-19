"""Tests for maverick.config — configuration loading and saving."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick import config


class TestLoadJson:
    def test_nonexistent_file(self, tmp_path: Path):
        result = config._load_json(tmp_path / "missing.json")
        assert result == {}

    def test_valid_json(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text('{"key": "value"}')
        result = config._load_json(f)
        assert result == {"key": "value"}

    def test_invalid_json(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("not json {{{")
        result = config._load_json(f)
        assert result == {}

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.json"
        f.write_text("")
        result = config._load_json(f)
        assert result == {}


class TestInitConfig:
    def test_project_config_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        project_dir = tmp_path / ".maverick"
        project_dir.mkdir()
        (project_dir / "config.json").write_text('{"source": "project"}')

        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", project_dir)
        result = config.init_config()
        assert result == {"source": "project"}

    def test_falls_back_to_system_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # No project config
        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", tmp_path / ".maverick")

        system_cfg = tmp_path / "system_config.json"
        system_cfg.write_text('{"source": "system"}')
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", system_cfg)

        result = config.init_config()
        assert result == {"source": "system"}

    def test_returns_empty_when_no_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", tmp_path / "no-project")
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", tmp_path / "no-system.json")
        result = config.init_config()
        assert result == {}


class TestSaveConfig:
    def test_creates_dir_and_writes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        cfg_dir = tmp_path / "new_dir"
        cfg_file = cfg_dir / "config.json"
        monkeypatch.setattr(config, "USER_CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", cfg_file)

        config.save_config({"aws_region": "us-east-1"})

        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text())
        assert data == {"aws_region": "us-east-1"}

    def test_overwrites_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        cfg_dir = tmp_path
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text('{"old": true}')
        monkeypatch.setattr(config, "USER_CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", cfg_file)

        config.save_config({"new": True})
        data = json.loads(cfg_file.read_text())
        assert data == {"new": True}

"""Tests for the integration-status block in .maverick/config.json.

Covers the schema helpers in maverick.config, the maverick.init writer,
and the maverick.integration_cli command handlers.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from maverick import config, integration_cli
from maverick import init as init_module


class TestSchemaDefaults:
    def test_all_milestones_default_false(self):
        defaults = config.CONFIG_DEFAULTS["integration"]
        assert defaults == {
            "init": False,
            "alignment": False,
            "upskill": False,
            "tech_docs_scaffolded": False,
            "code_review_workflow": False,
        }


class TestReadIntegrationStatus:
    def test_missing_file_returns_defaults(self, tmp_path: Path):
        status = config.read_integration_status(tmp_path / "missing.json")
        assert status == config.CONFIG_DEFAULTS["integration"]

    def test_file_without_integration_block(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"modules": ["python"]}))
        status = config.read_integration_status(path)
        assert status == config.CONFIG_DEFAULTS["integration"]

    def test_partial_integration_block(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"integration": {"init": True, "upskill": True}}))
        status = config.read_integration_status(path)
        assert status["init"] is True
        assert status["upskill"] is True
        assert status["alignment"] is False  # default for missing flag

    def test_unknown_keys_dropped(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps({"integration": {"init": True, "made_up_flag": True}})
        )
        status = config.read_integration_status(path)
        assert "made_up_flag" not in status
        assert status["init"] is True

    def test_non_bool_values_ignored(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"integration": {"init": "true"}}))
        status = config.read_integration_status(path)
        assert status["init"] is False  # string "true" is not bool


class TestWriteIntegrationStatus:
    def test_creates_file_when_missing(self, tmp_path: Path):
        path = tmp_path / "nested" / "config.json"
        config.write_integration_status(
            {
                "init": True,
                "alignment": False,
                "upskill": False,
                "tech_docs_scaffolded": False,
                "code_review_workflow": False,
            },
            path=path,
        )
        data = json.loads(path.read_text())
        assert data == {
            "integration": {
                "init": True,
                "alignment": False,
                "upskill": False,
                "tech_docs_scaffolded": False,
                "code_review_workflow": False,
            }
        }

    def test_preserves_other_top_level_keys(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps({"modules": ["python"], "platform": "linux"})
        )
        config.write_integration_status(
            config.CONFIG_DEFAULTS["integration"], path=path
        )
        data = json.loads(path.read_text())
        assert data["modules"] == ["python"]
        assert data["platform"] == "linux"
        assert "integration" in data


class TestSetIntegrationFlag:
    def test_flips_a_known_flag(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"modules": []}))
        config.set_integration_flag("upskill", True, path=path)
        data = json.loads(path.read_text())
        assert data["integration"]["upskill"] is True
        assert data["integration"]["init"] is False

    def test_idempotent(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"modules": []}))
        config.set_integration_flag("upskill", True, path=path)
        config.set_integration_flag("upskill", True, path=path)
        data = json.loads(path.read_text())
        assert data["integration"]["upskill"] is True

    def test_unknown_key_raises(self, tmp_path: Path):
        with pytest.raises(KeyError, match="unknown integration key"):
            config.set_integration_flag(
                "made_up_flag", True, path=tmp_path / "x.json"
            )


class TestInitWritesIntegrationBlock:
    def test_fresh_init_sets_init_true(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        args = Namespace(
            override=None,
            add=None,
            remove=None,
            platform=None,
            dry_run=False,
        )
        init_module.main(args)
        data = json.loads((tmp_path / ".maverick" / "config.json").read_text())
        assert data["integration"]["init"] is True
        assert data["integration"]["alignment"] is False
        assert data["integration"]["upskill"] is False

    def test_re_init_preserves_existing_flags(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".maverick"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps(
                {
                    "modules": ["python"],
                    "integration": {"init": True, "upskill": True},
                }
            )
        )
        args = Namespace(
            override=None,
            add=None,
            remove=None,
            platform=None,
            dry_run=False,
        )
        init_module.main(args)
        data = json.loads((cfg_dir / "config.json").read_text())
        assert data["integration"]["upskill"] is True  # preserved
        assert data["integration"]["init"] is True

    def test_dry_run_does_not_write(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = Namespace(
            override=None,
            add=None,
            remove=None,
            platform=None,
            dry_run=True,
        )
        init_module.main(args)
        assert not (tmp_path / ".maverick" / "config.json").exists()
        captured = capsys.readouterr()
        assert "integration" in captured.out


class TestIntegrationCliGet:
    def test_get_all_text(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".maverick"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"integration": {"init": True, "upskill": True}})
        )
        args = Namespace(integration_action="get", key=None, json=False)
        integration_cli.main(args)
        out = capsys.readouterr().out
        assert "[x] init" in out
        assert "[x] upskill" in out
        assert "[ ] alignment" in out

    def test_get_all_json(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".maverick"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({"integration": {"init": True}}))
        args = Namespace(integration_action="get", key=None, json=True)
        integration_cli.main(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["init"] is True
        assert data["upskill"] is False

    def test_get_single_key(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".maverick"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(
            json.dumps({"integration": {"upskill": True}})
        )
        args = Namespace(integration_action="get", key="upskill", json=False)
        integration_cli.main(args)
        assert capsys.readouterr().out.strip() == "true"

    def test_get_unknown_key_exits_2(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        args = Namespace(integration_action="get", key="nonsense", json=False)
        with pytest.raises(SystemExit) as e:
            integration_cli.main(args)
        assert e.value.code == 2


class TestIntegrationCliSet:
    def test_set_flips_flag(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".maverick"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({"modules": []}))
        args = Namespace(integration_action="set", key="upskill", value="true")
        integration_cli.main(args)
        data = json.loads((cfg_dir / "config.json").read_text())
        assert data["integration"]["upskill"] is True
        assert "upskill = true" in capsys.readouterr().out

    def test_set_without_init_exits_1(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = Namespace(integration_action="set", key="upskill", value="true")
        with pytest.raises(SystemExit) as e:
            integration_cli.main(args)
        assert e.value.code == 1
        assert "maverick init" in capsys.readouterr().err

    def test_set_unknown_key_exits_2(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".maverick"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({"modules": []}))
        args = Namespace(integration_action="set", key="nope", value="true")
        with pytest.raises(SystemExit) as e:
            integration_cli.main(args)
        assert e.value.code == 2

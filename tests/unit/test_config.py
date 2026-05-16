"""Tests for maverick.config — configuration loading, defaults, migration, and validation."""

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


class TestMigrateLegacy:
    def test_migrates_ec2_key_pair(self):
        raw: dict = {"aws": {"region": "us-east-1", "ec2_key_pair": "my-key"}}
        result = config._migrate_legacy(raw)
        assert result["aws"]["key_pair"] == "my-key"
        assert "ec2_key_pair" not in result["aws"]

    def test_migrates_ec2_security_group(self):
        raw: dict = {"aws": {"ec2_security_group": "sg-123"}}
        result = config._migrate_legacy(raw)
        assert result["aws"]["security_group"] == "sg-123"

    def test_migrates_parameter_store_arn_to_secret_arn(self):
        raw: dict = {"aws": {"parameter_store_arn": "arn:aws:secretsmanager:..."}}
        result = config._migrate_legacy(raw)
        assert result["aws"]["secret_arn"] == "arn:aws:secretsmanager:..."

    def test_migrates_ec2_instance_type_to_instance_section(self):
        raw: dict = {"aws": {"ec2_instance_type": "t3.large"}}
        result = config._migrate_legacy(raw)
        assert result["instance"]["type"] == "t3.large"
        assert "ec2_instance_type" not in result["aws"]

    def test_migrates_ec2_ssm_parameter_to_ami_section(self):
        raw: dict = {"aws": {"ec2_ssm_parameter": "/custom/param"}}
        result = config._migrate_legacy(raw)
        assert result["ami"]["ssm_parameter"] == "/custom/param"

    def test_migrates_ec2_description_to_ami_section(self):
        raw: dict = {"aws": {"ec2_description": "My AMI"}}
        result = config._migrate_legacy(raw)
        assert result["ami"]["description"] == "My AMI"

    def test_does_not_overwrite_existing_new_key(self):
        raw: dict = {"aws": {"key_pair": "existing", "ec2_key_pair": "legacy"}}
        result = config._migrate_legacy(raw)
        assert result["aws"]["key_pair"] == "existing"

    def test_skips_empty_legacy_values(self):
        raw: dict = {"aws": {"ec2_key_pair": ""}}
        config._migrate_legacy(raw)
        assert "key_pair" not in raw["aws"]

    def test_noop_on_current_schema(self):
        raw: dict = {"aws": {"region": "us-east-1", "key_pair": "my-key"}}
        original = json.dumps(raw)
        config._migrate_legacy(raw)
        assert json.dumps(raw) == original


class TestHasUnknownKeys:
    def test_no_unknowns_on_clean_config(self):
        cfg = dict(config.CONFIG_DEFAULTS)
        assert config._has_unknown_keys(cfg) == []

    def test_detects_sqs_keys(self):
        raw: dict = {"aws": {"region": "us-east-1", "sqs_queue_url": "https://..."}}
        unknown = config._has_unknown_keys(raw)
        assert "aws.sqs_queue_url" in unknown

    def test_detects_multiple_unknowns(self):
        raw: dict = {"aws": {"sqs_queue_url": "", "sqs_visibility_timeout": 3600}}
        unknown = config._has_unknown_keys(raw)
        assert len(unknown) == 2

    def test_ignores_extra_top_level_keys(self):
        raw: dict = {"custom_section": {"anything": True}}
        unknown = config._has_unknown_keys(raw)
        assert unknown == []


class TestApplyDefaults:
    def test_empty_input_returns_full_defaults(self):
        result = config._apply_defaults({})
        assert result == config.CONFIG_DEFAULTS

    def test_user_values_override_defaults(self):
        raw: dict = {"aws": {"region": "eu-west-1", "key_pair": "my-key"}}
        result = config._apply_defaults(raw)
        assert result["aws"]["region"] == "eu-west-1"
        assert result["aws"]["key_pair"] == "my-key"
        assert result["aws"]["security_group"] == ""
        assert result["aws"]["iam_profile"] == ""

    def test_other_sections_get_defaults(self):
        raw: dict = {"aws": {"region": "us-west-2"}}
        result = config._apply_defaults(raw)
        assert result["worker"]["webhook_label"] == "claude-do"
        assert result["instance"]["type"] == "t3.medium"
        assert result["ami"]["ssm_parameter"] == config._DEFAULT_SSM_PARAMETER

    def test_unknown_keys_in_section_are_dropped(self):
        raw: dict = {"aws": {"region": "us-east-1", "sqs_queue_url": "https://..."}}
        result = config._apply_defaults(raw)
        assert "sqs_queue_url" not in result["aws"]

    def test_user_section_values_not_clobbered(self):
        raw: dict = {"worker": {"webhook_label": "custom-label"}}
        result = config._apply_defaults(raw)
        assert result["worker"]["webhook_label"] == "custom-label"
        assert result["worker"]["cloudwatch_log_group"] == "/maverick/worker"


class TestValidateConfig:
    def test_valid_config_no_errors(self):
        cfg = config._apply_defaults({"aws": {"region": "us-east-1"}})
        errors = config.validate_config(cfg)
        assert errors == []

    def test_missing_region_is_error(self):
        cfg = config._apply_defaults({"aws": {"region": ""}})
        errors = config.validate_config(cfg)
        assert any("aws.region" in e for e in errors)

    def test_skip_aws_validation(self):
        cfg = config._apply_defaults({})
        errors = config.validate_config(cfg, require_aws=False)
        assert errors == []

    def test_invalid_max_attempts_type(self):
        cfg = config._apply_defaults({})
        cfg["queue"]["max_attempts"] = "not-an-int"  # type: ignore[typeddict-item]
        errors = config.validate_config(cfg, require_aws=False)
        assert any("queue.max_attempts" in e for e in errors)

    def test_default_close_policy_is_valid(self):
        cfg = config._apply_defaults({})
        assert cfg["issue_lifecycle"]["close_policy"] == "on_pr_merge"
        errors = config.validate_config(cfg, require_aws=False)
        assert all("issue_lifecycle" not in e for e in errors)

    def test_recognised_close_policies(self):
        for policy in config.ISSUE_CLOSE_POLICIES:
            cfg = config._apply_defaults({"issue_lifecycle": {"close_policy": policy}})
            errors = config.validate_config(cfg, require_aws=False)
            assert all("issue_lifecycle" not in e for e in errors), (
                f"valid policy {policy!r} flagged as error: {errors}"
            )

    def test_unknown_close_policy_is_error(self):
        cfg = config._apply_defaults({})
        cfg["issue_lifecycle"]["close_policy"] = "on_full_moon"  # type: ignore[typeddict-item]
        errors = config.validate_config(cfg, require_aws=False)
        assert any("issue_lifecycle.close_policy" in e for e in errors)


class TestLoadAndHeal:
    def test_clean_config_unchanged(self, tmp_path: Path):
        f = tmp_path / "config.json"
        data = {"aws": {"region": "us-east-1", "key_pair": "my-key"}}
        f.write_text(json.dumps(data))
        result = config._load_and_heal(f)
        assert result["aws"]["region"] == "us-east-1"
        assert not (tmp_path / "config.json.bak").exists()

    def test_legacy_config_backed_up_and_replaced(self, tmp_path: Path):
        f = tmp_path / "config.json"
        legacy = {
            "aws": {
                "region": "us-east-1",
                "ec2_key_pair": "old-key",
                "ec2_security_group": "sg-old",
                "sqs_queue_url": "https://sqs...",
                "sqs_visibility_timeout": 3600,
            },
            "worker": {"webhook_label": "custom"},
        }
        f.write_text(json.dumps(legacy))

        result = config._load_and_heal(f)

        # Backup created
        bak = tmp_path / "config.json.bak"
        assert bak.exists()
        bak_data = json.loads(bak.read_text())
        assert "sqs_queue_url" in bak_data["aws"]

        # New file is clean
        new_data = json.loads(f.read_text())
        assert "sqs_queue_url" not in new_data["aws"]

        # Migrated values preserved
        assert result["aws"]["key_pair"] == "old-key"
        assert result["aws"]["security_group"] == "sg-old"
        assert result["aws"]["region"] == "us-east-1"
        assert result["worker"]["webhook_label"] == "custom"

    def test_multiple_backups_dont_clobber(self, tmp_path: Path):
        f = tmp_path / "config.json"
        legacy = {"aws": {"sqs_queue_url": "old"}}

        # Create first backup
        (tmp_path / "config.json.bak").write_text("{}")

        f.write_text(json.dumps(legacy))
        config._load_and_heal(f)

        assert (tmp_path / "config.json.bak").exists()
        assert (tmp_path / "config.json.bak.1").exists()

    def test_nonexistent_file_returns_empty(self, tmp_path: Path):
        result = config._load_and_heal(tmp_path / "missing.json")
        assert result == {}


class TestInitConfig:
    def test_project_config_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        project_dir = tmp_path / ".maverick"
        project_dir.mkdir()
        (project_dir / "config.json").write_text(
            '{"aws": {"region": "ap-southeast-1", "key_pair": "project-key"}}'
        )
        # System config has a different region — should be ignored
        system_cfg = tmp_path / "system_config.json"
        system_cfg.write_text('{"aws": {"region": "eu-west-1"}}')
        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", project_dir)
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", system_cfg)

        result = config.init_config()
        assert result["aws"]["region"] == "ap-southeast-1"
        assert result["aws"]["key_pair"] == "project-key"
        assert result["worker"]["webhook_label"] == "claude-do"

    def test_falls_back_to_system_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", tmp_path / ".maverick")
        system_cfg = tmp_path / "system_config.json"
        system_cfg.write_text('{"aws": {"region": "eu-west-1", "key_pair": "system-key"}}')
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", system_cfg)

        result = config.init_config()
        assert result["aws"]["region"] == "eu-west-1"
        assert result["aws"]["key_pair"] == "system-key"

    def test_defaults_when_no_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", tmp_path / "no-project")
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", tmp_path / "no-system.json")
        result = config.init_config()
        assert result == config.CONFIG_DEFAULTS

    def test_legacy_system_config_healed_on_load(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(config, "PROJECT_CONFIG_DIR", tmp_path / "no-project")
        system_cfg = tmp_path / "config.json"
        legacy = {
            "aws": {
                "region": "us-west-2",
                "ec2_key_pair": "migrated-key",
                "sqs_queue_url": "https://old",
            },
        }
        system_cfg.write_text(json.dumps(legacy))
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", system_cfg)

        result = config.init_config()
        assert result["aws"]["region"] == "us-west-2"
        assert result["aws"]["key_pair"] == "migrated-key"
        assert "sqs_queue_url" not in result["aws"]
        # Backup was created
        assert (tmp_path / "config.json.bak").exists()


class TestGitWorkflowConfig:
    """Tests for the git_workflow config section."""

    def test_defaults_present(self):
        cfg = config._apply_defaults({})
        gw = cfg["git_workflow"]
        assert gw["story_base"] == "main"
        assert gw["pr_target"] == "main"
        assert gw["promotion_chain"] == ["main"]
        assert isinstance(gw["branch_prefixes"], dict)
        assert gw["branch_prefixes"]["bug"] == "fix"
        assert gw["branch_prefixes"]["enhancement"] == "feat"

    def test_user_overrides(self):
        raw: dict = {"git_workflow": {"story_base": "develop", "pr_target": "develop"}}
        result = config._apply_defaults(raw)
        assert result["git_workflow"]["story_base"] == "develop"
        assert result["git_workflow"]["pr_target"] == "develop"

    def test_partial_override_fills_defaults(self):
        raw: dict = {"git_workflow": {"story_base": "develop"}}
        result = config._apply_defaults(raw)
        assert result["git_workflow"]["story_base"] == "develop"
        assert result["git_workflow"]["pr_target"] == "main"

    def test_promotion_chain_override(self):
        raw: dict = {
            "git_workflow": {
                "promotion_chain": ["develop", "staging", "main"],
            }
        }
        result = config._apply_defaults(raw)
        assert result["git_workflow"]["promotion_chain"] == ["develop", "staging", "main"]

    def test_branch_prefixes_override(self):
        raw: dict = {
            "git_workflow": {
                "branch_prefixes": {"bug": "bugfix", "feature": "feature"},
            }
        }
        result = config._apply_defaults(raw)
        assert result["git_workflow"]["branch_prefixes"]["bug"] == "bugfix"

    def test_validation_empty_story_base(self):
        cfg = config._apply_defaults({})
        cfg["git_workflow"]["story_base"] = ""
        errors = config.validate_config(cfg, require_aws=False)
        assert any("git_workflow.story_base" in e for e in errors)

    def test_validation_empty_pr_target(self):
        cfg = config._apply_defaults({})
        cfg["git_workflow"]["pr_target"] = ""
        errors = config.validate_config(cfg, require_aws=False)
        assert any("git_workflow.pr_target" in e for e in errors)

    def test_validation_invalid_promotion_chain(self):
        cfg = config._apply_defaults({})
        cfg["git_workflow"]["promotion_chain"] = "not-a-list"
        errors = config.validate_config(cfg, require_aws=False)
        assert any("promotion_chain" in e for e in errors)

    def test_validation_invalid_branch_prefixes(self):
        cfg = config._apply_defaults({})
        cfg["git_workflow"]["branch_prefixes"] = "not-a-dict"
        errors = config.validate_config(cfg, require_aws=False)
        assert any("branch_prefixes" in e for e in errors)

    def test_validation_valid_git_workflow(self):
        cfg = config._apply_defaults({
            "git_workflow": {
                "story_base": "develop",
                "pr_target": "develop",
                "promotion_chain": ["develop", "main"],
                "branch_prefixes": {"bug": "fix"},
            }
        })
        errors = config.validate_config(cfg, require_aws=False)
        assert all("git_workflow" not in e for e in errors)


class TestSaveConfig:
    def test_creates_dir_and_writes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        cfg_dir = tmp_path / "new_dir"
        cfg_file = cfg_dir / "config.json"
        monkeypatch.setattr(config, "USER_CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", cfg_file)

        config.save_config({"aws_region": "us-east-1"})  # type: ignore[typeddict-item]

        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text())
        assert data == {"aws_region": "us-east-1"}

    def test_overwrites_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        cfg_dir = tmp_path
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text('{"old": true}')
        monkeypatch.setattr(config, "USER_CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config, "SYSTEM_CONFIG_FILE", cfg_file)

        config.save_config({"new": True})  # type: ignore[typeddict-item]
        data = json.loads(cfg_file.read_text())
        assert data == {"new": True}

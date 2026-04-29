"""Tests for maverick.preflight — prereq evaluation and CLI handler."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from subprocess import CompletedProcess

from maverick import preflight, preflight_cli

# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------


class TestEvaluateBootstrap:
    """Bootstrap skills are exempt — they produce prerequisites, can't require them.

    do-init is *not* in this set: it requires `gh_app_configured` so users
    are forced to set up the GitHub App before any maverick automation runs.
    """

    def test_do_install_passes_with_no_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = preflight.evaluate("do-install")
        assert result.passed

    def test_do_init_requires_gh_app(self, tmp_path: Path, monkeypatch):
        """do-init must not pass when the GitHub App is unconfigured."""
        monkeypatch.chdir(tmp_path)
        with patch.dict(
            preflight.RUNTIME_CHECKS,
            {"gh_app_configured": lambda: (False, "App missing")},
            clear=False,
        ):
            result = preflight.evaluate("do-init")
        assert not result.passed
        assert ("gh_app_configured", "App missing") in result.failing_runtime

    def test_do_init_passes_when_gh_app_configured(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        with patch.dict(
            preflight.RUNTIME_CHECKS,
            {"gh_app_configured": lambda: (True, "")},
            clear=False,
        ):
            result = preflight.evaluate("do-init")
        assert result.passed


class TestEvaluateUnknownSkill:
    def test_unknown_skill_marked(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = preflight.evaluate("does-not-exist")
        assert result.unknown_skill
        assert not result.passed


class TestEvaluateFlagChecks:
    def test_missing_init_flag_fails(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No .maverick/config.json -> all flags default false
        with patch.object(preflight.shutil, "which", return_value="/usr/bin/x"):
            with patch.dict(preflight.RUNTIME_CHECKS, {}, clear=False):
                # Stub all runtime checks to "ok" so we isolate flag failures
                for name in list(preflight.RUNTIME_CHECKS):
                    preflight.RUNTIME_CHECKS[name] = lambda: (True, "")
                result = preflight.evaluate("do-upskill")
        assert "init" in result.missing_flags
        assert not result.passed

    def test_all_flags_set_passes_flag_check(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / ".maverick"
        cfg.mkdir()
        (cfg / "config.json").write_text(
            json.dumps({"integration": {"init": True}})
        )
        with patch.object(preflight.shutil, "which", return_value="/usr/bin/x"):
            result = preflight.evaluate("do-upskill")
        assert not result.missing_flags


class TestEvaluateToolChecks:
    def test_missing_tool_recorded(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / ".maverick"
        cfg.mkdir()
        (cfg / "config.json").write_text(
            json.dumps({"integration": {"init": True}})
        )

        def fake_which(name):
            return None  # nothing on PATH

        with patch.object(preflight.shutil, "which", side_effect=fake_which):
            result = preflight.evaluate("do-upskill")
        assert "uv" in result.missing_tools

    def test_present_tool_does_not_appear(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / ".maverick"
        cfg.mkdir()
        (cfg / "config.json").write_text(
            json.dumps({"integration": {"init": True}})
        )
        with patch.object(preflight.shutil, "which", return_value="/usr/bin/uv"):
            result = preflight.evaluate("do-upskill")
        assert result.missing_tools == []


class TestEvaluateRuntimeChecks:
    def test_failing_runtime_check_recorded(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / ".maverick"
        cfg.mkdir()
        (cfg / "config.json").write_text(
            json.dumps(
                {
                    "integration": {
                        "init": True,
                        "code_review_workflow": True,
                    }
                }
            )
        )

        with patch.object(preflight.shutil, "which", return_value="/usr/bin/x"):
            with patch.dict(
                preflight.RUNTIME_CHECKS,
                {
                    "gh_app_configured": lambda: (False, "bot says no"),
                    "worktrees_enabled": lambda: (True, ""),
                },
                clear=True,
            ):
                result = preflight.evaluate("do-issue-solo")
        assert ("gh_app_configured", "bot says no") in result.failing_runtime
        assert not result.passed

    def test_all_passing(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / ".maverick"
        cfg.mkdir()
        (cfg / "config.json").write_text(
            json.dumps(
                {
                    "integration": {
                        "init": True,
                        "code_review_workflow": True,
                    }
                }
            )
        )
        with patch.object(preflight.shutil, "which", return_value="/usr/bin/x"):
            with patch.dict(
                preflight.RUNTIME_CHECKS,
                {
                    "gh_app_configured": lambda: (True, ""),
                    "worktrees_enabled": lambda: (True, ""),
                },
                clear=True,
            ):
                result = preflight.evaluate("do-issue-solo")
        assert result.passed


# ---------------------------------------------------------------------------
# render_human()
# ---------------------------------------------------------------------------


class TestRenderHuman:
    def test_passing_message(self):
        result = preflight.PreflightResult(skill="do-upskill")
        assert "OK" in preflight.render_human(result)

    def test_unknown_skill_message(self):
        result = preflight.PreflightResult(skill="does-not-exist", unknown_skill=True)
        assert "no declared prerequisites" in preflight.render_human(result)

    def test_missing_flags_listed(self):
        result = preflight.PreflightResult(
            skill="do-upskill", missing_flags=["init"]
        )
        text = preflight.render_human(result)
        assert "Missing integration flags" in text
        assert "init" in text

    def test_missing_flag_includes_remediation(self):
        """Each missing flag is rendered with its FLAG_REMEDIATION entry.

        code_review_workflow is no longer a hard prereq for any skill, but
        the remediation entry still has to exist (TestPrereqsTableConsistency
        enforces that), and it must read sensibly when surfaced.
        """
        result = preflight.PreflightResult(
            skill="do-issue-solo",
            missing_flags=["code_review_workflow"],
        )
        text = preflight.render_human(result)
        assert "code_review_workflow" in text
        # New remediation text points users at the optional-gate skill rather
        # than do-init, since do-init no longer scaffolds the workflow.
        assert "code-review.yml" in text

    def test_missing_flag_with_no_remediation_falls_back(self, monkeypatch):
        """Defensive: a flag without an entry doesn't crash render."""
        monkeypatch.setitem(preflight.FLAG_REMEDIATION, "init", "Run /maverick:do-init")
        result = preflight.PreflightResult(
            skill="do-upskill", missing_flags=["__synthetic_no_remedy__"]
        )
        text = preflight.render_human(result)
        assert "no remediation registered" in text

    def test_missing_tools_listed(self):
        result = preflight.PreflightResult(
            skill="do-upskill", missing_tools=["gh"]
        )
        text = preflight.render_human(result)
        assert "Missing PATH tools" in text
        assert "gh" in text

    def test_runtime_failures_listed(self):
        result = preflight.PreflightResult(
            skill="do-epic", failing_runtime=[("gh_app_configured", "no token")]
        )
        text = preflight.render_human(result)
        assert "Failing runtime checks" in text
        assert "gh_app_configured" in text
        assert "no token" in text


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------


class TestPreflightCli:
    def test_passing_skill_returns_0(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        # do-install is a true bootstrap skill (no prereqs); always passes.
        rc = preflight_cli.main(Namespace(skill="do-install", json=False))
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_unknown_skill_returns_2(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        rc = preflight_cli.main(Namespace(skill="nope", json=False))
        assert rc == 2
        assert "no declared prerequisites" in capsys.readouterr().err

    def test_failing_skill_returns_1(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        # do-upskill needs init=true, project has no config -> fails
        with patch.object(preflight.shutil, "which", return_value="/usr/bin/x"):
            rc = preflight_cli.main(Namespace(skill="do-upskill", json=False))
        assert rc == 1
        assert "init" in capsys.readouterr().err

    def test_json_output(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        rc = preflight_cli.main(Namespace(skill="do-install", json=True))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["passed"] is True
        assert data["skill"] == "do-install"


# ---------------------------------------------------------------------------
# Schema sanity — every flag in PREREQS must be a real integration flag
# ---------------------------------------------------------------------------


class TestPrereqsTableConsistency:
    def test_all_flags_are_known(self):
        from maverick.config import CONFIG_DEFAULTS

        valid = set(CONFIG_DEFAULTS["integration"].keys())
        for skill, prereqs in preflight.PREREQS.items():
            for flag in prereqs.flags:
                assert flag in valid, (
                    f"PREREQS[{skill!r}] references unknown integration "
                    f"flag {flag!r}; valid: {sorted(valid)}"
                )

    def test_all_runtime_checks_are_registered(self):
        for skill, prereqs in preflight.PREREQS.items():
            for name in prereqs.runtime:
                assert name in preflight.RUNTIME_CHECKS, (
                    f"PREREQS[{skill!r}] references runtime check "
                    f"{name!r} which is not registered in RUNTIME_CHECKS"
                )

    def test_check_gh_app_configured_parses_real_json(self, monkeypatch):
        """Regression: the runtime check must parse the JSON output of
        `maverick gh-app status`, not substring-match. The JSON shape
        emits `"configured": true` with quotes around the key — earlier
        code looked for the literal needle `configured: true`, which
        never matched and made do-issue-solo / do-epic / do-init
        impossible to preflight-pass.
        """
        real_output = json.dumps(
            {"app_id": 1, "configured": True, "installation_id": 2}, indent=2
        )

        def fake_run(*args, **kwargs):
            return CompletedProcess(
                args=args[0], returncode=0, stdout=real_output, stderr=""
            )

        monkeypatch.setattr(preflight.subprocess, "run", fake_run)
        ok, msg = preflight._check_gh_app_configured()
        assert ok, f"expected pass; got fail with message: {msg}"

    def test_check_gh_app_configured_fails_on_configured_false(self, monkeypatch):
        real_output = json.dumps(
            {"configured": False, "reason": "no config at /x"}, indent=2
        )

        def fake_run(*args, **kwargs):
            return CompletedProcess(
                args=args[0], returncode=0, stdout=real_output, stderr=""
            )

        monkeypatch.setattr(preflight.subprocess, "run", fake_run)
        ok, _ = preflight._check_gh_app_configured()
        assert ok is False

    def test_check_gh_app_configured_fails_on_malformed_stdout(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return CompletedProcess(
                args=args[0], returncode=0, stdout="not json at all", stderr=""
            )

        monkeypatch.setattr(preflight.subprocess, "run", fake_run)
        ok, _ = preflight._check_gh_app_configured()
        assert ok is False

    def test_every_integration_flag_has_remediation(self):
        """FLAG_REMEDIATION must cover every flag that can appear in a missing list."""
        from maverick.config import CONFIG_DEFAULTS

        flags = set(CONFIG_DEFAULTS["integration"].keys())
        missing = flags - set(preflight.FLAG_REMEDIATION.keys())
        assert not missing, (
            f"FLAG_REMEDIATION is missing entries for: {sorted(missing)}"
        )

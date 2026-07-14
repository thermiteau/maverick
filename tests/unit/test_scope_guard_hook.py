"""Tests for the PreToolUse scope-guard hook.

The guard is the mechanical layer of mav-scope-boundaries: rule hits ask
in interactive sessions, deny in autonomous mode, and production patterns
deny everywhere. It must fail open on anything it does not understand.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HOOK_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "maverick" / "hooks" / "scope_guard.py"
)


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("scope_guard_hook", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses resolve `from __future__ import
    # annotations` types via sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def _bash(command: str, cwd: str = ".") -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}


def _edit(path: str, cwd: str = ".") -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": cwd}


# ---------------------------------------------------------------------------
# Destructive git
# ---------------------------------------------------------------------------


class TestDestructiveGit:
    @pytest.mark.parametrize(
        "command",
        [
            "git push --force origin feat/x",
            "git push -f",
            "git push origin --force feat/x",
            "cd /tmp && git push --force",
            "GIT_TRACE=1 git push -f origin feat/x",
            "git -C /repo push --force",
            "git push --force-with-lease",
            "git push --mirror backup",
            "git push origin --delete old-branch",
            "git push origin :dead-branch",
            "git reset --hard HEAD~3",
            "git branch -D feature",
            "git clean -fd",
            "git checkout .",
            "git checkout -- .",
            "git restore .",
            "git filter-branch --tree-filter 'rm -f secrets'",
        ],
    )
    def test_hits(self, guard, command):
        verdict = guard.decide(_bash(command))
        assert verdict.decision == guard.ASK, command

    @pytest.mark.parametrize(
        "command",
        [
            "git push origin feat/42-export",
            "git push --force-if-includes-not-a-thing",  # not a recognized flag combo
            "git status",
            "git branch -d merged-branch",
            "git checkout feat/42",
            "git restore src/app.py",
            "git clean -n",
            "git log --oneline -5",
            "echo 'git push --force' > notes.md || true",  # not a git invocation
            "grep -r 'git reset --hard' docs/",
        ],
    )
    def test_safe_commands_pass(self, guard, command):
        verdict = guard.decide(_bash(command))
        # None of these are git invocations of a destructive form; infra/write
        # rules may still fire for redirects, so only assert not a git hit.
        assert "history" not in verdict.reason
        assert "irreversib" not in verdict.reason

    def test_compound_command_second_position(self, guard):
        verdict = guard.decide(_bash("make test && git push --force origin x"))
        assert verdict.decision == guard.ASK


class TestProtectedBranches:
    def test_commit_on_protected_branch(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "main")
        verdict = guard.decide(_bash("git commit -m 'x'"))
        assert verdict.decision == guard.ASK
        assert "protected branch 'main'" in verdict.reason

    def test_commit_on_feature_branch(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "feat/42-x")
        verdict = guard.decide(_bash("git commit -m 'x'"))
        assert verdict.decision == guard.ALLOW

    def test_push_refspec_targeting_protected(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "feat/42-x")
        verdict = guard.decide(_bash("git push origin feat/42-x:stable"))
        assert verdict.decision == guard.ASK
        assert "stable" in verdict.reason

    def test_push_positional_protected(self, guard, monkeypatch):
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "feat/42-x")
        verdict = guard.decide(_bash("git push origin main"))
        assert verdict.decision == guard.ASK

    def test_custom_protected_list(self, guard, tmp_path, monkeypatch):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "config.json").write_text(
            json.dumps({"scope_guards": {"protected_branches": ["develop"]}})
        )
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "develop")
        verdict = guard.decide(_bash("git commit -m x", cwd=str(tmp_path)))
        assert verdict.decision == guard.ASK
        # main is no longer protected when the project overrides the list
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "main")
        verdict = guard.decide(_bash("git commit -m x", cwd=str(tmp_path)))
        assert verdict.decision == guard.ALLOW


# ---------------------------------------------------------------------------
# Infrastructure paths
# ---------------------------------------------------------------------------


class TestInfraPaths:
    @pytest.mark.parametrize(
        "path",
        [
            ".github/workflows/ci.yml",
            "Dockerfile",
            "Dockerfile.prod",
            "docker-compose.yml",
            "infra/main.tf",
            "vars/prod.tfvars",
            "infra/maverick-vpc.template.json",
            "k8s/deployment.yaml",
            "helm/values.yaml",
            ".gitlab-ci.yml",
            "azure-pipelines.yml",
            "Jenkinsfile",
        ],
    )
    def test_infra_edit_hits(self, guard, path):
        verdict = guard.decide(_edit(path))
        assert verdict.decision == guard.ASK, path
        assert "infrastructure" in verdict.reason

    @pytest.mark.parametrize(
        "path",
        [
            "src/app.py",
            "docs/dockerfiles.md",
            "README.md",
            "terraform.md",
            "src/k8s_client.py",
        ],
    )
    def test_normal_edit_passes(self, guard, path):
        assert guard.decide(_edit(path)).decision == guard.ALLOW, path

    def test_bash_write_to_infra_path_hits(self, guard):
        verdict = guard.decide(_bash("cat config > .github/workflows/deploy.yml"))
        assert verdict.decision == guard.ASK

    def test_bash_read_of_infra_path_passes(self, guard):
        verdict = guard.decide(_bash("cat .github/workflows/ci.yml"))
        assert verdict.decision == guard.ALLOW


# ---------------------------------------------------------------------------
# Production patterns
# ---------------------------------------------------------------------------


class TestProductionPatterns:
    def test_builtin_aws_profile(self, guard):
        verdict = guard.decide(_bash("AWS_PROFILE=prod aws s3 ls"))
        assert verdict.decision == guard.DENY
        assert verdict.always_deny

    def test_project_pattern_in_command(self, guard, tmp_path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "config.json").write_text(
            json.dumps({"scope_guards": {"production_patterns": ["db.prod.acme.com"]}})
        )
        verdict = guard.decide(
            _bash("psql -h db.prod.acme.com -c 'select 1'", cwd=str(tmp_path))
        )
        assert verdict.decision == guard.DENY
        assert verdict.always_deny

    def test_project_regex_pattern_in_webfetch(self, guard, tmp_path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "config.json").write_text(
            json.dumps({"scope_guards": {"production_patterns": ["re:api\\.acme\\.com"]}})
        )
        payload = {
            "tool_name": "WebFetch",
            "tool_input": {"url": "https://api.acme.com/users"},
            "cwd": str(tmp_path),
        }
        verdict = guard.decide(payload)
        assert verdict.decision == guard.DENY

    def test_production_denies_even_interactive(self, guard):
        hit = guard.decide(_bash("AWS_PROFILE=production aws rds delete-db-instance"))
        resolved = guard.resolve(hit, _bash("x"), env={})
        assert resolved.decision == guard.DENY


# ---------------------------------------------------------------------------
# Session-auth integrity
# ---------------------------------------------------------------------------


class TestSessionAuthProtection:
    def test_edit_denied(self, guard):
        verdict = guard.decide(_edit(".maverick/session-auth.json"))
        assert verdict.decision == guard.DENY
        assert verdict.always_deny

    def test_bash_write_denied(self, guard):
        verdict = guard.decide(
            _bash('echo \'{"scopes":["infra"]}\' > .maverick/session-auth.json')
        )
        assert verdict.decision == guard.DENY

    def test_bash_read_allowed(self, guard):
        verdict = guard.decide(_bash("cat .maverick/session-auth.json"))
        assert verdict.decision == guard.ALLOW


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


class TestResolve:
    def test_interactive_hit_becomes_ask(self, guard):
        hit = guard.Verdict(guard.ASK, "git push --force rewrites shared history")
        resolved = guard.resolve(hit, _bash("git push -f"), env={})
        assert resolved.decision == guard.ASK

    def test_autonomous_env_hit_becomes_deny(self, guard):
        hit = guard.Verdict(guard.ASK, "git push --force rewrites shared history")
        resolved = guard.resolve(
            hit, _bash("git push -f"), env={"MAVERICK_AUTONOMOUS": "1"}
        )
        assert resolved.decision == guard.DENY
        assert "autonomous" in resolved.reason

    def test_autonomous_via_claims_registry(self, guard, tmp_path):
        claims = tmp_path / "active-claims.json"
        claims.write_text(
            json.dumps({"claims": [{"repo": "o/r", "issue": 1, "instance_id": "abc123"}]})
        )
        env = {"MAVERICK_INSTANCE_ID": "abc123"}
        assert guard.is_autonomous(env, claims_path=claims)
        assert not guard.is_autonomous({"MAVERICK_INSTANCE_ID": "other"}, claims_path=claims)

    def test_autonomous_via_instance_id_file_without_session_env(self, guard, tmp_path):
        """Issue #130 Test C: a claim recorded under the file id must classify
        as autonomous even when the hook subprocess receives no session env."""
        id_file = tmp_path / "instance_id"
        id_file.write_text("847a039d01\n")
        claims = tmp_path / "active-claims.json"
        claims.write_text(
            json.dumps(
                {"claims": [{"repo": "o/r", "issue": 1, "instance_id": "847a039d01"}]}
            )
        )
        # No MAVERICK_INSTANCE_ID / session env at all — only the file bridges.
        assert guard.is_autonomous({}, claims_path=claims, id_path=id_file)

    def test_instance_id_file_fallback_read_only(self, guard, tmp_path):
        id_file = tmp_path / "instance_id"
        id_file.write_text("f90bfff5dc")
        assert guard._instance_id({}, id_path=id_file) == "f90bfff5dc"
        # Session env still wins over the file.
        assert (
            guard._instance_id(
                {"CLAUDE_CODE_SESSION_ID": "sess"}, id_path=id_file
            )
            != "f90bfff5dc"
        )

    def test_instance_id_missing_file_is_none(self, guard, tmp_path):
        assert guard._instance_id({}, id_path=tmp_path / "nonexistent") is None

    def test_autonomous_infra_allowed_with_session_auth(self, guard, tmp_path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "session-auth.json").write_text(
            json.dumps({"repo": "o/r", "issue": 1, "scopes": ["infra"]})
        )
        hit = guard.decide(_edit(".github/workflows/ci.yml", cwd=str(tmp_path)))
        assert hit.decision == guard.ASK
        resolved = guard.resolve(
            hit,
            _edit(".github/workflows/ci.yml", cwd=str(tmp_path)),
            env={"MAVERICK_AUTONOMOUS": "1"},
        )
        assert resolved.decision == guard.ALLOW

    def test_interactive_infra_allowed_with_session_auth(self, guard, tmp_path):
        """A recorded `infra` grant suppresses the prompt regardless of how the
        run is classified — an interactive (mis)classification must not defeat
        an authorization the user already recorded (issue #130 secondary)."""
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "session-auth.json").write_text(
            json.dumps({"repo": "o/r", "issue": 1, "scopes": ["infra"]})
        )
        payload = _edit(".github/workflows/ci.yml", cwd=str(tmp_path))
        hit = guard.decide(payload)
        # env has no autonomous signal → classified interactive.
        resolved = guard.resolve(hit, payload, env={})
        assert resolved.decision == guard.ALLOW

    def test_autonomous_infra_denied_without_session_auth(self, guard, tmp_path):
        hit = guard.decide(_edit(".github/workflows/ci.yml", cwd=str(tmp_path)))
        resolved = guard.resolve(
            hit,
            _edit(".github/workflows/ci.yml", cwd=str(tmp_path)),
            env={"MAVERICK_AUTONOMOUS": "1"},
        )
        assert resolved.decision == guard.DENY

    def test_allow_passes_through(self, guard):
        resolved = guard.resolve(guard.Verdict(guard.ALLOW), _bash("ls"), env={})
        assert resolved.decision == guard.ALLOW


# ---------------------------------------------------------------------------
# Fail-open behavior
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_unknown_tool_allows(self, guard):
        payload = {"tool_name": "Glob", "tool_input": {"pattern": "*"}}
        assert guard.decide(payload).decision == guard.ALLOW

    def test_empty_payload_allows(self, guard):
        assert guard.decide({}).decision == guard.ALLOW

    def test_missing_tool_input_allows(self, guard):
        assert guard.decide({"tool_name": "Bash"}).decision == guard.ALLOW

"""Tests for the PreToolUse scope-guard hook.

The guard is the mechanical layer of mav-scope-boundaries: rule hits ask
in interactive sessions, deny in autonomous mode, and production patterns
deny everywhere. It must fail open on anything it does not understand.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from maverick.runtime_hooks import claims, scope_guard
from maverick.runtime_hooks.adapters import ClaudeAdapter, ToolCall


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Keep the real ~/.maverick out of every test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


@pytest.fixture(scope="module")
def guard():
    return scope_guard


def _claude(payload: dict) -> ToolCall:
    """Normalize a Claude Code PreToolUse payload the way the hook does."""
    return ClaudeAdapter().normalize(payload).tool or ToolCall("other")


def _bash(command: str, cwd: str = ".") -> ToolCall:
    return _claude({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})


def _edit(path: str, cwd: str = ".") -> ToolCall:
    return _claude({"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": cwd})


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


class TestShellWriteTargets:
    """#167: only real write targets are checked against infra paths."""

    @pytest.mark.parametrize(
        "command",
        [
            'grep -rn "\\.github/workflows" src/ 2>/dev/null',
            'gh issue comment 5 --body "fixes the Dockerfiles" >/dev/null 2>&1',
            'git commit -m "touch .github/workflows/ci.yml later" 2>&1',
            "rg Dockerfile docs/ > /dev/null",
            "cp .github/workflows/ci.yml /tmp/ci.yml",
            "sed -n 1,5p Dockerfile",
            "ls k8s/ 2>&1 | head",
            "cat Dockerfile >&2",
        ],
    )
    def test_reads_and_prose_pass(self, guard, command, monkeypatch):
        # Pin the branch: on a protected branch (CI on main) `git commit`
        # rightly asks, which is not what this test is about.
        monkeypatch.setattr(guard, "_current_branch", lambda cwd: "feat/1-x")
        assert guard.decide(_bash(command)).decision == guard.ALLOW, command

    @pytest.mark.parametrize(
        "command, target",
        [
            ("echo x > Dockerfile", "Dockerfile"),
            ("echo x >> docker-compose.yml", "docker-compose.yml"),
            ("make gen &> k8s/out.yaml", "k8s/out.yaml"),
            ("echo x | tee -a helm/values.yaml", "helm/values.yaml"),
            ("cp a.yml .github/workflows/b.yml", ".github/workflows/b.yml"),
            ("mv Dockerfile Dockerfile.old", "Dockerfile"),
            ("sed -i 's/a/b/' Dockerfile", "Dockerfile"),
            ("sed -i.bak -e 's/a/b/' infra/main.tf", "infra/main.tf"),
            ("rm -f .github/workflows/old.yml", ".github/workflows/old.yml"),
            ("git rm k8s/svc.yaml", "k8s/svc.yaml"),
            ("sudo tee Dockerfile < x", "Dockerfile"),
        ],
    )
    def test_writes_hit(self, guard, command, target):
        verdict = guard.decide(_bash(command))
        assert verdict.decision == guard.ASK, command
        assert repr(target) in verdict.reason

    @pytest.mark.parametrize(
        "command",
        [
            "bash -c 'echo x > .github/workflows/x.yml'",
            "sh -c \"git push --force origin feat/x\"",
            "eval 'cp a Dockerfile'",
            "bash -c \"sh -c 'echo x > Dockerfile'\"",
            "bash -c 'echo \"unclosed > Dockerfile'",
            "bash -lc 'cp /tmp/x .github/workflows/ci.yml'",
            "sh -xc 'echo x > Dockerfile'",
            "env -i bash -c 'cp /tmp/x .github/workflows/ci.yml'",
            "sudo -u root sh -c 'tee Dockerfile < x'",
            "env -u HOME tee Dockerfile < x",
            "bash -o pipefail -c 'cp /tmp/x .github/workflows/ci.yml'",
            "bash +O extglob -lc 'echo x > Dockerfile'",
            "bash --rcfile /tmp/rc -c 'tee Dockerfile < x'",
            "bash x -c 'echo > Dockerfile'",
            "python3 -c \"open('Dockerfile','w')\" > /tmp/log",
        ],
    )
    def test_nested_shells_are_checked(self, guard, command):
        assert guard.decide(_bash(command)).decision == guard.ASK, command

    @pytest.mark.parametrize(
        "command",
        [
            "cd .github/workflows && echo x > ci.yml",
            "W=.github/workflows/ci.yml; cp /tmp/x $W",
            "xargs -I{} cp /tmp/x .github/workflows/ci.yml",
            "find .github/workflows -name '*.yml' -exec sed -i s/a/b/ {} +",
            "timeout 5 tee .github/workflows/ci.yml < /tmp/x",
            "echo x > $(echo Dockerfile)",
            "perl -pi -e 's/a/b/' Dockerfile",
        ],
    )
    def test_indirect_infra_writes_ask(self, guard, command):
        """#167 security review: indirection must not hide an infra write."""
        assert guard.decide(_bash(command)).decision == guard.ASK, command

    @pytest.mark.parametrize(
        "command",
        [
            "F=.maverick/session-auth.json; echo '{\"scopes\":[\"infra\"]}' > $F",
            "export F=.maverick/session-auth.json; echo x > $F",
            "cd .maverick && echo '{}' > session-auth.json",
            "bash -c 'F=.maverick/session-auth.json; echo x > $F'",
        ],
    )
    def test_indirect_session_auth_writes_denied(self, guard, command):
        verdict = guard.decide(_bash(command))
        assert verdict.decision == guard.DENY, command
        assert verdict.always_deny

    @pytest.mark.parametrize(
        "command",
        [
            "cd .maverick && echo x > session-auth'.json'",
            "cd .maverick && echo x > session-auth.js\"\"on",
            "cd .maverick && cp /tmp/x session-{auth,x}.json",
            "cd .maverick && cp /tmp/x s?ssion-auth.json",
            "cp /tmp/x .maverick/sess*.json",
            "cp /tmp/x .maverick/session-auth.{j..k}son",
            "cp /tmp/x .maverick/se{s,t}{s,t}{i,j}{o,p}{n,m}{-,_}{a,b}uth.json",
            "bash -c 'echo x <> .maverick/sess*.json'",
        ],
    )
    def test_quoted_braced_globbed_session_auth_denied(self, guard, command):
        """Post-push review: names hidden by quotes, braces or globs."""
        verdict = guard.decide(_bash(command))
        assert verdict.decision == guard.DENY, command

    @pytest.mark.parametrize(
        "command",
        [
            "cp /tmp/x Docker{file,}",
            "echo x > .github/{workflows,x}/ci.yml",
            "echo x <> Dockerfile",
            "echo x > >(tee Dockerfile)",
            "tee >(cat > k8s/x.yaml) < /tmp/x",
            "cp /tmp/x Docker{e..g}ile",
            "bash -c 'echo x <> Dockerfile'",
            "bash -c 'echo x > >(tee Dockerfile)'",
            "cp /tmp/x .mave*/config.json",
            "cd .mave* && cp /tmp/x c?nfig.json",
        ],
    )
    def test_braces_and_unhandled_redirects_ask(self, guard, command):
        assert guard.decide(_bash(command)).decision == guard.ASK, command

    @pytest.mark.parametrize(
        "command",
        ["prettier --write src/*.json 2>/dev/null", "find . -name '*.json' -exec cat {} +"],
    )
    def test_generic_json_globs_do_not_hit_protected_files(self, guard, command):
        assert guard.decide(_bash(command)).decision == guard.ALLOW, command

    @pytest.mark.parametrize(
        "command",
        [
            "C=.maverick/config.json; echo '{}' > $C",
            "cd .maverick && python3 -c 'open(\"config.json\",\"w\")'",
        ],
    )
    def test_indirect_guard_config_writes_ask(self, guard, command):
        verdict = guard.decide(_bash(command))
        assert verdict.decision == guard.ASK, command
        assert "scope_guards" in verdict.reason

    def test_nested_shell_read_passes(self, guard):
        assert guard.decide(_bash("bash -c 'cat Dockerfile 2>/dev/null'")).decision == guard.ALLOW

    def test_unparseable_command_falls_back_to_coarse_check(self, guard):
        verdict = guard.decide(_bash('echo "unclosed > Dockerfile'))
        assert verdict.decision == guard.ASK

    def test_infra_reason_says_what_is_covered(self, guard):
        verdict = guard.decide(_edit("Dockerfile"))
        assert "CDK" in verdict.reason and "not restricted" in verdict.reason

    def test_compound_denial_says_nothing_ran(self, guard):
        verdict = guard.decide(_bash("git worktree remove --force wt && git push -f"))
        assert "none of it ran" in verdict.reason
        single = guard.decide(_bash("git push -f"))
        assert "none of it ran" not in single.reason


class TestGuardConfigProtection:
    """The file that tunes the guards must not be widened by the guarded agent."""

    @pytest.mark.parametrize(
        "call",
        [
            _edit(".maverick/config.json"),
            _edit("/repo/.maverick/config.json"),
            _bash("echo '{}' > .maverick/config.json"),
            _bash("jq '.scope_guards.auth_scan=\"advisory\"' c > .maverick/config.json"),
            _bash("python3 -c \"open('.maverick/config.json','w')\""),
        ],
    )
    def test_writes_ask(self, guard, call):
        verdict = guard.decide(call)
        assert verdict.decision == guard.ASK
        assert "scope_guards" in verdict.reason

    def test_read_allowed(self, guard):
        assert guard.decide(_bash("jq .scope_guards .maverick/config.json")).decision == guard.ALLOW

    def test_infra_grant_does_not_unlock_config(self, guard, tmp_path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "session-auth.json").write_text(
            json.dumps({"repo": "o/r", "issue": 1, "scopes": ["infra"]})
        )
        call = _edit(str(tmp_path / ".maverick/config.json"), cwd=str(tmp_path))
        resolved = guard.resolve(guard.decide(call), call, env={"MAVERICK_AUTONOMOUS": "1"})
        assert resolved.decision == guard.DENY


class TestBranchForceDelete:
    @pytest.fixture
    def repo(self, tmp_path):
        def git(*args):
            subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

        git("init", "-q", "-b", "main")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "a")
        git("branch", "empty-story")
        git("checkout", "-q", "-b", "real-work")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "b")
        git("checkout", "-q", "main")
        return tmp_path

    def test_branch_without_own_commits_allowed(self, guard, repo):
        verdict = guard.decide(_bash("git branch -D empty-story", cwd=str(repo)))
        assert verdict.decision == guard.ALLOW

    def test_branch_with_unique_commits_asks(self, guard, repo):
        verdict = guard.decide(_bash("git branch -D real-work", cwd=str(repo)))
        assert verdict.decision == guard.ASK
        assert "real-work" in verdict.reason

    def test_unknown_branch_asks(self, guard, repo):
        verdict = guard.decide(_bash("git branch -D no-such-branch", cwd=str(repo)))
        assert verdict.decision == guard.ASK

    def test_combined_short_flags_detected(self, guard, repo):
        verdict = guard.decide(_bash("git branch -df real-work", cwd=str(repo)))
        assert verdict.decision == guard.ASK

    def test_dash_c_checks_the_named_repo(self, guard, repo, tmp_path):
        """`git -C other branch -D x` must not be judged against the session repo."""
        other = tmp_path / "other"
        other.mkdir()
        subprocess.run(["git", "-C", str(other), "init", "-q", "-b", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(other), "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-q", "--allow-empty", "-m", "a"], check=True,
        )
        subprocess.run(["git", "-C", str(other), "checkout", "-q", "-b", "empty-story"], check=True)
        subprocess.run(
            ["git", "-C", str(other), "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-q", "--allow-empty", "-m", "b"], check=True,
        )
        subprocess.run(["git", "-C", str(other), "checkout", "-q", "main"], check=True)
        # empty-story is redundant in `repo` but has a unique commit in `other`.
        verdict = guard.decide(_bash(f"git -C {other} branch -D empty-story", cwd=str(repo)))
        assert verdict.decision == guard.ASK

    def test_cd_first_never_trusts_redundancy(self, guard, repo):
        verdict = guard.decide(_bash("cd /elsewhere && git branch -D empty-story", cwd=str(repo)))
        assert verdict.decision == guard.ASK

    def test_mixed_list_names_only_unsafe(self, guard, repo):
        verdict = guard.decide(_bash("git branch -D empty-story real-work", cwd=str(repo)))
        assert verdict.decision == guard.ASK
        assert "real-work" in verdict.reason and "empty-story" not in verdict.reason


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
        verdict = guard.decide(_claude(payload))
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
        verdict = guard.decide(_bash("jq . .maverick/session-auth.json 2>/dev/null"))
        assert verdict.decision == guard.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            "cp /tmp/x.json .maverick/session-auth.json",
            "echo '{}' | tee .maverick/session-auth.json",
            "python3 -c \"open('.maverick/session-auth.json','w').write('{}')\"",
        ],
    )
    def test_other_writers_denied(self, guard, command):
        verdict = guard.decide(_bash(command))
        assert verdict.decision == guard.DENY, command
        assert verdict.always_deny


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

    @pytest.mark.parametrize(
        "call",
        [
            _edit(".github/workflows/ci.yml"),
            _bash("echo x > Dockerfile"),
            _bash("git push --force origin feat/1-x"),
        ],
        ids=["infra-edit", "infra-shell-write", "git-force-push"],
    )
    @pytest.mark.parametrize("autonomous", [False, True], ids=["interactive", "autonomous"])
    def test_escalation_text_appears_exactly_once(self, guard, tmp_path, call, autonomous):
        """#151: rules used to embed ESCALATION and resolve() appended it again."""
        verdict = guard.decide(call)
        assert verdict.decision == guard.ASK
        assert guard.ESCALATION not in verdict.reason  # rules give only the why
        env = {"MAVERICK_AUTONOMOUS": "1"} if autonomous else {}
        resolved = guard.resolve(verdict, call, env=env)
        assert resolved.decision == (guard.DENY if autonomous else guard.ASK)
        assert resolved.reason.count(guard.ESCALATION) == 1
        assert resolved.reason.count("mav-scope-boundaries") == 1

    def test_claims_do_not_make_a_session_autonomous(self, guard, tmp_path, monkeypatch):
        """#167: the interactive coordinator holds claims; it must still ask."""
        home = tmp_path / "home" / ".maverick"
        home.mkdir(parents=True, exist_ok=True)
        (home / "active-claims.json").write_text(
            json.dumps({"claims": [{"repo": "o/r", "issue": 1, "instance_id": "abc123"}]})
        )
        env = {"MAVERICK_INSTANCE_ID": "abc123"}
        assert not guard.is_autonomous(env, _bash("git push -f"))
        hit = guard.Verdict(guard.ASK, "git push --force rewrites shared history")
        assert guard.resolve(hit, _bash("git push -f"), env=env).decision == guard.ASK

    def test_subagent_call_is_autonomous(self, guard):
        call = _claude(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git push -f"},
                "agent_id": "a1b2",
                "agent_type": "general-purpose",
            }
        )
        assert call.subagent
        hit = guard.decide(call)
        resolved = guard.resolve(hit, call, env={})
        assert resolved.decision == guard.DENY
        assert "subagent" in resolved.reason

    def test_agent_type_alone_is_not_a_subagent(self, guard):
        """`claude --agent x` sets agent_type on the main session too."""
        call = _claude(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}, "agent_type": "x"}
        )
        assert not call.subagent

    def test_instance_id_file_fallback_read_only(self, guard, tmp_path):
        id_file = tmp_path / "instance_id"
        id_file.write_text("f90bfff5dc")
        assert claims.instance_id({}, id_path=id_file) == "f90bfff5dc"
        # Session env still wins over the file.
        assert (
            claims.instance_id(
                {"CLAUDE_CODE_SESSION_ID": "sess"}, id_path=id_file
            )
            != "f90bfff5dc"
        )

    def test_instance_id_missing_file_is_none(self, guard, tmp_path):
        assert claims.instance_id({}, id_path=tmp_path / "nonexistent") is None

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
        assert guard.decide(_claude(payload)).decision == guard.ALLOW

    def test_empty_payload_allows(self, guard):
        assert guard.decide(_claude({})).decision == guard.ALLOW

    def test_missing_tool_input_allows(self, guard):
        assert guard.decide(_claude({"tool_name": "Bash"})).decision == guard.ALLOW

"""Tests for maverick.issue_lifecycle — per-project issue close policy.

Covers the pure decision logic (decide_close), the get_policy fallback
behaviour, and the side-effecting close_on_merge with a stubbed gh
runner so the network never engages.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from maverick import issue_lifecycle


class TestDecideClose:
    """Pure-logic close decision. The skill bodies and the CLI both
    consume this, so the policy semantics live in one place."""

    def test_on_pr_merge_always_closes(self):
        should, reason = issue_lifecycle.decide_close("on_pr_merge", "develop", "main")
        assert should is True
        assert reason == ""

    def test_on_pr_merge_closes_even_when_target_is_default(self):
        should, _ = issue_lifecycle.decide_close("on_pr_merge", "main", "main")
        assert should is True

    def test_on_default_branch_merge_closes_only_for_default(self):
        should, _ = issue_lifecycle.decide_close(
            "on_default_branch_merge", "main", "main"
        )
        assert should is True

    def test_on_default_branch_merge_skips_for_non_default(self):
        should, reason = issue_lifecycle.decide_close(
            "on_default_branch_merge", "develop", "main"
        )
        assert should is False
        assert "develop" in reason
        assert "main" in reason

    def test_manual_never_closes(self):
        should, reason = issue_lifecycle.decide_close("manual", "main", "main")
        assert should is False
        assert "manual" in reason


class TestGetPolicy:
    def test_default_when_field_absent(self, tmp_path, monkeypatch):
        # Empty cfg — get_policy must fall back to the default.
        cfg = {"aws": {"region": "us-east-1"}}
        assert issue_lifecycle.get_policy(cfg) == "on_pr_merge"

    def test_returns_explicit_policy(self):
        cfg = {"issue_lifecycle": {"close_policy": "manual"}}
        assert issue_lifecycle.get_policy(cfg) == "manual"

    def test_unknown_value_falls_back_to_default(self):
        """Forward-compat / hand-edited config — never raise, never
        accidentally turn into a third semantic. Default to on_pr_merge."""
        cfg = {"issue_lifecycle": {"close_policy": "on_full_moon"}}
        assert issue_lifecycle.get_policy(cfg) == "on_pr_merge"


class _FakeGh:
    """Records every gh invocation. ``raise_on`` lets a single call sequence
    raise CalledProcessError to simulate ``gh label create`` failing because
    the label already exists."""

    def __init__(self, raise_on: tuple[str, ...] | None = None):
        self.calls: list[tuple[str, ...]] = []
        self.raise_on = raise_on

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if self.raise_on and args[: len(self.raise_on)] == self.raise_on:
            raise subprocess.CalledProcessError(1, list(args))
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="", stderr="")

    def call_args(self, *prefix: str) -> list[tuple[str, ...]]:
        return [c for c in self.calls if c[: len(prefix)] == prefix]


class TestCloseOnMerge:
    """Audit comment + label fire unconditionally; close fires per policy."""

    def test_default_policy_closes_and_emits_comment_and_label(self):
        gh = _FakeGh()
        cfg = {"issue_lifecycle": {"close_policy": "on_pr_merge"}}

        decision = issue_lifecycle.close_on_merge(
            "me/r", 42,
            pr_num=99, target_branch="develop", default_branch="main",
            cfg=cfg, gh_runner=gh,
        )

        assert decision.closed is True
        assert decision.skip_reason == ""
        assert decision.policy == "on_pr_merge"
        assert decision.label_applied == "merged-to-develop"
        # Comment posted with the resolved-in template.
        comments = gh.call_args("issue", "comment")
        assert len(comments) == 1
        assert "PR #99" in " ".join(comments[0])
        assert "develop" in " ".join(comments[0])
        # Label applied.
        assert gh.call_args("issue", "edit") and any(
            "--add-label" in c for c in gh.call_args("issue", "edit")
        )
        # Close called.
        assert gh.call_args("issue", "close")

    def test_manual_policy_skips_close_but_keeps_audit_trail(self):
        gh = _FakeGh()
        cfg = {"issue_lifecycle": {"close_policy": "manual"}}

        decision = issue_lifecycle.close_on_merge(
            "me/r", 42,
            pr_num=99, target_branch="develop", default_branch="main",
            cfg=cfg, gh_runner=gh,
        )

        assert decision.closed is False
        assert "manual" in decision.skip_reason
        # Comment + label still posted — that's the policy-independent trail.
        assert gh.call_args("issue", "comment")
        assert gh.call_args("issue", "edit")
        # No close.
        assert not gh.call_args("issue", "close")

    def test_default_branch_policy_closes_on_main(self):
        gh = _FakeGh()
        cfg = {"issue_lifecycle": {"close_policy": "on_default_branch_merge"}}

        decision = issue_lifecycle.close_on_merge(
            "me/r", 42,
            pr_num=99, target_branch="main", default_branch="main",
            cfg=cfg, gh_runner=gh,
        )

        assert decision.closed is True
        assert gh.call_args("issue", "close")

    def test_default_branch_policy_skips_on_develop(self):
        gh = _FakeGh()
        cfg = {"issue_lifecycle": {"close_policy": "on_default_branch_merge"}}

        decision = issue_lifecycle.close_on_merge(
            "me/r", 42,
            pr_num=99, target_branch="develop", default_branch="main",
            cfg=cfg, gh_runner=gh,
        )

        assert decision.closed is False
        assert "default" in decision.skip_reason
        # Audit trail still present.
        assert gh.call_args("issue", "comment")
        assert decision.label_applied == "merged-to-develop"

    def test_label_already_exists_does_not_break_flow(self):
        """``gh label create`` exits non-zero when the label is already
        present. The helper swallows that and proceeds with apply + close."""
        gh = _FakeGh(raise_on=("label", "create"))
        cfg = {"issue_lifecycle": {"close_policy": "on_pr_merge"}}

        decision = issue_lifecycle.close_on_merge(
            "me/r", 42,
            pr_num=99, target_branch="main", default_branch="main",
            cfg=cfg, gh_runner=gh,
        )

        assert decision.closed is True
        assert gh.call_args("issue", "close")


class TestDecisionToJson:
    def test_emits_stable_keys(self):
        d = issue_lifecycle.CloseDecision(
            policy="on_pr_merge",
            target_branch="develop",
            default_branch="main",
            closed=True,
            skip_reason="",
            comment_posted=True,
            label_applied="merged-to-develop",
        )
        out = json.loads(issue_lifecycle.decision_to_json(d))
        assert out["policy"] == "on_pr_merge"
        assert out["closed"] is True
        assert out["label_applied"] == "merged-to-develop"
        assert out["skip_reason"] == ""


class TestCliHandler:
    """The CLI handler is a thin wrapper — assert it forwards args and
    prints the JSON decision."""

    def test_close_on_merge_handler(self, monkeypatch, capsys):
        import argparse

        from maverick import coord_cli

        def fake_default_branch():
            return "main"

        captured: dict = {}

        def fake_close_on_merge(repo, issue, *, pr_num, target_branch, default_branch):
            captured.update(
                repo=repo,
                issue=issue,
                pr_num=pr_num,
                target_branch=target_branch,
                default_branch=default_branch,
            )
            return issue_lifecycle.CloseDecision(
                policy="on_pr_merge",
                target_branch=target_branch,
                default_branch=default_branch,
                closed=True,
                skip_reason="",
                comment_posted=True,
                label_applied=f"merged-to-{target_branch}",
            )

        monkeypatch.setattr(coord_cli.worktree, "default_branch", fake_default_branch)
        monkeypatch.setattr(
            coord_cli.issue_lifecycle, "close_on_merge", fake_close_on_merge
        )
        args = argparse.Namespace(
            repo="me/r", issue=42, pr=99, target="develop", default_branch=None
        )

        rc = coord_cli._issue_close_on_merge(args)

        assert rc == 0
        assert captured == {
            "repo": "me/r",
            "issue": 42,
            "pr_num": 99,
            "target_branch": "develop",
            "default_branch": "main",
        }
        out = capsys.readouterr().out
        assert "on_pr_merge" in out
        assert "merged-to-develop" in out

    def test_explicit_default_branch_skips_detection(self, monkeypatch, capsys):
        """Passing --default-branch lets the skill avoid an extra gh API
        call when it already knows the value (it does, post-merge)."""
        import argparse

        from maverick import coord_cli

        def boom():
            raise AssertionError("default_branch should not be invoked")

        captured: dict = {}

        def fake_close_on_merge(repo, issue, *, pr_num, target_branch, default_branch):
            captured["default_branch"] = default_branch
            return issue_lifecycle.CloseDecision(
                policy="on_pr_merge",
                target_branch=target_branch,
                default_branch=default_branch,
                closed=True,
                skip_reason="",
                comment_posted=True,
                label_applied=f"merged-to-{target_branch}",
            )

        monkeypatch.setattr(coord_cli.worktree, "default_branch", boom)
        monkeypatch.setattr(
            coord_cli.issue_lifecycle, "close_on_merge", fake_close_on_merge
        )
        args = argparse.Namespace(
            repo="me/r", issue=42, pr=99, target="main", default_branch="trunk"
        )

        coord_cli._issue_close_on_merge(args)

        assert captured["default_branch"] == "trunk"

    def test_policy_handler_prints_policy(self, monkeypatch, capsys):
        import argparse

        from maverick import coord_cli

        monkeypatch.setattr(coord_cli.issue_lifecycle, "get_policy", lambda: "manual")

        rc = coord_cli._issue_policy(argparse.Namespace())

        assert rc == 0
        assert capsys.readouterr().out.strip() == "manual"


@pytest.fixture(autouse=True)
def _no_real_gh(monkeypatch):
    """Defence in depth: even if a test forgets to inject a fake runner,
    the real ``subprocess.run`` for ``gh`` must not fire from this file."""
    real_run = subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "gh":
            raise AssertionError(f"unexpected gh call from test: {cmd}")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)

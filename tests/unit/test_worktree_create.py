"""Tests for ``maverick.worktree.create`` — base-branch resolution.

Covers the fix for #112: when no ``base`` is passed, ``create`` must
honour the project's configured ``git_workflow.story_base`` rather
than silently branching off ``origin/HEAD``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from maverick import worktree


def _stub_git_factory(captured: list[tuple[tuple[str, ...], Path | None]]):
    """Build a stub for ``worktree._git`` that records calls and returns
    a HEAD-like SHA when asked, otherwise an empty string.
    """

    def _stub(*args: str, cwd: Path | None = None) -> str:
        captured.append((args, cwd))
        if args[:2] == ("rev-parse", "HEAD"):
            return "deadbeef\n"
        return ""

    return _stub


class TestCreateBaseResolution:
    """``create()`` should prefer the configured story_base over the
    repo's default branch when no ``base`` argument is supplied.
    """

    def test_uses_configured_story_base_when_no_base_passed(
        self, tmp_path: Path
    ) -> None:
        calls: list[tuple[tuple[str, ...], Path | None]] = []
        with patch.object(worktree, "_git", side_effect=_stub_git_factory(calls)), \
            patch.object(worktree, "repo_root", return_value=tmp_path), \
            patch.object(worktree, "_run_post_create_hook"), \
            patch.object(worktree.git_workflow, "get_story_base", return_value="develop"), \
            patch.object(worktree, "default_branch") as default_branch_mock:
            worktree.create("feat/foo")

        # The worktree must be added from origin/develop, not the repo
        # default branch — and default_branch() must not be consulted
        # when story_base resolves to a non-empty value.
        add_calls = [args for args, _ in calls if args[:1] == ("worktree",)]
        assert add_calls, "expected a `git worktree add` invocation"
        assert add_calls[0][-1] == "origin/develop"
        default_branch_mock.assert_not_called()

    def test_falls_back_to_default_branch_when_story_base_empty(
        self, tmp_path: Path
    ) -> None:
        calls: list[tuple[tuple[str, ...], Path | None]] = []
        with patch.object(worktree, "_git", side_effect=_stub_git_factory(calls)), \
            patch.object(worktree, "repo_root", return_value=tmp_path), \
            patch.object(worktree, "_run_post_create_hook"), \
            patch.object(worktree.git_workflow, "get_story_base", return_value=""), \
            patch.object(worktree, "default_branch", return_value="master"):
            worktree.create("feat/foo")

        add_calls = [args for args, _ in calls if args[:1] == ("worktree",)]
        assert add_calls, "expected a `git worktree add` invocation"
        assert add_calls[0][-1] == "origin/master"

    def test_explicit_base_overrides_config(self, tmp_path: Path) -> None:
        calls: list[tuple[tuple[str, ...], Path | None]] = []
        with patch.object(worktree, "_git", side_effect=_stub_git_factory(calls)), \
            patch.object(worktree, "repo_root", return_value=tmp_path), \
            patch.object(worktree, "_run_post_create_hook"), \
            patch.object(worktree.git_workflow, "get_story_base", return_value="develop"), \
            patch.object(worktree, "default_branch") as default_branch_mock:
            worktree.create("feat/foo", base="feat/sibling")

        add_calls = [args for args, _ in calls if args[:1] == ("worktree",)]
        assert add_calls, "expected a `git worktree add` invocation"
        assert add_calls[0][-1] == "origin/feat/sibling"
        default_branch_mock.assert_not_called()

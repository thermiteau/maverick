"""Tests for maverick.git_workflow — resolver functions for per-project
branching config."""

from __future__ import annotations

from maverick import git_workflow
from maverick.config import _DEFAULT_BRANCH_PREFIXES


class TestGetStoryBase:
    def test_defaults_to_main(self):
        assert git_workflow.get_story_base({}) == "main"

    def test_reads_from_config(self):
        cfg = {"git_workflow": {"story_base": "develop"}}
        assert git_workflow.get_story_base(cfg) == "develop"

    def test_falls_back_on_empty_string(self):
        cfg = {"git_workflow": {"story_base": ""}}
        assert git_workflow.get_story_base(cfg) == "main"

    def test_falls_back_on_missing_section(self):
        assert git_workflow.get_story_base({"other": {}}) == "main"


class TestGetPrTarget:
    def test_defaults_to_main(self):
        assert git_workflow.get_pr_target({}) == "main"

    def test_reads_from_config(self):
        cfg = {"git_workflow": {"pr_target": "develop"}}
        assert git_workflow.get_pr_target(cfg) == "develop"

    def test_falls_back_on_empty_string(self):
        cfg = {"git_workflow": {"pr_target": ""}}
        assert git_workflow.get_pr_target(cfg) == "main"


class TestGetPromotionChain:
    def test_defaults_to_main_only(self):
        assert git_workflow.get_promotion_chain({}) == ["main"]

    def test_reads_from_config(self):
        cfg = {"git_workflow": {"promotion_chain": ["develop", "staging", "main"]}}
        assert git_workflow.get_promotion_chain(cfg) == ["develop", "staging", "main"]

    def test_falls_back_on_empty_list(self):
        cfg = {"git_workflow": {"promotion_chain": []}}
        assert git_workflow.get_promotion_chain(cfg) == ["main"]

    def test_falls_back_on_non_list(self):
        cfg = {"git_workflow": {"promotion_chain": "not-a-list"}}
        assert git_workflow.get_promotion_chain(cfg) == ["main"]


class TestGetBranchPrefix:
    def test_known_label(self):
        assert git_workflow.get_branch_prefix("bug", {}) == "fix"

    def test_unknown_label_defaults_to_feat(self):
        assert git_workflow.get_branch_prefix("unknown-label", {}) == "feat"

    def test_case_insensitive(self):
        assert git_workflow.get_branch_prefix("BUG", {}) == "fix"
        assert git_workflow.get_branch_prefix("Enhancement", {}) == "feat"

    def test_custom_prefixes(self):
        cfg = {"git_workflow": {"branch_prefixes": {"bug": "bugfix", "story": "story"}}}
        assert git_workflow.get_branch_prefix("bug", cfg) == "bugfix"
        assert git_workflow.get_branch_prefix("story", cfg) == "story"
        assert git_workflow.get_branch_prefix("unknown", cfg) == "feat"

    def test_falls_back_on_invalid_prefixes(self):
        cfg = {"git_workflow": {"branch_prefixes": "not-a-dict"}}
        assert git_workflow.get_branch_prefix("bug", cfg) == "fix"


class TestGetBranchPrefixes:
    def test_returns_defaults(self):
        result = git_workflow.get_branch_prefixes({})
        assert result == _DEFAULT_BRANCH_PREFIXES

    def test_returns_custom(self):
        custom = {"bug": "bugfix"}
        cfg = {"git_workflow": {"branch_prefixes": custom}}
        assert git_workflow.get_branch_prefixes(cfg) == custom

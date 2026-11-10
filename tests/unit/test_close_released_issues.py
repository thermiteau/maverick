"""Tests for scripts/close_released_issues.py (release-finalize step)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "close_released_issues.py"
_spec = importlib.util.spec_from_file_location("close_released_issues", _PATH)
assert _spec and _spec.loader
cri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cri)

REPO = "thermiteau/maverick"


class TestPrNumbers:
    def test_takes_trailing_pr_number(self):
        subjects = [
            "chore: release 5.2.0 (#149)",
            "fix: read config-defined commands from the base branch (#147) (#148)",
            "feat: review gates (#145) (#146)",
            "Merge branch 'x'",  # no PR number
        ]
        assert cri.pr_numbers(subjects) == [149, 148, 146]

    def test_deduplicates(self):
        assert cri.pr_numbers(["a (#5)", "b (#5)"]) == [5]


class TestClosingRefs:
    def test_keywords_and_forms(self):
        body = (
            "Closes #145\n"
            "fixes: #7 and Resolved #8\n"
            "close thermiteau/maverick#9\n"
            "Fixed https://github.com/thermiteau/maverick/issues/10\n"
        )
        assert cri.closing_refs(body, REPO) == [145, 7, 8, 9, 10]

    def test_ignores_other_repos_and_plain_refs(self):
        body = (
            "Closes other/repo#1\n"
            "Fixes https://github.com/other/repo/issues/2\n"
            "Refs #3, related to #4, see issue #5\n"
            "prefixes #6\n"  # 'fixes' inside a word is not a keyword
        )
        assert cri.closing_refs(body, REPO) == []

    def test_case_insensitive_repo_and_dedupe(self):
        body = "CLOSES Thermiteau/Maverick#11\nCloses #11"
        assert cri.closing_refs(body, REPO) == [11]

    def test_empty_body(self):
        assert cri.closing_refs("", REPO) == []


class TestMainGuards:
    def test_rejects_non_release_tag(self, capsys):
        assert cri.main(["main", "--repo", REPO]) == 2
        assert "not a release tag" in capsys.readouterr().err

    def test_requires_repo(self, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert cri.main(["v1.2.3", "--repo", ""]) == 2

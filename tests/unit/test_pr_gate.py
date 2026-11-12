"""Tests for the pre-merge auth-scan gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from maverick import pr_gate


class TestScanPaths:
    def test_auth_segments_hit(self):
        hits = pr_gate.scan_paths(
            [
                "src/auth/token.py",
                "app/middleware/authentication.ts",
                "lib/oauth2/client.go",
                "config/rbac/roles.yaml",
                "src/login-form.tsx",
            ]
        )
        assert len(hits) == 5

    def test_filename_tokens_hit(self):
        assert pr_gate.scan_paths(["src/auth.py"]) == ["src/auth.py"]
        assert pr_gate.scan_paths(["middleware/session_store.ts"]) == [
            "middleware/session_store.ts"
        ]

    def test_author_does_not_match_auth(self):
        assert pr_gate.scan_paths(["src/author.py", "docs/authors.md"]) == []

    def test_workflows_dir_gated(self):
        assert pr_gate.scan_paths([".github/workflows/ci.yml"]) == [
            ".github/workflows/ci.yml"
        ]
        assert pr_gate.scan_paths(["./.github/workflows/ci.yml"]) == [
            "./.github/workflows/ci.yml"
        ]

    def test_clean_paths_pass(self):
        assert (
            pr_gate.scan_paths(
                ["src/app.py", "README.md", "tests/unit/test_export.py", "docs/api.md"]
            )
            == []
        )

    def test_project_extra_tokens(self, tmp_path: Path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "config.json").write_text(
            json.dumps({"scope_guards": {"auth_paths": ["gatekeeper"]}})
        )
        hits = pr_gate.scan_paths(["src/gatekeeper/rules.py"], project_dir=tmp_path)
        assert hits == ["src/gatekeeper/rules.py"]

    def test_corrupt_project_config_ignored(self, tmp_path: Path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "config.json").write_text("{broken")
        assert pr_gate.scan_paths(["src/app.py"], project_dir=tmp_path) == []


class TestNarrowing:
    """#167: generic tokens must not strand PRs that cannot change auth."""

    @pytest.mark.parametrize(
        "path",
        [
            "src/tasks/task-comments-person-session.integration.test.ts",
            "web/__tests__/member-roles-card.tsx",
            "src/login.spec.js",
            "tests/unit/test_auth.py",
            "pkg/session/store_test.go",
        ],
    )
    def test_test_files_cleared(self, path):
        result = pr_gate.scan([path])
        assert result.hits == []
        assert result.cleared == {path: "test file"}

    @pytest.mark.parametrize(
        "path",
        ["src/auth/test_mode.py", "src/auth/policy.spec.json", "tests/fixtures/auth.yml"],
    )
    def test_non_test_code_named_like_tests_still_gated(self, path):
        assert pr_gate.scan([path]).auth_hits == [path]

    def test_auth_paths_exclude(self, tmp_path: Path):
        (tmp_path / ".maverick").mkdir()
        (tmp_path / ".maverick" / "config.json").write_text(
            json.dumps({"scope_guards": {"auth_paths_exclude": ["roles", "Credentials"]}})
        )
        paths = ["src/member-roles-card.tsx", "db/seed-staff-credentials.ts", "src/auth/x.ts"]
        assert pr_gate.scan_paths(paths, project_dir=tmp_path) == ["src/auth/x.ts"]

    def test_comment_only_change_cleared(self):
        diff = pr_gate.parse_diff(
            "diff --git a/src/task-context-permissions.ts b/src/task-context-permissions.ts\n"
            "index 1..2 100644\n"
            "--- a/src/task-context-permissions.ts\n"
            "+++ b/src/task-context-permissions.ts\n"
            "@@ -1,3 +1,4 @@\n"
            " export function canEdit() {\n"
            "-  // old note\n"
            "+  // new note\n"
            "+\n"
            "   return x;\n"
        )
        result = pr_gate.scan(["src/task-context-permissions.ts"], diff=diff)
        assert result.hits == []
        assert "comment" in result.cleared["src/task-context-permissions.ts"]

    @pytest.mark.parametrize(
        "line",
        [
            "/* x */ return true;",
            "/* istanbul ignore next */ if (!isAdmin) return;",
            "*/ return true;",
            "*ptr = 0;",
            " * looks like a block comment body",
        ],
    )
    def test_code_after_or_ambiguous_comment_not_cleared(self, line):
        diff = {"src/auth/x.ts": ["// note", line]}
        assert pr_gate.scan(["src/auth/x.ts"], diff=diff).auth_hits == ["src/auth/x.ts"]

    @pytest.mark.parametrize(
        "path, line",
        [
            ("src/auth/x.ts", "// note \\"),
            ("src/auth/x.c", "/* ok */ \\"),
            ("src/auth/x.php", "// done ?> <?php"),
            ("src/auth/x.py", "# -*- coding: utf-7 -*-"),
        ],
    )
    def test_context_changing_comments_not_cleared(self, path, line):
        """A trailing backslash comments out the next, unchanged line."""
        diff = {path: [line]}
        assert pr_gate.scan([path], diff=diff).auth_hits == [path]

    def test_whole_line_block_comment_cleared(self):
        diff = {"src/auth/x.ts": ["/* note */", "// other", ""]}
        assert pr_gate.scan(["src/auth/x.ts"], diff=diff).auth_hits == []

    def test_parse_diff_added_line_starting_with_plus_plus(self):
        """A `+++ counter;` change inside a hunk is content, not a header."""
        diff = pr_gate.parse_diff(
            "diff --git a/src/auth/x.c b/src/auth/x.c\n"
            "--- a/src/auth/x.c\n"
            "+++ b/src/auth/x.c\n"
            "@@ -1,1 +1,4 @@\n"
            " int f() {\n"
            "+// note\n"
            "+++ counter;\n"
            "+if (isAdmin) return 1;\n"
        )
        assert diff == {"src/auth/x.c": ["// note", "++ counter;", "if (isAdmin) return 1;"]}
        assert pr_gate.scan(["src/auth/x.c"], diff=diff).auth_hits == ["src/auth/x.c"]

    def test_parse_diff_malformed_raises(self):
        with pytest.raises(ValueError):
            pr_gate.parse_diff("+++ b/x.py\n+code without a hunk header\n")

    def test_guard_config_is_hard_gated(self):
        result = pr_gate.scan([".maverick/config.json"], diff={".maverick/config.json": []})
        assert result.ci_hits == [".maverick/config.json"]

    def test_code_change_still_gated(self):
        diff = {"src/change-member-roles.ts": ["  // why", "  return replaceRoles(m);"]}
        assert pr_gate.scan(["src/change-member-roles.ts"], diff=diff).auth_hits == [
            "src/change-member-roles.ts"
        ]

    def test_comment_check_needs_known_language(self):
        # Markdown "#" is a heading, not a comment.
        diff = {"docs/auth.md": ["# Heading"]}
        assert pr_gate.scan(["docs/auth.md"], diff=diff).auth_hits == ["docs/auth.md"]

    def test_no_changed_lines_never_comment_only(self):
        diff = {"src/auth.py": []}  # pure rename or binary
        assert pr_gate.scan(["src/auth.py"], diff=diff).auth_hits == ["src/auth.py"]

    def test_workflows_gate_even_in_tests_dir_and_comment_only(self):
        diff = {".github/workflows/test.yml": ["# comment"]}
        assert pr_gate.scan([".github/workflows/test.yml"], diff=diff).ci_hits == [
            ".github/workflows/test.yml"
        ]

    def test_parse_diff_deleted_file_uses_old_path(self):
        diff = pr_gate.parse_diff(
            "diff --git a/src/auth.py b/src/auth.py\n"
            "deleted file mode 100644\n"
            "--- a/src/auth.py\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-SECRET = 1\n"
        )
        assert diff == {"src/auth.py": ["SECRET = 1"]}


class TestAuthScanCli:
    def _run(self, monkeypatch, tmp_path, files, config, verdict, local=None):
        """*config* is what the PR's base branch holds; *local* the working tree."""
        from maverick import coord_cli

        monkeypatch.chdir(tmp_path)
        if local is not None:
            (tmp_path / ".maverick").mkdir()
            (tmp_path / ".maverick" / "config.json").write_text(json.dumps(local))
        base = (config or {}).get("scope_guards", {})
        monkeypatch.setattr(pr_gate, "pr_base_guards", lambda repo, pr: base)
        monkeypatch.setattr(pr_gate, "pr_changed_files", lambda repo, pr: files)
        monkeypatch.setattr(pr_gate, "pr_diff", lambda repo, pr: {})
        args = argparse.Namespace(repo="o/r", pr="1", security_verdict=verdict)
        return coord_cli._pr_auth_scan(args)

    def test_auth_hit_gates_by_default(self, monkeypatch, tmp_path):
        assert self._run(monkeypatch, tmp_path, ["src/auth.py"], None, "PASS") == 3

    def test_advisory_with_pass_does_not_gate(self, monkeypatch, tmp_path, capsys):
        config = {"scope_guards": {"auth_scan": "advisory"}}
        assert self._run(monkeypatch, tmp_path, ["src/auth.py"], config, "PASS") == 0
        assert "advisory" in capsys.readouterr().out

    @pytest.mark.parametrize("verdict", [None, "FINDINGS", "BLOCKING"])
    def test_advisory_without_pass_gates(self, monkeypatch, tmp_path, verdict):
        config = {"scope_guards": {"auth_scan": "advisory"}}
        assert self._run(monkeypatch, tmp_path, ["src/auth.py"], config, verdict) == 3

    def test_working_tree_config_ignored(self, monkeypatch, tmp_path):
        """An uncommitted local edit must not switch the gate off (#167 review)."""
        local = {"scope_guards": {"auth_scan": "advisory", "auth_paths_exclude": ["auth"]}}
        assert self._run(monkeypatch, tmp_path, ["src/auth.py"], None, "PASS", local=local) == 3

    def test_base_config_unreadable_is_scan_error(self, monkeypatch, tmp_path):
        import subprocess as sp

        from maverick import coord_cli

        monkeypatch.setattr(pr_gate, "pr_changed_files", lambda repo, pr: ["src/app.py"])

        def boom(repo, pr):
            raise sp.CalledProcessError(1, ["gh"], "", "HTTP 500")

        monkeypatch.setattr(pr_gate, "pr_base_guards", boom)
        args = argparse.Namespace(repo="o/r", pr="1", security_verdict=None)
        assert coord_cli._pr_auth_scan(args) == 2

    def test_advisory_never_covers_workflows(self, monkeypatch, tmp_path):
        config = {"scope_guards": {"auth_scan": "advisory"}}
        files = [".github/workflows/ci.yml"]
        assert self._run(monkeypatch, tmp_path, files, config, "PASS") == 3

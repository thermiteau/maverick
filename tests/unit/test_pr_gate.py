"""Tests for the pre-merge auth-scan gate."""

from __future__ import annotations

import json
from pathlib import Path

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

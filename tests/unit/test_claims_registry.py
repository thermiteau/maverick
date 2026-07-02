"""Tests for the local claims registry, release_all, and authorize."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick import coordinator


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Point the claims registry at a temp file and pin the instance id."""
    path = tmp_path / "active-claims.json"
    monkeypatch.setattr(coordinator, "_claims_registry_path", lambda: path)
    monkeypatch.setenv("MAVERICK_INSTANCE_ID", "test-instance")
    return path


class TestRegistry:
    def test_add_and_read(self, registry):
        coordinator._registry_add("o/r", 42)
        claims = coordinator._read_claims_registry()
        assert len(claims) == 1
        assert claims[0]["repo"] == "o/r"
        assert claims[0]["issue"] == 42
        assert claims[0]["instance_id"] == "test-instance"

    def test_add_is_idempotent_per_issue(self, registry):
        coordinator._registry_add("o/r", 42)
        coordinator._registry_add("o/r", 42)
        assert len(coordinator._read_claims_registry()) == 1

    def test_remove(self, registry):
        coordinator._registry_add("o/r", 42)
        coordinator._registry_add("o/r", 43)
        coordinator._registry_remove("o/r", 42)
        claims = coordinator._read_claims_registry()
        assert [c["issue"] for c in claims] == [43]

    def test_corrupt_file_reads_empty(self, registry):
        registry.write_text("{not json")
        assert coordinator._read_claims_registry() == []

    def test_missing_file_reads_empty(self, registry):
        assert coordinator._read_claims_registry() == []


class TestReleaseAll:
    def test_releases_only_this_instances_claims(self, registry):
        coordinator._registry_add("o/r", 1)
        # A claim held by another instance on the same machine.
        claims = coordinator._read_claims_registry()
        claims.append(
            {"repo": "o/r", "issue": 2, "instance_id": "other", "claimed_at": "x"}
        )
        coordinator._write_claims_registry(claims)

        with patch.object(coordinator, "release") as release:
            released = coordinator.release_all(reason="session-end")

        release.assert_called_once_with("o/r", 1, reason="session-end", env=None)
        assert released == [("o/r", 1)]
        # The other instance's claim is untouched.
        remaining = coordinator._read_claims_registry()
        assert [c["issue"] for c in remaining] == [2]

    def test_release_failure_drops_stale_entry(self, registry):
        coordinator._registry_add("o/r", 1)
        with patch.object(coordinator, "release", side_effect=RuntimeError("gone")):
            released = coordinator.release_all()
        assert released == []
        assert coordinator._read_claims_registry() == []

    def test_empty_registry_is_noop(self, registry):
        assert coordinator.release_all() == []


class TestAuthorize:
    @pytest.fixture
    def in_tmp_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            coordinator, "SESSION_AUTH_PATH", Path(".maverick/session-auth.json")
        )
        return tmp_path

    def test_label_grants(self, in_tmp_project):
        with patch.object(
            coordinator, "_issue_labels", return_value=["maverick-authorize-infra"]
        ):
            auth = coordinator.authorize("o/r", 42, "infra")
        assert auth["scopes"] == ["infra"]
        written = json.loads(Path(".maverick/session-auth.json").read_text())
        assert written["issue"] == 42
        assert written["scopes"] == ["infra"]

    def test_body_line_grants(self, in_tmp_project):
        body = "Please fix CI.\n\nMaverick-Authorize: infra\n"
        with (
            patch.object(coordinator, "_issue_labels", return_value=[]),
            patch.object(
                coordinator, "_gh", return_value=json.dumps({"body": body})
            ),
        ):
            auth = coordinator.authorize("o/r", 42, "infra")
        assert auth["scopes"] == ["infra"]

    def test_no_authorization_raises(self, in_tmp_project):
        with (
            patch.object(coordinator, "_issue_labels", return_value=["bug"]),
            patch.object(
                coordinator, "_gh", return_value=json.dumps({"body": "Fix the bug"})
            ),
            pytest.raises(coordinator.AuthorizationRejected),
        ):
            coordinator.authorize("o/r", 42, "infra")
        assert not Path(".maverick/session-auth.json").exists()

    def test_scopes_merge_for_same_issue(self, in_tmp_project):
        with patch.object(
            coordinator,
            "_issue_labels",
            side_effect=[["maverick-authorize-infra"], ["maverick-authorize-deps"]],
        ):
            coordinator.authorize("o/r", 42, "infra")
            auth = coordinator.authorize("o/r", 42, "deps")
        assert auth["scopes"] == ["deps", "infra"]

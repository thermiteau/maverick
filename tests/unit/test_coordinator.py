"""Tests for maverick.coordinator — pure-logic coverage.

Network-facing calls (claim, heartbeat, release) are not exercised here;
those live under tests/integration/. These tests cover the pure helpers:
instance-id stability, label/block detection, lease-liveness math,
payload shape.
"""

import os
from datetime import datetime, timedelta, timezone

from maverick import coordinator


class TestInstanceId:
    def test_stable_within_session(self, monkeypatch):
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        a = coordinator.instance_id()
        b = coordinator.instance_id()
        assert a == b
        assert len(a) == 10

    def test_respects_env_override(self, monkeypatch):
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "explicit-id")
        assert coordinator.instance_id() == "explicit-id"


class TestBlockLabel:
    def test_detects_block_label(self):
        assert coordinator._has_block_label(["some", "blocked-by:#42", "other"]) == "blocked-by:#42"

    def test_returns_none_when_no_block(self):
        assert coordinator._has_block_label(["feat", "enhancement"]) is None

    def test_first_block_wins(self):
        assert (
            coordinator._has_block_label(["blocked-by:#5", "blocked-by:#7"])
            == "blocked-by:#5"
        )


class TestLeaseLiveness:
    def test_future_expiry_is_live(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert coordinator._lease_is_live({"expires_at": future}) is True

    def test_past_expiry_is_dead(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert coordinator._lease_is_live({"expires_at": past}) is False

    def test_missing_expiry_is_dead(self):
        assert coordinator._lease_is_live({}) is False

    def test_malformed_expiry_is_dead(self):
        assert coordinator._lease_is_live({"expires_at": "not-a-date"}) is False


class TestClaimPayload:
    def test_claim_payload_shape(self):
        c = coordinator.Claim(
            repo="me/r",
            issue=42,
            instance_id="abc",
            host="h",
            scope=["42", "43"],
            claimed_at="2026-04-23T10:00:00Z",
        )
        p = c.to_payload()
        assert p["instance_id"] == "abc"
        assert p["host"] == "h"
        assert p["scope"] == ["42", "43"]
        assert p["claimed_at"] == "2026-04-23T10:00:00Z"

    def test_claimed_at_auto_fills(self):
        c = coordinator.Claim(repo="r", issue=1, instance_id="i", host="h")
        p = c.to_payload()
        assert p["claimed_at"].endswith("Z")


class TestConstants:
    def test_lease_ttl_minutes(self):
        assert coordinator.LEASE_TTL_MINUTES == 10

    def test_heartbeat_interval_minutes(self):
        assert coordinator.HEARTBEAT_INTERVAL_MINUTES == 2

    def test_claim_label(self):
        assert coordinator.CLAIM_LABEL == "claude-in-progress"


class TestFormatLeaseSummary:
    def test_live_lease(self):
        msg = coordinator.format_lease_summary(
            {"instance_id": "abc", "expires_at": "2026-04-23T10:00:00Z"}
        )
        assert "abc" in msg
        assert "2026-04-23T10:00:00Z" in msg

    def test_no_lease(self):
        assert coordinator.format_lease_summary(None) == "no lease"

    def test_partial_lease(self, monkeypatch):
        # Ensure we don't produce a non-deterministic instance id from env
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "ignored")
        # A lease that exists but is missing fields should still format cleanly.
        msg = coordinator.format_lease_summary({"released_at": "2026-04-23T10:00:00Z"})
        assert "unknown" in msg
        assert "?" in msg

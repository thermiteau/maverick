"""Tests for maverick.coordinator — pure-logic coverage.

Network-facing calls (claim, heartbeat, release) are exercised here only
with the gh-touching helpers monkeypatched out; full end-to-end coverage
lives under tests/integration/. These tests cover the pure helpers
(instance-id stability, label/block detection, lease-liveness math,
payload shape) plus the in-process race-detection logic.
"""

from datetime import datetime, timedelta, timezone

import pytest

from maverick import coordinator, gh_state


class TestInstanceId:
    def test_stable_within_session(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        a = coordinator.instance_id()
        b = coordinator.instance_id()
        assert a == b
        assert len(a) == 10

    def test_respects_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "explicit-id")
        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        assert coordinator.instance_id() == "explicit-id"

    def test_persists_across_processes(self, monkeypatch, tmp_path):
        """First call writes the id to disk; a fresh process (env cleared)
        reads the same id back. This is what protects heartbeat and
        claim-retry under per-call subprocess harnesses like Claude Code.
        """
        path = tmp_path / "instance_id"
        monkeypatch.setattr(coordinator, "_instance_id_path", lambda: path)

        # First "process": no env var, no file — generate and persist.
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        first = coordinator.instance_id()
        assert path.read_text() == first

        # Second "process": env var cleared, file present — read from file.
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        second = coordinator.instance_id()
        assert second == first

    def test_env_overrides_persisted_file(self, monkeypatch, tmp_path):
        """An explicit MAVERICK_INSTANCE_ID env var must win over a
        previously-persisted id, so callers can pin a specific instance
        for tests or recovery scenarios.
        """
        path = tmp_path / "instance_id"
        path.write_text("file-id")
        monkeypatch.setattr(coordinator, "_instance_id_path", lambda: path)
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "env-id")
        assert coordinator.instance_id() == "env-id"

    def test_persistence_failure_falls_back_to_env_cache(
        self, monkeypatch, tmp_path
    ):
        """If the persistence path is unwritable, the call still returns a
        stable id within the current process via env caching — it just
        won't survive subprocess boundaries on this run.
        """
        unwritable = tmp_path / "no-such-dir" / "instance_id"
        # Force the parent to be a file so mkdir(parents=True) fails.
        (tmp_path / "no-such-dir").write_text("blocking file")
        monkeypatch.setattr(coordinator, "_instance_id_path", lambda: unwritable)
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        a = coordinator.instance_id()
        b = coordinator.instance_id()
        assert a == b
        assert len(a) == 10
        assert not unwritable.exists()

    def test_derives_from_claude_session_id(self, monkeypatch, tmp_path):
        """#40: when CLAUDE_CODE_SESSION_ID is set, every subagent and
        subprocess within that session derives the same instance id
        deterministically, with no file write required — sidesteps the
        first-call file-cache race that produced multiple ids per session.
        """
        path = tmp_path / "instance_id"
        monkeypatch.setattr(coordinator, "_instance_id_path", lambda: path)
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-abc-123")

        first = coordinator.instance_id()

        # Fresh "process": clear the in-process env cache, the on-disk
        # cache is also intentionally absent.
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        second = coordinator.instance_id()

        assert first == second
        assert len(first) == 10
        assert not path.exists()

    def test_derives_from_legacy_session_id(self, monkeypatch, tmp_path):
        """Falls back to the legacy CLAUDE_SESSION_ID name when the current
        CLAUDE_CODE_SESSION_ID is absent (older Claude Code versions)."""
        path = tmp_path / "instance_id"
        monkeypatch.setattr(coordinator, "_instance_id_path", lambda: path)
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.setenv("CLAUDE_SESSION_ID", "legacy-session")

        first = coordinator.instance_id()
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        second = coordinator.instance_id()

        assert first == second
        assert len(first) == 10
        assert not path.exists()

    def test_current_session_id_wins_over_legacy(self, monkeypatch, tmp_path):
        """When both names are present the current CLAUDE_CODE_SESSION_ID is
        preferred, so behaviour is stable across the rename."""
        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "current")
        monkeypatch.setenv("CLAUDE_SESSION_ID", "legacy")
        both = coordinator.instance_id()

        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        current_only = coordinator.instance_id()

        assert both == current_only

    def test_distinct_sessions_derive_distinct_ids(self, monkeypatch, tmp_path):
        """Two concurrent Claude Code sessions on the same machine must
        present as distinct instances to the coordinator."""
        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-A")
        a = coordinator.instance_id()

        monkeypatch.delenv("MAVERICK_INSTANCE_ID", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-B")
        b = coordinator.instance_id()

        assert a != b

    def test_explicit_env_overrides_session_id(self, monkeypatch, tmp_path):
        """MAVERICK_INSTANCE_ID still wins over CLAUDE_CODE_SESSION_ID, so
        users can pin a specific id for recovery scenarios."""
        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "explicit")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "ignored")
        assert coordinator.instance_id() == "explicit"


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


@pytest.fixture
def stub_gh(monkeypatch):
    """Stub every gh-touching helper so claim()/takeover() can be exercised
    without network. Returns a dict the test can populate to control what
    find_markers returns at the read-after-write step."""
    state: dict = {"find_markers": []}

    monkeypatch.setattr(coordinator, "_gh", lambda *a, **k: "")
    monkeypatch.setattr(coordinator, "post_marker", lambda *a, **k: 1)
    monkeypatch.setattr(coordinator, "upsert_marker", lambda *a, **k: 1)
    # find_markers is imported function-locally inside claim(), so the
    # patch target is the gh_state module attribute.
    monkeypatch.setattr(
        gh_state, "find_markers", lambda *a, **k: state["find_markers"]
    )
    return state


def _marker(instance: str, comment_id: int, issue: int = 42) -> gh_state.Marker:
    return gh_state.Marker(
        kind="maverick-claim",
        payload={"instance_id": instance},
        comment_id=comment_id,
        issue_number=issue,
    )


def _expired_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


class TestClaimRaceDetection:
    """Issue #38 — race detection counted historical claim markers, so a
    fresh claim or takeover would lose to long-released holders. The fix
    only consults the latest marker, since GitHub assigns strictly-monotonic
    comment ids."""

    def test_historical_released_claims_do_not_block_new_claim(
        self, monkeypatch, stub_gh
    ):
        """Two prior holders released cleanly; we come in fresh. Pre-fix
        this rejected because lex-min picked one of the historical ids."""
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "z-newcomer")
        monkeypatch.setattr(coordinator, "_issue_labels", lambda *a, **k: [])
        monkeypatch.setattr(coordinator, "latest_marker", lambda *a, **k: None)
        stub_gh["find_markers"] = [
            _marker("a-old1", 1),
            _marker("b-old2", 2),
            _marker("z-newcomer", 3),
        ]

        c = coordinator.claim("me/r", 42)

        assert c.instance_id == "z-newcomer"

    def test_latest_marker_from_other_instance_rejects(
        self, monkeypatch, stub_gh
    ):
        """A concurrent instance posted after us — its marker is the
        latest, so we yield."""
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "us")
        monkeypatch.setattr(coordinator, "_issue_labels", lambda *a, **k: [])
        monkeypatch.setattr(coordinator, "latest_marker", lambda *a, **k: None)
        stub_gh["find_markers"] = [
            _marker("us", 5),
            _marker("them", 6),
        ]

        with pytest.raises(coordinator.ClaimRejected, match="superseded"):
            coordinator.claim("me/r", 42)

    def test_takeover_succeeds_against_accumulated_history(
        self, monkeypatch, stub_gh
    ):
        """Reproducer for #38: a stale lease from instance A, plus several
        historical claim markers from earlier failed attempts. A new
        instance B takes over. Pre-fix the historical-min check rejected
        because B was not lex-min; with the fix, only B's latest marker
        matters and the takeover succeeds."""
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "z-takeover")
        # Stale state read by both takeover() and the inner claim().
        fake_state = {
            "labels": [coordinator.CLAIM_LABEL],
            "block_label": None,
            "in_progress": True,
            "claim": {"instance_id": "a-stale"},
            "lease": {"instance_id": "a-stale", "expires_at": _expired_iso()},
            "lease_live": False,
        }
        monkeypatch.setattr(coordinator, "read_claim_state", lambda *a, **k: fake_state)
        # After the takeover post + claim post, the latest marker is ours.
        stub_gh["find_markers"] = [
            _marker("a-stale", 1, issue=3),
            _marker("b-prior-attempt", 2, issue=3),
            _marker("z-takeover", 3, issue=3),
            _marker("z-takeover", 4, issue=3),
        ]

        c = coordinator.takeover("me/r", 3)

        assert c.instance_id == "z-takeover"


class TestHeartbeatLoop:
    """#47: foreground loop self-terminates when the claim is released, so
    skills don't have to track and kill a backgrounded shell loop."""

    def test_exits_when_heartbeat_raises_claim_lost(self, monkeypatch):
        """Simulates `coord release` clearing the claim label — the next
        heartbeat raises ClaimLost and the loop returns 0."""
        calls = {"n": 0}

        def fake_heartbeat(repo, issue, env=None):
            calls["n"] += 1
            raise coordinator.ClaimLost("released")

        monkeypatch.setattr(coordinator, "heartbeat", fake_heartbeat)
        # Ensure no real sleeping happens.
        monkeypatch.setattr("time.sleep", lambda _s: None)

        rc = coordinator.heartbeat_loop("me/r", 42, interval_seconds=1)

        assert rc == 0
        assert calls["n"] == 1

    def test_loops_until_claim_lost(self, monkeypatch):
        """Heartbeats refresh on a live claim; loop exits once heartbeat
        signals the claim is gone."""
        results = iter([None, None, coordinator.ClaimLost("gone")])

        def fake_heartbeat(repo, issue, env=None):
            r = next(results)
            if isinstance(r, Exception):
                raise r

        monkeypatch.setattr(coordinator, "heartbeat", fake_heartbeat)
        monkeypatch.setattr("time.sleep", lambda _s: None)

        rc = coordinator.heartbeat_loop("me/r", 42, interval_seconds=1)

        assert rc == 0

    def test_restores_signal_handlers(self, monkeypatch):
        """SIGINT/SIGTERM handlers are restored on exit so the loop doesn't
        leak handler state into the parent process."""
        import signal

        original_int = signal.getsignal(signal.SIGINT)
        original_term = signal.getsignal(signal.SIGTERM)

        def fake_heartbeat(repo, issue, env=None):
            raise coordinator.ClaimLost("done")

        monkeypatch.setattr(coordinator, "heartbeat", fake_heartbeat)
        monkeypatch.setattr("time.sleep", lambda _s: None)

        coordinator.heartbeat_loop("me/r", 42, interval_seconds=1)

        assert signal.getsignal(signal.SIGINT) == original_int
        assert signal.getsignal(signal.SIGTERM) == original_term

    def test_cli_handler_forwards_to_loop(self, monkeypatch):
        """`coord heartbeat-loop` CLI handler delegates to coordinator.heartbeat_loop."""
        import argparse

        from maverick import coord_cli

        captured: dict = {}

        def fake_loop(repo, issue, *, interval_seconds):
            captured["repo"] = repo
            captured["issue"] = issue
            captured["interval_seconds"] = interval_seconds
            return 0

        monkeypatch.setattr(coord_cli.coordinator, "heartbeat_loop", fake_loop)
        args = argparse.Namespace(repo="me/r", issue=7, interval=5)

        rc = coord_cli._coord_heartbeat_loop(args)

        assert rc == 0
        assert captured == {"repo": "me/r", "issue": 7, "interval_seconds": 5}


class TestTaskProgressCli:
    """#41: `task-progress read|set` are the durability primitives that
    let do-issue-solo resume from a phase checkpoint instead of replaying
    work against an in-flight or merged PR."""

    def test_set_writes_marker_with_phase_and_instance_id(
        self, monkeypatch, tmp_path
    ):
        import argparse

        from maverick import coord_cli, gh_state, report_cli

        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "i-abc")

        captured: dict = {}

        def fake_upsert(repo, issue, kind, payload, preamble="", env=None):
            captured["repo"] = repo
            captured["issue"] = issue
            captured["kind"] = kind
            captured["payload"] = payload
            captured["preamble"] = preamble
            return 1

        monkeypatch.setattr(gh_state, "upsert_marker", fake_upsert)
        # Redirect the timeline append to a captured list so the test
        # doesn't litter the working tree's .maverick/reports/. The new
        # append_event signature takes a single typed event dict.
        timeline_events: list[dict] = []

        def fake_append(event, repo_root=None):
            timeline_events.append(event)
            return True

        monkeypatch.setattr(report_cli, "append_event", fake_append)

        args = argparse.Namespace(repo="me/r", issue=42, phase="review")

        rc = coord_cli._task_progress_set(args)

        assert rc == 0
        assert captured["repo"] == "me/r"
        assert captured["issue"] == 42
        assert captured["kind"] == "maverick-task-progress"
        assert captured["payload"]["phase"] == "review"
        assert captured["payload"]["instance_id"] == "i-abc"
        assert captured["payload"]["updated_at"].endswith("Z")
        assert "task-progress" in captured["preamble"]
        # task-progress set must also append a phase-boundary event to
        # the local timeline JSONL so the report generator can
        # reconstruct per-phase timestamps.
        assert len(timeline_events) == 1
        assert timeline_events[0]["action"] == "phase-boundary"
        assert timeline_events[0]["phase"] == "review"
        assert timeline_events[0]["issue"] == 42
        assert timeline_events[0]["issue"] == 42

    def test_set_stamps_llm_on_phase_boundary_event(self, monkeypatch, tmp_path):
        """The phase-boundary event must carry an `llm` field resolved via
        `_current_llm` (#98). Without it, the renderer falls back to the
        literal FALLBACK_LLM ("claude-code") whenever a phase contains no
        agent-dispatch sibling to inherit from — surfaced as misleading
        `claude-code` cells on the LLM column for phases like Phase 8
        ("open PR" / "CI green") and the final Phase 10 ("complete")."""
        import argparse

        from maverick import coord_cli, gh_state, report_cli

        monkeypatch.setattr(
            coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
        )
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "i-llm")
        # Distinctive sentinel so the assertion proves the resolver ran,
        # rather than coincidentally matching the baked-in default.
        monkeypatch.setenv("MAVERICK_LLM", "test-sentinel-llm")
        monkeypatch.setattr(gh_state, "upsert_marker", lambda *a, **k: 1)

        timeline_events: list[dict] = []
        monkeypatch.setattr(
            report_cli, "append_event", lambda e, repo_root=None: timeline_events.append(e) or True
        )

        rc = coord_cli._task_progress_set(
            argparse.Namespace(repo="me/r", issue=42, phase="pr_open")
        )

        assert rc == 0
        assert len(timeline_events) == 1
        assert timeline_events[0]["llm"] == "test-sentinel-llm"

    def test_read_returns_latest_marker_payload(self, monkeypatch):
        import argparse

        from maverick import coord_cli, gh_state

        fake_marker = gh_state.Marker(
            kind="maverick-task-progress",
            payload={"phase": "review", "instance_id": "x"},
            comment_id=99,
            issue_number=42,
        )
        monkeypatch.setattr(gh_state, "latest_marker", lambda *a, **k: fake_marker)
        args = argparse.Namespace(repo="me/r", issue=42)

        rc = coord_cli._task_progress_read(args)

        assert rc == 0

    def test_read_returns_none_when_no_marker(self, monkeypatch):
        import argparse

        from maverick import coord_cli, gh_state

        monkeypatch.setattr(gh_state, "latest_marker", lambda *a, **k: None)
        args = argparse.Namespace(repo="me/r", issue=42)

        rc = coord_cli._task_progress_read(args)

        assert rc == 0

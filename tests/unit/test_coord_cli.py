"""Argparse-level tests for the coord/worktree/gh-app CLI surface.

Covers the small papercut fixes from Wave 2 (#42, #43, #44, #45):
the `coord status` alias, the `gh-app gh -- <args>` separator handling,
the `worktree destroy --force` default, and the `coord takeover`
--scope/--reason flags. Handlers are stubbed so we can assert what
arguments would have been forwarded without hitting the network.
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from maverick import coord_cli


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    coord_cli.build_subparsers(sub)
    return parser.parse_args(list(argv))


class TestCoordStatusAlias:
    """#43: `coord status` is an alias for `coord read`."""

    def test_status_dispatches_to_read_handler(self):
        args = _parse("coord", "status", "owner/repo", "42")
        assert args._handler is coord_cli._coord_read
        assert args.repo == "owner/repo"
        assert args.issue == 42

    def test_read_still_works(self):
        args = _parse("coord", "read", "owner/repo", "42")
        assert args._handler is coord_cli._coord_read


class TestGhAppGhSeparator:
    """#44: `gh-app gh -- <args>` and `gh-app gh <args>` produce the same
    downstream `gh` invocation. argparse.REMAINDER captures the literal
    `--` as the first element, so the handler must strip it."""

    def test_strips_leading_double_dash(self, monkeypatch):
        captured: dict = {}

        def fake_gh_app_gh(*args):
            captured["args"] = args
            r = MagicMock()
            r.stdout = ""
            r.stderr = ""
            r.returncode = 0
            return r

        monkeypatch.setattr(coord_cli.gh_app, "gh_app_gh", fake_gh_app_gh)
        args = _parse("gh-app", "gh", "--", "issue", "comment", "42", "--body", "hi")

        coord_cli._gh_app_gh(args)

        assert captured["args"] == ("issue", "comment", "42", "--body", "hi")

    def test_without_double_dash_unchanged(self, monkeypatch):
        captured: dict = {}

        def fake_gh_app_gh(*args):
            captured["args"] = args
            r = MagicMock()
            r.stdout = ""
            r.stderr = ""
            r.returncode = 0
            return r

        monkeypatch.setattr(coord_cli.gh_app, "gh_app_gh", fake_gh_app_gh)
        args = _parse("gh-app", "gh", "issue", "comment", "42", "--body", "hi")

        coord_cli._gh_app_gh(args)

        assert captured["args"] == ("issue", "comment", "42", "--body", "hi")

    def test_only_first_double_dash_stripped(self, monkeypatch):
        """A `--` deeper in the arg list (e.g. as a value) must NOT be stripped."""
        captured: dict = {}

        def fake_gh_app_gh(*args):
            captured["args"] = args
            r = MagicMock()
            r.stdout = ""
            r.stderr = ""
            r.returncode = 0
            return r

        monkeypatch.setattr(coord_cli.gh_app, "gh_app_gh", fake_gh_app_gh)
        args = _parse("gh-app", "gh", "--", "api", "--", "/repos/x/y")

        coord_cli._gh_app_gh(args)

        assert captured["args"] == ("api", "--", "/repos/x/y")


class TestGhAppGhStderrRelay:
    """#56: when `gh` exits non-zero the wrapper must surface gh's own
    stderr (so the operator sees `unknown flag --foo` etc.) and return
    gh's exit code — not bury it under a Python CalledProcessError."""

    def test_nonzero_exit_relays_stderr_and_returncode(self, monkeypatch, capsys):
        def fake_gh_app_gh(*args):
            r = MagicMock()
            r.stdout = ""
            r.stderr = "gh: unknown flag --bogus\n"
            r.returncode = 1
            return r

        monkeypatch.setattr(coord_cli.gh_app, "gh_app_gh", fake_gh_app_gh)
        args = _parse("gh-app", "gh", "--", "issue", "comment", "42", "--bogus")

        rc = coord_cli._gh_app_gh(args)

        captured = capsys.readouterr()
        assert rc == 1
        assert "gh: unknown flag --bogus" in captured.err


class TestWorktreeDestroyForce:
    """#45: destroy is force-by-default; --no-force opts out."""

    def test_force_default_true(self):
        args = _parse("worktree", "destroy", ".maverick/worktrees/foo")
        assert args.force is True

    def test_no_force_opts_out(self):
        args = _parse("worktree", "destroy", "--no-force", ".maverick/worktrees/foo")
        assert args.force is False

    def test_explicit_force_still_accepted(self):
        args = _parse("worktree", "destroy", "--force", ".maverick/worktrees/foo")
        assert args.force is True


class TestCoordTakeoverFlags:
    """#42: takeover accepts --scope (CSV) and --reason (audit-trail note)."""

    def test_takeover_accepts_scope_and_reason(self):
        args = _parse(
            "coord",
            "takeover",
            "owner/repo",
            "3",
            "--scope",
            "3,28,30,32",
            "--reason",
            "previous lease expired 2026-05-01T12:34:11Z",
        )
        assert args.repo == "owner/repo"
        assert args.issue == 3
        assert args.scope == "3,28,30,32"
        assert args.reason == "previous lease expired 2026-05-01T12:34:11Z"

    def test_takeover_flags_are_optional(self):
        args = _parse("coord", "takeover", "owner/repo", "3")
        assert args.scope is None
        assert args.reason is None

    def test_handler_forwards_scope_and_reason(self, monkeypatch):
        """The handler splits scope on commas and forwards both flags to
        coordinator.takeover()."""
        captured: dict = {}

        class FakeClaim:
            def to_payload(self):
                return {"ok": True}

        def fake_takeover(repo, issue, *, scope=None, reason=None):
            captured["repo"] = repo
            captured["issue"] = issue
            captured["scope"] = scope
            captured["reason"] = reason
            return FakeClaim()

        monkeypatch.setattr(coord_cli.coordinator, "takeover", fake_takeover)
        args = _parse(
            "coord", "takeover", "owner/repo", "3",
            "--scope", "3,28,30",
            "--reason", "stale",
        )

        rc = coord_cli._coord_takeover(args)

        assert rc == 0
        assert captured == {
            "repo": "owner/repo",
            "issue": 3,
            "scope": ["3", "28", "30"],
            "reason": "stale",
        }


class TestCoordTakeoverCoordinatorAPI:
    """#42 at the library level: coordinator.takeover() must accept and
    plumb through scope and reason without hitting the network."""

    def test_scope_forwarded_and_reason_recorded(self, monkeypatch):
        from maverick import coordinator, gh_state

        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "us")
        # Stale lease, prior holder is 'a-stale'.
        from datetime import datetime, timedelta, timezone
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        fake_state = {
            "labels": [coordinator.CLAIM_LABEL],
            "block_label": None,
            "in_progress": True,
            "claim": {"instance_id": "a-stale"},
            "lease": {"instance_id": "a-stale", "expires_at": expired},
            "lease_live": False,
        }
        monkeypatch.setattr(coordinator, "read_claim_state", lambda *a, **k: fake_state)
        monkeypatch.setattr(coordinator, "_issue_labels", lambda *a, **k: [])
        monkeypatch.setattr(coordinator, "latest_marker", lambda *a, **k: None)
        monkeypatch.setattr(coordinator, "_gh", lambda *a, **k: "")
        monkeypatch.setattr(coordinator, "upsert_marker", lambda *a, **k: 1)
        monkeypatch.setattr(
            gh_state,
            "find_markers",
            lambda *a, **k: [
                gh_state.Marker(
                    kind="maverick-claim",
                    payload={"instance_id": "us"},
                    comment_id=1,
                    issue_number=3,
                )
            ],
        )

        posted: list[dict] = []

        def fake_post_marker(repo, issue, kind, payload, preamble="", env=None):
            posted.append({"kind": kind, "payload": payload, "preamble": preamble})
            return 1

        monkeypatch.setattr(coordinator, "post_marker", fake_post_marker)

        c = coordinator.takeover(
            "me/r", 3, scope=["3", "28", "30"], reason="prior lease expired"
        )

        # scope landed on the resulting claim object via the inner claim() call.
        assert c.scope == ["3", "28", "30"]
        # The takeover-marker payload includes reason + takeover_of.
        takeover_marker = posted[0]
        assert takeover_marker["payload"]["takeover_of"] == "a-stale"
        assert takeover_marker["payload"]["reason"] == "prior lease expired"
        # And the audit-trail preamble carries the reason.
        assert "prior lease expired" in takeover_marker["preamble"]


@pytest.fixture(autouse=True)
def _no_instance_id_persistence(monkeypatch, tmp_path):
    """Keep these tests from touching the user's real ~/.maverick/instance_id."""
    from maverick import coordinator

    monkeypatch.setattr(
        coordinator, "_instance_id_path", lambda: tmp_path / "instance_id"
    )

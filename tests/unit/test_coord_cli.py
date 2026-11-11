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


class TestReleaseFinalisesReport:
    """Every exit path releases the claim, so release writes the report —
    runs that halted before their own `report generate` step still get one."""

    def test_release_generates_report(self, monkeypatch, tmp_path, capsys):
        from maverick import coordinator, report_cli

        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        monkeypatch.setattr(report_cli, "_fetch_pr", lambda repo, issue: None)
        monkeypatch.setattr(report_cli, "_session_model", lambda: None)
        monkeypatch.setattr(coordinator, "release", MagicMock())
        monkeypatch.setenv("MAVERICK_INSTANCE_ID", "i-1")
        report_cli._report_run_start(
            argparse.Namespace(skill="do-issue-solo", issue=7, phase="claimed", llm="m")
        )

        args = _parse("coord", "release", "o/r", "7", "--reason", "blocked")
        assert args._handler(args) == 0
        out = capsys.readouterr().out
        assert "released" in out
        report = report_cli.report_path(7, repo_root=tmp_path)
        assert report.exists()
        assert f"report: {report}" in out

    def test_no_timeline_is_silent(self, monkeypatch, tmp_path, capsys):
        from maverick import coordinator, report_cli

        monkeypatch.setattr(report_cli, "_main_repo_root", lambda cwd=None: tmp_path)
        monkeypatch.setattr(coordinator, "release", MagicMock())
        args = _parse("coord", "release", "o/r", "100")
        assert args._handler(args) == 0
        assert "report:" not in capsys.readouterr().out

    def test_no_report_flag(self, monkeypatch):
        from maverick import report_cli

        called = MagicMock()
        monkeypatch.setattr(report_cli, "finalise_report", called)
        monkeypatch.setattr(coord_cli.coordinator, "release", MagicMock())
        args = _parse("coord", "release", "o/r", "7", "--no-report")
        assert args._handler(args) == 0
        called.assert_not_called()


class TestChecksRunBase:
    def test_base_reads_trusted_config(self, monkeypatch):
        from maverick import config, workflow_verbs

        seen: dict = {}
        monkeypatch.setattr(
            config, "checks_config_at_ref",
            lambda ref, repo_root=None: seen.setdefault("ref", ref) and {"commands": ["true"]},
        )
        monkeypatch.setattr(
            config, "read_checks_config",
            lambda path=None: pytest.fail("working-tree config must not be read with --base"),
        )
        monkeypatch.setattr(
            workflow_verbs, "checks_run",
            lambda commands, timeout=600: [{"command": c, "ok": True, "exit": 0, "output": ""} for c in commands],
        )
        monkeypatch.setattr(
            config, "fetch_trusted_base", lambda base, repo_root=None: f"refs/maverick/trusted-base/{base}"
        )
        args = _parse("checks", "run", "--base", "main")
        assert args._handler(args) == 0
        assert seen["ref"] == "refs/maverick/trusted-base/main"

    def test_unreadable_trusted_config_fails_closed(self, monkeypatch, capsys):
        from maverick import config, workflow_verbs

        def boom(base, repo_root=None):
            raise config.ConfigRefError("could not fetch origin/main")

        monkeypatch.setattr(config, "fetch_trusted_base", boom)
        monkeypatch.setattr(
            workflow_verbs, "checks_run", lambda *a, **k: pytest.fail("no checks may run")
        )
        args = _parse("checks", "run", "--base", "main")
        assert args._handler(args) == 2
        assert "cannot read the trusted config" in capsys.readouterr().err

    def test_no_fetch_reads_local_origin_ref(self, monkeypatch):
        from maverick import config, workflow_verbs

        seen: list[str] = []
        monkeypatch.setattr(
            config, "fetch_trusted_base", lambda *a, **k: pytest.fail("must not fetch")
        )
        monkeypatch.setattr(
            config, "checks_config_at_ref",
            lambda ref, repo_root=None: seen.append(ref) or {"commands": []},
        )
        monkeypatch.setattr(workflow_verbs, "checks_run", lambda *a, **k: [])
        args = _parse("checks", "run", "--base", "main", "--no-fetch")
        assert args._handler(args) == 0
        assert seen == ["origin/main"]


class TestGhStateWritePayloadStdin:
    """#159: `--payload-file -` reads the payload from stdin so callers never
    stage it in a shared /tmp path that concurrent runs can overwrite."""

    def test_reads_payload_from_stdin(self, monkeypatch, capsys):
        import io

        seen: dict = {}

        def fake_upsert(repo, issue, kind, payload, preamble=None):
            seen.update(repo=repo, issue=issue, kind=kind, payload=payload)
            return 42

        monkeypatch.setattr(coord_cli.gh_state, "upsert_marker", fake_upsert)
        monkeypatch.setattr("sys.stdin", io.StringIO('{"stories": {}}'))
        args = _parse(
            "gh-state", "write", "o/r", "7", "maverick-dag", "--payload-file", "-"
        )
        assert args._handler(args) == 0
        assert seen["payload"] == {"stories": {}}
        assert '"comment_id": 42' in capsys.readouterr().out

    def test_invalid_stdin_payload_exits_2(self, monkeypatch, capsys):
        import io

        monkeypatch.setattr(
            coord_cli.gh_state, "upsert_marker", lambda *a, **k: pytest.fail("no write")
        )
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        args = _parse(
            "gh-state", "write", "o/r", "7", "maverick-dag", "--payload-file", "-"
        )
        assert args._handler(args) == 2
        assert "cannot read payload" in capsys.readouterr().err


class TestTaskProgressCompletedAlias:
    """#160: `completed` is accepted and stored as the `complete` phase, so
    worktree-isolated agents never need the bare token their guard refuses."""

    def test_completed_is_stored_as_complete(self, monkeypatch):
        seen: dict = {}

        def fake_patch(repo, issue, updates):
            seen.update(updates)
            return {**updates}

        monkeypatch.setattr(coord_cli.gh_state, "patch_task_progress", fake_patch)
        monkeypatch.setattr(coord_cli.coordinator, "instance_id", lambda: "abc")
        from maverick import report_cli

        events: list = []
        monkeypatch.setattr(report_cli, "append_event", events.append)
        args = _parse("task-progress", "set", "o/r", "7", "completed")
        assert args._handler(args) == 0
        assert seen["phase"] == "complete"
        assert [e["phase"] for e in events] == ["complete"]

    def test_complete_still_accepted(self):
        args = _parse("task-progress", "set", "o/r", "7", "complete")
        assert args.phase == "complete"


class TestIssueCommentBodySafety:
    """#159: refuse a body written for another issue, and delete staged
    `.maverick/tmp/` body files once posted."""

    @staticmethod
    def _fake_post(monkeypatch, sink):
        def fake(repo, issue, kind, body):
            sink.append(body)
            return 99

        monkeypatch.setattr(coord_cli.workflow_verbs, "comment_post", fake)

    def test_foreign_heading_is_refused(self, monkeypatch, tmp_path, capsys):
        posted: list = []
        self._fake_post(monkeypatch, posted)
        body = tmp_path / "design-542.md"
        body.write_text("## Solution design: other story (#906)\n\nbody\n")
        args = _parse(
            "issue", "comment", "post", "o/r", "542",
            "--kind", "design", "--body-file", str(body),
        )
        assert args._handler(args) == 2
        assert posted == []
        assert "#906" in capsys.readouterr().err

    def test_matching_heading_posts(self, monkeypatch, tmp_path):
        posted: list = []
        self._fake_post(monkeypatch, posted)
        body = tmp_path / "design-542.md"
        body.write_text("## Solution design: export (#542, epic #10)\n\nbody\n")
        args = _parse(
            "issue", "comment", "post", "o/r", "542",
            "--kind", "design", "--body-file", str(body),
        )
        assert args._handler(args) == 0
        assert len(posted) == 1
        assert body.exists()  # outside .maverick/tmp: left alone

    def test_heading_without_issue_ref_posts(self, monkeypatch, tmp_path):
        posted: list = []
        self._fake_post(monkeypatch, posted)
        body = tmp_path / "b.md"
        body.write_text("## Tasks\n\n- [ ] one\n")
        args = _parse(
            "issue", "comment", "post", "o/r", "5",
            "--kind", "tasks", "--body-file", str(body),
        )
        assert args._handler(args) == 0

    def test_staged_body_is_deleted_after_post(self, monkeypatch, tmp_path):
        posted: list = []
        self._fake_post(monkeypatch, posted)
        staged = tmp_path / ".maverick" / "tmp" / "design-542.md"
        staged.parent.mkdir(parents=True)
        staged.write_text("## Solution design: x (#542)\n")
        args = _parse(
            "issue", "comment", "post", "o/r", "542",
            "--kind", "design", "--body-file", str(staged),
        )
        assert args._handler(args) == 0
        assert not staged.exists()

    def test_missing_body_file_exits_2(self, monkeypatch, tmp_path, capsys):
        self._fake_post(monkeypatch, [])
        args = _parse(
            "issue", "comment", "post", "o/r", "1",
            "--kind", "design", "--body-file", str(tmp_path / "nope.md"),
        )
        assert args._handler(args) == 2
        assert "cannot read --body-file" in capsys.readouterr().err

"""Tests for the deterministic workflow verbs (C2) and the task-progress
payload helpers (C1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick import gh_state, workflow_verbs
from maverick.gh_state import Marker

# ---------------------------------------------------------------------------
# C1 — patch_task_progress merge semantics
# ---------------------------------------------------------------------------


class TestPatchTaskProgress:
    def _existing(self, payload):
        return Marker(
            kind="maverick-task-progress", payload=payload, comment_id=7, issue_number=42
        )

    def test_merges_comments_keywise(self):
        existing = self._existing(
            {"phase": "design", "comments": {"design": 100}, "branch": "feat/42-x"}
        )
        with (
            patch.object(gh_state, "latest_marker", return_value=existing),
            patch.object(gh_state, "upsert_marker") as upsert,
        ):
            merged = gh_state.patch_task_progress(
                "o/r", 42, {"phase": "tasks", "comments": {"tasks": 200}}
            )
        assert merged["comments"] == {"design": 100, "tasks": 200}
        assert merged["phase"] == "tasks"
        assert merged["branch"] == "feat/42-x"  # accreted field preserved
        assert upsert.call_args[0][3] is merged

    def test_from_scratch(self):
        with (
            patch.object(gh_state, "latest_marker", return_value=None),
            patch.object(gh_state, "upsert_marker"),
        ):
            merged = gh_state.patch_task_progress("o/r", 42, {"phase": "claimed"})
        assert merged == {"phase": "claimed"}


# ---------------------------------------------------------------------------
# resume-point
# ---------------------------------------------------------------------------


class TestResumePoint:
    def _run(self, payload, pr=None, details=None):
        with (
            patch.object(gh_state, "read_task_progress", return_value=payload),
            patch.object(workflow_verbs, "_find_pr", return_value=pr),
            patch.object(workflow_verbs, "_pr_details", return_value=details or {}),
        ):
            return workflow_verbs.resume_point("o/r", 42)

    def test_no_marker_starts_fresh(self):
        result = self._run({})
        assert result["next"] == "understand"

    def test_phase_only_rows(self):
        assert self._run({"phase": "design"})["next"] == "tasks"
        assert self._run({"phase": "tasks"})["next"] == "branch"
        assert self._run({"phase": "branch"})["next"] == "implement"
        assert self._run({"phase": "docs"})["next"] == "security"
        assert self._run({"phase": "security"})["next"] == "pr_open"
        assert self._run({"phase": "ejected"})["next"] == "ejected"

    def test_merged_pr_resumes_cleanup(self):
        result = self._run(
            {"phase": "review", "branch": "feat/42-x"},
            pr={"number": 9, "state": "MERGED", "url": "u"},
        )
        assert result["next"] == "merged"
        assert "Phase 10" in result["instruction"]

    def test_complete_with_merged_pr_is_done(self):
        result = self._run(
            {"phase": "complete", "branch": "feat/42-x"},
            pr={"number": 9, "state": "MERGED", "url": "u"},
        )
        assert result["next"] == "complete"

    def test_open_pr_failing_checks(self):
        result = self._run(
            {"phase": "pr_open", "branch": "b"},
            pr={"number": 9, "state": "OPEN", "url": "u"},
            details={"statusCheckRollup": [{"conclusion": "FAILURE"}]},
        )
        assert result["next"] == "ci_green"
        assert "fix" in result["instruction"]

    def test_open_pr_pending_checks_waits(self):
        result = self._run(
            {"phase": "pr_open", "branch": "b"},
            pr={"number": 9, "state": "OPEN", "url": "u"},
            details={"statusCheckRollup": [{"state": "PENDING"}]},
        )
        assert "pr wait" in result["instruction"]

    def test_open_pr_green_no_verdict_reviews(self):
        result = self._run(
            {"phase": "ci_green", "branch": "b"},
            pr={"number": 9, "state": "OPEN", "url": "u"},
            details={"statusCheckRollup": [{"conclusion": "SUCCESS"}], "reviews": []},
        )
        assert result["next"] == "review"

    def test_open_pr_fail_verdict_ejects(self):
        result = self._run(
            {"phase": "review", "branch": "b"},
            pr={"number": 9, "state": "OPEN", "url": "u"},
            details={
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                "reviews": [{"body": "## Verdict: FAIL\n\nMAVERICK_VERDICT: FAIL"}],
            },
        )
        assert result["next"] == "ejected"

    def test_latest_verdict_wins(self):
        result = self._run(
            {"phase": "review", "branch": "b"},
            pr={"number": 9, "state": "OPEN", "url": "u"},
            details={
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                "reviews": [{"body": "MAVERICK_VERDICT: FAIL"}],
                "comments": [{"body": "re-reviewed\n\nMAVERICK_VERDICT: PASS"}],
            },
        )
        assert result["next"] == "merged"

    def test_closed_pr_flags_investigation(self):
        result = self._run(
            {"phase": "pr_open", "branch": "b"},
            pr={"number": 9, "state": "CLOSED", "url": "u"},
        )
        assert result["next"] == "ejected"
        assert "investigate" in result["instruction"]


# ---------------------------------------------------------------------------
# tasks check
# ---------------------------------------------------------------------------

TASKS_BODY = """## Tasks

- [ ] First task
- [x] Second task (done)
- [ ] Third task

Footer text.
"""


class TestTasksCheck:
    def _run(self, n, payload=None, body=TASKS_BODY):
        calls = []

        def fake_gh(*args, env=None):
            calls.append(args)
            if args[0] == "api" and "--method" not in args:
                return json.dumps({"body": body})
            return "{}"

        with (
            patch.object(
                gh_state,
                "read_task_progress",
                return_value=payload
                if payload is not None
                else {"comments": {"tasks": 555}},
            ),
            patch.object(workflow_verbs, "_gh", side_effect=fake_gh),
            patch.object(workflow_verbs, "_app_env", return_value=None),
        ):
            result = workflow_verbs.tasks_check("o/r", 42, n)
        return result, calls

    def test_checks_nth_unchecked(self):
        result, calls = self._run(1)
        assert result == {"task": 1, "text": "First task", "status": "checked"}
        patch_call = [c for c in calls if "--method" in c][0]
        body_arg = [a for a in patch_call if a.startswith("body=")][0]
        assert "- [x] First task" in body_arg
        assert "- [ ] Third task" in body_arg  # untouched

    def test_already_checked_is_noop(self):
        result, calls = self._run(2)
        assert result["status"] == "already-checked"
        assert not [c for c in calls if "--method" in c]  # no PATCH

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="3 checkbox"):
            self._run(9)

    def test_missing_tasks_comment_raises(self):
        with pytest.raises(workflow_verbs.TasksCommentMissing):
            self._run(1, payload={})


# ---------------------------------------------------------------------------
# issue comments
# ---------------------------------------------------------------------------


class TestComments:
    def test_post_records_id_in_marker(self):
        with (
            patch.object(workflow_verbs, "_gh", return_value=json.dumps({"id": 777})),
            patch.object(workflow_verbs, "_app_env", return_value=None),
            patch.object(gh_state, "patch_task_progress") as patch_tp,
        ):
            cid = workflow_verbs.comment_post("o/r", 42, "design", "## Design")
        assert cid == 777
        assert patch_tp.call_args[0][2] == {"comments": {"design": 777}}

    def test_post_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="unknown comment kind"):
            workflow_verbs.comment_post("o/r", 42, "musings", "x")

    def test_update_requires_recorded_id(self):
        with patch.object(gh_state, "read_task_progress", return_value={}):
            with pytest.raises(ValueError, match="post it first"):
                workflow_verbs.comment_update("o/r", 42, "plan", "x")

    def test_update_patches_recorded_comment(self):
        with (
            patch.object(
                gh_state, "read_task_progress", return_value={"comments": {"plan": 888}}
            ),
            patch.object(workflow_verbs, "_gh") as gh,
            patch.object(workflow_verbs, "_app_env", return_value=None),
        ):
            cid = workflow_verbs.comment_update("o/r", 42, "plan", "new body")
        assert cid == 888
        assert "repos/o/r/issues/comments/888" in gh.call_args[0]


# ---------------------------------------------------------------------------
# pr wait
# ---------------------------------------------------------------------------


class TestPrWait:
    def _run(self, responses, until="merged", timeout=100):
        views = iter(responses)

        def fake_gh(*args, env=None):
            return json.dumps(next(views))

        slept = []
        with patch.object(workflow_verbs, "_gh", side_effect=fake_gh):
            code = workflow_verbs.pr_wait(
                "o/r", "9", until, timeout, interval_seconds=1, _sleep=slept.append
            )
        return code, slept

    def test_merged(self):
        code, _ = self._run([{"state": "OPEN"}, {"state": "MERGED"}])
        assert code == workflow_verbs.PR_WAIT_OK

    def test_closed(self):
        code, _ = self._run([{"state": "CLOSED"}])
        assert code == workflow_verbs.PR_WAIT_CLOSED

    def test_checks_green(self):
        code, _ = self._run(
            [{"state": "OPEN", "statusCheckRollup": [{"conclusion": "SUCCESS"}]}],
            until="checks",
        )
        assert code == workflow_verbs.PR_WAIT_OK

    def test_checks_failed(self):
        code, _ = self._run(
            [{"state": "OPEN", "statusCheckRollup": [{"conclusion": "FAILURE"}]}],
            until="checks",
        )
        assert code == workflow_verbs.PR_WAIT_CHECKS_FAILED

    def test_timeout(self):
        code, _ = self._run([{"state": "OPEN"}], timeout=0)
        assert code == workflow_verbs.PR_WAIT_TIMEOUT

    def test_parse_duration(self):
        assert workflow_verbs.parse_duration("90") == 90
        assert workflow_verbs.parse_duration("90s") == 90
        assert workflow_verbs.parse_duration("30m") == 1800
        assert workflow_verbs.parse_duration("2h") == 7200
        with pytest.raises(ValueError):
            workflow_verbs.parse_duration("soon")


# ---------------------------------------------------------------------------
# docs shortlist
# ---------------------------------------------------------------------------


class TestDocsShortlist:
    def test_terms_and_matching(self, tmp_path: Path):
        repo = tmp_path / "repo"
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "exporter.md").write_text("The CsvExporter handles exports.")
        (repo / "docs" / "unrelated.md").write_text("Nothing relevant here.")
        (repo / "node_modules" / "docs").mkdir(parents=True)
        (repo / "node_modules" / "docs" / "junk.md").write_text("CsvExporter")

        diff = (
            "diff --git a/src/export.py b/src/export.py\n"
            "--- a/src/export.py\n"
            "+++ b/src/export.py\n"
            "+class CsvExporter:\n"
            "+    pass\n"
        )
        out = tmp_path / "out"
        with patch.object(
            workflow_verbs,
            "_git",
            side_effect=[diff, "src/export.py\n"],
        ):
            result = workflow_verbs.docs_shortlist("main", repo_root=repo, out_dir=out)

        docs = [Path(d).name for d in result["docs"]]
        assert "exporter.md" in docs
        assert "unrelated.md" not in docs
        assert "junk.md" not in docs  # node_modules excluded
        assert (out / "diff.patch").read_text() == diff
        assert "src/export.py" in (out / "changed-paths.txt").read_text()

    def test_empty_shortlist_is_valid(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        out = tmp_path / "out"
        with patch.object(workflow_verbs, "_git", side_effect=["", ""]):
            result = workflow_verbs.docs_shortlist("main", repo_root=repo, out_dir=out)
        assert result["docs"] == []
        assert (out / "doc-shortlist.txt").read_text() == ""


# ---------------------------------------------------------------------------
# bprop run
# ---------------------------------------------------------------------------


class TestBpropRun:
    def _fake_dag(self, descendants):
        class FakeDag:
            def transitive_descendants(self, story):
                return set(descendants)

        return FakeDag()

    def test_walk_labels_and_clears(self):
        gh_calls = []

        def fake_gh(*args, env=None):
            gh_calls.append(args)
            if args[0] == "issue" and args[1] == "view":
                return json.dumps({"labels": []})
            return "{}"

        from maverick import dag as dag_mod
        from maverick import epic_state

        with (
            patch.object(dag_mod, "load_dag", return_value=self._fake_dag(["150", "160"])),
            patch.object(epic_state, "hydrate_from_gh", return_value=None),
            patch.object(epic_state, "transition"),
            patch.object(gh_state, "latest_marker", return_value=None),
            patch.object(gh_state, "upsert_marker", return_value=31) as upsert,
            patch.object(gh_state, "update_marker") as update,
            patch.object(gh_state, "delete_marker_comment") as delete,
            patch.object(workflow_verbs, "_gh", side_effect=fake_gh),
            patch.object(workflow_verbs, "_app_env", return_value=None),
        ):
            result = workflow_verbs.bprop_run("o/r", 100, 142)

        assert result["labelled"] == ["150", "160"]
        # Label applied + comment posted per story
        label_edits = [c for c in gh_calls if c[:2] == ("issue", "edit")]
        assert len(label_edits) == 2
        assert all("blocked-by:#142" in c for c in label_edits)
        comments = [c for c in gh_calls if c[:2] == ("issue", "comment")]
        assert len(comments) == 2
        # Marker updated after each story, then cleared
        assert update.call_count == 2
        delete.assert_called_once_with("o/r", 31)
        assert upsert.call_args[0][2] == "maverick-bprop"

    def test_resume_skips_already_labelled(self):
        gh_calls = []

        def fake_gh(*args, env=None):
            gh_calls.append(args)
            if args[0] == "issue" and args[1] == "view":
                return json.dumps({"labels": [{"name": "blocked-by:#142"}]})
            return "{}"

        from maverick import dag as dag_mod
        from maverick import epic_state

        in_flight = Marker(
            kind="maverick-bprop",
            payload={
                "ejected": "142",
                "descendants": ["150", "160"],
                "labelled": ["150"],
                "started_at": "x",
            },
            comment_id=31,
            issue_number=100,
        )
        with (
            patch.object(dag_mod, "load_dag", return_value=self._fake_dag(["150", "160"])),
            patch.object(epic_state, "hydrate_from_gh", return_value=None),
            patch.object(epic_state, "transition"),
            patch.object(gh_state, "latest_marker", return_value=in_flight),
            patch.object(gh_state, "upsert_marker", return_value=31),
            patch.object(gh_state, "update_marker"),
            patch.object(gh_state, "delete_marker_comment") as delete,
            patch.object(workflow_verbs, "_gh", side_effect=fake_gh),
            patch.object(workflow_verbs, "_app_env", return_value=None),
        ):
            result = workflow_verbs.bprop_run("o/r", 100, 142)

        # 150 was already labelled (skipped); 160 already carries the label
        # on GitHub, so no edit and no comment — just marker bookkeeping.
        assert result["labelled"] == ["150", "160"]
        assert not [c for c in gh_calls if c[:2] == ("issue", "edit")]
        assert not [c for c in gh_calls if c[:2] == ("issue", "comment")]
        delete.assert_called_once()

    def test_missing_dag_raises(self):
        from maverick import dag as dag_mod

        with (
            patch.object(dag_mod, "load_dag", return_value=None),
            pytest.raises(RuntimeError, match="no maverick-dag"),
        ):
            workflow_verbs.bprop_run("o/r", 100, 142)

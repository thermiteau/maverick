"""CLI sub-commands for the new multi-instance coordination layer.

Exposes the gh_state, dag, epic_state, worktree, coordinator, and gh_app
modules as shell-callable commands so skill bodies can invoke them via
`uv run maverick <sub> <op> …` without re-implementing anything.

Usage shape:

    uv run maverick coord read     <repo> <issue>
    uv run maverick coord claim    <repo> <issue> [--scope N,N,N]
    uv run maverick coord heartbeat <repo> <issue>
    uv run maverick coord heartbeat-loop <repo> <issue> [--interval SECS]
    uv run maverick coord release  <repo> <issue> [--reason R]
    uv run maverick coord takeover <repo> <issue> [--scope N,N,N] [--reason R]
    uv run maverick dag show       <repo> <epic>
    uv run maverick dag waves      <repo> <epic>
    uv run maverick dag descendants <repo> <epic> <story>
    uv run maverick state show     <repo> <epic>
    uv run maverick state set      <repo> <epic> <story> <status>
    uv run maverick worktree create <branch> [--base BASE]
    uv run maverick worktree list
    uv run maverick worktree destroy <path>
    uv run maverick gh-app status
    uv run maverick gh-app gh -- <gh args…>
    uv run maverick task-progress read <repo> <issue>
    uv run maverick task-progress set  <repo> <issue> <phase>
    uv run maverick issue close-on-merge <repo> <issue> --pr N --target B
    uv run maverick git-workflow story-base
    uv run maverick git-workflow pr-target
    uv run maverick git-workflow branch-prefix <label>
    uv run maverick git-workflow promotion-chain
    uv run maverick git-workflow show
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from maverick import (
    coordinator,
    dag,
    epic_state,
    gh_app,
    gh_state,
    git_workflow,
    issue_lifecycle,
    workflow_verbs,
    worktree,
)


def _json_print(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# coord
# ---------------------------------------------------------------------------


def _coord_read(args: argparse.Namespace) -> int:
    state = coordinator.read_claim_state(args.repo, args.issue)
    _json_print(state)
    return 0


def _coord_claim(args: argparse.Namespace) -> int:
    scope = args.scope.split(",") if args.scope else None
    try:
        c = coordinator.claim(args.repo, args.issue, scope=scope)
    except coordinator.ClaimRejected as e:
        print(f"claim rejected: {e}", file=sys.stderr)
        return 2
    _json_print(c.to_payload())
    return 0


def _coord_heartbeat(args: argparse.Namespace) -> int:
    try:
        coordinator.heartbeat(args.repo, args.issue)
    except coordinator.ClaimLost as e:
        print(f"claim lost: {e}", file=sys.stderr)
        return 3
    print("ok")
    return 0


def _coord_heartbeat_loop(args: argparse.Namespace) -> int:
    if getattr(args, "daemonize", False):
        pid = coordinator.daemonize_heartbeat_loop(
            args.repo, args.issue, interval_seconds=args.interval
        )
        _json_print({"daemon": True, "pid": pid})
        return 0
    return coordinator.heartbeat_loop(
        args.repo, args.issue, interval_seconds=args.interval
    )


def _coord_heartbeat_status(args: argparse.Namespace) -> int:
    pid = coordinator.heartbeat_pid(args.repo, args.issue)
    _json_print({"running": pid is not None, "pid": pid})
    return 0 if pid is not None else 3


def _coord_resume_point(args: argparse.Namespace) -> int:
    _json_print(workflow_verbs.resume_point(args.repo, args.issue))
    return 0


def _coord_release(args: argparse.Namespace) -> int:
    coordinator.release(args.repo, args.issue, reason=args.reason)
    print("released")
    return 0


def _coord_release_all(args: argparse.Namespace) -> int:
    released = coordinator.release_all(reason=args.reason)
    for repo, issue in released:
        print(f"released {repo}#{issue}")
    print(f"{len(released)} claim(s) released")
    return 0


def _coord_authorize(args: argparse.Namespace) -> int:
    try:
        auth = coordinator.authorize(args.repo, args.issue, args.scope)
    except coordinator.AuthorizationRejected as e:
        print(f"authorization rejected: {e}", file=sys.stderr)
        return 2
    _json_print(auth)
    return 0


def _coord_takeover(args: argparse.Namespace) -> int:
    scope = args.scope.split(",") if args.scope else None
    try:
        c = coordinator.takeover(
            args.repo, args.issue, scope=scope, reason=args.reason
        )
    except coordinator.ClaimRejected as e:
        print(f"takeover rejected: {e}", file=sys.stderr)
        return 2
    _json_print(c.to_payload())
    return 0


# ---------------------------------------------------------------------------
# dag
# ---------------------------------------------------------------------------


def _dag_show(args: argparse.Namespace) -> int:
    d = dag.load_dag(args.repo, args.epic)
    if d is None:
        print("no maverick-dag marker on epic", file=sys.stderr)
        return 1
    _json_print(d.to_payload())
    return 0


def _dag_waves(args: argparse.Namespace) -> int:
    d = dag.load_dag(args.repo, args.epic)
    if d is None:
        print("no maverick-dag marker on epic", file=sys.stderr)
        return 1
    _json_print(d.waves())
    return 0


def _dag_descendants(args: argparse.Namespace) -> int:
    d = dag.load_dag(args.repo, args.epic)
    if d is None:
        print("no maverick-dag marker on epic", file=sys.stderr)
        return 1
    _json_print(sorted(d.transitive_descendants(args.story)))
    return 0


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------


def _state_show(args: argparse.Namespace) -> int:
    s = epic_state.hydrate_from_gh(args.repo, args.epic)
    if s is None:
        print("no maverick-state marker on epic", file=sys.stderr)
        return 1
    _json_print(s.to_payload())
    return 0


def _state_set(args: argparse.Namespace) -> int:
    s = epic_state.hydrate_from_gh(args.repo, args.epic) or epic_state.EpicState(epic=args.epic)
    epic_state.transition(args.repo, s, args.story, args.status)  # type: ignore[arg-type]
    _json_print(s.to_payload())
    return 0


# ---------------------------------------------------------------------------
# worktree
# ---------------------------------------------------------------------------


def _worktree_create(args: argparse.Namespace) -> int:
    worktree.ensure_available()
    w = worktree.create(args.branch, base=args.base)
    _json_print({"path": str(w.path), "branch": w.branch, "head": w.head})
    return 0


def _worktree_list(args: argparse.Namespace) -> int:
    trees = worktree.list_worktrees()
    _json_print(
        [{"path": str(w.path), "branch": w.branch, "head": w.head} for w in trees]
    )
    return 0


def _worktree_destroy(args: argparse.Namespace) -> int:
    worktree.destroy(Path(args.path), force=args.force)
    print("destroyed")
    return 0


# ---------------------------------------------------------------------------
# gh-app
# ---------------------------------------------------------------------------


def _gh_app_status(args: argparse.Namespace) -> int:
    _json_print(gh_app.check_configured())
    return 0


def _gh_app_gh(args: argparse.Namespace) -> int:
    # POSIX "end of options" — argparse.REMAINDER preserves the literal `--`
    # as the first element. The skill docs (and most users) write
    # `gh-app gh -- <gh args>` to make the boundary explicit; strip it so
    # both forms produce the same downstream invocation. (#44)
    gh_args = list(args.gh_args)
    if gh_args and gh_args[0] == "--":
        gh_args = gh_args[1:]
    try:
        result = gh_app.gh_app_gh(*gh_args)
    except gh_app.GhAppNotConfigured as e:
        print(f"GitHub App not configured: {e}", file=sys.stderr)
        return 4
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


# ---------------------------------------------------------------------------
# gh-state
# ---------------------------------------------------------------------------


def _gh_state_read(args: argparse.Namespace) -> int:
    m = gh_state.latest_marker(args.repo, args.issue, args.kind)
    _json_print(m.payload if m else None)
    return 0


# ---------------------------------------------------------------------------
# task-progress (#41)
# ---------------------------------------------------------------------------


def _task_progress_read(args: argparse.Namespace) -> int:
    """Print the latest do-issue-solo phase checkpoint for an issue."""
    m = gh_state.latest_marker(args.repo, args.issue, "maverick-task-progress")
    _json_print(m.payload if m else None)
    return 0


def _task_progress_set(args: argparse.Namespace) -> int:
    """Merge-set the do-issue-solo phase checkpoint marker. Always rolls one
    marker per issue, so re-entering instances see the latest phase rather
    than a paginated history. Merge semantics (patch_task_progress) preserve
    accreted fields — branch, comment ids, authorized scopes — across
    checkpoints."""
    from datetime import datetime, timezone

    updates: dict[str, Any] = {
        "phase": args.phase,
        "instance_id": coordinator.instance_id(),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if getattr(args, "branch", None):
        updates["branch"] = args.branch
    if getattr(args, "has_sub_issues", False):
        updates["has_sub_issues"] = True
    payload = gh_state.patch_task_progress(args.repo, args.issue, updates)
    # Best-effort timeline append for the `maverick report generate`
    # path. Local history; never fails the durable marker write.
    try:
        from maverick import report_cli

        event: dict[str, Any] = {
            "schema_version": report_cli.SCHEMA_VERSION,
            "action": "phase-boundary",
            "start_ts": payload["updated_at"],
            "instance_id": payload["instance_id"],
            "issue": args.issue,
            "maverick_version": report_cli._get_version(),
            "phase": args.phase,
            "llm": report_cli._current_llm(issue=args.issue),
        }
        skill = report_cli._current_skill(args.issue)
        if skill:
            event["maverick_skill"] = skill
        report_cli.append_event(event)
    except Exception as e:  # noqa: BLE001 — best-effort
        print(f"warning: timeline append failed: {e}", file=sys.stderr)
    _json_print(payload)
    return 0


# ---------------------------------------------------------------------------
# issue (#52)
# ---------------------------------------------------------------------------


def _issue_close_on_merge(args: argparse.Namespace) -> int:
    """Run the post-merge issue-lifecycle steps: audit comment + label
    are unconditional, close decision follows the per-project policy."""
    default_branch = args.default_branch or worktree.default_branch()
    decision = issue_lifecycle.close_on_merge(
        args.repo,
        args.issue,
        pr_num=args.pr,
        target_branch=args.target,
        default_branch=default_branch,
    )
    print(issue_lifecycle.decision_to_json(decision))
    return 0


def _issue_policy(args: argparse.Namespace) -> int:
    """Print the per-project issue close policy. Skill bodies query this
    when they need to make their own close decisions for cases that
    don't fit `close-on-merge` (notably epic-level close, which spans
    multiple PRs)."""
    print(issue_lifecycle.get_policy())
    return 0


# ---------------------------------------------------------------------------
# pr — pre-merge gates
# ---------------------------------------------------------------------------


def _pr_auth_scan(args: argparse.Namespace) -> int:
    from maverick import pr_gate

    try:
        files = pr_gate.pr_changed_files(args.repo, args.pr)
    except subprocess.CalledProcessError as e:
        print(f"auth-scan error: {e.stderr or e}", file=sys.stderr)
        return 2
    hits = pr_gate.scan_paths(files)
    if hits:
        print("gated paths touched — do not auto-merge; eject to needs-human:")
        for path in hits:
            print(f"  {path}")
        return 3
    print(f"clean ({len(files)} file(s) scanned)")
    return 0


def _pr_wait(args: argparse.Namespace) -> int:
    try:
        timeout = workflow_verbs.parse_duration(args.timeout)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    until = "checks" if args.checks else "merged"
    code = workflow_verbs.pr_wait(
        args.repo, args.pr, until, timeout, interval_seconds=args.interval
    )
    labels = {
        workflow_verbs.PR_WAIT_OK: "ok",
        workflow_verbs.PR_WAIT_TIMEOUT: "timeout",
        workflow_verbs.PR_WAIT_CLOSED: "closed-without-merge",
        workflow_verbs.PR_WAIT_CHECKS_FAILED: "checks-failed",
    }
    print(labels.get(code, str(code)))
    return code


# ---------------------------------------------------------------------------
# tasks / bprop / docs / issue comments
# ---------------------------------------------------------------------------


def _tasks_check(args: argparse.Namespace) -> int:
    try:
        result = workflow_verbs.tasks_check(args.repo, args.issue, args.n)
    except (workflow_verbs.TasksCommentMissing, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    _json_print(result)
    return 0


def _bprop_run(args: argparse.Namespace) -> int:
    try:
        result = workflow_verbs.bprop_run(args.repo, args.epic, args.ejected)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    _json_print(result)
    return 0


def _read_comment_body(args: argparse.Namespace) -> str:
    if args.body_file == "-":
        return sys.stdin.read()
    return Path(args.body_file).read_text()


def _issue_comment_post(args: argparse.Namespace) -> int:
    comment_id = workflow_verbs.comment_post(
        args.repo, args.issue, args.kind, _read_comment_body(args)
    )
    _json_print({"kind": args.kind, "comment_id": comment_id})
    return 0


def _issue_comment_update(args: argparse.Namespace) -> int:
    try:
        comment_id = workflow_verbs.comment_update(
            args.repo, args.issue, args.kind, _read_comment_body(args)
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    _json_print({"kind": args.kind, "comment_id": comment_id})
    return 0


def _docs_shortlist(args: argparse.Namespace) -> int:
    result = workflow_verbs.docs_shortlist(args.base, out_dir=Path(args.out_dir))
    _json_print(result)
    return 0


def _gh_state_write(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.payload_file).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read payload: {e}", file=sys.stderr)
        return 2
    comment_id = gh_state.upsert_marker(
        args.repo,
        args.issue,
        args.kind,
        payload,
        preamble=args.preamble or f"<!-- maverick {args.kind} -->",
    )
    _json_print({"kind": args.kind, "comment_id": comment_id})
    return 0


# ---------------------------------------------------------------------------
# git-workflow
# ---------------------------------------------------------------------------


def _gw_story_base(args: argparse.Namespace) -> int:
    print(git_workflow.get_story_base())
    return 0


def _gw_pr_target(args: argparse.Namespace) -> int:
    print(git_workflow.get_pr_target())
    return 0


def _gw_branch_prefix(args: argparse.Namespace) -> int:
    print(git_workflow.get_branch_prefix(args.label))
    return 0


def _gw_promotion_chain(args: argparse.Namespace) -> int:
    _json_print(git_workflow.get_promotion_chain())
    return 0


def _gw_show(args: argparse.Namespace) -> int:
    _json_print({
        "story_base": git_workflow.get_story_base(),
        "pr_target": git_workflow.get_pr_target(),
        "promotion_chain": git_workflow.get_promotion_chain(),
        "branch_prefixes": git_workflow.get_branch_prefixes(),
    })
    return 0


# ---------------------------------------------------------------------------
# wiring
# ---------------------------------------------------------------------------


def build_subparsers(subparsers: argparse._SubParsersAction) -> None:
    """Register all new subcommands on the shared top-level parser."""
    # coord
    coord = subparsers.add_parser("coord", help="Multi-instance claim/lease primitives")
    coord_sub = coord.add_subparsers(dest="coord_cmd", required=True)

    p = coord_sub.add_parser(
        "read",
        aliases=["status"],
        help="Read claim state for an issue (alias: status)",
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_coord_read)

    p = coord_sub.add_parser("claim", help="Claim an issue")
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument("--scope", help="Comma-separated issue numbers in scope")
    p.set_defaults(_handler=_coord_claim)

    p = coord_sub.add_parser("heartbeat", help="Refresh a lease (one shot)")
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_coord_heartbeat)

    p = coord_sub.add_parser(
        "heartbeat-loop",
        help="Refresh the lease in a loop until the claim is released",
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument(
        "--interval",
        type=int,
        default=coordinator.HEARTBEAT_INTERVAL_MINUTES * 60,
        help="Seconds between heartbeats (default: HEARTBEAT_INTERVAL_MINUTES * 60)",
    )
    p.add_argument(
        "--daemonize",
        action="store_true",
        help=(
            "Detach as a pidfile-managed daemon and return immediately. "
            "Check liveness with `coord heartbeat-status`. Preferred over "
            "shell backgrounding, which dies with the tool shell."
        ),
    )
    p.set_defaults(_handler=_coord_heartbeat_loop)

    p = coord_sub.add_parser(
        "heartbeat-status",
        help="Report whether a daemonized heartbeat loop is alive (exit 3 if not)",
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_coord_heartbeat_status)

    p = coord_sub.add_parser(
        "resume-point",
        help=(
            "Compute where a fresh instance should resume work on an issue "
            "from the task-progress marker + PR/CI/verdict state. Replaces "
            "the prose resume table in do-issue-solo Phase 0."
        ),
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_coord_resume_point)

    p = coord_sub.add_parser("release", help="Release a claim")
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument("--reason", default="complete")
    p.set_defaults(_handler=_coord_release)

    p = coord_sub.add_parser(
        "release-all",
        help=(
            "Release every claim this instance recorded locally. Idempotent; "
            "used by the SessionEnd hook so abnormal exits still release."
        ),
    )
    p.add_argument("--reason", default="session-end")
    p.set_defaults(_handler=_coord_release_all)

    p = coord_sub.add_parser(
        "authorize",
        help=(
            "Verify the GitHub issue explicitly authorizes a guarded scope "
            "(label maverick-authorize-<scope> or a 'Maverick-Authorize: <scope>' "
            "body line) and record it in .maverick/session-auth.json for the "
            "scope-guard hook. Exits 2 if the issue does not authorize it."
        ),
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument("scope", help="Guarded scope to authorize (e.g. infra)")
    p.set_defaults(_handler=_coord_authorize)

    p = coord_sub.add_parser("takeover", help="Take over a stale lease")
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument(
        "--scope",
        help="Comma-separated issue numbers in scope (mirrors `coord claim`)",
    )
    p.add_argument(
        "--reason",
        help="Free-form audit-trail note recorded on the takeover marker",
    )
    p.set_defaults(_handler=_coord_takeover)

    # dag
    d = subparsers.add_parser("dag", help="Read/walk the epic DAG")
    d_sub = d.add_subparsers(dest="dag_cmd", required=True)

    p = d_sub.add_parser("show", help="Print the DAG JSON")
    p.add_argument("repo")
    p.add_argument("epic", type=int)
    p.set_defaults(_handler=_dag_show)

    p = d_sub.add_parser("waves", help="Print wave grouping")
    p.add_argument("repo")
    p.add_argument("epic", type=int)
    p.set_defaults(_handler=_dag_waves)

    p = d_sub.add_parser("descendants", help="Print transitive descendants of a story")
    p.add_argument("repo")
    p.add_argument("epic", type=int)
    p.add_argument("story")
    p.set_defaults(_handler=_dag_descendants)

    # state
    s = subparsers.add_parser("state", help="Read/update epic state")
    s_sub = s.add_subparsers(dest="state_cmd", required=True)

    p = s_sub.add_parser("show", help="Print epic-state JSON")
    p.add_argument("repo")
    p.add_argument("epic", type=int)
    p.set_defaults(_handler=_state_show)

    p = s_sub.add_parser("set", help="Set story status and mirror to GH")
    p.add_argument("repo")
    p.add_argument("epic", type=int)
    p.add_argument("story")
    p.add_argument("status", choices=["pending", "in_flight", "merged", "ejected", "blocked"])
    p.set_defaults(_handler=_state_set)

    # worktree
    w = subparsers.add_parser("worktree", help="Per-story worktree management")
    w_sub = w.add_subparsers(dest="wt_cmd", required=True)

    p = w_sub.add_parser("create", help="Create a worktree")
    p.add_argument("branch")
    p.add_argument("--base", help="Base branch (default: repo default)")
    p.set_defaults(_handler=_worktree_create)

    p = w_sub.add_parser("list", help="List worktrees")
    p.set_defaults(_handler=_worktree_list)

    p = w_sub.add_parser(
        "destroy",
        help="Destroy a worktree (force-removes by default; --no-force to opt out)",
    )
    p.add_argument("path")
    p.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Force-remove dirty worktrees (default). Use --no-force to keep "
        "the conservative `git worktree remove` behaviour.",
    )
    p.set_defaults(_handler=_worktree_destroy)

    # gh-app
    b = subparsers.add_parser(
        "gh-app", help="Maverick GitHub App operations (auth, status)"
    )
    b_sub = b.add_subparsers(dest="gh_app_cmd", required=True)

    p = b_sub.add_parser("status", help="Show GitHub App configuration state")
    p.set_defaults(_handler=_gh_app_status)

    p = b_sub.add_parser("gh", help="Run `gh` authenticated as the GitHub App")
    p.add_argument("gh_args", nargs=argparse.REMAINDER)
    p.set_defaults(_handler=_gh_app_gh)

    # gh-state raw read
    gs = subparsers.add_parser("gh-state", help="Read raw markers from GitHub")
    gs_sub = gs.add_subparsers(dest="gs_cmd", required=True)

    p = gs_sub.add_parser("read", help="Read latest marker of a kind on an issue")
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument(
        "kind",
        choices=list(gh_state.MARKER_KINDS),
    )
    p.set_defaults(_handler=_gh_state_read)

    p = gs_sub.add_parser(
        "write",
        help=(
            "Upsert a marker of a kind on an issue from a JSON payload file. "
            "The sanctioned write path for markers without a dedicated verb "
            "(e.g. maverick-dag) — never compose marker comments by hand."
        ),
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument("kind", choices=list(gh_state.MARKER_KINDS))
    p.add_argument("--payload-file", required=True, help="Path to the JSON payload")
    p.add_argument("--preamble", help="Markdown shown above the fenced marker block")
    p.set_defaults(_handler=_gh_state_write)

    # task-progress — per-issue do-issue-solo phase checkpoint (#41)
    tp = subparsers.add_parser(
        "task-progress",
        help="Read or update the do-issue-solo phase checkpoint for an issue",
    )
    tp_sub = tp.add_subparsers(dest="tp_cmd", required=True)

    p = tp_sub.add_parser("read", help="Print the latest task-progress marker")
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_task_progress_read)

    p = tp_sub.add_parser(
        "set",
        help=(
            "Merge-set the task-progress marker (the single issue-state "
            "surface). Accreted fields — branch, comment ids, authorized "
            "scopes — survive across checkpoints."
        ),
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument(
        "phase",
        choices=list(gh_state.TASK_PROGRESS_PHASES),
        help="The do-issue-solo phase boundary just completed",
    )
    p.add_argument("--branch", help="Record the working branch in the payload")
    p.add_argument(
        "--has-sub-issues",
        action="store_true",
        help="Record that tasks were created as GitHub sub-issues (>= 5 tasks)",
    )
    p.set_defaults(_handler=_task_progress_set)

    # issue — per-project close policy (#52)
    iss = subparsers.add_parser(
        "issue",
        help="Issue lifecycle operations (post-merge close per project policy)",
    )
    iss_sub = iss.add_subparsers(dest="issue_cmd", required=True)

    p = iss_sub.add_parser(
        "close-on-merge",
        help=(
            "Run the post-merge issue-lifecycle steps. Always posts the audit "
            "comment and applies a `merged-to-<branch>` label. Closes the issue "
            "based on issue_lifecycle.close_policy in .maverick/config.json: "
            "on_pr_merge (default) closes always; on_default_branch_merge "
            "closes only when target is the default branch; manual never closes."
        ),
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument(
        "--pr",
        type=int,
        required=True,
        help="Number of the PR that just merged (referenced in the audit comment)",
    )
    p.add_argument(
        "--target",
        required=True,
        help="The branch the PR merged into (e.g. main, develop)",
    )
    p.add_argument(
        "--default-branch",
        help="Repo's default branch. If omitted, detected via `gh repo view`.",
    )
    p.set_defaults(_handler=_issue_close_on_merge)

    p = iss_sub.add_parser(
        "policy",
        help="Print the per-project issue close policy from .maverick/config.json",
    )
    p.set_defaults(_handler=_issue_policy)

    cmt = iss_sub.add_parser(
        "comment",
        help=(
            "Post/update artefact comments (design, plan, tasks, completion). "
            "Uses the GitHub App identity when configured, returns the comment "
            "id as JSON, and records it in the task-progress marker."
        ),
    )
    cmt_sub = cmt.add_subparsers(dest="comment_cmd", required=True)

    for verb, handler, help_text in (
        ("post", _issue_comment_post, "Post a new artefact comment and record its id"),
        ("update", _issue_comment_update, "Overwrite the recorded artefact comment"),
    ):
        p = cmt_sub.add_parser(verb, help=help_text)
        p.add_argument("repo")
        p.add_argument("issue", type=int)
        p.add_argument(
            "--kind",
            required=True,
            choices=list(workflow_verbs.COMMENT_KINDS),
        )
        p.add_argument(
            "--body-file",
            required=True,
            help="Path to the markdown body, or '-' for stdin",
        )
        p.set_defaults(_handler=handler)

    # pr — pre-merge gates for autonomous flows
    pr = subparsers.add_parser(
        "pr",
        help="Pre-merge gates for autonomous PR handling",
    )
    pr_sub = pr.add_subparsers(dest="pr_cmd", required=True)

    p = pr_sub.add_parser(
        "auth-scan",
        help=(
            "Scan a PR's changed files for auth-sensitive paths and CI workflow "
            "definitions. Exit 0 = clean (safe to auto-merge), 3 = gated paths "
            "touched (eject to needs-human instead of auto-merging), 2 = error. "
            "Extra tokens: .maverick/config.json -> scope_guards.auth_paths."
        ),
    )
    p.add_argument("repo")
    p.add_argument("pr", help="PR number or URL")
    p.set_defaults(_handler=_pr_auth_scan)

    p = pr_sub.add_parser(
        "wait",
        help=(
            "Bounded wait for a PR to merge (default) or for its checks to "
            "settle (--checks). Exit codes: 0 ok, 3 timeout, 4 closed "
            "without merge, 5 checks failed. Replaces unbounded polling."
        ),
    )
    p.add_argument("repo")
    p.add_argument("pr", help="PR number or URL")
    p.add_argument(
        "--checks",
        action="store_true",
        help="Wait for checks to settle instead of the merge itself",
    )
    p.add_argument("--timeout", default="30m", help="e.g. 300s, 30m, 1h (default 30m)")
    p.add_argument("--interval", type=int, default=15, help="Poll interval seconds")
    p.set_defaults(_handler=_pr_wait)

    # tasks — durable task-list operations
    tasks = subparsers.add_parser(
        "tasks", help="Operations on the durable tasks checklist comment"
    )
    tasks_sub = tasks.add_subparsers(dest="tasks_cmd", required=True)

    p = tasks_sub.add_parser(
        "check",
        help=(
            "Check off the nth (1-based) checkbox in the issue's tasks "
            "comment. Idempotent. Replaces hand-edited comment PATCHes."
        ),
    )
    p.add_argument("repo")
    p.add_argument("issue", type=int)
    p.add_argument("n", type=int, help="1-based task number to check off")
    p.set_defaults(_handler=_tasks_check)

    # bprop — block propagation
    bprop = subparsers.add_parser(
        "bprop", help="Block propagation across an epic's dependency DAG"
    )
    bprop_sub = bprop.add_subparsers(dest="bprop_cmd", required=True)

    p = bprop_sub.add_parser(
        "run",
        help=(
            "Run the marker-write-walk-clear protocol: label every transitive "
            "descendant of an ejected story blocked-by:#N, comment each, "
            "mirror epic state, clear the bprop marker. Idempotent and "
            "resumable — safe to re-run after a crash mid-walk."
        ),
    )
    p.add_argument("repo")
    p.add_argument("epic", type=int)
    p.add_argument("--ejected", type=int, required=True, help="The ejected story number")
    p.set_defaults(_handler=_bprop_run)

    # docs — docs-review support
    docs = subparsers.add_parser("docs", help="Docs-review phase support")
    docs_sub = docs.add_subparsers(dest="docs_cmd", required=True)

    p = docs_sub.add_parser(
        "shortlist",
        help=(
            "Build the candidate-doc shortlist for the docs-review phase from "
            "the diff against a base branch. Writes diff.patch, "
            "changed-paths.txt, and doc-shortlist.txt to --out-dir."
        ),
    )
    p.add_argument("--base", required=True, help="Base branch (e.g. from git-workflow story-base)")
    p.add_argument("--out-dir", default="/tmp", help="Output directory (default /tmp)")
    p.set_defaults(_handler=_docs_shortlist)

    # git-workflow — per-project branching config
    gw = subparsers.add_parser(
        "git-workflow",
        help="Resolve git branching parameters from .maverick/config.json",
    )
    gw_sub = gw.add_subparsers(dest="gw_cmd", required=True)

    p = gw_sub.add_parser(
        "story-base",
        help="Print the branch to create feature/fix branches from",
    )
    p.set_defaults(_handler=_gw_story_base)

    p = gw_sub.add_parser(
        "pr-target",
        help="Print the default --base for gh pr create",
    )
    p.set_defaults(_handler=_gw_pr_target)

    p = gw_sub.add_parser(
        "branch-prefix",
        help="Resolve branch prefix for an issue label (e.g. bug → fix)",
    )
    p.add_argument("label", help="Issue label or keyword (e.g. bug, enhancement)")
    p.set_defaults(_handler=_gw_branch_prefix)

    p = gw_sub.add_parser(
        "promotion-chain",
        help="Print the ordered promotion chain as JSON",
    )
    p.set_defaults(_handler=_gw_promotion_chain)

    p = gw_sub.add_parser(
        "show",
        help="Print the full git-workflow config as JSON",
    )
    p.set_defaults(_handler=_gw_show)


def dispatch(args: argparse.Namespace) -> int:
    """Run the handler registered on the parsed args. Returns exit code."""
    handler = getattr(args, "_handler", None)
    if handler is None:
        print("no handler wired", file=sys.stderr)
        return 1
    return int(handler(args) or 0)

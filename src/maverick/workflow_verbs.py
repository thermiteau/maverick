"""Deterministic workflow verbs extracted from skill prose.

Each function backs a `maverick` CLI verb that previously existed as
bash-in-prose inside a skill (jq pipelines, grep/awk shortlist derivation,
LLM-executed DAG walks, unbounded polling loops). LLM transcription of
shell pipelines is a known failure mode; these verbs make the hot loop
deterministic, testable, and idempotent.

All GitHub interaction goes through the small `_gh` wrapper so tests can
mock one seam. Comment writes prefer the Maverick GitHub App identity
when configured (see mav-github-issue-workflow's identity rule) and fall
back to the user's `gh` credentials.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from maverick import gh_state

# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------


def _gh(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, env=env
    )
    return result.stdout


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, cwd=cwd
    )
    return result.stdout


def _app_env() -> dict[str, str] | None:
    """The GitHub App credential env, or None to use the user's gh auth.

    Maverick-authored comments should be visually distinct from the human
    user's. Falling back silently is the documented behaviour for solo /
    ad-hoc use (mav-github-issue-workflow, 'App not configured').
    """
    try:
        from maverick.gh_app import GhAppNotConfigured, gh_app_env

        try:
            return gh_app_env()
        except GhAppNotConfigured:
            return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# coord resume-point — replaces do-issue-solo's prose resume table
# ---------------------------------------------------------------------------

#: phase checkpoint recorded → where a fresh instance resumes when no PR
#: exists yet. Values are (next_focus, human instruction).
_NO_PR_RESUME: dict[str | None, tuple[str, str]] = {
    None: ("understand", "no task-progress marker — start from Phase 1 (understand)"),
    "claimed": ("understand", "claim exists but no work recorded — start Phase 1 (understand)"),
    "design": ("tasks", "design posted — resume at Phase 3 (create tasks)"),
    "tasks": ("branch", "tasks exist — resume at Phase 4 (worktree + branch)"),
    "branch": ("implement", "branch created — resume at Phase 5 (implement tasks)"),
    "implement": (
        "implement",
        "resume at Phase 5 — continue from the first unchecked task; if all "
        "tasks are checked, run full verification and proceed to Phase 7 (docs)",
    ),
    "docs": ("security", "docs review done — resume at Phase 7 (security review)"),
    "security": ("pr_open", "security gate passed — resume at Phase 8 (push + open PR)"),
    "pr_open": ("pr_open", "marker says PR opened but none found — re-run Phase 8 (open PR)"),
    "ci_green": ("pr_open", "marker says CI green but no PR found — re-run Phase 8 (open PR)"),
    "review": ("pr_open", "marker says review ran but no PR found — re-run Phase 8 (open PR)"),
    "merged": ("merged", "resume at Phase 10 step 6 — post-merge cleanup"),
    "complete": ("complete", "workflow already complete — nothing to resume"),
    "ejected": ("ejected", "issue was ejected to a human — do not resume autonomously"),
}

_VERDICT_RE = re.compile(r"^MAVERICK_VERDICT:\s*(PASS|FAIL)\s*$", re.MULTILINE)


def _find_pr(repo: str, branch: str) -> dict[str, Any] | None:
    out = _gh(
        "pr",
        "list",
        "--repo",
        repo,
        "--head",
        branch,
        "--state",
        "all",
        "--json",
        "number,state,url",
        "--limit",
        "1",
    )
    prs = json.loads(out)
    return prs[0] if prs else None


def _pr_details(repo: str, number: int) -> dict[str, Any]:
    out = _gh(
        "pr",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        "state,statusCheckRollup,reviews,comments",
    )
    return json.loads(out)


def _checks_status(rollup: list[dict[str, Any]] | None) -> str:
    """Summarize a statusCheckRollup: failing | pending | green."""
    if not rollup:
        return "green"  # no required checks configured
    states = {
        str(c.get("conclusion") or c.get("state") or "").upper() for c in rollup
    }
    if states & {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
        return "failing"
    if states & {"", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "WAITING"}:
        return "pending"
    return "green"


def _latest_verdict(details: dict[str, Any]) -> str | None:
    """The most recent MAVERICK_VERDICT marker across reviews + comments."""
    bodies: list[str] = []
    for review in details.get("reviews") or []:
        bodies.append(str(review.get("body") or ""))
    for comment in details.get("comments") or []:
        bodies.append(str(comment.get("body") or ""))
    verdict = None
    for body in bodies:  # both lists are chronological; last marker wins
        for m in _VERDICT_RE.finditer(body):
            verdict = m.group(1)
    return verdict


def resume_point(repo: str, issue: int) -> dict[str, Any]:
    """Compute where a fresh instance should resume work on `issue`.

    Replaces the prose resume table in do-issue-solo Phase 0: reads the
    task-progress marker, finds the PR (via the recorded branch), and
    refines with CI/verdict state. Returns
    {"next": <focus>, "instruction": <human text>, "evidence": {...}}.
    """
    payload = gh_state.read_task_progress(repo, issue)
    phase = payload.get("phase")
    branch = payload.get("branch")
    evidence: dict[str, Any] = {"phase": phase, "branch": branch}

    pr = _find_pr(repo, branch) if branch else None
    if pr is None:
        next_focus, instruction = _NO_PR_RESUME.get(
            phase, ("understand", f"unrecognized phase {phase!r} — start from Phase 1")
        )
        return {"next": next_focus, "instruction": instruction, "evidence": evidence}

    evidence["pr"] = {"number": pr["number"], "state": pr["state"], "url": pr.get("url")}

    if pr["state"] == "MERGED":
        if phase == "complete":
            return {
                "next": "complete",
                "instruction": "PR merged and workflow complete — nothing to resume",
                "evidence": evidence,
            }
        return {
            "next": "merged",
            "instruction": (
                "PR merged — resume at Phase 10 step 6 (completion comment, "
                "close-on-merge, release claim, destroy worktree)"
            ),
            "evidence": evidence,
        }

    if pr["state"] == "CLOSED":
        return {
            "next": "ejected",
            "instruction": (
                "PR was closed without merging — investigate before resuming; "
                "do not reopen or re-push autonomously"
            ),
            "evidence": evidence,
        }

    # OPEN PR: refine with checks, then review verdict.
    details = _pr_details(repo, pr["number"])
    checks = _checks_status(details.get("statusCheckRollup"))
    evidence["checks"] = checks
    if checks == "failing":
        return {
            "next": "ci_green",
            "instruction": "PR open with failing checks — resume at Phase 8 step 4 (read CI logs, fix, push)",
            "evidence": evidence,
        }
    if checks == "pending":
        return {
            "next": "ci_green",
            "instruction": (
                "PR open with checks in flight — wait with "
                f"`uv run maverick pr wait {repo} {pr['number']} --checks --timeout 30m`"
            ),
            "evidence": evidence,
        }

    verdict = _latest_verdict(details)
    evidence["verdict"] = verdict
    if verdict == "FAIL":
        return {
            "next": "ejected",
            "instruction": "reviewer verdict FAIL on PR — resume at Phase 11 (eject)",
            "evidence": evidence,
        }
    if verdict == "PASS":
        return {
            "next": "merged",
            "instruction": "reviewer verdict PASS — resume at Phase 10 (auth-scan, approve, auto-merge)",
            "evidence": evidence,
        }
    return {
        "next": "review",
        "instruction": "PR open, CI green, no review verdict — resume at Phase 9 (dispatch agent-code-reviewer)",
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# tasks check — replaces the hand-rolled checkbox PATCH in mav-plan-execution
# ---------------------------------------------------------------------------

_CHECKBOX_RE = re.compile(r"^(\s*(?:[-*]|\d+\.)\s+)\[( |x|X)\](\s+.*)$")


class TasksCommentMissing(RuntimeError):
    """No tasks comment id recorded in the task-progress marker."""


def tasks_check(repo: str, issue: int, n: int) -> dict[str, Any]:
    """Check off the nth (1-based) checkbox in the issue's tasks comment.

    Reads the comment id from the task-progress marker, toggles exactly one
    checkbox, and PATCHes the body back. Idempotent: an already-checked
    task is a reported no-op, never an error.
    """
    payload = gh_state.read_task_progress(repo, issue)
    comment_id = (payload.get("comments") or {}).get("tasks")
    if not comment_id:
        raise TasksCommentMissing(
            f"no tasks comment recorded for {repo}#{issue} — post it via "
            "`maverick issue comment post --kind tasks` first"
        )

    body = json.loads(_gh("api", f"repos/{repo}/issues/comments/{comment_id}"))["body"]
    lines = body.splitlines()
    seen = 0
    for i, line in enumerate(lines):
        m = _CHECKBOX_RE.match(line)
        if not m:
            continue
        seen += 1
        if seen != n:
            continue
        task_text = m.group(3).strip()
        if m.group(2) in ("x", "X"):
            return {"task": n, "text": task_text, "status": "already-checked"}
        lines[i] = f"{m.group(1)}[x]{m.group(3)}"
        new_body = "\n".join(lines)
        env = _app_env()
        _gh(
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/comments/{comment_id}",
            "-f",
            f"body={new_body}",
            env=env,
        )
        return {"task": n, "text": task_text, "status": "checked"}
    raise ValueError(f"tasks comment has {seen} checkbox(es); task {n} not found")


# ---------------------------------------------------------------------------
# issue comment post/update — replaces the stderr-scraping URL plumbing
# ---------------------------------------------------------------------------

COMMENT_KINDS = ("design", "plan", "tasks", "completion")


def comment_post(repo: str, issue: int, kind: str, body: str) -> int:
    """Post an artefact comment and record its id in the task-progress marker.

    Returns the comment id from the API response JSON — never scraped from
    a URL on a stream that may also carry warnings.
    """
    if kind not in COMMENT_KINDS:
        raise ValueError(f"unknown comment kind {kind!r}; expected one of {COMMENT_KINDS}")
    env = _app_env()
    out = _gh(
        "api",
        "--method",
        "POST",
        f"repos/{repo}/issues/{issue}/comments",
        "-f",
        f"body={body}",
        env=env,
    )
    comment_id = json.loads(out)["id"]
    gh_state.patch_task_progress(repo, issue, {"comments": {kind: comment_id}})
    return comment_id


def comment_update(repo: str, issue: int, kind: str, body: str) -> int:
    """Overwrite the recorded artefact comment of `kind` with a new body."""
    if kind not in COMMENT_KINDS:
        raise ValueError(f"unknown comment kind {kind!r}; expected one of {COMMENT_KINDS}")
    payload = gh_state.read_task_progress(repo, issue)
    comment_id = (payload.get("comments") or {}).get(kind)
    if not comment_id:
        raise ValueError(
            f"no {kind} comment recorded for {repo}#{issue} — post it first"
        )
    _gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/issues/comments/{comment_id}",
        "-f",
        f"body={body}",
        env=_app_env(),
    )
    return comment_id


# ---------------------------------------------------------------------------
# bprop run — replaces the LLM-executed DAG walk in mav-block-propagation
# ---------------------------------------------------------------------------


def bprop_run(repo: str, epic: int, ejected: int) -> dict[str, Any]:
    """Run the marker-write-walk-clear block-propagation protocol.

    Idempotent and resumable: an existing maverick-bprop marker is resumed
    (already-labelled descendants are skipped), every step re-checks GitHub
    state before writing, and the marker is deleted only when every
    descendant is labelled.
    """
    from maverick import dag as dag_mod
    from maverick import epic_state

    d = dag_mod.load_dag(repo, epic)
    if d is None:
        raise RuntimeError(f"no maverick-dag marker on {repo}#{epic}")
    descendants = sorted(d.transitive_descendants(str(ejected)), key=int)

    label = f"blocked-by:#{ejected}"
    marker = gh_state.latest_marker(repo, epic, "maverick-bprop")
    if marker is not None and str(marker.payload.get("ejected")) == str(ejected):
        payload = dict(marker.payload)
        payload.setdefault("labelled", [])
    else:
        from datetime import datetime, timezone

        payload = {
            "ejected": str(ejected),
            "descendants": descendants,
            "labelled": [],
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    comment_id = gh_state.upsert_marker(
        repo, epic, "maverick-bprop", payload, preamble="<!-- maverick bprop -->"
    )

    # Ensure the dynamic label exists once (idempotent with --force).
    try:
        _gh(
            "label",
            "create",
            label,
            "--repo",
            repo,
            "--force",
            "--color",
            "d93f0b",
            "--description",
            f"Blocked by ejected issue #{ejected}",
        )
    except subprocess.CalledProcessError:
        pass  # label may already exist on older gh versions without --force

    state = epic_state.hydrate_from_gh(repo, epic) or epic_state.EpicState(epic=epic)
    for story in descendants:
        if story in payload["labelled"]:
            continue
        current = json.loads(
            _gh("issue", "view", story, "--repo", repo, "--json", "labels")
        )
        names = [lbl["name"] for lbl in current.get("labels") or []]
        if label not in names:
            _gh("issue", "edit", story, "--repo", repo, "--add-label", label)
            _gh(
                "issue",
                "comment",
                story,
                "--repo",
                repo,
                "--body",
                (
                    f"⛔ **Blocked by #{ejected}** — that story was ejected for "
                    f"human review, and this story depends on it (epic #{epic}). "
                    "Maverick will not work on this issue until a human resolves "
                    f"#{ejected} and removes the `{label}` label."
                ),
                env=_app_env(),
            )
        try:
            epic_state.transition(repo, state, story, "blocked")
        except Exception:
            pass  # epic-state mirror is best-effort; the label is the block
        payload["labelled"].append(story)
        gh_state.update_marker(
            repo, comment_id, "maverick-bprop", payload,
            preamble="<!-- maverick bprop -->",
        )

    gh_state.delete_marker_comment(repo, comment_id)
    return {"ejected": str(ejected), "labelled": payload["labelled"]}


# ---------------------------------------------------------------------------
# docs shortlist — replaces the duplicated grep/sed/awk pipeline
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(
    r"\b(?:function|def|class|interface|type|const|export)\s+([A-Za-z_][A-Za-z0-9_]+)"
)
_EXCLUDED_DIR_PARTS = {"node_modules", ".git", ".venv"}


def docs_shortlist(
    base: str, repo_root: Path = Path("."), out_dir: Path = Path("/tmp")
) -> dict[str, Any]:
    """Build the candidate-doc shortlist for the docs-review phase.

    Ports the bash pipeline the skills used to carry inline: derive search
    terms from the diff (top-level dirs, basenames, identifiers introduced
    or removed), then find every .md/.mdx under any docs/ tree containing
    one of them. Writes diff.patch, changed-paths.txt, and
    doc-shortlist.txt to `out_dir`. An empty shortlist is a valid outcome.
    """
    diff = _git("diff", f"origin/{base}...HEAD", cwd=repo_root)
    changed = _git("diff", "--name-only", f"origin/{base}...HEAD", cwd=repo_root)
    changed_paths = [p for p in changed.splitlines() if p.strip()]

    terms: set[str] = set()
    for path in changed_paths:
        terms.add(path.split("/", 1)[0])  # top-level dir (or bare filename)
        base_name = path.rsplit("/", 1)[-1]
        terms.add(base_name.rsplit(".", 1)[0])  # basename sans extension
    for line in diff.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            terms.update(_IDENTIFIER_RE.findall(line))
    terms = {t for t in terms if len(t) >= 3}

    doc_roots = [
        p
        for p in repo_root.rglob("docs")
        if p.is_dir() and not (_EXCLUDED_DIR_PARTS & set(p.parts))
    ]
    shortlist: set[str] = set()
    if terms:
        for root in doc_roots:
            for doc in root.rglob("*"):
                if doc.suffix not in (".md", ".mdx") or not doc.is_file():
                    continue
                try:
                    content = doc.read_text(errors="ignore")
                except OSError:
                    continue
                if any(t in content for t in terms):
                    shortlist.add(str(doc))

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "diff.patch").write_text(diff)
    (out_dir / "changed-paths.txt").write_text("\n".join(changed_paths) + "\n")
    shortlist_path = out_dir / "doc-shortlist.txt"
    shortlist_path.write_text("\n".join(sorted(shortlist)) + ("\n" if shortlist else ""))

    return {
        "terms": len(terms),
        "docs": sorted(shortlist),
        "diff": str(out_dir / "diff.patch"),
        "shortlist": str(shortlist_path),
    }


# ---------------------------------------------------------------------------
# pr wait — replaces the unbounded polling loops
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"^(\d+)\s*(s|m|h)?$")


def parse_duration(text: str) -> int:
    """'90', '90s', '30m', '2h' → seconds."""
    m = _DURATION_RE.match(text.strip())
    if not m:
        raise ValueError(f"invalid duration {text!r} — use e.g. 300s, 30m, 1h")
    value = int(m.group(1))
    unit = m.group(2) or "s"
    return value * {"s": 1, "m": 60, "h": 3600}[unit]


#: pr_wait exit codes — distinct so skills can branch without parsing prose.
PR_WAIT_OK = 0
PR_WAIT_TIMEOUT = 3
PR_WAIT_CLOSED = 4
PR_WAIT_CHECKS_FAILED = 5


def pr_wait(
    repo: str,
    pr: str,
    until: str,
    timeout_seconds: int,
    interval_seconds: int = 15,
    _sleep=time.sleep,
) -> int:
    """Wait for a PR to merge (`until='merged'`) or its checks to settle
    (`until='checks'`). Bounded: returns PR_WAIT_TIMEOUT when the deadline
    passes, instead of polling forever against a check that never reports.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        out = _gh(
            "pr",
            "view",
            pr,
            "--repo",
            repo,
            "--json",
            "state,statusCheckRollup",
        )
        details = json.loads(out)
        state = details.get("state")
        if state == "MERGED":
            return PR_WAIT_OK
        if state == "CLOSED":
            return PR_WAIT_CLOSED
        if until == "checks":
            checks = _checks_status(details.get("statusCheckRollup"))
            if checks == "failing":
                return PR_WAIT_CHECKS_FAILED
            if checks == "green":
                return PR_WAIT_OK
        if time.monotonic() >= deadline:
            return PR_WAIT_TIMEOUT
        _sleep(interval_seconds)

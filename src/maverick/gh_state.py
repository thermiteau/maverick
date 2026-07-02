"""Read/write helpers for the Maverick GitHub marker comments.

All workflow state that must survive machine death is persisted to GitHub as
fenced JSON comments. This module is the single parser/writer for those markers
so every skill and agent reads and writes them the same way.

Marker kinds (see docs/conventions/github-markers.md):

- maverick-dag: pinned DAG on the epic issue
- maverick-state: rolling epic-state snapshot on the epic issue
- maverick-claim: atomic claim record on a claimed issue
- maverick-lease: heartbeat lease record on a claimed issue
- maverick-bprop: block-propagation in-flight marker on the epic issue
- maverick-task-progress: per-issue do-issue-solo phase checkpoint, so
  a fresh agent re-entering can resume from N+1 instead of restarting (#41)

Each marker is a fenced code block with a kind-specific language tag, e.g.:

    ```maverick-state
    {"merged": [...], "in_flight": [...], "blocked": [...]}
    ```
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any

MARKER_KINDS = (
    "maverick-dag",
    "maverick-state",
    "maverick-claim",
    "maverick-lease",
    "maverick-bprop",
    "maverick-task-progress",
)

# Phase names that may appear in a maverick-task-progress payload's `phase`
# field. The list mirrors do-issue-solo's phase boundaries; agents resume
# from the next phase after the recorded one (#41).
#
# The task-progress marker is the SINGLE state surface for issue-driven
# work — it replaced the old `.claude/issue-state.json` local file, whose
# schema had drifted from the skills that read it. Full payload shape:
#
#     {
#       "phase": "<one of TASK_PROGRESS_PHASES>",
#       "instance_id": "abc123def0",
#       "updated_at": "2026-07-02T10:20:00Z",
#       "branch": "feat/42-add-export",          // once created
#       "comments": {                             // artefact comment ids
#         "design": 123, "plan": 124,
#         "tasks": 125, "completion": 126
#       },
#       "has_sub_issues": true,                   // >= 5 tasks path
#       "authorized": ["infra"]                   // via `coord authorize`
#     }
#
# Only `phase`, `instance_id`, and `updated_at` are always present; the
# rest accrete as the workflow reaches them. Writers must MERGE into the
# existing payload (see patch_task_progress) — a blind upsert that
# rebuilds the payload from scratch would wipe the accreted fields.
TASK_PROGRESS_PHASES = (
    "claimed",
    "design",
    "tasks",
    "branch",
    "implement",
    "docs",
    "security",
    "pr_open",
    "ci_green",
    "review",
    "merged",
    "complete",
    "ejected",
)


@dataclass
class Marker:
    """A parsed Maverick marker from a GitHub comment."""

    kind: str
    payload: dict[str, Any]
    comment_id: int
    issue_number: int


def _fence_pattern(kind: str) -> re.Pattern[str]:
    return re.compile(rf"```{re.escape(kind)}\s*\n(.*?)\n```", re.DOTALL)


def parse_body(body: str, kind: str) -> dict[str, Any] | None:
    """Extract the JSON payload of the first marker of `kind` in a comment body.

    Returns None if no marker of that kind is present. Raises ValueError if the
    marker is present but contains invalid JSON.
    """
    if kind not in MARKER_KINDS:
        raise ValueError(f"unknown marker kind: {kind}")
    m = _fence_pattern(kind).search(body)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed {kind} marker: {e}") from e


def format_marker(kind: str, payload: dict[str, Any]) -> str:
    """Format a payload as a fenced marker block."""
    if kind not in MARKER_KINDS:
        raise ValueError(f"unknown marker kind: {kind}")
    return f"```{kind}\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"


def _gh(*args: str, env: dict[str, str] | None = None) -> str:
    """Run `gh` and return stdout. Raises CalledProcessError on non-zero exit."""
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, env=env
    )
    return result.stdout


def _list_comments(repo: str, issue: int) -> list[dict[str, Any]]:
    """List all comments on an issue. Returns raw GitHub API comment objects."""
    out = _gh("api", f"repos/{repo}/issues/{issue}/comments", "--paginate")
    return json.loads(out)


def find_markers(repo: str, issue: int, kind: str) -> list[Marker]:
    """Find every comment on `issue` carrying a marker of the given kind."""
    if kind not in MARKER_KINDS:
        raise ValueError(f"unknown marker kind: {kind}")
    found: list[Marker] = []
    for c in _list_comments(repo, issue):
        body = c.get("body") or ""
        payload = parse_body(body, kind)
        if payload is not None:
            found.append(
                Marker(kind=kind, payload=payload, comment_id=c["id"], issue_number=issue)
            )
    return found


def latest_marker(repo: str, issue: int, kind: str) -> Marker | None:
    """Return the most recently posted marker of `kind`, or None."""
    markers = find_markers(repo, issue, kind)
    if not markers:
        return None
    return markers[-1]


def post_marker(
    repo: str,
    issue: int,
    kind: str,
    payload: dict[str, Any],
    preamble: str = "",
    env: dict[str, str] | None = None,
) -> int:
    """Post a new comment carrying a marker of `kind`. Returns the comment id.

    `preamble` is free-form markdown that appears above the fenced block.
    `env` lets the caller override credentials (e.g. to post as the Maverick GitHub App).
    """
    body = (preamble + "\n\n" if preamble else "") + format_marker(kind, payload)
    out = _gh(
        "api",
        "--method",
        "POST",
        f"repos/{repo}/issues/{issue}/comments",
        "-f",
        f"body={body}",
        env=env,
    )
    return json.loads(out)["id"]


def update_marker(
    repo: str,
    comment_id: int,
    kind: str,
    payload: dict[str, Any],
    preamble: str = "",
    env: dict[str, str] | None = None,
) -> None:
    """Overwrite an existing marker comment with a new payload."""
    body = (preamble + "\n\n" if preamble else "") + format_marker(kind, payload)
    _gh(
        "api",
        "--method",
        "PATCH",
        f"repos/{repo}/issues/comments/{comment_id}",
        "-f",
        f"body={body}",
        env=env,
    )


def upsert_marker(
    repo: str,
    issue: int,
    kind: str,
    payload: dict[str, Any],
    preamble: str = "",
    env: dict[str, str] | None = None,
) -> int:
    """Update the latest marker of `kind` on `issue`, or post a new one if absent.

    Returns the comment id of the updated or created comment.
    """
    existing = latest_marker(repo, issue, kind)
    if existing is None:
        return post_marker(repo, issue, kind, payload, preamble=preamble, env=env)
    update_marker(repo, existing.comment_id, kind, payload, preamble=preamble, env=env)
    return existing.comment_id


def delete_marker_comment(
    repo: str, comment_id: int, env: dict[str, str] | None = None
) -> None:
    """Delete a marker comment outright. Used to clear `maverick-bprop` on completion."""
    _gh(
        "api",
        "--method",
        "DELETE",
        f"repos/{repo}/issues/comments/{comment_id}",
        env=env,
    )


# ---------------------------------------------------------------------------
# Task-progress payload helpers (the single issue-state surface)
# ---------------------------------------------------------------------------


def read_task_progress(repo: str, issue: int) -> dict[str, Any]:
    """Return the latest task-progress payload for `issue`, or {} if absent."""
    m = latest_marker(repo, issue, "maverick-task-progress")
    return dict(m.payload) if m else {}


def patch_task_progress(
    repo: str,
    issue: int,
    updates: dict[str, Any],
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Merge `updates` into the task-progress payload and upsert the marker.

    Top-level keys in `updates` replace the existing values, except
    `comments`, which is merged key-wise so recording the plan comment id
    never drops the design comment id. Returns the merged payload.
    """
    payload = read_task_progress(repo, issue)
    updates = dict(updates)
    if "comments" in updates:
        merged_comments = {**payload.get("comments", {}), **(updates.pop("comments") or {})}
        payload["comments"] = merged_comments
    payload.update(updates)
    upsert_marker(
        repo,
        issue,
        "maverick-task-progress",
        payload,
        preamble="<!-- maverick task-progress -->",
        env=env,
    )
    return payload

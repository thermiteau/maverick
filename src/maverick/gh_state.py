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
    `env` lets the caller override credentials (e.g. to post as maverick-bot).
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

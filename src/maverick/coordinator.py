"""Multi-instance coordination — claim, lease, heartbeat, release.

Two or more Claude Code instances may be asked to work on the same issue,
story group, or epic at the same time. This module implements the claim
protocol they use to decide who owns what.

Primitives:

- **claim** — atomic-ish acquisition of an issue: adds `claude-in-progress`
  label, posts a `maverick-claim` marker, starts a `maverick-lease`.
- **heartbeat** — refreshes the `maverick-lease` `expires_at` so other
  instances know the holder is alive.
- **release** — removes the label, posts a release comment, unassigns.
- **takeover** — reclaim a stale lease from a crashed instance.

The protocol is eventually-consistent: GitHub label writes are not
strongly ordered, so two instances can both add the label at the same
millisecond. The **read-after-write** step at the end of `claim` detects
this and applies the loser-aborts tiebreaker.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from maverick.gh_state import (
    format_marker,
    latest_marker,
    post_marker,
    upsert_marker,
)

CLAIM_LABEL = "claude-in-progress"
LEASE_TTL_MINUTES = 10
HEARTBEAT_INTERVAL_MINUTES = 2


class ClaimLost(RuntimeError):
    """Raised when a claim is detected as lost to another instance mid-run."""


class ClaimRejected(RuntimeError):
    """Raised when claim() cannot proceed — target already held by another
    instance with a live lease, or target carries a block label.
    """


@dataclass
class Claim:
    repo: str
    issue: int
    instance_id: str
    host: str
    scope: list[str] = field(default_factory=list)
    claimed_at: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "host": self.host,
            "scope": list(self.scope),
            "claimed_at": self.claimed_at or _now_iso(),
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _instance_id_path() -> Path:
    """Where the per-user instance id is persisted between CLI invocations."""
    return Path("~/.maverick/instance_id").expanduser()


def instance_id() -> str:
    """Short, unique id for this Maverick instance.

    Stable across all CLI invocations within a single Claude Code session,
    and across separate invocations on the same machine outside one.
    Without stability, harnesses that exec the CLI per call (Claude Code's
    Bash tool, CI step runners, etc.) see a fresh id every invocation,
    which breaks heartbeat / claim-retry — every call looks like a
    different instance.

    Resolution order:
    1. ``MAVERICK_INSTANCE_ID`` env var — explicit override, wins.
    2. ``CLAUDE_SESSION_ID`` env var — derive a deterministic 10-char id
       from a hash of the session id. Two different CC sessions get
       distinct ids; every subagent and subprocess inside one CC session
       converges on the same id without needing a file write, which
       sidesteps the first-call race in the file-cache path (#40).
    3. Cached file at ``~/.maverick/instance_id`` — created on first call.
    4. Fresh random id — generated, written to the file.
    """
    cached = os.environ.get("MAVERICK_INSTANCE_ID")
    if cached:
        return cached
    session = os.environ.get("CLAUDE_SESSION_ID")
    if session:
        value = hashlib.sha256(session.encode("utf-8")).hexdigest()[:10]
        os.environ["MAVERICK_INSTANCE_ID"] = value
        return value
    path = _instance_id_path()
    try:
        value = path.read_text().strip()
        if value:
            os.environ["MAVERICK_INSTANCE_ID"] = value
            return value
    except OSError:
        # Missing file, unreadable parent, etc — fall through and generate.
        pass
    value = uuid.uuid4().hex[:10]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    except OSError:
        # Persistence failed (read-only home, sandbox, parent is a file).
        # Fall back to env-only caching so the value is at least stable
        # within this process.
        pass
    os.environ["MAVERICK_INSTANCE_ID"] = value
    return value


def _gh(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, env=env
    )
    return result.stdout


def _issue_labels(repo: str, issue: int) -> list[str]:
    out = _gh("issue", "view", str(issue), "--repo", repo, "--json", "labels")
    data = json.loads(out)
    return [lbl["name"] for lbl in data.get("labels") or []]


def _has_block_label(labels: list[str]) -> str | None:
    for lbl in labels:
        if lbl.startswith("blocked-by:#"):
            return lbl
    return None


def _lease_is_live(lease: dict[str, Any]) -> bool:
    expires = _parse_iso(str(lease.get("expires_at") or ""))
    if expires is None:
        return False
    return expires > _now()


def read_claim_state(repo: str, issue: int) -> dict[str, Any]:
    """Snapshot of coordination state for one issue — used by skills at CC1."""
    labels = _issue_labels(repo, issue)
    claim_marker = latest_marker(repo, issue, "maverick-claim")
    lease_marker = latest_marker(repo, issue, "maverick-lease")
    return {
        "labels": labels,
        "block_label": _has_block_label(labels),
        "in_progress": CLAIM_LABEL in labels,
        "claim": claim_marker.payload if claim_marker else None,
        "lease": lease_marker.payload if lease_marker else None,
        "lease_live": bool(lease_marker and _lease_is_live(lease_marker.payload)),
    }


def claim(
    repo: str,
    issue: int,
    scope: list[str] | None = None,
    env: dict[str, str] | None = None,
    allow_takeover: bool = False,
) -> Claim:
    """Attempt to claim `issue`. Raises ClaimRejected if blocked or already held."""
    state = read_claim_state(repo, issue)
    if state["block_label"]:
        raise ClaimRejected(f"#{issue} is labelled {state['block_label']}")
    if state["in_progress"] and state["lease_live"]:
        holder = (state["claim"] or {}).get("instance_id", "unknown")
        if holder != instance_id() and not allow_takeover:
            raise ClaimRejected(
                f"#{issue} already claimed by instance {holder} with live lease"
            )

    c = Claim(
        repo=repo,
        issue=issue,
        instance_id=instance_id(),
        host=socket.gethostname(),
        scope=scope or [str(issue)],
        claimed_at=_now_iso(),
    )

    # 1. Add the label (idempotent — gh will no-op if already applied)
    _gh("issue", "edit", str(issue), "--repo", repo, "--add-label", CLAIM_LABEL, env=env)
    # 2. Post the claim marker
    post_marker(
        repo,
        issue,
        "maverick-claim",
        c.to_payload(),
        preamble="<!-- maverick claim -->",
        env=env,
    )
    # 3. Start the lease
    _write_lease(repo, issue, env=env)

    # 4. Read-after-write race detection. GitHub assigns strictly-monotonic
    #    comment ids, so the most recent claim marker is canonical. If a
    #    concurrent instance posted after us, its marker will be the latest
    #    and we yield. Earlier markers are either superseded by ours or
    #    represent already-released/expired claims and must not be counted —
    #    accumulating historical markers used to permanently lock out new
    #    claimers, including legitimate takeovers (#38).
    from maverick.gh_state import find_markers

    markers = find_markers(repo, issue, "maverick-claim")
    if markers:
        latest_holder = (markers[-1].payload or {}).get("instance_id")
        if latest_holder and latest_holder != instance_id():
            raise ClaimRejected(
                f"#{issue} race lost — superseded by claim from instance {latest_holder}"
            )

    return c


def _write_lease(repo: str, issue: int, env: dict[str, str] | None = None) -> None:
    now = _now()
    payload = {
        "instance_id": instance_id(),
        "heartbeat_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(minutes=LEASE_TTL_MINUTES)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    upsert_marker(
        repo,
        issue,
        "maverick-lease",
        payload,
        preamble="<!-- maverick lease -->",
        env=env,
    )


def heartbeat(repo: str, issue: int, env: dict[str, str] | None = None) -> None:
    """Refresh the lease expiry. Raises ClaimLost if the label or claim is gone."""
    state = read_claim_state(repo, issue)
    if not state["in_progress"]:
        raise ClaimLost(f"#{issue} lost claim label")
    if (state["claim"] or {}).get("instance_id") != instance_id():
        raise ClaimLost(f"#{issue} claim now held by another instance")
    _write_lease(repo, issue, env=env)


def release(
    repo: str,
    issue: int,
    reason: str = "complete",
    env: dict[str, str] | None = None,
) -> None:
    """Drop the claim cleanly."""
    _gh(
        "issue",
        "edit",
        str(issue),
        "--repo",
        repo,
        "--remove-label",
        CLAIM_LABEL,
        env=env,
    )
    payload = {
        "instance_id": instance_id(),
        "released_at": _now_iso(),
        "reason": reason,
    }
    post_marker(
        repo,
        issue,
        "maverick-lease",
        payload,
        preamble=f"<!-- maverick lease released: {reason} -->",
        env=env,
    )


def takeover(
    repo: str,
    issue: int,
    env: dict[str, str] | None = None,
) -> Claim:
    """Take over a stale lease from a crashed instance.

    Posts an explicit takeover comment naming the prior instance, then runs
    the normal claim flow with allow_takeover=True to bypass the live-lease
    check (it is known stale).
    """
    state = read_claim_state(repo, issue)
    prior_instance = (state["claim"] or {}).get("instance_id", "unknown")
    if state["lease_live"]:
        raise ClaimRejected(
            f"#{issue} lease is still live; not a stale lease — refusing takeover"
        )
    preamble = (
        f"<!-- maverick takeover -->\n"
        f"Taking over #{issue} from instance `{prior_instance}` — prior lease stale."
    )
    post_marker(
        repo,
        issue,
        "maverick-claim",
        {
            "instance_id": instance_id(),
            "takeover_of": prior_instance,
            "claimed_at": _now_iso(),
        },
        preamble=preamble,
        env=env,
    )
    return claim(repo, issue, env=env, allow_takeover=True)


def format_lease_summary(lease_payload: dict[str, Any] | None) -> str:
    """Human-readable one-liner — used in error messages and reports."""
    if not lease_payload:
        return "no lease"
    expires = lease_payload.get("expires_at") or "?"
    instance = lease_payload.get("instance_id") or "unknown"
    return f"held by {instance} until {expires}"


# Re-export so CLI can check marker formatting without importing gh_state
__all__ = [
    "CLAIM_LABEL",
    "HEARTBEAT_INTERVAL_MINUTES",
    "LEASE_TTL_MINUTES",
    "Claim",
    "ClaimLost",
    "ClaimRejected",
    "claim",
    "format_lease_summary",
    "format_marker",
    "heartbeat",
    "instance_id",
    "read_claim_state",
    "release",
    "takeover",
]

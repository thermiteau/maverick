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

#: Env vars carrying the current Claude Code session id, most-preferred first.
#: Claude Code exports ``CLAUDE_CODE_SESSION_ID``; ``CLAUDE_SESSION_ID`` was an
#: earlier name kept as a fallback for older Claude Code versions.
_SESSION_ID_ENV_VARS = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")


def claude_session_id() -> str | None:
    """Return the current Claude Code session id, or ``None`` outside a session.

    Reads ``CLAUDE_CODE_SESSION_ID`` (the current name) and falls back to the
    legacy ``CLAUDE_SESSION_ID`` for older Claude Code versions.
    """
    for name in _SESSION_ID_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


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


def _claims_registry_path() -> Path:
    """Local registry of claims held by instances on this machine.

    The registry exists so that (a) the SessionEnd hook can release every
    claim this session still holds without knowing repo/issue numbers, and
    (b) the scope-guard hook can detect "this session is running an
    autonomous workflow" (an instance that holds a claim is by definition
    autonomous). It is a derivable cache — GitHub markers stay the source
    of truth, and a stale registry entry is harmless: release is
    idempotent and lease expiry covers machine death.
    """
    return Path("~/.maverick/active-claims.json").expanduser()


def _read_claims_registry() -> list[dict[str, Any]]:
    """Read the local claims registry, tolerating a missing/corrupt file."""
    try:
        raw = json.loads(_claims_registry_path().read_text())
    except (OSError, json.JSONDecodeError):
        return []
    claims = raw.get("claims") if isinstance(raw, dict) else None
    return claims if isinstance(claims, list) else []


def _write_claims_registry(claims: list[dict[str, Any]]) -> None:
    path = _claims_registry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"claims": claims}, indent=2) + "\n")
    except OSError:
        pass  # registry is best-effort; the GitHub marker is authoritative


def _registry_add(repo: str, issue: int) -> None:
    claims = [
        c
        for c in _read_claims_registry()
        if not (c.get("repo") == repo and c.get("issue") == issue)
    ]
    claims.append(
        {
            "repo": repo,
            "issue": issue,
            "instance_id": instance_id(),
            "claimed_at": _now_iso(),
        }
    )
    _write_claims_registry(claims)


def _registry_remove(repo: str, issue: int) -> None:
    claims = [
        c
        for c in _read_claims_registry()
        if not (c.get("repo") == repo and c.get("issue") == issue)
    ]
    _write_claims_registry(claims)


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
    2. ``CLAUDE_CODE_SESSION_ID`` env var (legacy ``CLAUDE_SESSION_ID``) —
       derive a deterministic 10-char id from a hash of the session id.
       Two different CC sessions get
       distinct ids; every subagent and subprocess inside one CC session
       converges on the same id without needing a file write, which
       sidesteps the first-call race in the file-cache path (#40).
    3. Cached file at ``~/.maverick/instance_id`` — created on first call.
    4. Fresh random id — generated, written to the file.
    """
    cached = os.environ.get("MAVERICK_INSTANCE_ID")
    if cached:
        return cached
    session = claude_session_id()
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

    # Record locally so the SessionEnd hook can release-all on exit and the
    # scope-guard hook can detect autonomous mode.
    _registry_add(repo, issue)

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


def heartbeat_loop(
    repo: str,
    issue: int,
    interval_seconds: int = HEARTBEAT_INTERVAL_MINUTES * 60,
    env: dict[str, str] | None = None,
) -> int:
    """Run heartbeat in a foreground loop, exiting cleanly when the claim
    is released or otherwise lost.

    Designed to be backgrounded by a single skill step (e.g. `do-epic`
    Phase 0) so that the loop owns its own lifecycle: when `coord release`
    runs at session end the claim label is removed, the next heartbeat
    raises `ClaimLost`, and this function returns 0 — no separate `kill`
    step needed (#47).

    Also handles SIGINT/SIGTERM so a parent process killing it gets a
    clean exit. Sleeps in 1-second slices to keep signals responsive.
    """
    import signal
    import time

    stopping = False

    def _stop(_signum: int, _frame: object | None) -> None:
        nonlocal stopping
        stopping = True

    prev_int = signal.signal(signal.SIGINT, _stop)
    prev_term = signal.signal(signal.SIGTERM, _stop)
    try:
        while not stopping:
            try:
                heartbeat(repo, issue, env=env)
            except ClaimLost:
                return 0
            slept = 0
            while slept < interval_seconds and not stopping:
                time.sleep(1)
                slept += 1
        return 0
    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)


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
    _registry_remove(repo, issue)


def release_all(
    reason: str = "session-end", env: dict[str, str] | None = None
) -> list[tuple[str, int]]:
    """Release every claim this instance recorded in the local registry.

    Designed for the SessionEnd hook: idempotent, tolerant of claims that
    were already released or taken over remotely (each release failure is
    swallowed — lease expiry is the backstop). Returns the (repo, issue)
    pairs that were released.
    """
    mine = [c for c in _read_claims_registry() if c.get("instance_id") == instance_id()]
    released: list[tuple[str, int]] = []
    for c in mine:
        repo, issue = c.get("repo"), c.get("issue")
        if not isinstance(repo, str) or not isinstance(issue, int):
            continue
        try:
            release(repo, issue, reason=reason, env=env)
            released.append((repo, issue))
        except Exception:
            # Claim may already be gone (released, taken over, issue closed).
            pass
        # Drop the registry entry either way — release() also removes it,
        # but the registry must never retain an entry past this pass.
        _registry_remove(repo, issue)
    return released


AUTHORIZE_LABEL_PREFIX = "maverick-authorize-"
AUTHORIZE_BODY_RE = r"(?im)^\s*maverick-authorize:\s*(?P<scopes>[a-z, -]+)\s*$"
SESSION_AUTH_PATH = Path(".maverick/session-auth.json")


class AuthorizationRejected(Exception):
    """The issue does not carry an explicit authorization for the scope."""


def authorize(
    repo: str, issue: int, scope: str, env: dict[str, str] | None = None
) -> dict[str, Any]:
    """Verify issue-level authorization for *scope* and record it locally.

    Authorization must be explicit on the GitHub issue itself — either a
    ``maverick-authorize-<scope>`` label or a ``Maverick-Authorize: <scope>``
    line in the issue body. This function is the only sanctioned writer of
    ``.maverick/session-auth.json`` (the scope-guard hook blocks direct
    edits to that file), so an agent cannot self-grant a scope the issue
    never authorized.
    """
    import re

    scope = scope.strip().lower()
    labels = _issue_labels(repo, issue)
    granted = f"{AUTHORIZE_LABEL_PREFIX}{scope}" in labels

    if not granted:
        out = _gh("issue", "view", str(issue), "--repo", repo, "--json", "body", env=env)
        body = json.loads(out).get("body") or ""
        for m in re.finditer(AUTHORIZE_BODY_RE, body):
            scopes = [s.strip() for s in m.group("scopes").split(",")]
            if scope in scopes:
                granted = True
                break

    if not granted:
        raise AuthorizationRejected(
            f"{repo}#{issue} does not authorize scope {scope!r}: add the "
            f"'{AUTHORIZE_LABEL_PREFIX}{scope}' label or a 'Maverick-Authorize: "
            f"{scope}' line to the issue body."
        )

    auth: dict[str, Any] = {"repo": repo, "issue": issue, "scopes": [scope]}
    try:
        existing = json.loads(SESSION_AUTH_PATH.read_text())
        if existing.get("repo") == repo and existing.get("issue") == issue:
            merged = sorted(set(existing.get("scopes") or []) | {scope})
            auth["scopes"] = merged
    except (OSError, json.JSONDecodeError):
        pass
    auth["granted_at"] = _now_iso()
    SESSION_AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_AUTH_PATH.write_text(json.dumps(auth, indent=2) + "\n")
    return auth


def takeover(
    repo: str,
    issue: int,
    scope: list[str] | None = None,
    reason: str | None = None,
    env: dict[str, str] | None = None,
) -> Claim:
    """Take over a stale lease from a crashed instance.

    Posts an explicit takeover comment naming the prior instance, then runs
    the normal claim flow with allow_takeover=True to bypass the live-lease
    check (it is known stale). `scope` is forwarded to the inner claim so a
    multi-story epic can be taken over and re-scoped in one call rather
    than forcing N+1 round-trips (#42). `reason` is recorded on the
    takeover marker for the audit trail.
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
    if reason:
        preamble += f"\nReason: {reason}"
    payload: dict[str, Any] = {
        "instance_id": instance_id(),
        "takeover_of": prior_instance,
        "claimed_at": _now_iso(),
    }
    if reason:
        payload["reason"] = reason
    post_marker(
        repo,
        issue,
        "maverick-claim",
        payload,
        preamble=preamble,
        env=env,
    )
    return claim(repo, issue, scope=scope, env=env, allow_takeover=True)


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

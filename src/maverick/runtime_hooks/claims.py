"""Read-only view of this instance's identity and claims, shared by handlers.

Handlers run in a hook subprocess, so they must never generate or persist
an instance id — that is ``coordinator.instance_id()``'s job. They only
mirror its derivation so the hook and the coordinator agree on whether a
claim belongs to this instance (#130).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def claims_registry_path() -> Path:
    return Path("~/.maverick/active-claims.json").expanduser()


def instance_id_path() -> Path:
    """Where coordinator.instance_id() persists the per-user id."""
    return Path("~/.maverick/instance_id").expanduser()


def instance_id(env: dict[str, str], id_path: Path | None = None) -> str | None:
    """Mirror coordinator.instance_id()'s derivation (read-only, never writes).

    The rungs must match ``coordinator.instance_id()`` exactly. The file
    fallback is essential: hooks run in a separately-spawned subprocess that
    in some runtime versions does not receive the session-id env, so without
    it the hook would fall straight to ``None`` while the coordinator
    resolved a real id via the session hash (or the file).
    """
    explicit = env.get("MAVERICK_INSTANCE_ID")
    if explicit:
        return explicit
    session = env.get("CLAUDE_CODE_SESSION_ID") or env.get("CLAUDE_SESSION_ID")
    if session:
        return hashlib.sha256(session.encode("utf-8")).hexdigest()[:10]
    try:
        cached = (id_path or instance_id_path()).read_text().strip()
        if cached:
            return cached
    except OSError:
        pass
    return None


def load_claims(registry: Path | None = None) -> list[dict]:
    """All claims in the registry; empty on any read or parse problem."""
    try:
        claims = json.loads((registry or claims_registry_path()).read_text()).get(
            "claims", []
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    return [c for c in claims if isinstance(c, dict)] if isinstance(claims, list) else []


def my_claims(
    env: dict[str, str],
    registry: Path | None = None,
    id_path: Path | None = None,
) -> list[dict]:
    """Claims held by this instance."""
    instance = instance_id(env, id_path)
    if not instance:
        return []
    return [c for c in load_claims(registry) if c.get("instance_id") == instance]

"""Session-end handler — release any claims this session still holds.

Replaces the old (unimplementable) skill instruction to "register a
release handler that fires on every exit path": each shell tool call is a
fresh shell, so a trap can never survive to session end. This hook is the
real exit path. It runs ``maverick coord release-all``, which releases
every claim recorded for this instance in ``~/.maverick/active-claims.json``.

Failure model:

- Never raises — a release failure must never break session teardown.
- No registry file, or no claims at all → silent no-op.
- If the release command errors, lease expiry (10 min TTL) remains the
  designed crash path; another instance can take over cleanly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from maverick.runtime_hooks.adapters import HookOutput
from maverick.runtime_hooks.claims import load_claims

TIMEOUT_SECONDS = 60


def release_command() -> list[str]:
    """Run the CLI through this interpreter, so it is the same installation."""
    return [sys.executable, "-m", "maverick.cli", "coord", "release-all", "--reason", "session-end"]


def handle(registry: Path | None = None) -> HookOutput:
    if not load_claims(registry):
        return HookOutput()
    try:
        result = subprocess.run(
            release_command(),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        summary = (result.stdout or "").strip().splitlines()
        if summary:
            return HookOutput(stderr=f"maverick session-release: {summary[-1]}\n")
    except Exception as exc:  # noqa: BLE001 — never break session teardown
        return HookOutput(
            stderr=f"maverick session-release: {exc}; relying on lease expiry.\n"
        )
    return HookOutput()

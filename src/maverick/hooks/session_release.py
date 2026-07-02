#!/usr/bin/env python3
"""SessionEnd hook — release any claims this session still holds.

Replaces the old (unimplementable) skill instruction to "register a
release handler that fires on every exit path": each Bash tool call is a
fresh shell, so a trap can never survive to session end. This hook is the
real exit path. It runs ``maverick coord release-all``, which releases
every claim recorded for this instance in ``~/.maverick/active-claims.json``.

Failure model, in line with install_check.py's standard:

- Always exits 0 — a release failure must never break session teardown.
- No registry file, or no claims for this instance → silent no-op.
- If the CLI is missing or errors, lease expiry (10 min TTL) remains the
  designed crash path; another instance can take over cleanly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

CLAIMS_REGISTRY = Path("~/.maverick/active-claims.json").expanduser()
TIMEOUT_SECONDS = 60


def _has_claims() -> bool:
    try:
        claims = json.loads(CLAIMS_REGISTRY.read_text()).get("claims", [])
        return bool(claims)
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def _cli_command() -> list[str] | None:
    """Prefer the installed CLI; fall back to `uv run maverick` in a checkout."""
    if shutil.which("maverick"):
        return ["maverick"]
    if shutil.which("uv") and Path("pyproject.toml").is_file():
        return ["uv", "run", "maverick"]
    return None


def main() -> int:
    if not _has_claims():
        return 0
    cli = _cli_command()
    if cli is None:
        print(
            "maverick session-release: CLI not found; relying on lease expiry.",
            file=sys.stderr,
        )
        return 0
    try:
        result = subprocess.run(
            [*cli, "coord", "release-all", "--reason", "session-end"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        summary = (result.stdout or "").strip().splitlines()
        if summary:
            print(f"maverick session-release: {summary[-1]}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — never break session teardown
        print(
            f"maverick session-release: {exc}; relying on lease expiry.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

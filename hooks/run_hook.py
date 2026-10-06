#!/usr/bin/env python3
"""Hook shim — pipe the runtime's hook payload into ``maverick hook``.

    python3 run_hook.py <handler> --runtime <name>

All hook logic lives in the Maverick CLI (``maverick.runtime_hooks``); the
plugin ships only this shim, so policy cannot drift between plugin copies.

Failure model: the shim must never break or block the session.

- CLI not found → one-line warning, exit 0.
- CLI exits non-zero (e.g. an older CLI without ``maverick hook``, which
  exits 2 from argparse — a code the runtime would read as "block") →
  warning, exit 0. The CLI expresses every real decision on stdout with
  exit 0, so a non-zero exit is always a failure, never a verdict.
- CLI exits 0 → its stdout and stderr are relayed verbatim.

Pure stdlib: runs under bare ``python3`` before the CLI is installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 90


def _cli_command() -> list[str] | None:
    """Prefer the installed CLI; fall back to `uv run maverick` in a checkout."""
    if shutil.which("maverick"):
        return ["maverick"]
    if shutil.which("uv") and Path("pyproject.toml").is_file():
        return ["uv", "run", "maverick"]
    return None


def main(argv: list[str]) -> int:
    payload = sys.stdin.read()
    handler = argv[0] if argv else "unknown"
    cli = _cli_command()
    if cli is None:
        print(
            f"maverick {handler}: CLI not found, hook skipped. "
            "Run /maverick:do-install.",
            file=sys.stderr,
        )
        return 0
    try:
        result = subprocess.run(
            [*cli, "hook", *argv],
            input=payload,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — never break the session
        print(f"maverick {handler}: {exc}; hook skipped.", file=sys.stderr)
        return 0
    if result.returncode != 0:
        print(
            f"maverick {handler}: CLI could not run the hook (exit "
            f"{result.returncode}); skipped. The installed CLI may predate "
            "`maverick hook` — run /maverick:do-install.",
            file=sys.stderr,
        )
        return 0
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

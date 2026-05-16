#!/usr/bin/env python3
"""SessionStart hook — install the Maverick CLI if missing, warn if stale.

Claude Code has no PluginInstall lifecycle event, so SessionStart is the
closest fit for keeping the system-wide CLI in sync with the markdown
plugin that ``/plugin update`` refreshes. Steady-state cost is a single
``shutil.which`` call plus, when the CLI is present, one
``maverick --version`` invocation to detect drift.

Behaviour:
  - ``maverick`` not on PATH and ``CLAUDE_PLUGIN_ROOT`` set
        -> auto-install via ``python -m maverick.install_cli``.
  - ``maverick`` not on PATH and no plugin root
        -> print one-line nudge, exit 0.
  - ``maverick`` on PATH and version is older than the plugin
        -> print a clear stderr warning telling the user to run
           /maverick:do-install. Do NOT auto-heal — a pinned CLI is a
           legitimate state we must not clobber silently.
  - ``maverick`` on PATH and version matches (or cannot be parsed)
        -> exit 0 silently.

The hook always exits 0 so a transient failure cannot abort the session.
``preflight`` is the hard gate that blocks skill execution on drift; this
hook only surfaces the problem early.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _import_version_check(plugin_root: str):
    """Best-effort import of ``maverick.version_check`` from the plugin source.

    The hook runs under bare ``python3``, not ``uv``, so ``maverick``
    isn't necessarily on the import path. We point ``sys.path`` at the
    plugin's ``src/`` directory and import directly. Returns ``None`` if
    the module is missing — older plugin checkouts pre-date the version
    check, and that's fine: preflight remains the backstop.
    """
    src_dir = Path(plugin_root) / "src"
    if not src_dir.is_dir():
        return None
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        from maverick import version_check  # type: ignore[import-not-found]
    except Exception:
        return None
    return version_check


def _warn_if_stale(plugin_root: str) -> None:
    """If the installed CLI is older than the plugin, print a warning."""
    version_check = _import_version_check(plugin_root)
    if version_check is None:
        return
    try:
        result = version_check.check_cli_compatibility(Path(plugin_root))
    except Exception:
        # Defensive: the comparison must never abort session start.
        return
    if result.ok:
        return
    print(
        f"Maverick: CLI/plugin version skew detected. {result.remediation}",
        file=sys.stderr,
    )


def main() -> int:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()

    if shutil.which("maverick"):
        if plugin_root:
            _warn_if_stale(plugin_root)
        return 0

    if not plugin_root:
        print(
            "Maverick CLI not detected. Run /maverick:do-install for setup.",
            file=sys.stderr,
        )
        return 0

    if not shutil.which("uv"):
        print(
            "Maverick CLI not detected and 'uv' is not installed. "
            "Install uv (curl -LsSf https://astral.sh/uv/install.sh | sh), "
            "then run /maverick:do-install.",
            file=sys.stderr,
        )
        return 0

    print("Maverick CLI not detected — running first-time install...", file=sys.stderr)
    try:
        subprocess.run(
            [
                "uv",
                "run",
                "--directory",
                plugin_root,
                "python",
                "-m",
                "maverick.install_cli",
                "--plugin-root",
                plugin_root,
            ],
            check=True,
        )
        print(
            "Maverick CLI installed. You may need to refresh your shell "
            "PATH or restart the session for the binary to be visible.",
            file=sys.stderr,
        )
    except subprocess.CalledProcessError:
        print(
            "Maverick auto-install failed. Run /maverick:do-install for details.",
            file=sys.stderr,
        )
    except FileNotFoundError:
        print(
            "Maverick auto-install failed: 'uv' was reported on PATH but could "
            "not be executed. Run /maverick:do-install for details.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

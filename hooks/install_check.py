#!/usr/bin/env python3
"""SessionStart hook — auto-install the Maverick CLI if missing.

Claude Code has no PluginInstall lifecycle event. SessionStart is the
closest fit; this hook short-circuits to a no-op once the CLI is on PATH,
so the steady-state cost is one ``shutil.which`` call per session.

Behaviour:
  - ``maverick`` already on PATH       -> exit 0 silently.
  - ``CLAUDE_PLUGIN_ROOT`` not set     -> print one-line nudge, exit 0.
  - ``uv`` not on PATH                 -> print one-line install hint, exit 0.
  - Otherwise                          -> run ``python -m maverick.install_cli``
                                          via ``uv run --directory <plugin-root>``.

The hook always exits 0 so a transient failure cannot abort the session.
The user sees stderr output and can run ``/maverick:do-install`` manually
for a richer diagnosis.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def main() -> int:
    if shutil.which("maverick"):
        return 0

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
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

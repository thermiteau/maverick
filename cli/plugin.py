"""Plugin management for maverick — install/uninstall the Claude Code plugin."""

import shutil
import subprocess
import sys
from pathlib import Path

MARKETPLACE_SOURCE = "thermiteau/maverick"
MARKETPLACE_NAME = "maverick"


def _run_claude(*args: str) -> subprocess.CompletedProcess:
    """Run a claude CLI command, forwarding stdout/stderr."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        print("Error: 'claude' CLI not found on PATH.")
        print("Install it from https://docs.anthropic.com/en/docs/claude-code")
        sys.exit(1)

    return subprocess.run(
        [claude_bin, *args],
        check=False,
    )


def get_plugin_dir() -> Path:
    """Resolve path to the maverick-plugin/ directory for --dev mode.

    Checks (in order):
    1. Relative to this file's package root (editable/dev install from repo)
    2. Current working directory (uv tool install, run from repo checkout)
    3. Relative to this file's package dir (bundled install)
    """
    candidates = [
        # Editable install: src/maverick/plugin.py -> ../../maverick-plugin
        Path(__file__).resolve().parent.parent.parent / "maverick-plugin",
        # uv tool install, run from repo checkout: ./maverick-plugin
        Path.cwd().resolve() / "maverick-plugin",
        # Bundled alongside package
        Path(__file__).resolve().parent / "maverick-plugin",
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    print("Error: Could not find maverick-plugin/ directory.")
    print("Run this command from the maverick repo, or use an editable install.")
    print("Checked:")
    for c in candidates:
        print(f"  {c}")
    sys.exit(1)


def install(dev: bool = False) -> None:
    """Install the maverick plugin for Claude Code."""
    if dev:
        plugin_dir = str(get_plugin_dir())
        print(f"Loading plugin from local directory: {plugin_dir}")
        print(f"Use 'claude --plugin-dir {plugin_dir}' to start Claude Code with this plugin.")
        print()
        print("Alternatively, run Claude Code with:")
        print(f"  claude --plugin-dir {plugin_dir}")
    else:
        print(f"Adding maverick marketplace from {MARKETPLACE_SOURCE}...")
        result = _run_claude("plugin", "marketplace", "add", MARKETPLACE_SOURCE)
        if result.returncode != 0:
            print("Failed to add maverick marketplace.")
            sys.exit(1)
        print("Maverick plugin marketplace added successfully.")


def uninstall() -> None:
    """Remove the maverick plugin from Claude Code."""
    print(f"Removing maverick marketplace...")
    result = _run_claude("plugin", "marketplace", "remove", MARKETPLACE_NAME)
    if result.returncode != 0:
        print("Failed to remove maverick marketplace.")
        sys.exit(1)
    print("Maverick marketplace removed successfully.")


def main(action: str, dev: bool = False, clean: bool = False) -> None:
    """Entry point called from cli.py."""
    if action == "install":
        install(dev=dev)
    elif action == "uninstall":
        uninstall()
        if clean:
            from maverick.init import clean as run_clean

            run_clean(dry_run=False)
    else:
        print(f"Unknown plugin action: {action}")
        sys.exit(1)

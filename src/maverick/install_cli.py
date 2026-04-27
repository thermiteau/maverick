"""Install the maverick CLI tool from a plugin directory.

Run from a shell with the plugin root as the working directory:

    uv run --directory <plugin-root> python -m maverick.install_cli

Or pass the root explicitly:

    uv run python -m maverick.install_cli --plugin-root <path>

Steps performed:
    1. Verify ``uv`` is on PATH.
    2. Verify ``pyproject.toml`` exists at the plugin root.
    3. Run ``uv tool install --force <plugin-root>``.
    4. Verify ``maverick`` is now on PATH (warn if not).
    5. Add a Claude permission entry granting read access to the
       maverick plugin cache, so future sessions can read plugin files
       without prompting.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PERMISSION_ENTRY = "Read(~/.claude/plugins/cache/thermite/maverick/**)"
DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


class InstallError(Exception):
    """Raised when a precondition for installing the CLI is not satisfied."""


def _check_uv_available() -> None:
    if shutil.which("uv") is None:
        raise InstallError(
            "uv is required but not installed.\n"
            "Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh"
        )


def _check_gh_available() -> None:
    if shutil.which("gh") is None:
        raise InstallError(
            "GitHub CLI (gh) is required but not installed.\n"
            "Maverick workflows depend on gh for issue and PR operations.\n"
            "\n"
            "Install instructions:\n"
            "  macOS:    brew install gh\n"
            "  Linux:    https://github.com/cli/cli/blob/trunk/docs/install_linux.md\n"
            "  Windows:  winget install --id GitHub.cli\n"
            "\n"
            "After install, authenticate once with:  gh auth login\n"
            "Then re-run this installer."
        )


def _check_plugin_root(plugin_root: Path) -> None:
    if not (plugin_root / "pyproject.toml").is_file():
        raise InstallError(
            f"pyproject.toml not found at {plugin_root}\n"
            "This script must be run from a complete maverick plugin directory."
        )


def _install_cli(plugin_root: Path) -> None:
    print(f"Installing maverick CLI from {plugin_root} ...")
    subprocess.run(
        ["uv", "tool", "install", "--force", str(plugin_root)],
        check=True,
    )


def _verify_on_path() -> bool:
    """Return True if maverick is now on PATH; print a warning otherwise."""
    maverick_path = shutil.which("maverick")
    if maverick_path:
        print(f"maverick installed successfully: {maverick_path}")
        return True

    print(
        "\nWarning: maverick was installed but is not on your PATH.\n"
        "Add ~/.local/bin to your PATH:\n"
        '  export PATH="$HOME/.local/bin:$PATH"\n\n'
        "Then restart your shell or run the export command above.",
        file=sys.stderr,
    )
    return False


def update_settings_permission(
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    entry: str = PERMISSION_ENTRY,
) -> bool:
    """Add ``entry`` to ``permissions.allow`` in the Claude settings file.

    Creates the file (and parent directory) if missing. Returns True if the
    file was modified, False if the entry was already present.
    """
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}

    permissions = settings.setdefault("permissions", {})
    allow = list(permissions.get("allow", []))

    if entry in allow:
        print(f"Permission already present in {settings_path}.")
        return False

    allow.append(entry)
    permissions["allow"] = allow
    permissions.setdefault("deny", [])
    settings["permissions"] = permissions
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Updated {settings_path} with read permission for plugin cache.")
    return True


def install(plugin_root: Path) -> int:
    """Run the full install procedure. Returns a process exit code."""
    try:
        _check_uv_available()
        _check_gh_available()
        _check_plugin_root(plugin_root)
    except InstallError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        _install_cli(plugin_root)
    except subprocess.CalledProcessError as e:
        print(f"Error: 'uv tool install' failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode

    _verify_on_path()
    update_settings_permission()
    print("\nDone.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install the maverick CLI from a plugin directory.",
    )
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the plugin directory containing pyproject.toml (default: cwd).",
    )
    args = parser.parse_args(argv)
    return install(args.plugin_root.resolve())


if __name__ == "__main__":
    sys.exit(main())

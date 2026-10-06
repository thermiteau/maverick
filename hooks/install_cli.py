"""Install the maverick CLI tool for a plugin directory.

The build copies this file into the plugin's ``hooks/`` directory, so it
runs under bare ``python3`` before the CLI exists — it must stay
stdlib-only with no ``maverick.*`` imports:

    python3 <plugin-root>/hooks/install_cli.py --plugin-root <plugin-root>

From a source checkout it also runs as a module:

    uv run python -m maverick.install_cli --plugin-root <path>

What gets installed depends on the plugin root:

- **Source checkout** (``pyproject.toml`` present — a dev checkout, or a
  plugin that ships its source): ``uv tool install --force <plugin-root>``.
- **Released plugin** (no source): the PyPI release matching the plugin
  version, ``uv tool install --force maverick-harness==<version>``.

Steps performed:
    1. Verify ``uv`` and ``gh`` are on PATH.
    2. Resolve what to install (above).
    3. Remove the legacy ``maverick`` uv tool (the distribution was renamed
       to ``maverick-harness``; both would provide the ``maverick`` command).
    4. Install, then verify ``maverick`` is on PATH (warn if not).
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

#: PyPI distribution name. The command and import package are ``maverick``;
#: that name is taken on PyPI.
DIST_NAME = "maverick-harness"
#: uv tool name used before the rename. Same ``maverick`` executable.
LEGACY_TOOL_NAME = "maverick"

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


def _read_plugin_version(plugin_root: Path) -> str | None:
    try:
        data = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else None


def install_spec(plugin_root: Path) -> str:
    """What ``uv tool install`` should install for this plugin root."""
    if (plugin_root / "pyproject.toml").is_file():
        return str(plugin_root)
    version = _read_plugin_version(plugin_root)
    if version is None:
        raise InstallError(
            f"No pyproject.toml and no readable plugin version at {plugin_root}.\n"
            "This script must be run against a complete maverick plugin directory."
        )
    if "dev" in version:
        raise InstallError(
            f"Plugin version {version} is a development build, which is not "
            "published to PyPI.\nInstall the CLI from a source checkout instead: "
            "uv tool install --force <path-to-maverick-checkout>"
        )
    return f"{DIST_NAME}=={version.lstrip('v')}"


def _has_legacy_tool() -> bool:
    """True when ``uv tool list`` shows a tool named exactly ``maverick``."""
    try:
        result = subprocess.run(
            ["uv", "tool", "list"], capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    for line in result.stdout.splitlines():
        # Tool lines are "<name> v<version>"; executable lines start with "-".
        parts = line.split()
        if parts and not line.startswith("-") and parts[0] == LEGACY_TOOL_NAME:
            return True
    return False


def _remove_legacy_tool() -> None:
    """Uninstall the pre-rename tool so it cannot shadow or clobber the new one.

    Must run *before* installing: uninstalling afterwards would delete the
    ``maverick`` executable link the new install just took over.
    """
    if not _has_legacy_tool():
        return
    print(
        f"Removing legacy '{LEGACY_TOOL_NAME}' tool (now distributed as {DIST_NAME}) ..."
    )
    subprocess.run(["uv", "tool", "uninstall", LEGACY_TOOL_NAME], check=False)


def _install_cli(spec: str) -> None:
    print(f"Installing maverick CLI from {spec} ...")
    subprocess.run(
        ["uv", "tool", "install", "--force", spec],
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
        spec = install_spec(plugin_root)
    except InstallError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    _remove_legacy_tool()
    try:
        _install_cli(spec)
    except subprocess.CalledProcessError as e:
        print(
            f"Error: 'uv tool install' failed with exit code {e.returncode}. "
            "Re-run this installer once the problem is fixed.",
            file=sys.stderr,
        )
        return e.returncode

    _verify_on_path()
    update_settings_permission()
    print("\nDone.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install the maverick CLI for a plugin directory.",
    )
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the plugin directory (default: cwd).",
    )
    args = parser.parse_args(argv)
    return install(args.plugin_root.resolve())


if __name__ == "__main__":
    sys.exit(main())

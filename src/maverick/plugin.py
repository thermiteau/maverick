"""Claude Code plugin management commands for Maverick.

Manages the Maverick plugin entry in ~/.claude/settings.json so that
Claude Code loads the Maverick skills and agents.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

SETTINGS_FILE = Path.home() / ".claude" / "settings.json"


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")


def _find_plugin_dir(dev: bool) -> Path:
    """Resolve the maverick-plugin directory path.

    In dev mode, looks for a maverick-plugin/ subdirectory in cwd first,
    then falls back to cwd/maverick-plugin (which may not exist yet but
    is the conventional location referenced by CLAUDE.md).

    In production mode, uses the standard installed plugin path.
    """
    if dev:
        cwd = Path.cwd()
        candidate = cwd / "maverick-plugin"
        return candidate.resolve()
    else:
        return Path.home() / ".claude" / "plugins" / "maverick-plugin"


def main(action: str, dev: bool = False, clean: bool = False) -> None:
    """Install or uninstall the Maverick Claude Code plugin.

    Args:
        action: Either "install" or "uninstall".
        dev: Whether to use the local development plugin directory.
        clean: Whether to also remove project-level artifacts on uninstall.
    """
    if action == "install":
        _install(dev)
    elif action == "uninstall":
        _uninstall(clean)


def _install(dev: bool) -> None:
    plugin_dir = _find_plugin_dir(dev)
    settings = _load_settings()
    dirs = settings.get("pluginDirs", [])
    plugin_path = str(plugin_dir)
    if plugin_path not in dirs:
        dirs.append(plugin_path)
    settings["pluginDirs"] = dirs
    _save_settings(settings)
    mode = "dev" if dev else "production"
    print(f"Installed maverick-plugin ({mode}): {plugin_dir}")


def _uninstall(clean: bool) -> None:
    settings = _load_settings()
    if "pluginDirs" in settings:
        del settings["pluginDirs"]
    _save_settings(settings)
    print("Uninstalled maverick-plugin from settings.json")

    if clean:
        maverick_dir = Path.cwd() / ".maverick"
        if maverick_dir.is_dir():
            shutil.rmtree(maverick_dir)
            print(f"Removed {maverick_dir}/")


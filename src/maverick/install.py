"""Maverick CLI installation helpers — manages Claude Code permissions."""

import json
from pathlib import Path

PERM_ENTRY = "Read(~/.claude/plugins/cache/thermite/maverick/**)"


def _read_settings() -> tuple[Path, dict]:
    """Read ~/.claude/settings.json, returning (path, parsed dict)."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        return settings_path, json.loads(settings_path.read_text())
    return settings_path, {}


def _write_settings(path: Path, settings: dict) -> None:
    """Write settings dict to the given path as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")


def update_claude_permissions() -> None:
    """Add plugin cache read permission to ~/.claude/settings.json."""
    settings_path, settings = _read_settings()

    permissions = settings.setdefault("permissions", {})
    allow = list(permissions.get("allow", []))

    if PERM_ENTRY not in allow:
        allow.append(PERM_ENTRY)
        permissions["allow"] = allow
        permissions.setdefault("deny", [])
        settings["permissions"] = permissions
        _write_settings(settings_path, settings)
        print(f"Updated {settings_path} with read permission for plugin cache.")
    else:
        print(f"Permission already present in {settings_path}.")

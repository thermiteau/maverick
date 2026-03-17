"""Configuration loading and state file locations for Maverick CLI.

This module centralises where configuration and state are stored on disk.
It is intentionally lightweight so it can be imported from infra, instance,
worker, and build_ami without side effects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# Project-level config directory, per CLAUDE.md
PROJECT_CONFIG_DIR = Path(".maverick")
USER_CONFIG_DIR = Path.home() / ".maverick"

SYSTEM_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

# Derived state file locations
STATE_DIR = USER_CONFIG_DIR
AMI_STATE = STATE_DIR / "ami_state.json"
INFRA_STATE = STATE_DIR / "infra_state.json"
INSTANCE_STATE = STATE_DIR / "instance_state.json"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def init_config() -> Dict[str, Any]:
    """Load system configuration.

    Preference order:
    1. Project-level .maverick/config.json if present
    2. User-level ~/.maverick/config.json
    3. Empty dict (caller should validate required keys)
    """
    project_cfg = PROJECT_CONFIG_DIR / "config.json"
    if project_cfg.exists():
        return _load_json(project_cfg)
    return _load_json(SYSTEM_CONFIG_FILE)


def save_config(cfg: Dict[str, Any]) -> None:
    """Persist configuration to the user-level config file."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")


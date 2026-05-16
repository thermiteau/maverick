"""Compare the installed Maverick CLI version against the plugin's version.

Claude Code's ``/plugin update`` refreshes only the markdown skills under
``skills/``; it never touches the system-wide ``maverick`` CLI installed
via ``uv tool install``. The two artefacts can therefore drift — a stale
2.x CLI is happy to launch but blows up the moment a 3.x skill calls
``maverick task-progress``.

This module is the single source of truth for detecting that drift. It
is imported by:

  - ``maverick.preflight`` as a runtime check (hard gate before a skill).
  - ``hooks/install_check.py`` for a soft warning at session start.

The hook runs under bare ``python3`` (no ``uv``), so this module is
stdlib-only and contains no ``maverick.*`` imports.

The minimum CLI version is the plugin's own version, read from
``.claude-plugin/plugin.json`` at the plugin root. The release process
keeps the plugin's version field in sync with the CLI's
``pyproject.toml`` version, so the two are always equivalent at release
time. Patch differences are ignored — no skill should ever depend on a
patch bump.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Strict enough to catch typos, lax enough for `-dev`, `.dev0`, optional `v` prefix.
_VERSION_RE = re.compile(
    r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?dev\d*)?$"
)

CompatibilityReason = Literal[
    "ok",
    "cli_missing",
    "cli_older",
    "version_unreadable",
]


@dataclass(frozen=True)
class CompatibilityResult:
    """Outcome of a CLI/plugin version comparison.

    ``ok`` is the single boolean a caller should branch on. ``reason``
    discriminates the failure modes for callers that want to render
    different messages, and ``remediation`` is the user-facing fix line.
    """

    ok: bool
    reason: CompatibilityReason
    installed_version: str | None
    required_version: str | None
    remediation: str


def parse_semver(text: str) -> tuple[int, int, int] | None:
    """Parse a version string into a ``(major, minor, patch)`` tuple.

    Returns ``None`` if the input cannot be interpreted. Accepted shapes:

      ``3.1.1``         -> (3, 1, 1)
      ``3.1``           -> (3, 1, 0)
      ``v3.1.1``        -> (3, 1, 1)
      ``3.1.2-dev``     -> (3, 1, 2)
      ``3.1.2.dev0``    -> (3, 1, 2)
      ``maverick 3.1.1`` -> (3, 1, 1)   (the leading word is stripped)

    The dev suffix is collapsed to the release it precedes — an editable
    install from a dev branch is treated as the release whose number it
    carries. Skills that depend on something introduced in that dev cycle
    must bump the plugin floor when they land in a release.
    """
    if not text:
        return None
    candidate = text.strip()
    # Strip a leading word like "maverick" from `maverick 3.1.1`.
    if " " in candidate:
        candidate = candidate.rsplit(" ", 1)[-1]
    match = _VERSION_RE.match(candidate)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) is not None else 0
    return (major, minor, patch)


def _read_plugin_version(plugin_root: Path) -> str | None:
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def _read_installed_cli_version() -> str | None:
    """Return the bare version string emitted by ``maverick --version``.

    ``argparse``'s ``--version`` prints ``"maverick 3.1.1"`` (or whatever
    is in ``prog``), so we strip everything before the last token. This
    keeps user-facing remediation messages from rendering ``vmaverick
    3.1.1``.
    """
    if shutil.which("maverick") is None:
        return None
    try:
        result = subprocess.run(
            ["maverick", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return None
    # `maverick 3.1.1` → `3.1.1`. Bare strings pass through unchanged.
    return output.rsplit(None, 1)[-1]


def resolve_plugin_root(explicit: Path | None = None) -> Path | None:
    """Find the plugin root — the directory containing ``.claude-plugin/``.

    Resolution order:

      1. ``explicit`` argument (used by tests).
      2. ``CLAUDE_PLUGIN_ROOT`` env var (set by Claude Code at runtime).
      3. Walk up from this file. ``__file__`` lives at
         ``<plugin_root>/src/maverick/version_check.py``, so the plugin
         root is two parents up.

    Returns ``None`` if no candidate looks like a plugin (no
    ``.claude-plugin/plugin.json``).
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        candidates.append(Path(env))
    # Walk up two parents from this file — repo layout is stable.
    candidates.append(Path(__file__).resolve().parents[2])
    for c in candidates:
        if (c / ".claude-plugin" / "plugin.json").exists():
            return c
    return None


def _is_compatible(
    installed: tuple[int, int, int], required: tuple[int, int, int]
) -> bool:
    """Match MAJOR, require installed MINOR ≥ required MINOR. Patch is ignored.

    A MAJOR mismatch is treated as incompatible in either direction — a
    newer-major CLI is just as likely to break a current skill as an
    older-major one, since major bumps reserve the right to drop
    subcommands. In practice the only real case we see is older-installed
    against newer-required.
    """
    if installed[0] != required[0]:
        return False
    return installed[1] >= required[1]


def check_cli_compatibility(plugin_root: Path | None = None) -> CompatibilityResult:
    """Return whether the installed CLI satisfies the plugin's version floor.

    Designed to be safe to call from anywhere — never raises, returns a
    structured result even on internal failure. Callers map the result
    onto their own exit-code policy.
    """
    root = resolve_plugin_root(plugin_root)
    if root is None:
        return CompatibilityResult(
            ok=True,
            reason="version_unreadable",
            installed_version=None,
            required_version=None,
            remediation="",
        )
    required_str = _read_plugin_version(root)
    required = parse_semver(required_str) if required_str else None
    if required is None:
        return CompatibilityResult(
            ok=True,
            reason="version_unreadable",
            installed_version=None,
            required_version=required_str,
            remediation="",
        )
    installed_str = _read_installed_cli_version()
    if installed_str is None:
        return CompatibilityResult(
            ok=False,
            reason="cli_missing",
            installed_version=None,
            required_version=required_str,
            remediation=(
                f"Maverick CLI is not installed. Run /maverick:do-install "
                f"to install v{required_str}."
            ),
        )
    installed = parse_semver(installed_str)
    if installed is None:
        return CompatibilityResult(
            ok=True,
            reason="version_unreadable",
            installed_version=installed_str,
            required_version=required_str,
            remediation="",
        )
    if _is_compatible(installed, required):
        return CompatibilityResult(
            ok=True,
            reason="ok",
            installed_version=installed_str,
            required_version=required_str,
            remediation="",
        )
    return CompatibilityResult(
        ok=False,
        reason="cli_older",
        installed_version=installed_str,
        required_version=required_str,
        remediation=(
            f"Installed Maverick CLI v{installed_str} is older than plugin "
            f"v{required_str}. Run /maverick:do-install to upgrade."
        ),
    )

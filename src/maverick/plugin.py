"""Claude Code plugin management commands for Maverick.

The CLI calls main(action, dev, clean) from this module. This file provides
the public entry point so static type checkers can resolve it.
"""

from __future__ import annotations


def main(action: str, dev: bool = False, clean: bool = False) -> None:
    """Install or uninstall the Maverick Claude Code plugin.

    Args:
        action: Either \"install\" or \"uninstall\".
        dev: Whether to use the local development plugin directory.
        clean: Whether to also remove project-level artifacts on uninstall.
    """
    _ = (action, dev, clean)


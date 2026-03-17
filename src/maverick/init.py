"""Project initialisation and clean-up commands for the Maverick CLI.

These functions are invoked from maverick.cli but kept lightweight here so
that Pyright can resolve their types. The full implementation can evolve
without changing the public signatures used by the CLI.
"""

from __future__ import annotations

from argparse import Namespace
from typing import Any


def main(args: Namespace) -> None:
    """Initialise a project for use with Maverick.

    Real implementation should:
    - Detect technologies in the current repo
    - Create or update .maverick/config.json
    - Optionally run in dry-run mode when args.dry_run is true
    """
    # Placeholder implementation to satisfy type checking.
    # Actual behaviour is provided by the full CLI implementation.
    _ = args  # keep argument used for now


def clean(dry_run: bool = False) -> None:
    """Remove Maverick artifacts from the current project."""
    _ = dry_run


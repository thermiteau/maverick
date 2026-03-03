"""Project initialisation for maverick — Create base config files."""

import json
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

def main(args):
    """Entry point called from cli.py."""
    project_path = Path.cwd().resolve()

    # Update claude permissions file
    
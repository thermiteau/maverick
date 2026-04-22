"""Project initialisation and clean-up commands for the Maverick CLI.

Detects technologies in the current repo, creates .maverick/config.json,
and optionally supports dry-run mode.
"""

from __future__ import annotations

import json
import shutil
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from maverick.config import PROJECT_CONFIG_DIR

# Marker files → detected module name
_DETECTORS: List[tuple[str, str]] = [
    ("package.json", "nodejs"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("build.gradle.kts", "kotlin"),
    ("build.gradle", "java"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("Dockerfile", "docker"),
    ("docker-compose.yml", "docker"),
    ("docker-compose.yaml", "docker"),
    (".github/workflows", "github-actions"),
    (".gitlab-ci.yml", "gitlab-ci"),
    ("azure-pipelines.yml", "azure-pipelines"),
    ("terraform", "terraform"),
    ("cdk.json", "aws-cdk"),
]


def _detect_modules() -> List[str]:
    """Scan the current directory for known technology markers."""
    cwd = Path.cwd()
    found: set[str] = set()
    for marker, module in _DETECTORS:
        if (cwd / marker).exists():
            found.add(module)
    return sorted(found)


def main(args: Namespace) -> None:
    """Initialise a project for use with Maverick.

    Detects technologies in the current repo, creates .maverick/config.json,
    and prints what was found. Supports --override, --add, --remove, --dry-run.
    """
    modules = _detect_modules()

    if args.override:
        modules = sorted(set(args.override))
    else:
        if args.add:
            modules = sorted(set(modules) | set(args.add))
        if args.remove:
            modules = sorted(set(modules) - set(args.remove))

    config: Dict[str, Any] = {
        "modules": modules,
    }

    if args.platform:
        config["platform"] = args.platform

    if args.dry_run:
        print("Detected modules:", ", ".join(modules) if modules else "(none)")
        print("Would write .maverick/config.json:")
        print(json.dumps(config, indent=2))
        return

    PROJECT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path = PROJECT_CONFIG_DIR / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print("Detected modules:", ", ".join(modules) if modules else "(none)")
    print(f"Wrote {config_path}")


def clean(dry_run: bool = False) -> None:
    """Remove Maverick artifacts from the current project."""
    target = PROJECT_CONFIG_DIR
    if not target.exists():
        print("Nothing to clean — .maverick/ does not exist.")
        return

    if dry_run:
        print(f"Would remove {target}/")
        return

    shutil.rmtree(target)
    print(f"Removed {target}/")


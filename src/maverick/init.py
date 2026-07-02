"""Project initialisation and clean-up commands for the Maverick CLI.

Detects technologies in the current repo, creates .maverick/config.json,
and optionally supports dry-run mode.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any

from maverick.config import (
    _DEFAULT_BRANCH_PREFIXES,
    CONFIG_DEFAULTS,
    PROJECT_CONFIG_DIR,
)

# Marker files → detected module name
_DETECTORS: list[tuple[str, str]] = [
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


def _detect_modules() -> list[str]:
    """Scan the current directory for known technology markers."""
    cwd = Path.cwd()
    found: set[str] = set()
    for marker, module in _DETECTORS:
        if (cwd / marker).exists():
            found.add(module)
    return sorted(found)


def _detect_default_branch() -> str:
    """Detect the repo's default branch via ``gh``, falling back to ``main``."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "-q",
             ".defaultBranchRef.name"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "main"


def _detect_git_workflow() -> dict[str, Any]:
    """Propose a ``git_workflow`` config block from detection.

    Detects the repo's default branch to decide whether the project uses
    trunk-based (``main``) or a separate integration branch (``develop``).
    The result is written once and never re-detected at runtime.
    """
    default_branch = _detect_default_branch()

    # Heuristic: if the default branch is not main/master, it's likely
    # an integration branch (e.g. develop). In that case, use it as
    # both story_base and pr_target.
    if default_branch in ("main", "master"):
        story_base = default_branch
        pr_target = default_branch
        chain = [default_branch]
    else:
        story_base = default_branch
        pr_target = default_branch
        chain = [default_branch, "main"]

    return {
        "story_base": story_base,
        "pr_target": pr_target,
        "promotion_chain": chain,
        "branch_prefixes": dict(_DEFAULT_BRANCH_PREFIXES),
    }


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

    # Build the integration block. If the file already exists and has flags
    # set, preserve them — re-running init must not erase milestones the
    # project has already reached. Always set ``init: true`` since this run
    # of init counts as "init has happened".
    config_path = PROJECT_CONFIG_DIR / "config.json"
    integration: dict[str, Any] = dict(CONFIG_DEFAULTS["integration"])
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
            existing_block = existing.get("integration")
            if isinstance(existing_block, dict):
                for k, v in existing_block.items():
                    if k in integration and isinstance(v, bool):
                        integration[k] = v
        except json.JSONDecodeError:
            pass
    integration["init"] = True

    # Detect git workflow settings. If re-running init, preserve existing
    # git_workflow values — the user may have customised them.
    git_workflow: dict[str, Any] = dict(CONFIG_DEFAULTS["git_workflow"])
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
            existing_gw = existing.get("git_workflow")
            if isinstance(existing_gw, dict):
                git_workflow.update(existing_gw)
        except json.JSONDecodeError:
            pass
    else:
        git_workflow = _detect_git_workflow()

    config: dict[str, Any] = {
        "modules": modules,
        "integration": integration,
        "git_workflow": git_workflow,
    }

    if args.platform:
        config["platform"] = args.platform

    if args.dry_run:
        print("Detected modules:", ", ".join(modules) if modules else "(none)")
        print("Would write .maverick/config.json:")
        print(json.dumps(config, indent=2))
        missing = _missing_permission_denies(Path("."))
        if missing:
            print("Would add permission deny rules to .claude/settings.json:")
            for rule in missing:
                print(f"  {rule}")
        return

    PROJECT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print("Detected modules:", ", ".join(modules) if modules else "(none)")
    print(f"Wrote {config_path}")
    write_permission_denies(Path("."))


#: Baseline deny rules mirroring the scope-guard hook's hard limits. A second,
#: hook-independent enforcement layer: permission rules keep working even if
#: the user disables hooks (mav-scope-boundaries defence-in-depth).
PERMISSION_DENY_RULES = (
    "Bash(git push --force*)",
    "Bash(git push -f*)",
    "Edit(.github/workflows/**)",
    "Write(.github/workflows/**)",
)


def _missing_permission_denies(project_dir: Path) -> list[str]:
    """The baseline deny rules not yet present in .claude/settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    existing: list[str] = []
    if settings_path.exists():
        try:
            raw = json.loads(settings_path.read_text())
            existing = list(raw.get("permissions", {}).get("deny", []))
        except (json.JSONDecodeError, AttributeError):
            return []  # unreadable settings — never risk clobbering (see writer)
    return [r for r in PERMISSION_DENY_RULES if r not in existing]


def write_permission_denies(project_dir: Path) -> bool:
    """Merge Maverick's baseline deny rules into the project's settings.json.

    Preserves everything already in the file and only appends missing rules.
    If the file exists but cannot be parsed, it is left untouched (a warning
    is printed) — init must never destroy a hand-edited settings file.
    Returns True when the file was modified.
    """
    settings_path = project_dir / ".claude" / "settings.json"
    settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            print(
                f"Warning: {settings_path} is not valid JSON — skipped adding "
                "permission deny rules. Add them manually:",
                *(f"  {r}" for r in PERMISSION_DENY_RULES),
                sep="\n",
            )
            return False
        if not isinstance(settings, dict):
            print(f"Warning: {settings_path} is not a JSON object — skipped.")
            return False

    permissions = settings.setdefault("permissions", {})
    deny = permissions.setdefault("deny", [])
    missing = [r for r in PERMISSION_DENY_RULES if r not in deny]
    if not missing:
        return False

    deny.extend(missing)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Added {len(missing)} permission deny rule(s) to {settings_path}")
    return True


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


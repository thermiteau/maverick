"""Configuration loading, schema, and state file locations for Maverick CLI.

This module centralises where configuration and state are stored on disk.
It is intentionally lightweight so it can be imported from infra, instance,
worker, and build_ami without side effects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TypedDict

# Project-level config directory, per CLAUDE.md
PROJECT_CONFIG_DIR = Path(".maverick")
USER_CONFIG_DIR = Path.home() / ".maverick"

SYSTEM_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

# Derived state file locations
STATE_DIR = USER_CONFIG_DIR
AMI_STATE = STATE_DIR / "ami_state.json"
INFRA_STATE = STATE_DIR / "infra_state.json"
INSTANCE_STATE = STATE_DIR / "instance_state.json"


# ---------------------------------------------------------------------------
# Config schema — TypedDicts define the expected shape of config.json
# ---------------------------------------------------------------------------

# Default SSM parameter for Ubuntu 24.04 LTS AMI lookup
_DEFAULT_SSM_PARAMETER = (
    "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
)


class AwsConfig(TypedDict):
    """AWS resource identifiers and credentials.

    Required (user must set):
        region:          AWS region (e.g. "us-east-1")
        key_pair:        EC2 key pair name for SSH access

    Written by ``infra deploy`` (not set manually):
        security_group:  Security group ID from VPC stack
        iam_profile:     IAM instance profile name from VPC stack
        secret_arn:      Secrets Manager ARN from VPC stack
        subnet:          Subnet ID from VPC stack
        work_table_name: DynamoDB table name from infra stack

    Optional:
        cloud_config:    Path override for cloud-init config file
    """

    region: str
    key_pair: str
    security_group: str
    iam_profile: str
    secret_arn: str
    subnet: str
    work_table_name: str
    cloud_config: str


class WorkerConfig(TypedDict):
    """Worker daemon and webhook configuration.

    All fields have defaults applied by ``_apply_defaults()``.
    """

    webhook_label: str  # GitHub label that triggers work items (default: "claude-do")
    cloudwatch_log_group: str  # Log group name (default: "/maverick/worker")
    prompt_template: str  # Claude prompt template with {issue_number} placeholder
    work_dir: str  # Directory for cloning repos (default: "/home/claude/work")
    user: str  # Unix user to run worker as (default: "claude")


class QueueConfig(TypedDict):
    """Queue processing configuration."""

    max_attempts: int  # Max retry attempts per work item (default: 3)


class InstanceConfig(TypedDict):
    """EC2 instance configuration."""

    type: str  # Instance type (default: "t3.medium")


class AmiConfig(TypedDict):
    """AMI build configuration."""

    ssm_parameter: str  # SSM parameter for base AMI lookup
    description: str  # Description for built AMIs


class IssueLifecycleConfig(TypedDict):
    """Per-project policy for what happens to GitHub issues after their PR
    merges. Different repos use different merge patterns (trunk-based vs
    Gitflow vs custom promotion chains), so the close decision can't be
    hard-coded in the skill.

    Fields:
        close_policy:
            One of:
              - "on_pr_merge" (default): close the issue as soon as the PR
                merges, regardless of which branch was the merge target.
                Right for trunk-based, GitHub Flow, and Gitflow teams who
                treat "merged to develop" as "done".
              - "on_default_branch_merge": only close when the PR target
                is the repo's default branch. Lets GitHub's native
                ``Closes #N`` handle default-branch merges; Maverick
                stays out of the way for non-default merges so the issue
                stays open until the team's promotion gate runs.
              - "manual": never close from the skill. Always post the
                audit comment and apply the ``merged-to-<branch>`` label,
                but leave the close to the team's own workflow (release
                tag, environment promotion, manual sign-off).
    """

    close_policy: str  # "on_pr_merge" | "on_default_branch_merge" | "manual"


# Recognised values for issue_lifecycle.close_policy.
ISSUE_CLOSE_POLICIES = ("on_pr_merge", "on_default_branch_merge", "manual")


class IntegrationStatus(TypedDict):
    """Per-project record of which Maverick adoption milestones have been
    carried out. Each flag defaults to ``false`` and is flipped to ``true``
    when the corresponding skill completes successfully.

    The block lives in the project-level ``.maverick/config.json`` and is
    committed to git, so the state survives across machines and contributors
    rather than relying on a derivable filesystem signal.

    Adding a new flag: extend this TypedDict, add a default in
    CONFIG_DEFAULTS["integration"], and (optionally) wire the relevant skill
    to flip it via ``maverick state set <key> true``.
    """

    init: bool  # do-init has been run on this project
    alignment: bool  # do-maverick-alignment audit produced docs/maverick-audit.md
    upskill: bool  # do-upskill has populated docs/maverick/skills/<topic>/SKILL.md
    tech_docs_scaffolded: bool  # do-docs greenfield/refactor has populated docs/technical/
    code_review_workflow: bool  # .github/workflows/ ships a `# maverick:code-review` workflow
    cybersecurity_reviewed: bool  # do-cybersecurity-review produced docs/security-audit.md


class MaverickConfig(TypedDict):
    """Top-level maverick configuration schema.

    Loaded from ``.maverick/config.json`` (project) or
    ``~/.maverick/config.json`` (user).
    """

    aws: AwsConfig
    worker: WorkerConfig
    queue: QueueConfig
    instance: InstanceConfig
    ami: AmiConfig
    integration: IntegrationStatus
    issue_lifecycle: IssueLifecycleConfig


# Defaults applied when sections or keys are missing.
CONFIG_DEFAULTS: MaverickConfig = {
    "aws": {
        "region": "us-east-1",
        "key_pair": "",
        "security_group": "",
        "iam_profile": "",
        "secret_arn": "",
        "subnet": "",
        "work_table_name": "",
        "cloud_config": "",
    },
    "worker": {
        "webhook_label": "claude-do",
        "cloudwatch_log_group": "/maverick/worker",
        "prompt_template": "/do-issue-solo {issue_number}",
        "work_dir": "/home/claude/work",
        "user": "claude",
    },
    "queue": {
        "max_attempts": 3,
    },
    "instance": {
        "type": "t3.medium",
    },
    "ami": {
        "ssm_parameter": _DEFAULT_SSM_PARAMETER,
        "description": "Claude Code maverick worker",
    },
    "integration": {
        "init": False,
        "alignment": False,
        "upskill": False,
        "tech_docs_scaffolded": False,
        "code_review_workflow": False,
        "cybersecurity_reviewed": False,
    },
    "issue_lifecycle": {
        "close_policy": "on_pr_merge",
    },
}

# Valid keys per section — used to detect legacy/unknown fields.
_VALID_KEYS: dict[str, set[str]] = {
    section: set(fields.keys()) if isinstance(fields, dict) else set()
    for section, fields in CONFIG_DEFAULTS.items()
}

# Maps legacy key names to their current equivalents (within the same section).
_LEGACY_KEY_MAP: dict[str, dict[str, str]] = {
    "aws": {
        "ec2_key_pair": "key_pair",
        "ec2_security_group": "security_group",
        "ec2_iam_profile": "iam_profile",
        "parameter_store_arn": "secret_arn",
        "ec2_subnet": "subnet",
        "ec2_instance_type": "_migrate_to_instance_type",  # special: moves to instance.type
        "ec2_ssm_parameter": "_migrate_to_ami_ssm",  # special: moves to ami.ssm_parameter
        "ec2_description": "_migrate_to_ami_desc",  # special: moves to ami.description
    },
}


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _migrate_legacy(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy key names to the current schema in-place. Returns the dict."""
    aws = raw.get("aws", {})
    if not isinstance(aws, dict):
        return raw

    for old_key, new_key in _LEGACY_KEY_MAP.get("aws", {}).items():
        if old_key not in aws:
            continue
        value = aws.pop(old_key)
        if not value:
            continue
        # Cross-section migrations
        if new_key == "_migrate_to_instance_type":
            raw.setdefault("instance", {})["type"] = value
        elif new_key == "_migrate_to_ami_ssm":
            raw.setdefault("ami", {})["ssm_parameter"] = value
        elif new_key == "_migrate_to_ami_desc":
            raw.setdefault("ami", {})["description"] = value
        else:
            aws.setdefault(new_key, value)

    return raw


def _has_unknown_keys(raw: dict[str, Any]) -> list[str]:
    """Return a list of 'section.key' strings for keys not in the schema."""
    unknown: list[str] = []
    for section, valid_keys in _VALID_KEYS.items():
        user_section = raw.get(section, {})
        if not isinstance(user_section, dict):
            continue
        for key in user_section:
            if key not in valid_keys:
                unknown.append(f"{section}.{key}")
    return unknown


def _apply_defaults(raw: dict[str, Any]) -> MaverickConfig:
    """Merge user config over CONFIG_DEFAULTS, filling any missing sections or keys."""
    result: dict[str, Any] = {}
    for section, defaults in CONFIG_DEFAULTS.items():
        user_section = raw.get(section, {})
        if isinstance(defaults, dict):
            merged = dict(defaults)
            if isinstance(user_section, dict):
                # Only merge keys that belong to the current schema
                valid = _VALID_KEYS.get(section, set())
                merged.update({k: v for k, v in user_section.items() if k in valid})
            result[section] = merged
        else:
            result[section] = user_section if section in raw else defaults
    return result  # type: ignore[return-value]


def validate_config(cfg: MaverickConfig, require_aws: bool = True) -> list[str]:
    """Validate config and return a list of error messages (empty = valid).

    Args:
        cfg: Configuration dict to validate.
        require_aws: If True, check that ``aws.region`` is set.
                     Commands that don't need AWS (e.g. ``init``) pass False.
    """
    errors: list[str] = []

    if require_aws:
        region = cfg.get("aws", {}).get("region", "")
        if not region:
            errors.append("aws.region is required")

    instance_type = cfg.get("instance", {}).get("type", "")
    if instance_type and not isinstance(instance_type, str):
        errors.append("instance.type must be a string")

    max_attempts = cfg.get("queue", {}).get("max_attempts")
    if max_attempts is not None and not isinstance(max_attempts, int):
        errors.append("queue.max_attempts must be an integer")

    policy = cfg.get("issue_lifecycle", {}).get("close_policy")
    if policy is not None and policy not in ISSUE_CLOSE_POLICIES:
        errors.append(
            f"issue_lifecycle.close_policy must be one of "
            f"{', '.join(ISSUE_CLOSE_POLICIES)} (got {policy!r})"
        )

    return errors


def _backup_and_replace(source: Path, cfg: MaverickConfig) -> None:
    """Rename *source* to ``<name>.bak`` and write *cfg* in its place."""
    bak = source.with_suffix(".json.bak")
    # Avoid clobbering an existing backup — append a counter.
    counter = 1
    while bak.exists():
        bak = source.with_suffix(f".json.bak.{counter}")
        counter += 1
    source.rename(bak)
    print(f"  Backed up old config to {bak}", file=sys.stderr)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"  Wrote new config to {source}", file=sys.stderr)


def _load_and_heal(path: Path) -> dict[str, Any]:
    """Load config from *path*, migrating legacy keys and backing up if needed.

    Returns the raw dict (before defaults are applied).
    """
    raw = _load_json(path)
    if not raw:
        return raw

    # Phase 1: migrate known legacy keys
    raw = _migrate_legacy(raw)

    # Phase 2: check for remaining unknown keys
    unknown = _has_unknown_keys(raw)
    if not unknown:
        return raw

    # Unknown keys remain — the file predates the current schema.
    print(
        f"Config at {path} contains keys not in the current schema:",
        file=sys.stderr,
    )
    for key in unknown:
        print(f"  - {key}", file=sys.stderr)

    # Build a clean config preserving any values that map to current keys.
    healed = _apply_defaults(raw)

    _backup_and_replace(path, healed)
    # Return the healed dict so _apply_defaults in init_config is a no-op merge.
    return dict(healed)  # type: ignore[arg-type]


def init_config(require_aws: bool = True) -> MaverickConfig:
    """Load system configuration, apply defaults, and validate.

    Preference order:
    1. Project-level .maverick/config.json if present
    2. User-level ~/.maverick/config.json
    3. Defaults (see CONFIG_DEFAULTS)

    If the loaded file contains legacy or unrecognised keys, salvageable
    values are migrated, the old file is renamed to ``.json.bak``, and a
    clean config is written in its place.

    Exits with an error message if validation fails.
    """
    project_cfg = PROJECT_CONFIG_DIR / "config.json"
    if project_cfg.exists():
        raw = _load_and_heal(project_cfg)
    else:
        raw = _load_and_heal(SYSTEM_CONFIG_FILE)

    cfg = _apply_defaults(raw)

    errors = validate_config(cfg, require_aws=require_aws)
    if errors:
        print("Configuration errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(f"\nEdit {SYSTEM_CONFIG_FILE} to fix.", file=sys.stderr)
        sys.exit(1)

    return cfg


def save_config(cfg: MaverickConfig) -> None:
    """Persist configuration to the user-level config file."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Integration-status helpers (project-level)
# ---------------------------------------------------------------------------
#
# The ``integration`` block in .maverick/config.json records which Maverick
# adoption milestones a project has hit. The block is committed to git so it
# survives across machines. Each helper here reads or mutates only that
# block, preserving the rest of the file (modules, platform, any other
# top-level keys init may have written).


def project_config_path() -> Path:
    """Return the path to the project-level .maverick/config.json."""
    return PROJECT_CONFIG_DIR / "config.json"


def _default_integration() -> IntegrationStatus:
    """Return a fresh IntegrationStatus with every flag at its default."""
    return dict(CONFIG_DEFAULTS["integration"])  # type: ignore[return-value]


def read_integration_status(path: Path | None = None) -> IntegrationStatus:
    """Read the integration block from the project config.

    Returns the defaults (all flags False) if the file does not exist or has
    no integration block. Missing individual flags are filled with their
    default. Unknown flags are dropped.
    """
    target = path or project_config_path()
    raw = _load_json(target)
    block = raw.get("integration") if isinstance(raw, dict) else None
    status = _default_integration()
    if isinstance(block, dict):
        for key in status:
            if key in block and isinstance(block[key], bool):
                status[key] = block[key]  # type: ignore[literal-required]
    return status


def write_integration_status(
    status: IntegrationStatus, path: Path | None = None
) -> None:
    """Write the integration block back, preserving all other config fields.

    If the config file does not yet exist, creates it with just the
    integration block (and the parent directory). Other top-level fields
    written by ``init`` (modules, platform) are preserved untouched.
    """
    target = path or project_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = _load_json(target) if target.exists() else {}
    raw["integration"] = dict(status)
    target.write_text(json.dumps(raw, indent=2) + "\n")


def set_integration_flag(key: str, value: bool, path: Path | None = None) -> None:
    """Flip a single integration flag on the project config.

    Raises ``KeyError`` if ``key`` is not a known integration flag.
    """
    valid = set(CONFIG_DEFAULTS["integration"].keys())
    if key not in valid:
        raise KeyError(
            f"unknown integration key {key!r}; valid keys: {sorted(valid)}"
        )
    status = read_integration_status(path)
    status[key] = value  # type: ignore[literal-required]
    write_integration_status(status, path)

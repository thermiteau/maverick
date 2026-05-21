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


class GitWorkflowConfig(TypedDict):
    """Per-project git branching configuration.

    Replaces hard-coded ``main`` throughout the skills so that repos using
    Gitflow, ``develop``-based flows, or multi-stage promotion chains
    work out of the box.

    Written once by ``maverick init`` (proposed from detection, never
    re-detected at runtime) and read by skills at execution time.

    Fields:
        story_base:        Branch to create feature/fix branches from.
        pr_target:         Default ``--base`` for ``gh pr create``.
        promotion_chain:   Ordered list of branches in the promotion
                           pipeline (e.g. ``["develop", "staging", "main"]``).
                           Used by a future ``promote`` command.
        branch_prefixes:   Mapping of issue-label keywords to branch-name
                           prefixes (e.g. ``{"bug": "fix", "feature": "feat"}``).
                           Overrides the default table in ``mav-git-workflow``.
    """

    story_base: str
    pr_target: str
    promotion_chain: list[str]
    branch_prefixes: dict[str, str]


# Default branch prefixes — matches the table in mav-git-workflow.
_DEFAULT_BRANCH_PREFIXES: dict[str, str] = {
    "bug": "fix",
    "fix": "fix",
    "defect": "fix",
    "feature": "feat",
    "enhancement": "feat",
    "docs": "docs",
    "documentation": "docs",
    "refactor": "refactor",
    "tech-debt": "refactor",
    "chore": "chore",
    "maintenance": "chore",
    "deps": "chore",
    "test": "test",
    "testing": "test",
}


class LlmConfig(TypedDict):
    """Per-project LLM model selection for Maverick workflows.

    Three layers compose at resolution time (see
    ``report_cli._current_llm``):

    - ``default``: the model used when nothing more specific applies.
    - ``agents``: per-agent overrides, keyed by agent name (e.g.
      ``"agent-tech-docs-writer": "claude-sonnet-4-6"``). Applies to
      rows whose ``maverick_agent`` matches the key.
    - ``skills``: per-skill overrides, keyed by inner-skill name (e.g.
      ``"do-test": "claude-sonnet-4-6"``). Applies to ``skill-dispatch``
      rows whose ``dispatched_skill`` matches, AND to ``agent-dispatch``
      rows where the agent was invoked under that skill.

    The agent override takes priority over the skill override on
    ``agent-dispatch`` rows that carry both. Anything not matched falls
    through to ``default``.

    Maverick ships baseline defaults (see ``CONFIG_DEFAULTS["llm"]``).
    Repos override by writing an ``llm`` block in
    ``.maverick/config.json``; the loader deep-merges ``agents`` and
    ``skills`` so a repo can add or change a single entry without
    re-stating the whole table.
    """

    default: str
    agents: dict[str, str]
    skills: dict[str, str]


class HooksConfig(TypedDict):
    """Repo-specific scripts to run at maverick CLI lifecycle points.

    Each value is a path (relative to the repo root) to an executable.
    An empty string disables the hook.

    Fields:
        worktree_post_create: Runs after ``maverick worktree create`` succeeds.
                              Receives the worktree path as ``$1`` plus the
                              env vars ``MAVERICK_WORKTREE_PATH``,
                              ``MAVERICK_BRANCH``, ``MAVERICK_BASE_BRANCH``,
                              and ``MAVERICK_REPO_ROOT``. A non-zero exit
                              causes ``worktree create`` to fail with the
                              worktree left on disk for inspection.
    """

    worktree_post_create: str


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
    git_workflow: GitWorkflowConfig
    hooks: HooksConfig
    llm: LlmConfig


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
    "git_workflow": {
        "story_base": "main",
        "pr_target": "main",
        "promotion_chain": ["main"],
        "branch_prefixes": dict(_DEFAULT_BRANCH_PREFIXES),
    },
    "hooks": {
        "worktree_post_create": "",
    },
    "llm": {
        # Default model for any row not matched by a more specific
        # rule. Opus is the safe default — reasoning-heavy work expects
        # it. Set per-user in ~/.maverick/config.json's `llm.default`,
        # or per-repo in .maverick/config.json (repo overrides user).
        "default": "claude-opus-4-7",
        # Per-agent overrides are intentionally empty: the source of
        # truth for an agent's model is its AgentConfig.model field
        # (rendered into the agent's frontmatter), NOT a presumption
        # table on the consumer side (#108). The CLI reads each agent's
        # pinned model from the registry; this map only matters when a
        # user/repo explicitly forces an override.
        "agents": {},
        # Per-skill overrides are intentionally empty: skills are
        # instruction blocks loaded into the orchestrator's session,
        # not separate dispatch units. They cannot run on a different
        # model from the orchestrator (#108). The CLI ignores this map
        # at resolution time; it remains here for backward compatibility
        # with existing config files that wrote into it.
        "skills": {},
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

    gw = cfg.get("git_workflow", {})
    if isinstance(gw, dict):
        for field in ("story_base", "pr_target"):
            val = gw.get(field)
            if val is not None and (not isinstance(val, str) or not val.strip()):
                errors.append(f"git_workflow.{field} must be a non-empty string")
        chain = gw.get("promotion_chain")
        if chain is not None and (
            not isinstance(chain, list)
            or not all(isinstance(b, str) and b.strip() for b in chain)
        ):
            errors.append(
                "git_workflow.promotion_chain must be a list of non-empty strings"
            )
        prefixes = gw.get("branch_prefixes")
        if prefixes is not None and (
            not isinstance(prefixes, dict)
            or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in prefixes.items()
            )
        ):
            errors.append(
                "git_workflow.branch_prefixes must be a dict of string → string"
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


def _default_hooks() -> HooksConfig:
    """Return a fresh HooksConfig with every hook unset."""
    return dict(CONFIG_DEFAULTS["hooks"])  # type: ignore[return-value]


def read_hooks_config(path: Path | None = None) -> HooksConfig:
    """Read the hooks block from the project config.

    Returns the defaults (all hooks empty) if the file does not exist or has
    no hooks block. Missing individual hooks are filled with their default.
    Unknown hook names are dropped.
    """
    target = path or project_config_path()
    raw = _load_json(target)
    block = raw.get("hooks") if isinstance(raw, dict) else None
    hooks = _default_hooks()
    if isinstance(block, dict):
        for key in hooks:
            if key in block and isinstance(block[key], str):
                hooks[key] = block[key]  # type: ignore[literal-required]
    return hooks


def _default_llm() -> LlmConfig:
    """Return a fresh LlmConfig with Maverick's baked-in defaults."""
    defaults = CONFIG_DEFAULTS["llm"]
    return {
        "default": defaults["default"],
        "agents": dict(defaults["agents"]),
        "skills": dict(defaults["skills"]),
    }


def _merge_llm_block(result: LlmConfig, block: dict[str, Any]) -> None:
    """Deep-merge a single ``llm`` block over ``result`` in place."""
    if isinstance(block.get("default"), str) and block["default"]:
        result["default"] = block["default"]
    for sub in ("agents", "skills"):
        user_map = block.get(sub)
        if isinstance(user_map, dict):
            for k, v in user_map.items():
                if isinstance(k, str) and isinstance(v, str):
                    result[sub][k] = v  # type: ignore[literal-required]


def read_llm_config(path: Path | None = None) -> LlmConfig:
    """Read the llm block, deep-merged in order: defaults → user → repo.

    Merge order (later wins):

    1. Maverick's baked-in defaults (``CONFIG_DEFAULTS["llm"]``).
    2. User-level config at ``~/.maverick/config.json`` (``llm`` block).
    3. Repo-level config at ``.maverick/config.json`` (``llm`` block).

    Each layer is deep-merged: ``default`` is replaced if present;
    ``agents`` / ``skills`` entries override by key, leaving keys not
    mentioned at the earlier layer intact.

    For agents, the **source of truth** for which model an agent runs on
    is the agent's own ``AgentConfig.model`` field (rendered into its
    frontmatter), not this map. The map exists only so that a
    user/repo can force a different model identifier for the report
    (#108).
    """
    target = path or project_config_path()
    repo_raw = _load_json(target)
    user_raw = _load_json(SYSTEM_CONFIG_FILE) if SYSTEM_CONFIG_FILE.exists() else {}
    result = _default_llm()
    user_block = user_raw.get("llm") if isinstance(user_raw, dict) else None
    if isinstance(user_block, dict):
        _merge_llm_block(result, user_block)
    repo_block = repo_raw.get("llm") if isinstance(repo_raw, dict) else None
    if isinstance(repo_block, dict):
        _merge_llm_block(result, repo_block)
    return result


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

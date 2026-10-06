"""Shared dataclasses for skill template generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ClaudeSkillOptions:
    """Claude Code-only skill frontmatter, ignored by other render targets.

    https://code.claude.com/docs/en/skills#frontmatter-reference
    """

    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    context: Literal["fork"] | None = None
    agent: str | None = None
    hooks: dict[str, Any] | None = None


@dataclass
class SkillConfig:
    """Declarative, runtime-neutral configuration for a single skill.

    Core fields describe the skill in terms every runtime can honour; each
    render target in ``maverick.targets`` maps them onto its own format.
    Options only one runtime understands live in a per-runtime block
    (``claude``), so they cannot leak into other targets' builds.
    """

    name: str
    description: str | None = None
    argument_hint: str | None = None
    disable_model_invocation: bool = True
    user_invocable: bool = False

    depends_on: list[str] = field(default_factory=list)
    extra_context: dict[str, str] = field(default_factory=dict)
    # Files to ship alongside the rendered SKILL.md (paths relative to the
    # skill source directory). Listed assets must exist in source and are
    # copied verbatim to the build output. Validated by tests so a missing
    # asset fails the build rather than silently shipping a broken skill.
    assets: list[str] = field(default_factory=list)

    claude: ClaudeSkillOptions = field(default_factory=ClaudeSkillOptions)


@dataclass
class ClaudeAgentOptions:
    """Claude Code-only subagent frontmatter, ignored by other render targets.

    https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields
    """

    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    # Model alias (e.g. "sonnet", "opus", "haiku", "inherit") or a full model
    # ID. Deliberately a plain str: a Literal froze the schema to a model list
    # that goes stale as new families ship.
    model: str | None = None
    permission_mode: (
        Literal["default", "acceptEdits", "dontAsk", "bypassPermissions", "plan"] | None
    ) = None
    max_turns: int | None = None
    mcp_servers: dict[str, Any] | None = None
    hooks: dict[str, Any] | None = None
    memory: Literal["user", "project", "local"] | None = None
    background: bool = False
    isolation: Literal["worktree"] | None = None
    color: str | None = None


@dataclass
class AgentConfig:
    """Declarative, runtime-neutral configuration for a single agent.

    See :class:`SkillConfig` for the core/per-runtime split.
    """

    name: str
    description: str
    skills: list[str] = field(default_factory=list)
    # The agent may read and run commands but never edit files. A reviewer
    # that can fix what it reviews stops being a gate. Each target enforces
    # this in its own terms (Claude Code: disallowed edit tools).
    read_only: bool = False
    extra_context: dict[str, str] = field(default_factory=dict)

    claude: ClaudeAgentOptions = field(default_factory=ClaudeAgentOptions)


@dataclass
class TopicConfig:
    """Configuration for an upskill topic.

    The scan hints are the single source of truth for detection — they
    generate topics.json, the do-upskill body's hints section, and are
    referenced by do-adopt. Duplicated hint lists across skills drifted
    (modernization review, bp-M3); do not re-introduce copies.
    """

    topic: str
    prompt: str
    best_practice_skill: str  # skill name constant, e.g. "mav-bp-operability"
    scan_dependencies: list[str] = field(default_factory=list)
    scan_grep: str = ""
    scan_files: list[str] = field(default_factory=list)


@dataclass
class GlobalConfig:
    """Configuration shared across all skill templates."""

    extra_context: dict[str, str] = field(default_factory=dict)

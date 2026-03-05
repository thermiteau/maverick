"""Shared dataclasses for skill template generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SkillConfig:
    """Declarative configuration for a single skill template.

    Fields map to the Claude Code skill frontmatter schema:
    https://code.claude.com/docs/en/skills#frontmatter-reference
    """

    name: str
    description: str | None = None
    argument_hint: str | None = None
    disable_model_invocation: bool = True
    user_invocable: bool = False
    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    context: Literal["fork"] | None = None
    agent: str | None = None
    hooks: dict[str, Any] | None = None

    # Maverick-specific fields (not part of Claude Code frontmatter)
    depends_on: list[str] = field(default_factory=list)
    extra_context: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Declarative configuration for a single agent template.

    Fields map to the Claude Code subagent frontmatter schema:
    https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields
    """

    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None
    permission_mode: Literal[
        "default", "acceptEdits", "dontAsk", "bypassPermissions", "plan"
    ] | None = None
    max_turns: int | None = None
    skills: list[str] = field(default_factory=list)
    mcp_servers: dict[str, Any] | None = None
    hooks: dict[str, Any] | None = None
    memory: Literal["user", "project", "local"] | None = None
    background: bool = False
    isolation: Literal["worktree"] | None = None
    color: str | None = None


@dataclass
class TopicConfig:
    """Configuration for an upskill topic."""

    topic: str
    prompt: str
    best_practice_skill: str  # skill name constant, e.g. "mav-bp-logging"


@dataclass
class GlobalConfig:
    """Configuration shared across all skill templates."""

    extra_context: dict[str, str] = field(default_factory=dict)

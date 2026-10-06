"""Render targets — one per agent runtime Maverick builds a plugin for.

Skill and agent sources are runtime-neutral. Anything that differs per
runtime — product names, the plugin-root variable, how a skill is invoked,
the runtime-argument placeholder — comes from the target, exposed to every
template as ``{{ RUNTIME.<KEY> }}``.

A target also owns how the runtime-neutral ``SkillConfig``/``AgentConfig``
map onto the runtime's frontmatter, and where its plugin files go.

Claude Code is the only target today. Adding a runtime means adding a
:class:`Target` here; templates should not need to change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maverick.models import AgentConfig, SkillConfig

#: Frontmatter builders receive the config plus its description already
#: rendered for the target, and return the frontmatter mapping in order.
SkillFrontmatter = Callable[[SkillConfig, "str | None"], dict[str, Any]]
AgentFrontmatter = Callable[[AgentConfig, str], dict[str, Any]]


@dataclass(frozen=True)
class Target:
    """A runtime Maverick renders skills and agents for."""

    name: str
    skill_frontmatter: SkillFrontmatter
    agent_frontmatter: AgentFrontmatter
    #: Exposed to templates as ``{{ RUNTIME.<KEY> }}``.
    runtime: dict[str, str] = field(default_factory=dict)
    #: Literal token the runtime substitutes with user-supplied arguments.
    arguments_token: str = ""
    #: Source directory of the target's hook config and shim, copied verbatim.
    hooks_source: Path | None = None
    #: Plugin layout, relative to the output root.
    skills_dir: str = "skills"
    agents_dir: str = "agents"
    hooks_dir: str = "hooks"


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

#: Tools Claude Code agents lose when the config says ``read_only``.
CLAUDE_EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


def claude_skill_frontmatter(skill: SkillConfig, description: str | None) -> dict[str, Any]:
    """Claude Code skill frontmatter.

    The two invocation flags are always emitted explicitly. Claude Code's
    runtime defaults are ``user-invocable: true`` and
    ``disable-model-invocation: false`` — the opposite of this config
    schema's defaults — so omitting a flag silently inverted the declared
    intent for every non-invocable reference skill.
    """
    opts = skill.claude
    data: dict[str, Any] = {"name": skill.name}
    if description:
        data["description"] = description
    if skill.argument_hint:
        data["argument-hint"] = skill.argument_hint
    data["user-invocable"] = skill.user_invocable
    data["disable-model-invocation"] = skill.disable_model_invocation
    if opts.allowed_tools:
        data["allowed-tools"] = ", ".join(opts.allowed_tools)
    if opts.model:
        data["model"] = opts.model
    if opts.context:
        data["context"] = opts.context
    if opts.agent:
        data["agent"] = opts.agent
    if opts.hooks:
        data["hooks"] = opts.hooks
    return data


def claude_agent_frontmatter(agent: AgentConfig, description: str) -> dict[str, Any]:
    """Claude Code subagent frontmatter."""
    opts = agent.claude
    data: dict[str, Any] = {"name": agent.name, "description": description}
    if opts.model:
        data["model"] = opts.model
    if opts.color:
        data["color"] = opts.color
    if opts.permission_mode:
        data["permissionMode"] = opts.permission_mode
    if opts.max_turns is not None:
        data["maxTurns"] = opts.max_turns
    if opts.background:
        data["background"] = True
    if opts.isolation:
        data["isolation"] = opts.isolation
    if opts.memory:
        data["memory"] = opts.memory
    if opts.tools:
        data["tools"] = ", ".join(opts.tools)
    disallowed = list(CLAUDE_EDIT_TOOLS) if agent.read_only else []
    disallowed += [t for t in opts.disallowed_tools if t not in disallowed]
    if disallowed:
        data["disallowedTools"] = ", ".join(disallowed)
    if agent.skills:
        data["skills"] = list(agent.skills)
    if opts.mcp_servers:
        data["mcpServers"] = opts.mcp_servers
    if opts.hooks:
        data["hooks"] = opts.hooks
    return data


CLAUDE = Target(
    name="claude",
    runtime={
        # The product, as in "the orchestrating Claude Code session".
        "NAME": "Claude Code",
        # The model acting as the agent, as in "Claude's call was wrong".
        "AGENT": "Claude",
        # Absolute path to the installed plugin, expanded by the runtime.
        "PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
        # Prefix that turns a skill name into a user invocation.
        "SKILL_PREFIX": "/maverick:",
    },
    arguments_token="$ARGUMENTS",
    skill_frontmatter=claude_skill_frontmatter,
    agent_frontmatter=claude_agent_frontmatter,
    hooks_source=Path(__file__).resolve().parent / "hooks",
)

TARGETS: dict[str, Target] = {CLAUDE.name: CLAUDE}
DEFAULT_TARGET = CLAUDE

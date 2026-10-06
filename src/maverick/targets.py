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
    #: Stdlib-only CLI modules the hooks need before the CLI is installed
    #: (installer, version check), copied into the hooks directory.
    hook_modules: tuple[Path, ...] = ()
    #: Files that make the output a standalone plugin repo (manifest, README,
    #: LICENSE), as (source, destination relative to the output root).
    #: Rendered only with ``--out``; the repo root already has its own.
    dist_files: tuple[tuple[Path, str], ...] = ()
    #: Plugin layout, relative to the output root.
    skills_dir: str = "skills"
    agents_dir: str = "agents"
    hooks_dir: str = "hooks"


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

_SRC = Path(__file__).resolve().parent
_REPO = _SRC.parent.parent

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
        # Stable target id, for the rare template passage that must branch
        # ({% if RUNTIME.ID == "kiro" %}). Prefer the wording keys below.
        "ID": "claude",
        # The product, as in "the orchestrating Claude Code session".
        "NAME": "Claude Code",
        # The model acting as the agent, as in "Claude's call was wrong".
        "AGENT": "Claude",
        # Absolute path to the installed plugin, expanded by the runtime.
        "PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
        # Prefix that turns a skill name into a user invocation.
        "SKILL_PREFIX": "/maverick:",
        # Plugin manifest carrying the plugin version, relative to PLUGIN_ROOT.
        "PLUGIN_MANIFEST": ".claude-plugin/plugin.json",
        # Project folder whose files the runtime always loads into context.
        "RULES_DIR": ".claude/rules",
        # Project file `maverick init --runtime <ID>` writes for this runtime.
        "INIT_FILE": ".claude/settings.json",
    },
    arguments_token="$ARGUMENTS",
    skill_frontmatter=claude_skill_frontmatter,
    agent_frontmatter=claude_agent_frontmatter,
    hooks_source=_SRC / "hooks",
    hook_modules=(_SRC / "install_cli.py", _SRC / "version_check.py"),
    dist_files=(
        # Single source for the manifest: release.sh bumps its version.
        (_REPO / ".claude-plugin" / "plugin.json", ".claude-plugin/plugin.json"),
        (_SRC / "dist" / "claude" / "README.md", "README.md"),
        (_REPO / "LICENSE", "LICENSE"),
    ),
)

# ---------------------------------------------------------------------------
# Kiro
# ---------------------------------------------------------------------------

#: Where `maverick kiro install` puts the bundle by default. Skills and agents
#: are plain folders in Kiro (Powers cannot carry agents), so the CLI installs
#: them, tracked by a manifest under KIRO_MANIFEST.
KIRO_HOME = "~/.kiro"
KIRO_MANIFEST = "maverick/manifest.json"
#: Project steering folder. Kiro's custom agents don't load steering unless it
#: is listed in their resources, so Maverick's agents list it explicitly.
KIRO_STEERING_DIR = ".kiro/steering"


def kiro_skill_frontmatter(skill: SkillConfig, description: str | None) -> dict[str, Any]:
    """Agent Skills frontmatter (https://agentskills.io/specification).

    Kiro reads only name/description (plus optional license, compatibility,
    metadata); it has no equivalent of Claude Code's invocation flags, so
    every Maverick skill is both model-activatable and a `/name` command.
    """
    data: dict[str, Any] = {"name": skill.name, "description": description or skill.name}
    data["license"] = "Apache-2.0"
    return data


def kiro_agent_frontmatter(agent: AgentConfig, description: str) -> dict[str, Any]:
    """Kiro custom agent (V3 Markdown format: frontmatter + body as prompt).

    - Skills are attached as ``skill://`` resources and the project's
      steering as a ``file://`` resource; custom agents load neither unless
      listed.
    - ``read_only`` drops the write tools and denies ``fs_write``, so the
      agent can still read and run commands (git diff, tests) but not edit.
    - Claude-only options (model aliases, colours) are not rendered: Kiro
      model ids differ, and an unknown model only produces a warning.
    """
    tools = ["read", "shell", "web"] if agent.read_only else ["read", "write", "shell", "web"]
    data: dict[str, Any] = {"name": agent.name, "description": description, "tools": tools}
    if agent.read_only:
        data["permissions"] = {
            "rules": [{"capability": "fs_write", "effect": "deny"}]
        }
    # Project steering (including do-upskill's convention pointers): custom
    # agents don't load it unless listed. Workspace-relative.
    resources = [f"file://{KIRO_STEERING_DIR}/**/*.md"]
    resources += [f"skill://{KIRO_HOME}/skills/{name}/SKILL.md" for name in agent.skills]
    data["resources"] = resources
    return data


KIRO = Target(
    name="kiro",
    runtime={
        "ID": "kiro",
        "NAME": "Kiro",
        # Kiro runs whichever model the user picked; refer to the agent.
        "AGENT": "the agent",
        # Skills are installed under ~/.kiro/skills/<name>/, the same layout
        # the plugin root has, so plugin-relative paths keep working.
        "PLUGIN_ROOT": KIRO_HOME,
        # Kiro skills are invoked as /<name>, without a plugin namespace.
        "SKILL_PREFIX": "/",
        # Written by `maverick kiro install`; carries the bundle version.
        "PLUGIN_MANIFEST": KIRO_MANIFEST,
        # Steering files default to always-included, like .claude/rules.
        "RULES_DIR": KIRO_STEERING_DIR,
        "INIT_FILE": ".kiro/hooks/maverick.json",
    },
    arguments_token="$ARGUMENTS",
    skill_frontmatter=kiro_skill_frontmatter,
    agent_frontmatter=kiro_agent_frontmatter,
    # The scope guard is per project in Kiro: `maverick init --runtime kiro`.
    hooks_source=None,
)

TARGETS: dict[str, Target] = {CLAUDE.name: CLAUDE, KIRO.name: KIRO}
DEFAULT_TARGET = CLAUDE

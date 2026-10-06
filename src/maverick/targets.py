"""Render targets — one per agent runtime Maverick builds a plugin for.

Skill and agent sources are runtime-neutral. Anything that differs per
runtime — product names, the plugin-root variable, how a skill is invoked,
the runtime-argument placeholder — comes from the target, exposed to every
template as ``{{ RUNTIME.<KEY> }}``.

Claude Code is the only target today. Adding a runtime means adding a
:class:`Target` here; templates should not need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Target:
    """A runtime Maverick renders skills and agents for."""

    name: str
    #: Exposed to templates as ``{{ RUNTIME.<KEY> }}``.
    runtime: dict[str, str] = field(default_factory=dict)
    #: Literal token the runtime substitutes with user-supplied arguments.
    arguments_token: str = ""


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
)

TARGETS: dict[str, Target] = {CLAUDE.name: CLAUDE}
DEFAULT_TARGET = CLAUDE

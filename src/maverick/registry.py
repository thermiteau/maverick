"""Skill and agent template registry — discovers configs and renders templates."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from string import Template
from typing import Any

from maverick.models import AgentConfig, GlobalConfig, SkillConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_TEMPLATES_DIR = Path(__file__).resolve().parent / "skills"
AGENTS_TEMPLATES_DIR = Path(__file__).resolve().parent / "agents"
SKILLS_OUTPUT_DIR = PROJECT_ROOT / "skills"
AGENTS_OUTPUT_DIR = PROJECT_ROOT / "agents"

GLOBAL_CONFIG = GlobalConfig()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_config(config_path: Path) -> Any:
    """Dynamically load a CONFIG object from a config.py file."""
    spec = importlib.util.spec_from_file_location("_config", config_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.CONFIG


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def discover_skills(templates_dir: Path = SKILLS_TEMPLATES_DIR) -> list[SkillConfig]:
    """Find all skill directories that contain a config.py and load them."""
    return [
        _load_config(p)
        for p in sorted(templates_dir.glob("*/config.py"))
    ]


def _build_skill_frontmatter(skill: SkillConfig) -> str:
    """Build YAML frontmatter from a SkillConfig."""
    lines = ["---"]
    lines.append(f"name: {skill.name}")

    if skill.description:
        lines.append(f"description: {skill.description}")
    if skill.argument_hint:
        lines.append(f"argument-hint: {skill.argument_hint}")
    if skill.user_invocable:
        lines.append("user-invocable: true")
    if not skill.disable_model_invocation:
        lines.append("disable-model-invocation: false")
    if skill.allowed_tools:
        lines.append(f"allowed-tools: {', '.join(skill.allowed_tools)}")
    if skill.model:
        lines.append(f"model: {skill.model}")
    if skill.context:
        lines.append(f"context: {skill.context}")
    if skill.agent:
        lines.append(f"agent: {skill.agent}")

    lines.append("---")
    return "\n".join(lines)


def render_skill(
    skill: SkillConfig,
    global_config: GlobalConfig = GLOBAL_CONFIG,
    templates_dir: Path = SKILLS_TEMPLATES_DIR,
    output_dir: Path = SKILLS_OUTPUT_DIR,
) -> Path:
    """Render a single skill from its config and body template."""
    body_path = templates_dir / skill.name / "body.md"
    body = body_path.read_text()

    # Substitute body-level variables (e.g. $DEPENDS_ON, extra_context)
    context: dict[str, str] = {**global_config.extra_context, **skill.extra_context}
    if skill.depends_on:
        context["DEPENDS_ON"] = ", ".join(skill.depends_on)
    if context:
        body = Template(body).safe_substitute(context)

    frontmatter = _build_skill_frontmatter(skill)
    skill_output_dir = output_dir / skill.name
    skill_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = skill_output_dir / "SKILL.md"
    output_path.write_text(frontmatter + "\n" + body)
    return output_path


def _clean_skills_output(output_dir: Path) -> None:
    """Remove all skill subdirectories from the output directory."""
    if not output_dir.is_dir():
        return
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)


def render_all_skills(
    global_config: GlobalConfig = GLOBAL_CONFIG,
    templates_dir: Path = SKILLS_TEMPLATES_DIR,
    output_dir: Path = SKILLS_OUTPUT_DIR,
) -> list[Path]:
    """Discover all skill configs, clean output directory, and render."""
    skills = discover_skills(templates_dir)
    _clean_skills_output(output_dir)
    return [render_skill(s, global_config, templates_dir, output_dir) for s in skills]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def _build_agent_frontmatter(agent: AgentConfig) -> str:
    """Build YAML frontmatter from an AgentConfig."""
    lines = ["---"]
    lines.append(f"name: {agent.name}")
    lines.append(f"description: {agent.description}")

    if agent.model:
        lines.append(f"model: {agent.model}")
    if agent.color:
        lines.append(f"color: {agent.color}")
    if agent.permission_mode:
        lines.append(f"permissionMode: {agent.permission_mode}")
    if agent.max_turns is not None:
        lines.append(f"maxTurns: {agent.max_turns}")
    if agent.background:
        lines.append("background: true")
    if agent.isolation:
        lines.append(f"isolation: {agent.isolation}")
    if agent.memory:
        lines.append(f"memory: {agent.memory}")
    if agent.tools:
        lines.append(f"tools: {', '.join(agent.tools)}")
    if agent.disallowed_tools:
        lines.append(f"disallowedTools: {', '.join(agent.disallowed_tools)}")
    if agent.skills:
        lines.append("skills:")
        for skill in agent.skills:
            lines.append(f"  - {skill}")

    lines.append("---")
    return "\n".join(lines)


def discover_agents(
    templates_dir: Path = AGENTS_TEMPLATES_DIR,
) -> list[AgentConfig]:
    """Find all agent directories that contain a config.py and load them."""
    return [
        _load_config(p)
        for p in sorted(templates_dir.glob("*/config.py"))
    ]


def render_agent(
    agent: AgentConfig,
    templates_dir: Path = AGENTS_TEMPLATES_DIR,
    output_dir: Path = AGENTS_OUTPUT_DIR,
) -> Path:
    """Render a single agent from its config and body template."""
    body_path = templates_dir / agent.name / "body.md"
    body = body_path.read_text()

    frontmatter = _build_agent_frontmatter(agent)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{agent.name}.md"
    output_path.write_text(frontmatter + body)
    return output_path


def _clean_agents_output(output_dir: Path) -> None:
    """Remove all agent .md files from the output directory."""
    if not output_dir.is_dir():
        return
    for child in output_dir.glob("*.md"):
        child.unlink()


def render_all_agents(
    templates_dir: Path = AGENTS_TEMPLATES_DIR,
    output_dir: Path = AGENTS_OUTPUT_DIR,
) -> list[Path]:
    """Discover all agent configs, clean output directory, and render."""
    agents = discover_agents(templates_dir)
    _clean_agents_output(output_dir)
    return [render_agent(a, templates_dir, output_dir) for a in agents]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    for output in render_all_skills():
        print(f"Generated {output}")
    for output in render_all_agents():
        print(f"Generated {output}")


if __name__ == "__main__":
    main()

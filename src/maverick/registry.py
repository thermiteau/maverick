"""Skill and agent template registry — discovers configs and renders templates."""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Template as Jinja2Template

from maverick.models import AgentConfig, GlobalConfig, SkillConfig
from maverick.names import ALL_AGENT_NAMES, ALL_SKILL_NAMES

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_version() -> str:
    """Get the Maverick version for embedding in build output."""
    # Prefer pyproject.toml — always up-to-date in the source tree.
    # importlib.metadata caches the version from install time, which
    # can be stale after a version bump without reinstalling.
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.is_file():
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE)
        if match:
            return match.group(1)
    try:
        from importlib.metadata import version

        return version("maverick")
    except Exception:
        pass
    return "unknown"


SKILLS_TEMPLATES_DIR = Path(__file__).resolve().parent / "skills"
AGENTS_TEMPLATES_DIR = Path(__file__).resolve().parent / "agents"
HOOKS_TEMPLATES_DIR = Path(__file__).resolve().parent / "hooks"
SKILLS_OUTPUT_DIR = PROJECT_ROOT / "skills"
AGENTS_OUTPUT_DIR = PROJECT_ROOT / "agents"
HOOKS_OUTPUT_DIR = PROJECT_ROOT / "hooks"

GLOBAL_CONFIG = GlobalConfig()


def _build_names_dict(names: set[str]) -> dict[str, str]:
    """Build a dict mapping UPPER_SNAKE keys to their kebab-case name values.

    For example: {"MAV_BP_CICD": "mav-bp-cicd", "DO_ISSUE_SOLO": "do-issue-solo"}
    """
    return {name.upper().replace("-", "_"): name for name in names}


# Pre-built dicts available to all templates.
SKILLS_DICT = _build_names_dict(ALL_SKILL_NAMES)
AGENTS_DICT = _build_names_dict(ALL_AGENT_NAMES)


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
    return [_load_config(p) for p in sorted(templates_dir.glob("*/config.py"))]


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
    body_path = templates_dir / skill.name / "body.md.j2"
    body = body_path.read_text()

    # Build Jinja2 context
    context: dict[str, Any] = {**global_config.extra_context, **skill.extra_context}
    if skill.depends_on:
        context["DEPENDS_ON"] = ", ".join(skill.depends_on)
    context["SKILLS"] = SKILLS_DICT
    context["AGENTS"] = AGENTS_DICT

    body = Jinja2Template(body).render(**context)

    frontmatter = _build_skill_frontmatter(skill)
    version_marker = f"\n\n<!-- maverick-plugin-version: {_get_version()} -->\n"
    skill_output_dir = output_dir / skill.name
    skill_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = skill_output_dir / "SKILL.md"
    output_path.write_text(frontmatter + "\n" + body + version_marker)

    _copy_skill_assets(skill, templates_dir, skill_output_dir)
    return output_path


def _copy_skill_assets(
    skill: SkillConfig, templates_dir: Path, skill_output_dir: Path
) -> None:
    """Copy each declared asset from the skill source dir to the build output."""
    skill_src_dir = templates_dir / skill.name
    for asset in skill.assets:
        src = skill_src_dir / asset
        if not src.exists():
            raise FileNotFoundError(
                f"Skill {skill.name!r} declares asset {asset!r} but {src} does not exist."
            )
        dst = skill_output_dir / asset
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


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
    return [_load_config(p) for p in sorted(templates_dir.glob("*/config.py"))]


def render_agent(
    agent: AgentConfig,
    templates_dir: Path = AGENTS_TEMPLATES_DIR,
    output_dir: Path = AGENTS_OUTPUT_DIR,
) -> Path:
    """Render a single agent from its config and body template."""
    body_path = templates_dir / agent.name / "body.md.j2"
    body = body_path.read_text()

    # Build Jinja2 context
    context: dict[str, Any] = {**agent.extra_context}
    context["SKILLS"] = SKILLS_DICT
    context["AGENTS"] = AGENTS_DICT

    body = Jinja2Template(body).render(**context)

    frontmatter = _build_agent_frontmatter(agent)
    version_marker = f"\n\n<!-- maverick-plugin-version: {_get_version()} -->\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{agent.name}.md"
    output_path.write_text(frontmatter + body + version_marker)
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
# CloudFormation templates
# ---------------------------------------------------------------------------

INFRA_OUTPUT_DIR = PROJECT_ROOT / "infra"


def render_cfn_templates(output_dir: Path = INFRA_OUTPUT_DIR) -> list[Path]:
    """Render standalone CloudFormation templates for manual upload."""
    import json

    from maverick.infra import (
        _build_infra_template,
        _build_vpc_template,
        _prepare_user_data,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Read lambda handler source for inline embedding
    handler_path = Path(__file__).resolve().parent / "lambda_handler.py"
    lambda_code = handler_path.read_text()

    # Prepare cloud-init user data with CFN variable references
    user_data = _prepare_user_data()

    templates = {
        "maverick-vpc.template.json": _build_vpc_template(),
        "maverick-infra.template.json": _build_infra_template(lambda_code, user_data),
    }

    paths = []
    for filename, template in templates.items():
        out = output_dir / filename
        out.write_text(json.dumps(template, indent=2) + "\n")
        paths.append(out)

    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def render_all_hooks(
    templates_dir: Path = HOOKS_TEMPLATES_DIR,
    output_dir: Path = HOOKS_OUTPUT_DIR,
) -> list[Path]:
    """Copy every hook source file from src/ to the build output.

    Hooks are static distribution files (no Jinja templating) — the
    registry just mirrors the directory tree. The output dir is fully
    cleared first so deleted source files don't linger.
    """
    if not templates_dir.is_dir():
        return []

    if output_dir.is_dir():
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for src in sorted(templates_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(templates_dir)
        if any(part.startswith("__") for part in rel.parts):
            continue  # skip __pycache__ contents, __init__.py, etc.
        dst = output_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(dst)
    return written


def main() -> None:
    for output in render_all_skills():
        print(f"Generated {output}")
    for output in render_all_agents():
        print(f"Generated {output}")
    for output in render_all_hooks():
        print(f"Generated {output}")
    for output in render_cfn_templates():
        print(f"Generated {output}")


if __name__ == "__main__":
    main()

"""Skill and agent template registry — discovers configs and renders templates."""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined

from maverick.models import AgentConfig, GlobalConfig, SkillConfig
from maverick.names import ALL_AGENT_NAMES, ALL_SKILL_NAMES
from maverick.targets import DEFAULT_TARGET, TARGETS, Target

# StrictUndefined makes any undefined template variable fail the build loudly
# instead of silently rendering as an empty string (which shipped broken
# commands like `coord read <repo> ` when ARGUMENTS was missing from the
# context, and would silently delete a cross-reference on any SKILLS/AGENTS
# constant typo).
_JINJA_ENV = Environment(undefined=StrictUndefined)

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

        return version("maverick-harness")
    except Exception:
        pass
    return "unknown"


SKILLS_TEMPLATES_DIR = Path(__file__).resolve().parent / "skills"
AGENTS_TEMPLATES_DIR = Path(__file__).resolve().parent / "agents"
HOOKS_TEMPLATES_DIR = Path(__file__).resolve().parent / "hooks"
DOCS_SKILLS_TEMPLATE_DIR = Path(__file__).resolve().parent / "docs-skills"
SKILLS_OUTPUT_DIR = PROJECT_ROOT / "skills"
AGENTS_OUTPUT_DIR = PROJECT_ROOT / "agents"
HOOKS_OUTPUT_DIR = PROJECT_ROOT / "hooks"
DOCS_SKILLS_OUTPUT_PATH = PROJECT_ROOT / "docs" / "skills" / "maverick-skills.md"

GLOBAL_CONFIG = GlobalConfig()


def _build_names_dict(names: set[str]) -> dict[str, str]:
    """Build a dict mapping UPPER_SNAKE keys to their kebab-case name values.

    For example: {"MAV_BP_CICD": "mav-bp-cicd", "DO_ISSUE_SOLO": "do-issue-solo"}
    """
    return {name.upper().replace("-", "_"): name for name in names}


# Pre-built dicts available to all templates.
SKILLS_DICT = _build_names_dict(ALL_SKILL_NAMES)
AGENTS_DICT = _build_names_dict(ALL_AGENT_NAMES)


def _base_context(target: Target) -> dict[str, Any]:
    """Template variables every skill and agent template can use."""
    return {"SKILLS": SKILLS_DICT, "AGENTS": AGENTS_DICT, "RUNTIME": target.runtime}


def _render_text(text: str, target: Target) -> str:
    """Render a config string (e.g. a description) for *target*.

    Descriptions may name the runtime (``{{ RUNTIME.NAME }}``), so they are
    templates too — rendered with the base context only.
    """
    return _JINJA_ENV.from_string(text).render(**_base_context(target))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_config(config_path: Path) -> Any:
    """Dynamically load a CONFIG object from a config.py file."""
    spec = importlib.util.spec_from_file_location("_config", config_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.CONFIG


def _validate_config(config: Any, config_path: Path, registered_names: set[str]) -> Any:
    """Validate a discovered config against its directory and the name registry.

    A CONFIG whose name doesn't match its directory would render to a path
    nothing references; a name missing from names.py would break the
    ``{{ SKILLS.X }}`` / ``{{ AGENTS.X }}`` constant system. Both were
    previously silent — fail the build instead.
    """
    dir_name = config_path.parent.name
    if config.name != dir_name:
        raise ValueError(
            f"{config_path}: CONFIG.name {config.name!r} does not match its "
            f"directory name {dir_name!r}."
        )
    if config.name not in registered_names:
        raise ValueError(
            f"{config_path}: {config.name!r} is not registered in maverick.names — "
            "add a name constant and register it in ALL_SKILL_NAMES/ALL_AGENT_NAMES."
        )
    return config


def _dump_frontmatter(data: dict[str, Any]) -> str:
    """Serialize a frontmatter mapping to a fenced YAML block.

    Uses yaml.safe_dump rather than string concatenation so values containing
    YAML-significant characters (``: ``, ``#``, leading ``[``/``{``) are quoted
    correctly instead of silently truncating or breaking the block.
    """
    body = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100_000,  # never hard-wrap long descriptions
    ).rstrip("\n")
    return f"---\n{body}\n---"


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def discover_skills(templates_dir: Path = SKILLS_TEMPLATES_DIR) -> list[SkillConfig]:
    """Find all skill directories that contain a config.py and load them."""
    return [
        _validate_config(_load_config(p), p, ALL_SKILL_NAMES)
        for p in sorted(templates_dir.glob("*/config.py"))
    ]


def _build_skill_frontmatter(skill: SkillConfig, target: Target = DEFAULT_TARGET) -> str:
    """Build the target's YAML frontmatter for a skill."""
    description = _render_text(skill.description, target) if skill.description else None
    return _dump_frontmatter(target.skill_frontmatter(skill, description))


def render_skill(
    skill: SkillConfig,
    global_config: GlobalConfig = GLOBAL_CONFIG,
    templates_dir: Path = SKILLS_TEMPLATES_DIR,
    output_dir: Path = SKILLS_OUTPUT_DIR,
    target: Target = DEFAULT_TARGET,
) -> Path:
    """Render a single skill from its config and body template."""
    body_path = templates_dir / skill.name / "body.md.j2"
    body = body_path.read_text()

    # Build Jinja2 context
    context: dict[str, Any] = {**global_config.extra_context, **skill.extra_context}
    if skill.depends_on:
        context["DEPENDS_ON"] = ", ".join(skill.depends_on)
    context.update(_base_context(target))
    # ARGUMENTS is a *runtime* placeholder, not a build-time value: emit the
    # literal token the runtime substitutes when the skill is invoked (e.g.
    # Claude Code's $ARGUMENTS). (It previously rendered as "" via Jinja's
    # default Undefined, stripping the issue number out of every
    # argument-bearing command.)
    context["ARGUMENTS"] = target.arguments_token

    body = _JINJA_ENV.from_string(body).render(**context)

    frontmatter = _build_skill_frontmatter(skill, target)
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
    target: Target = DEFAULT_TARGET,
) -> list[Path]:
    """Discover all skill configs, clean output directory, and render."""
    skills = discover_skills(templates_dir)
    _clean_skills_output(output_dir)
    return [
        render_skill(s, global_config, templates_dir, output_dir, target) for s in skills
    ]


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def _build_agent_frontmatter(agent: AgentConfig, target: Target = DEFAULT_TARGET) -> str:
    """Build the target's YAML frontmatter for an agent."""
    description = _render_text(agent.description, target)
    return _dump_frontmatter(target.agent_frontmatter(agent, description))


def discover_agents(
    templates_dir: Path = AGENTS_TEMPLATES_DIR,
) -> list[AgentConfig]:
    """Find all agent directories that contain a config.py and load them."""
    return [
        _validate_config(_load_config(p), p, ALL_AGENT_NAMES)
        for p in sorted(templates_dir.glob("*/config.py"))
    ]


def render_agent(
    agent: AgentConfig,
    templates_dir: Path = AGENTS_TEMPLATES_DIR,
    output_dir: Path = AGENTS_OUTPUT_DIR,
    target: Target = DEFAULT_TARGET,
) -> Path:
    """Render a single agent from its config and body template."""
    body_path = templates_dir / agent.name / "body.md.j2"
    body = body_path.read_text()

    # Build Jinja2 context
    context: dict[str, Any] = {**agent.extra_context}
    context.update(_base_context(target))

    body = _JINJA_ENV.from_string(body).render(**context)

    frontmatter = _build_agent_frontmatter(agent, target)
    version_marker = f"\n\n<!-- maverick-plugin-version: {_get_version()} -->\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{agent.name}.md"
    # The newline after the frontmatter fence is load-bearing: without it a
    # body that starts with text produces `---You are...`, which strict
    # frontmatter parsers fail to terminate.
    output_path.write_text(frontmatter + "\n" + body + version_marker)
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
    target: Target = DEFAULT_TARGET,
) -> list[Path]:
    """Discover all agent configs, clean output directory, and render."""
    agents = discover_agents(templates_dir)
    _clean_agents_output(output_dir)
    return [render_agent(a, templates_dir, output_dir, target) for a in agents]


# ---------------------------------------------------------------------------
# Docs — skills index
# ---------------------------------------------------------------------------


def render_docs_skills(
    template_dir: Path = DOCS_SKILLS_TEMPLATE_DIR,
    output_path: Path = DOCS_SKILLS_OUTPUT_PATH,
) -> Path:
    """Render docs/skills/maverick-skills.md from all skill configs.

    Iterates over every skill registered in ALL_SKILL_NAMES, pulls its
    description from the corresponding SkillConfig, and feeds the data
    to the Jinja2 template at src/maverick/docs-skills/body.md.j2.
    """
    body = (template_dir / "body.md.j2").read_text()

    by_name = {s.name: s for s in discover_skills()}
    skills = [
        {
            "name": name,
            "description": _render_text(by_name[name].description or "", DEFAULT_TARGET).strip(),
        }
        for name in sorted(ALL_SKILL_NAMES)
        if name in by_name
    ]

    rendered = _JINJA_ENV.from_string(body).render(skills=skills)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered)
    return output_path


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


def render_target(target: Target, output_root: Path) -> list[Path]:
    """Render one target's complete plugin (skills, agents, hooks) under *output_root*."""
    from maverick.generate_topics import generate_topics_json  # imports this module

    skills_dir = output_root / target.skills_dir
    written = render_all_skills(output_dir=skills_dir, target=target)
    # do-upskill reads topics.json at runtime; render_all_skills just cleaned it.
    written.append(generate_topics_json(skills_dir))
    written += render_all_agents(output_dir=output_root / target.agents_dir, target=target)
    hooks_dir = output_root / target.hooks_dir
    if target.hooks_source is not None:
        written += render_all_hooks(target.hooks_source, hooks_dir)
    for module in target.hook_modules:
        hooks_dir.mkdir(parents=True, exist_ok=True)
        written.append(Path(shutil.copy2(module, hooks_dir / module.name)))
    return written


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m maverick.registry",
        description="Render skills, agents and hooks for a runtime target.",
    )
    parser.add_argument(
        "--target", choices=sorted(TARGETS), default=DEFAULT_TARGET.name,
        help=f"Runtime to render for (default: {DEFAULT_TARGET.name})",
    )
    parser.add_argument(
        "--out", type=Path, metavar="DIR",
        help="Render only the target's plugin into DIR. Without it, the default "
        "target renders into the repo root along with the docs index and "
        "CloudFormation templates.",
    )
    args = parser.parse_args(argv)
    target = TARGETS[args.target]

    output_root = args.out.resolve() if args.out else PROJECT_ROOT
    for output in render_target(target, output_root):
        print(f"Generated {output}")
    if args.out:
        return
    print(f"Generated {render_docs_skills()}")
    for output in render_cfn_templates():
        print(f"Generated {output}")


if __name__ == "__main__":
    main()

"""Plugin-as-deliverable integrity checks.

These tests catch the class of bug where Python code is internally consistent
but the plugin distribution is not — e.g. a skill body referencing a script
that isn't shipped, a manifest pointing at a deleted file, or a config
declaring a dependency on a skill name that no longer exists.

Unit tests on individual modules cannot catch these because the bugs live in
the relationships between artefacts, not in any single artefact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.registry import (
    AGENTS_TEMPLATES_DIR,
    PROJECT_ROOT,
    SKILLS_TEMPLATES_DIR,
    discover_agents,
    discover_skills,
)


@pytest.fixture(scope="module")
def all_skills():
    return discover_skills(SKILLS_TEMPLATES_DIR)


@pytest.fixture(scope="module")
def all_agents():
    return discover_agents(AGENTS_TEMPLATES_DIR)


@pytest.fixture(scope="module")
def skill_names(all_skills):
    return {s.name for s in all_skills}


class TestSkillCrossReferences:
    """Skill `depends_on` entries must reference existing skills."""

    def test_all_depends_on_resolve(self, all_skills, skill_names):
        problems = [
            (skill.name, dep)
            for skill in all_skills
            for dep in skill.depends_on
            if dep not in skill_names
        ]
        assert not problems, (
            "Skills declare depends_on referencing unknown skill names: "
            + ", ".join(f"{s} -> {d}" for s, d in problems)
        )


class TestSkillAssets:
    """Every asset declared on a skill must exist in source.

    Catches the bug where a skill declares it ships a companion file but
    the file has been deleted or renamed (the do-install / install.sh
    failure mode).
    """

    def test_all_declared_assets_exist_in_source(self, all_skills):
        problems: list[str] = []
        for skill in all_skills:
            skill_src = SKILLS_TEMPLATES_DIR / skill.name
            for asset in skill.assets:
                if not (skill_src / asset).exists():
                    problems.append(f"{skill.name} -> {asset}")
        assert not problems, (
            "Skills declare assets that do not exist in source: " + ", ".join(problems)
        )


class TestAgentCrossReferences:
    """Agent `skills` entries must reference existing skills."""

    def test_all_agent_skills_resolve(self, all_agents, skill_names):
        problems = [
            (agent.name, sk)
            for agent in all_agents
            for sk in agent.skills
            if sk not in skill_names
        ]
        assert not problems, (
            "Agents declare skills referencing unknown skill names: "
            + ", ".join(f"{a} -> {s}" for a, s in problems)
        )


class TestPluginManifests:
    """Path-valued strings in plugin manifests must resolve to real files.

    Caught the bug where .cursor-plugin/cursor.plugin.json referenced
    ./hooks/hooks.json after the file was deleted.
    """

    MANIFESTS = [
        PROJECT_ROOT / ".claude-plugin" / "plugin.json",
        PROJECT_ROOT / ".claude-plugin" / "marketplace.json",
        PROJECT_ROOT / ".cursor-plugin" / "cursor.plugin.json",
    ]

    @pytest.mark.parametrize(
        "manifest_path",
        MANIFESTS,
        ids=[m.name for m in MANIFESTS],
    )
    def test_manifest_paths_exist(self, manifest_path: Path):
        if not manifest_path.exists():
            pytest.skip(f"{manifest_path} does not exist")

        data = json.loads(manifest_path.read_text())
        problems = list(_collect_path_problems(data, manifest_path))
        assert not problems, (
            f"{manifest_path.name} references missing paths: " + ", ".join(problems)
        )


def _plugin_root_for(manifest_path: Path) -> Path:
    """Return the plugin root for a manifest.

    Claude Code and Cursor manifests live in `<plugin-root>/.<adapter>/`, and
    `./`-prefixed paths inside them are resolved relative to the plugin root
    (the parent of the dot-directory), not the manifest's own directory.
    """
    if manifest_path.parent.name.startswith("."):
        return manifest_path.parent.parent
    return manifest_path.parent


def _collect_path_problems(node, manifest_path: Path, key_path: str = "") -> list[str]:
    """Walk a JSON-like tree and report any './'-prefixed string that doesn't resolve."""
    problems: list[str] = []
    plugin_root = _plugin_root_for(manifest_path)
    if isinstance(node, dict):
        for k, v in node.items():
            problems.extend(_collect_path_problems(v, manifest_path, f"{key_path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            problems.extend(_collect_path_problems(v, manifest_path, f"{key_path}[{i}]"))
    elif isinstance(node, str) and node.startswith("./"):
        target = (plugin_root / node[2:]).resolve()
        if not target.exists():
            problems.append(f"{key_path.lstrip('.')} -> {node}")
    return problems

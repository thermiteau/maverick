"""Tests for maverick.registry — template discovery and rendering."""

from __future__ import annotations

from pathlib import Path

from maverick.models import AgentConfig, GlobalConfig, SkillConfig
from maverick.names import ALL_AGENT_NAMES, ALL_SKILL_NAMES
from maverick.registry import (
    AGENTS_DICT,
    SKILLS_DICT,
    _build_agent_frontmatter,
    _build_names_dict,
    _build_skill_frontmatter,
    _clean_agents_output,
    _clean_skills_output,
    _get_version,
    render_agent,
    render_skill,
)


class TestBuildNamesDict:
    def test_basic_conversion(self):
        result = _build_names_dict({"do-task-solo", "mav-bp-logging"})
        assert result["DO_TASK_SOLO"] == "do-task-solo"
        assert result["MAV_BP_LOGGING"] == "mav-bp-logging"

    def test_empty_set(self):
        assert _build_names_dict(set()) == {}

    def test_all_skills_covered(self):
        assert len(SKILLS_DICT) == len(ALL_SKILL_NAMES)
        for name in ALL_SKILL_NAMES:
            key = name.upper().replace("-", "_")
            assert key in SKILLS_DICT
            assert SKILLS_DICT[key] == name

    def test_all_agents_covered(self):
        assert len(AGENTS_DICT) == len(ALL_AGENT_NAMES)
        for name in ALL_AGENT_NAMES:
            key = name.upper().replace("-", "_")
            assert key in AGENTS_DICT


class TestBuildSkillFrontmatter:
    def test_minimal_skill(self):
        skill = SkillConfig(name="test-skill")
        fm = _build_skill_frontmatter(skill)
        assert fm.startswith("---")
        assert fm.endswith("---")
        assert "name: test-skill" in fm
        # Defaults should not appear
        assert "user-invocable" not in fm
        assert "disable-model-invocation" not in fm  # True is default, omitted

    def test_full_skill(self):
        skill = SkillConfig(
            name="my-skill",
            description="A cool skill",
            argument_hint="<url>",
            user_invocable=True,
            disable_model_invocation=False,
            allowed_tools=["Bash", "Read"],
            model="sonnet",
            context="fork",
            agent="agent-x",
        )
        fm = _build_skill_frontmatter(skill)
        assert "description: A cool skill" in fm
        assert "argument-hint: <url>" in fm
        assert "user-invocable: true" in fm
        assert "disable-model-invocation: false" in fm
        assert "allowed-tools: Bash, Read" in fm
        assert "model: sonnet" in fm
        assert "context: fork" in fm
        assert "agent: agent-x" in fm

    def test_no_description(self):
        skill = SkillConfig(name="no-desc")
        fm = _build_skill_frontmatter(skill)
        assert "description:" not in fm


class TestBuildAgentFrontmatter:
    def test_minimal_agent(self):
        agent = AgentConfig(name="agent-test", description="Test agent")
        fm = _build_agent_frontmatter(agent)
        assert "name: agent-test" in fm
        assert "description: Test agent" in fm
        assert "model:" not in fm
        assert "background:" not in fm

    def test_full_agent(self):
        agent = AgentConfig(
            name="agent-full",
            description="Full agent",
            model="opus",
            color="#FF0000",
            permission_mode="dontAsk",
            max_turns=25,
            background=True,
            isolation="worktree",
            memory="project",
            tools=["Read", "Write", "Bash"],
            disallowed_tools=["Agent"],
            skills=["do-task-solo", "mav-bp-logging"],
        )
        fm = _build_agent_frontmatter(agent)
        assert "model: opus" in fm
        assert "color: #FF0000" in fm
        assert "permissionMode: dontAsk" in fm
        assert "maxTurns: 25" in fm
        assert "background: true" in fm
        assert "isolation: worktree" in fm
        assert "memory: project" in fm
        assert "tools: Read, Write, Bash" in fm
        assert "disallowedTools: Agent" in fm
        assert "skills:" in fm
        assert "  - do-task-solo" in fm
        assert "  - mav-bp-logging" in fm


class TestGetVersion:
    def test_returns_non_empty(self):
        version = _get_version()
        assert isinstance(version, str)
        assert len(version) > 0
        assert version != "unknown"


class TestRenderSkill:
    def test_render_simple_skill(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("# Hello\n\nThis is a test skill.")

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="test-skill", description="Test")
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        assert result.exists()
        content = result.read_text()
        assert "---" in content
        assert "name: test-skill" in content
        assert "# Hello" in content

    def test_render_includes_version_marker(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "ver-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("Content here.")

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="ver-skill")
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        content = result.read_text()
        assert "<!-- maverick-plugin-version:" in content

    def test_render_with_jinja_variables(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "jinja-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text(
            "Depends on: {{ DEPENDS_ON }}\nSkill: {{ SKILLS.DO_TASK_SOLO }}"
        )

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="jinja-skill", depends_on=["dep-a", "dep-b"])
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        content = result.read_text()
        assert "dep-a, dep-b" in content
        assert "do-task-solo" in content

    def test_render_with_extra_context(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "ctx-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("Version: {{ VERSION }}")

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="ctx-skill", extra_context={"VERSION": "2.0"})
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        content = result.read_text()
        assert "Version: 2.0" in content


class TestRenderAgent:
    def test_render_simple_agent(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        agent_dir = templates_dir / "agent-test"
        agent_dir.mkdir(parents=True)
        (agent_dir / "body.md.j2").write_text("# Agent Prompt\n\nDo the thing.")

        output_dir = tmp_path / "output"
        agent = AgentConfig(name="agent-test", description="Test")
        result = render_agent(agent, templates_dir, output_dir)

        assert result.exists()
        content = result.read_text()
        assert "name: agent-test" in content
        assert "# Agent Prompt" in content

    def test_render_includes_version_marker(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        agent_dir = templates_dir / "agent-ver"
        agent_dir.mkdir(parents=True)
        (agent_dir / "body.md.j2").write_text("Agent content.")

        output_dir = tmp_path / "output"
        agent = AgentConfig(name="agent-ver", description="Version test")
        result = render_agent(agent, templates_dir, output_dir)

        content = result.read_text()
        assert "<!-- maverick-plugin-version:" in content

    def test_render_with_skill_refs(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        agent_dir = templates_dir / "agent-ref"
        agent_dir.mkdir(parents=True)
        (agent_dir / "body.md.j2").write_text(
            "Use {{ SKILLS.MAV_BP_LOGGING }} and {{ AGENTS.AGENT_CODE_REVIEWER }}"
        )

        output_dir = tmp_path / "output"
        agent = AgentConfig(name="agent-ref", description="Ref test")
        result = render_agent(agent, templates_dir, output_dir)

        content = result.read_text()
        assert "mav-bp-logging" in content
        assert "agent-code-reviewer" in content


class TestCleanOutput:
    def test_clean_skills_removes_subdirs(self, tmp_path: Path):
        (tmp_path / "skill-a").mkdir()
        (tmp_path / "skill-a" / "SKILL.md").write_text("x")
        (tmp_path / "skill-b").mkdir()

        _clean_skills_output(tmp_path)
        assert not (tmp_path / "skill-a").exists()
        assert not (tmp_path / "skill-b").exists()

    def test_clean_skills_nonexistent_dir(self, tmp_path: Path):
        _clean_skills_output(tmp_path / "nope")  # Should not raise

    def test_clean_agents_removes_md_files(self, tmp_path: Path):
        (tmp_path / "agent-a.md").write_text("x")
        (tmp_path / "agent-b.md").write_text("x")
        (tmp_path / "keep.txt").write_text("x")

        _clean_agents_output(tmp_path)
        assert not (tmp_path / "agent-a.md").exists()
        assert (tmp_path / "keep.txt").exists()

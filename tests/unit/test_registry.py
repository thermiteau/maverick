"""Tests for maverick.registry — template discovery and rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jinja2.exceptions import UndefinedError

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
    discover_agents,
    discover_skills,
    render_agent,
    render_all_hooks,
    render_skill,
)


def _parse_frontmatter(text: str) -> dict:
    """Extract and YAML-parse the frontmatter block from rendered output."""
    assert text.startswith("---\n"), "output must start with a frontmatter fence"
    block = text[len("---\n") :].split("\n---", 1)[0]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    return parsed


class TestBuildNamesDict:
    def test_basic_conversion(self):
        result = _build_names_dict({"do-issue-solo", "mav-bp-logging"})
        assert result["DO_ISSUE_SOLO"] == "do-issue-solo"
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
        parsed = _parse_frontmatter(fm + "\n")
        assert parsed["name"] == "test-skill"
        # The invocation flags are always emitted explicitly: Claude Code's
        # runtime defaults are the OPPOSITE of the config schema's defaults,
        # so omitting them silently inverted the declared intent.
        assert parsed["user-invocable"] is False
        assert parsed["disable-model-invocation"] is True

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
            hooks={"PreToolUse": [{"matcher": "Bash"}]},
        )
        parsed = _parse_frontmatter(_build_skill_frontmatter(skill) + "\n")
        assert parsed["description"] == "A cool skill"
        assert parsed["argument-hint"] == "<url>"
        assert parsed["user-invocable"] is True
        assert parsed["disable-model-invocation"] is False
        assert parsed["allowed-tools"] == "Bash, Read"
        assert parsed["model"] == "sonnet"
        assert parsed["context"] == "fork"
        assert parsed["agent"] == "agent-x"
        assert parsed["hooks"] == {"PreToolUse": [{"matcher": "Bash"}]}

    def test_no_description(self):
        skill = SkillConfig(name="no-desc")
        fm = _build_skill_frontmatter(skill)
        assert "description:" not in fm

    def test_yaml_significant_characters_survive(self):
        """Values with YAML metacharacters must round-trip, not truncate."""
        skill = SkillConfig(
            name="tricky-skill",
            description="Reviews code: two-stage #1 process [fast]",
            argument_hint="{issue: number}",
            user_invocable=True,
        )
        parsed = _parse_frontmatter(_build_skill_frontmatter(skill) + "\n")
        assert parsed["description"] == "Reviews code: two-stage #1 process [fast]"
        assert parsed["argument-hint"] == "{issue: number}"


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
            skills=["do-issue-solo", "mav-bp-logging"],
            mcp_servers={"github": {"type": "http"}},
            hooks={"Stop": []},
        )
        parsed = _parse_frontmatter(_build_agent_frontmatter(agent) + "\n")
        assert parsed["model"] == "opus"
        # '#FF0000' must be quoted by the serializer — unquoted, YAML reads
        # `color: #FF0000` as a comment and the value silently becomes null.
        assert parsed["color"] == "#FF0000"
        assert parsed["permissionMode"] == "dontAsk"
        assert parsed["maxTurns"] == 25
        assert parsed["background"] is True
        assert parsed["isolation"] == "worktree"
        assert parsed["memory"] == "project"
        assert parsed["tools"] == "Read, Write, Bash"
        assert parsed["disallowedTools"] == "Agent"
        assert parsed["skills"] == ["do-issue-solo", "mav-bp-logging"]
        assert parsed["mcpServers"] == {"github": {"type": "http"}}
        assert parsed["hooks"] == {"Stop": []}


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
            "Depends on: {{ DEPENDS_ON }}\nSkill: {{ SKILLS.DO_ISSUE_SOLO }}"
        )

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="jinja-skill", depends_on=["dep-a", "dep-b"])
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        content = result.read_text()
        assert "dep-a, dep-b" in content
        assert "do-issue-solo" in content

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

    def test_copies_declared_assets(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "asset-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("Body")
        (skill_dir / "helper.sh").write_text("#!/bin/bash\necho hi\n")
        (skill_dir / "data").mkdir()
        (skill_dir / "data" / "values.json").write_text('{"x": 1}')

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="asset-skill", assets=["helper.sh", "data"])
        render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        out_skill_dir = output_dir / "asset-skill"
        assert (out_skill_dir / "helper.sh").read_text() == "#!/bin/bash\necho hi\n"
        assert (out_skill_dir / "data" / "values.json").read_text() == '{"x": 1}'

    def test_missing_asset_raises(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "broken-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("Body")

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="broken-skill", assets=["does-not-exist.sh"])
        with pytest.raises(FileNotFoundError, match="does-not-exist.sh"):
            render_skill(skill, GlobalConfig(), templates_dir, output_dir)

    def test_arguments_renders_as_runtime_placeholder(self, tmp_path: Path):
        """{{ ARGUMENTS }} must emit the literal $ARGUMENTS runtime token.

        It previously rendered as "" (Jinja default Undefined), stripping the
        issue number out of every argument-bearing command in build output.
        """
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "args-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text(
            "Run `uv run maverick coord read <repo> {{ ARGUMENTS }}` now."
        )

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="args-skill")
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        assert "coord read <repo> $ARGUMENTS" in result.read_text()

    def test_undefined_template_variable_fails_build(self, tmp_path: Path):
        """Unknown template variables must raise, not render as empty string."""
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "typo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("See {{ SKILLS.MAV_BP_LOGING }}.")

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="typo-skill")
        with pytest.raises(UndefinedError):
            render_skill(skill, GlobalConfig(), templates_dir, output_dir)

    def test_frontmatter_yaml_parses(self, tmp_path: Path):
        templates_dir = tmp_path / "templates"
        skill_dir = templates_dir / "parse-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "body.md.j2").write_text("Body")

        output_dir = tmp_path / "output"
        skill = SkillConfig(name="parse-skill", description="Does things: safely")
        result = render_skill(skill, GlobalConfig(), templates_dir, output_dir)

        parsed = _parse_frontmatter(result.read_text())
        assert parsed["name"] == "parse-skill"
        assert parsed["description"] == "Does things: safely"


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
            "Use {{ SKILLS.MAV_BP_OPERABILITY }} and {{ AGENTS.AGENT_CODE_REVIEWER }}"
        )

        output_dir = tmp_path / "output"
        agent = AgentConfig(name="agent-ref", description="Ref test")
        result = render_agent(agent, templates_dir, output_dir)

        content = result.read_text()
        assert "mav-bp-operability" in content
        assert "agent-code-reviewer" in content

    def test_newline_after_frontmatter_fence(self, tmp_path: Path):
        """A body starting with text must not merge into the closing fence.

        `frontmatter + body` produced `---You are...`, which strict
        frontmatter parsers fail to terminate.
        """
        templates_dir = tmp_path / "templates"
        agent_dir = templates_dir / "agent-nl"
        agent_dir.mkdir(parents=True)
        (agent_dir / "body.md.j2").write_text("You are an agent. No leading blank line.")

        output_dir = tmp_path / "output"
        agent = AgentConfig(name="agent-nl", description="Newline test")
        content = render_agent(agent, templates_dir, output_dir).read_text()

        assert "\n---\nYou are an agent." in content
        parsed = _parse_frontmatter(content)
        assert parsed["name"] == "agent-nl"


class TestConfigValidation:
    def _write_config(self, dir_path: Path, name: str) -> None:
        dir_path.mkdir(parents=True)
        (dir_path / "config.py").write_text(
            "from maverick.models import SkillConfig\n"
            f"CONFIG = SkillConfig(name={name!r})\n"
        )

    def test_name_directory_mismatch_raises(self, tmp_path: Path):
        self._write_config(tmp_path / "some-dir", "other-name")
        with pytest.raises(ValueError, match="does not match its"):
            discover_skills(tmp_path)

    def test_unregistered_name_raises(self, tmp_path: Path):
        self._write_config(tmp_path / "not-a-real-skill", "not-a-real-skill")
        with pytest.raises(ValueError, match="not registered in maverick.names"):
            discover_skills(tmp_path)


class TestRealSourceTree:
    """Invariants over the actual shipped configs and templates."""

    def test_all_skill_configs_discover_and_validate(self):
        skills = discover_skills()
        assert len(skills) == len(ALL_SKILL_NAMES)

    def test_all_agent_configs_discover_and_validate(self):
        agents = discover_agents()
        assert len(agents) == len(ALL_AGENT_NAMES)

    def test_every_skill_frontmatter_round_trips(self):
        for skill in discover_skills():
            parsed = _parse_frontmatter(_build_skill_frontmatter(skill) + "\n")
            assert parsed["name"] == skill.name
            assert parsed["user-invocable"] is skill.user_invocable
            assert parsed["disable-model-invocation"] is skill.disable_model_invocation
            if skill.description:
                assert parsed["description"] == skill.description

    def test_every_agent_frontmatter_round_trips(self):
        for agent in discover_agents():
            parsed = _parse_frontmatter(_build_agent_frontmatter(agent) + "\n")
            assert parsed["name"] == agent.name
            assert parsed["description"] == agent.description
            if agent.skills:
                assert parsed["skills"] == agent.skills

    def test_reference_skills_are_non_invocable_in_output(self):
        """The bp reference tier must actually ship non-invocable."""
        by_name = {s.name: s for s in discover_skills()}
        logging_skill = by_name["mav-bp-operability"]
        parsed = _parse_frontmatter(_build_skill_frontmatter(logging_skill) + "\n")
        assert parsed["disable-model-invocation"] is True
        assert parsed["user-invocable"] is False

    def test_every_skill_has_a_consumer(self):
        """No orphaned skills: every non-user-invocable skill must be
        referenced by at least one other skill/agent (config or template)
        — a skill nothing loads is dead weight shipped into every
        installation. This lint would have caught the six orphans the
        modernization review found by hand.
        """
        from maverick.registry import AGENTS_TEMPLATES_DIR, SKILLS_TEMPLATES_DIR

        skills = discover_skills()

        # Build the reference corpus: every config's depends_on/skills
        # Reference corpus keyed by source directory, so a skill's own
        # body/config never counts as its consumer. config.py text catches
        # consumers beyond depends_on (e.g. do-upskill's TopicConfig
        # best_practice_skill references).
        sources: dict[str, str] = {}
        for tpl_dir in (SKILLS_TEMPLATES_DIR, AGENTS_TEMPLATES_DIR):
            for path in list(tpl_dir.glob("*/body.md.j2")) + list(tpl_dir.glob("*/config.py")):
                key = f"{tpl_dir.name}/{path.parent.name}"
                sources[key] = sources.get(key, "") + path.read_text()

        orphans = []
        for cfg in skills:
            if cfg.user_invocable:
                continue  # entry points are their own consumers
            constant = cfg.name.upper().replace("-", "_")
            own_key = f"skills/{cfg.name}"
            referenced = any(
                cfg.name in text or constant in text
                for key, text in sources.items()
                if key != own_key
            )
            if not referenced:
                orphans.append(cfg.name)
        assert not orphans, (
            f"orphaned skills with no consumer: {orphans} — wire them into a "
            "workflow/agent or delete them"
        )


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


class TestRenderAllHooks:
    def test_copies_files_preserving_subdirs(self, tmp_path: Path):
        src = tmp_path / "src-hooks"
        src.mkdir()
        (src / "hooks.json").write_text('{"hooks": {}}')
        (src / "scripts").mkdir()
        (src / "scripts" / "check.py").write_text("# script\n")

        out = tmp_path / "out-hooks"
        written = render_all_hooks(src, out)

        assert (out / "hooks.json").read_text() == '{"hooks": {}}'
        assert (out / "scripts" / "check.py").read_text() == "# script\n"
        assert {p.name for p in written} == {"hooks.json", "check.py"}

    def test_clears_stale_files(self, tmp_path: Path):
        src = tmp_path / "src-hooks"
        src.mkdir()
        (src / "hooks.json").write_text("{}")

        out = tmp_path / "out-hooks"
        out.mkdir()
        (out / "stale.py").write_text("old")
        (out / "stale-dir").mkdir()
        (out / "stale-dir" / "x.txt").write_text("x")

        render_all_hooks(src, out)

        assert (out / "hooks.json").exists()
        assert not (out / "stale.py").exists()
        assert not (out / "stale-dir").exists()

    def test_preserves_executable_mode(self, tmp_path: Path):
        src = tmp_path / "src-hooks"
        src.mkdir()
        script = src / "check.py"
        script.write_text("#!/usr/bin/env python3\n")
        script.chmod(0o755)

        out = tmp_path / "out-hooks"
        render_all_hooks(src, out)

        copied = out / "check.py"
        assert copied.stat().st_mode & 0o111, "executable bit should be preserved"

    def test_empty_when_source_dir_missing(self, tmp_path: Path):
        out = tmp_path / "out"
        result = render_all_hooks(tmp_path / "does-not-exist", out)
        assert result == []
        assert not out.exists()

    def test_skips_dunder_files(self, tmp_path: Path):
        src = tmp_path / "src-hooks"
        src.mkdir()
        (src / "hooks.json").write_text("{}")
        (src / "__pycache__").mkdir()
        (src / "__pycache__" / "junk.pyc").write_bytes(b"\x00")
        (src / "__init__.py").write_text("")

        out = tmp_path / "out-hooks"
        render_all_hooks(src, out)

        assert (out / "hooks.json").exists()
        assert not (out / "__pycache__").exists()
        assert not (out / "__init__.py").exists()

"""Tests for the KIRO render target and `maverick kiro install/uninstall/status`."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest
import yaml

from maverick import kiro_cli
from maverick.models import AgentConfig, ClaudeAgentOptions, SkillConfig
from maverick.names import ALL_AGENT_NAMES, ALL_SKILL_NAMES
from maverick.registry import (
    _build_agent_frontmatter,
    _build_skill_frontmatter,
    render_target,
)
from maverick.targets import KIRO, KIRO_MANIFEST


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    parsed = yaml.safe_load(text[4:].split("\n---", 1)[0])
    assert isinstance(parsed, dict)
    return parsed


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("kiro-bundle")
    render_target(KIRO, out)
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestKiroRender:
    def test_complete_bundle_without_hooks(self, bundle):
        assert {p.name for p in (bundle / "skills").iterdir()} == set(ALL_SKILL_NAMES)
        assert {p.stem for p in (bundle / "agents").glob("*.md")} == set(ALL_AGENT_NAMES)
        assert (bundle / "skills" / "do-upskill" / "topics.json").is_file()
        # The Kiro scope guard is per project (maverick init --runtime kiro).
        assert not (bundle / "hooks").exists()

    def test_skills_meet_agent_skills_spec(self, bundle):
        for skill_md in (bundle / "skills").glob("*/SKILL.md"):
            fm = _frontmatter(skill_md.read_text())
            assert fm["name"] == skill_md.parent.name
            assert 0 < len(fm["description"]) <= 1024
            # Claude Code-only fields must not leak into Kiro skills.
            assert not {"user-invocable", "disable-model-invocation", "context"} & set(fm)

    def test_no_claude_code_wording(self, bundle):
        for path in bundle.rglob("*.md"):
            text = path.read_text()
            for needle in (
                # No .claude/ path at all: Kiro projects must not grow one.
                "Claude Code", "CLAUDE_PLUGIN_ROOT", "/maverick:", ".claude",
            ):
                assert needle not in text, f"{path.relative_to(bundle)}: {needle!r}"

    def test_init_configures_kiro_runtime(self, bundle):
        """do-init must install Kiro's guard, not Claude's settings (demo-repo bug)."""
        init = (bundle / "skills" / "do-init" / "SKILL.md").read_text()
        assert "maverick init --runtime kiro" in init
        assert "git add .kiro/hooks/maverick.json" in init
        upskill = (bundle / "skills" / "do-upskill" / "SKILL.md").read_text()
        assert ".kiro/steering/maverick-<topic>.md" in upskill

    def test_install_skill_uses_kiro_flow(self, bundle):
        text = (bundle / "skills" / "do-install" / "SKILL.md").read_text()
        assert "maverick kiro install" in text
        assert "~/.kiro/maverick/manifest.json" in text
        assert "forked context" not in text

    def test_agents_are_v3_markdown_with_skill_resources(self, bundle):
        fm = _frontmatter((bundle / "agents" / "agent-code-reviewer.md").read_text())
        assert fm["name"] == "agent-code-reviewer"
        assert "write" not in fm["tools"] and "shell" in fm["tools"]
        assert {"capability": "fs_write", "effect": "deny"} in fm["permissions"]["rules"]
        assert "skill://~/.kiro/skills/mav-scope-boundaries/SKILL.md" in fm["resources"]
        assert "file://.kiro/steering/**/*.md" in fm["resources"]
        assert "model" not in fm  # Claude model aliases are not Kiro model ids


class TestKiroFrontmatter:
    def test_writer_agent_keeps_write_tools(self):
        agent = AgentConfig(name="agent-w", description="Writes docs")
        fm = _frontmatter(_build_agent_frontmatter(agent, KIRO) + "\n")
        assert fm["tools"] == ["read", "write", "shell", "web"]
        assert "permissions" not in fm
        assert fm["resources"] == ["file://.kiro/steering/**/*.md"]

    def test_claude_options_ignored(self):
        agent = AgentConfig(
            name="agent-x", description="d",
            claude=ClaudeAgentOptions(model="opus", color="red", disallowed_tools=["Agent"]),
        )
        fm = _frontmatter(_build_agent_frontmatter(agent, KIRO) + "\n")
        assert not {"model", "color", "disallowedTools"} & set(fm)

    def test_skill_description_rendered_for_kiro(self):
        skill = SkillConfig(name="s", description="Guards {{ RUNTIME.NAME }}.")
        assert _frontmatter(_build_skill_frontmatter(skill, KIRO) + "\n")["description"] == (
            "Guards Kiro."
        )


# ---------------------------------------------------------------------------
# maverick kiro install / uninstall / status
# ---------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path) -> Path:
    return tmp_path / ".kiro"


def _manifest(home: Path) -> dict:
    return json.loads((home / KIRO_MANIFEST).read_text())


class TestKiroInstall:
    def test_fresh_install(self, home):
        result = kiro_cli.install(home)
        assert set(result.installed_skills) == set(ALL_SKILL_NAMES)
        assert set(result.installed_agents) == {f"{a}.md" for a in ALL_AGENT_NAMES}
        manifest = _manifest(home)
        assert manifest["version"] == kiro_cli._cli_version()
        assert set(manifest["skills"]) == set(ALL_SKILL_NAMES)
        assert (home / "skills" / "do-init" / "SKILL.md").is_file()
        assert (home / "agents" / "agent-code-reviewer.md").is_file()

    def test_reinstall_is_clean(self, home):
        kiro_cli.install(home)
        (home / "skills" / "do-init" / "stray.txt").write_text("x")
        result = kiro_cli.install(home)
        assert not result.skipped and not result.removed
        assert not (home / "skills" / "do-init" / "stray.txt").exists()

    def test_upgrade_removes_skills_no_longer_shipped(self, home):
        kiro_cli.install(home)
        (home / "skills" / "mav-retired").mkdir()
        (home / "agents" / "agent-retired.md").write_text("x")
        manifest = _manifest(home)
        manifest["skills"].append("mav-retired")
        manifest["agents"].append("agent-retired.md")
        (home / KIRO_MANIFEST).write_text(json.dumps(manifest))
        result = kiro_cli.install(home)
        assert not (home / "skills" / "mav-retired").exists()
        assert not (home / "agents" / "agent-retired.md").exists()
        assert set(result.removed) == {"skills/mav-retired", "agents/agent-retired.md"}

    def test_foreign_skill_kept_unless_forced(self, home):
        (home / "skills" / "do-init").mkdir(parents=True)
        (home / "skills" / "do-init" / "SKILL.md").write_text("mine")
        result = kiro_cli.install(home)
        assert result.skipped == ["skills/do-init"]
        assert (home / "skills" / "do-init" / "SKILL.md").read_text() == "mine"
        assert "do-init" not in _manifest(home)["skills"]
        result = kiro_cli.install(home, force=True)
        assert not result.skipped
        assert "maverick" in (home / "skills" / "do-init" / "SKILL.md").read_text().lower()

    def test_uninstall_removes_only_maverick_files(self, home):
        (home / "skills" / "my-skill").mkdir(parents=True)
        (home / "agents").mkdir()
        (home / "agents" / "mine.md").write_text("x")
        kiro_cli.install(home)
        removed = kiro_cli.uninstall(home)
        assert len(removed) == len(ALL_SKILL_NAMES) + len(ALL_AGENT_NAMES)
        assert {p.name for p in (home / "skills").iterdir()} == {"my-skill"}
        assert {p.name for p in (home / "agents").iterdir()} == {"mine.md"}
        assert not (home / "maverick").exists()

    def test_uninstall_without_manifest_is_noop(self, home):
        assert kiro_cli.uninstall(home) == []


class TestKiroStatus:
    def _status(self, home) -> int:
        return kiro_cli.main(Namespace(kiro_action="status", home=str(home), force=False))

    def test_not_installed(self, home, capsys):
        assert self._status(home) == 1
        assert "not installed" in capsys.readouterr().out

    def test_matches_cli(self, home):
        kiro_cli.install(home)
        assert self._status(home) == 0

    def test_version_skew(self, home, capsys):
        kiro_cli.install(home)
        manifest = _manifest(home)
        manifest["version"] = "0.0.1"
        (home / KIRO_MANIFEST).write_text(json.dumps(manifest))
        assert self._status(home) == 1
        assert "maverick kiro install" in capsys.readouterr().err

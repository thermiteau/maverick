"""Tests for maverick.models — dataclass defaults and structure."""

from maverick.models import (
    AgentConfig,
    ClaudeAgentOptions,
    ClaudeSkillOptions,
    GlobalConfig,
    SkillConfig,
    TopicConfig,
)


class TestSkillConfig:
    def test_defaults(self):
        s = SkillConfig(name="test-skill")
        assert s.name == "test-skill"
        assert s.description is None
        assert s.argument_hint is None
        assert s.disable_model_invocation is True
        assert s.user_invocable is False
        assert s.depends_on == []
        assert s.extra_context == {}
        assert s.claude == ClaudeSkillOptions()
        assert s.claude.allowed_tools == []
        assert s.claude.model is None
        assert s.claude.context is None
        assert s.claude.agent is None
        assert s.claude.hooks is None

    def test_full_config(self):
        s = SkillConfig(
            name="my-skill",
            description="A test skill",
            argument_hint="<issue-url>",
            disable_model_invocation=False,
            user_invocable=True,
            depends_on=["dep-a", "dep-b"],
            extra_context={"KEY": "VALUE"},
            claude=ClaudeSkillOptions(allowed_tools=["Bash", "Read"], model="sonnet"),
        )
        assert s.user_invocable is True
        assert s.disable_model_invocation is False
        assert s.claude.allowed_tools == ["Bash", "Read"]
        assert s.depends_on == ["dep-a", "dep-b"]

    def test_mutable_defaults_are_independent(self):
        a = SkillConfig(name="a")
        b = SkillConfig(name="b")
        a.depends_on.append("x")
        a.claude.allowed_tools.append("Bash")
        assert "x" not in b.depends_on
        assert b.claude.allowed_tools == []


class TestAgentConfig:
    def test_defaults(self):
        a = AgentConfig(name="agent-test", description="Test agent")
        assert a.name == "agent-test"
        assert a.description == "Test agent"
        assert a.skills == []
        assert a.read_only is False
        assert a.claude.tools == []
        assert a.claude.disallowed_tools == []
        assert a.claude.model is None
        assert a.claude.max_turns is None
        assert a.claude.background is False
        assert a.claude.isolation is None

    def test_full_config(self):
        a = AgentConfig(
            name="agent-x",
            description="An agent",
            skills=["do-issue-solo"],
            read_only=True,
            claude=ClaudeAgentOptions(
                tools=["Read", "Write"],
                model="opus",
                max_turns=10,
                background=True,
                isolation="worktree",
            ),
        )
        assert a.read_only is True
        assert a.claude.model == "opus"
        assert a.claude.max_turns == 10
        assert a.claude.background is True
        assert a.claude.isolation == "worktree"


class TestTopicConfig:
    def test_fields(self):
        t = TopicConfig(topic="logging", prompt="Set up logging", best_practice_skill="mav-bp-logging")
        assert t.topic == "logging"
        assert t.prompt == "Set up logging"
        assert t.best_practice_skill == "mav-bp-logging"


class TestGlobalConfig:
    def test_defaults(self):
        g = GlobalConfig()
        assert g.extra_context == {}

    def test_with_context(self):
        g = GlobalConfig(extra_context={"VERSION": "1.0"})
        assert g.extra_context["VERSION"] == "1.0"

"""Tests for maverick.models — dataclass defaults and structure."""

from maverick.models import AgentConfig, GlobalConfig, SkillConfig, TopicConfig


class TestSkillConfig:
    def test_defaults(self):
        s = SkillConfig(name="test-skill")
        assert s.name == "test-skill"
        assert s.description is None
        assert s.argument_hint is None
        assert s.disable_model_invocation is True
        assert s.user_invocable is False
        assert s.allowed_tools == []
        assert s.model is None
        assert s.context is None
        assert s.agent is None
        assert s.hooks is None
        assert s.depends_on == []
        assert s.extra_context == {}

    def test_full_config(self):
        s = SkillConfig(
            name="my-skill",
            description="A test skill",
            argument_hint="<issue-url>",
            disable_model_invocation=False,
            user_invocable=True,
            allowed_tools=["Bash", "Read"],
            model="sonnet",
            depends_on=["dep-a", "dep-b"],
            extra_context={"KEY": "VALUE"},
        )
        assert s.user_invocable is True
        assert s.disable_model_invocation is False
        assert s.allowed_tools == ["Bash", "Read"]
        assert s.depends_on == ["dep-a", "dep-b"]

    def test_mutable_defaults_are_independent(self):
        a = SkillConfig(name="a")
        b = SkillConfig(name="b")
        a.depends_on.append("x")
        assert "x" not in b.depends_on


class TestAgentConfig:
    def test_defaults(self):
        a = AgentConfig(name="agent-test", description="Test agent")
        assert a.name == "agent-test"
        assert a.description == "Test agent"
        assert a.tools == []
        assert a.disallowed_tools == []
        assert a.model is None
        assert a.max_turns is None
        assert a.skills == []
        assert a.background is False
        assert a.isolation is None

    def test_full_config(self):
        a = AgentConfig(
            name="agent-x",
            description="An agent",
            tools=["Read", "Write"],
            model="opus",
            max_turns=10,
            skills=["do-issue-solo"],
            background=True,
            isolation="worktree",
        )
        assert a.model == "opus"
        assert a.max_turns == 10
        assert a.background is True
        assert a.isolation == "worktree"


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

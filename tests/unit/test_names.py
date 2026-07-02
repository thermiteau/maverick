"""Tests for maverick.names — name constants and registry sets."""

from maverick.names import (
    AGENT_CODE_REVIEWER,
    ALL_AGENT_NAMES,
    ALL_SKILL_NAMES,
    DO_ISSUE_GUIDED,
    DO_ISSUE_SOLO,
    MAV_BP_OPERABILITY,
)


class TestSkillNames:
    def test_all_skill_names_is_nonempty(self):
        assert len(ALL_SKILL_NAMES) > 0

    def test_known_skills_in_set(self):
        assert DO_ISSUE_SOLO in ALL_SKILL_NAMES
        assert DO_ISSUE_GUIDED in ALL_SKILL_NAMES
        assert MAV_BP_OPERABILITY in ALL_SKILL_NAMES

    def test_skill_names_are_kebab_case(self):
        for name in ALL_SKILL_NAMES:
            assert name == name.lower(), f"{name} is not lowercase"
            assert "_" not in name, f"{name} contains underscores"

    def test_no_duplicates(self):
        names_list = list(ALL_SKILL_NAMES)
        assert len(names_list) == len(set(names_list))


class TestAgentNames:
    def test_all_agent_names_is_nonempty(self):
        assert len(ALL_AGENT_NAMES) > 0

    def test_known_agents_in_set(self):
        assert AGENT_CODE_REVIEWER in ALL_AGENT_NAMES

    def test_agent_names_are_kebab_case(self):
        for name in ALL_AGENT_NAMES:
            assert name == name.lower()
            assert "_" not in name

    def test_agent_names_prefixed(self):
        for name in ALL_AGENT_NAMES:
            assert name.startswith("agent-"), f"{name} missing agent- prefix"

    def test_no_overlap_with_skills(self):
        assert ALL_SKILL_NAMES.isdisjoint(ALL_AGENT_NAMES)

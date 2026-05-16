"""Tests for maverick.session_review.skills — project skill discovery and classification."""

from __future__ import annotations

from pathlib import Path

from maverick.session_review.skills import (
    _extract_status,
    classify_skill_origin,
    find_project_skills,
    snapshot_skills,
)


def _create_skill(base: Path, topic: str, content: str) -> Path:
    """Helper to create a SKILL.md file under docs/maverick/skills/<topic>/."""
    skill_dir = base / "docs" / "maverick" / "skills" / topic
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content)
    return skill_file


class TestExtractStatus:
    def test_with_status(self):
        text = "---\nname: test\nstatus: adopted\n---\nContent"
        assert _extract_status(text) == "adopted"

    def test_without_status(self):
        assert _extract_status("---\nname: test\n---\nContent") is None

    def test_empty_string(self):
        assert _extract_status("") is None


class TestClassifySkillOrigin:
    def test_upskill_generated(self, tmp_path: Path):
        skill = _create_skill(tmp_path, "logging", "---\nstatus: adopted\n---\nContent")
        assert classify_skill_origin(skill) == "upskill-generated"

    def test_upskill_adopted(self, tmp_path: Path):
        skill = _create_skill(tmp_path, "logging", "---\nname: logging\n---\nContent")
        assert classify_skill_origin(skill) == "upskill-adopted"

    def test_user_created(self, tmp_path: Path):
        skill = _create_skill(tmp_path, "my-custom-skill", "---\nname: custom\n---\nContent")
        assert classify_skill_origin(skill) == "user-created"

    def test_nonexistent_file(self, tmp_path: Path):
        assert classify_skill_origin(tmp_path / "nope.md") == "user-created"


class TestFindProjectSkills:
    def test_finds_skills(self, tmp_path: Path):
        _create_skill(tmp_path, "logging", "content")
        _create_skill(tmp_path, "linting", "content")
        skills = find_project_skills(str(tmp_path))
        assert len(skills) == 2

    def test_empty_project(self, tmp_path: Path):
        assert find_project_skills(str(tmp_path)) == []

    def test_monorepo_packages(self, tmp_path: Path):
        # Top-level skill
        _create_skill(tmp_path, "logging", "content")
        # Package-level skill
        pkg_dir = tmp_path / "backend"
        _create_skill(pkg_dir, "alerting", "content")

        skills = find_project_skills(str(tmp_path))
        assert len(skills) == 2

    def test_ignores_hidden_dirs(self, tmp_path: Path):
        hidden = tmp_path / ".hidden"
        _create_skill(hidden, "logging", "content")
        skills = find_project_skills(str(tmp_path))
        # Top-level .hidden should be skipped by the mono-repo scan
        # but the top-level docs/ scan doesn't exist, so should be 0
        assert len(skills) == 0


class TestSnapshotSkills:
    def test_snapshot_copies_files(self, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        _create_skill(project, "logging", "---\nstatus: adopted\n---\nLogging content")
        _create_skill(project, "custom", "---\nname: custom\n---\nCustom content")

        output_dir = tmp_path / "output"
        meta = snapshot_skills(str(project), output_dir)

        assert len(meta) == 2
        topics = [m["topic"] for m in meta]
        assert "logging" in topics
        assert "custom" in topics

        # Verify files were copied
        snapshot_dir = output_dir / "skills-snapshot"
        assert snapshot_dir.is_dir()

    def test_snapshot_no_skills(self, tmp_path: Path):
        meta = snapshot_skills(str(tmp_path), tmp_path / "out")
        assert meta == []

    def test_snapshot_metadata_fields(self, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()
        _create_skill(project, "logging", "---\nstatus: draft\n---\nContent")

        output_dir = tmp_path / "output"
        meta = snapshot_skills(str(project), output_dir)
        assert meta[0]["topic"] == "logging"
        assert meta[0]["status"] == "draft"
        assert meta[0]["origin"] == "upskill-generated"
        assert "path" in meta[0]

"""Snapshot project-level skills for preservation alongside session reviews."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

# Standard topics produced by /upskill
STANDARD_UPSKILL_TOPICS = frozenset(
    {"logging", "alerting", "unit-testing", "integration-testing", "linting", "cicd"}
)

_STATUS_RE = re.compile(r"^status:\s*(\S+)", re.MULTILINE)


def find_project_skills(project_path: str) -> list[Path]:
    """Find all SKILL.md files under docs/maverick/skills/ in the project.

    Also checks for mono-repo package-scoped skills:
    ``<package>/docs/maverick/skills/<topic>/SKILL.md``
    """
    root = Path(project_path)
    results: list[Path] = []

    # Top-level project skills
    skills_dir = root / "docs" / "maverick" / "skills"
    if skills_dir.is_dir():
        results.extend(sorted(skills_dir.glob("*/SKILL.md")))

    # Mono-repo: one level deep packages
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        if child.is_dir() and not child.name.startswith("."):
            pkg_skills = child / "docs" / "maverick" / "skills"
            if pkg_skills.is_dir():
                results.extend(sorted(pkg_skills.glob("*/SKILL.md")))

    return results


def classify_skill_origin(skill_path: Path) -> str:
    """Infer how a project skill was created.

    Returns:
        ``'upskill-generated'`` — has ``status`` field in frontmatter
        ``'upskill-adopted'`` — standard topic name but no status field
        ``'user-created'`` — non-standard topic, no status field
    """
    topic = skill_path.parent.name
    try:
        text = skill_path.read_text()
    except OSError:
        return "user-created"

    has_status = bool(_STATUS_RE.search(text))

    if has_status:
        return "upskill-generated"
    if topic in STANDARD_UPSKILL_TOPICS:
        return "upskill-adopted"
    return "user-created"


def _extract_status(text: str) -> str | None:
    """Extract the status field value from skill frontmatter."""
    m = _STATUS_RE.search(text)
    return m.group(1) if m else None


def snapshot_skills(project_path: str, output_dir: Path) -> list[dict]:
    """Copy all project skills to output_dir/skills-snapshot/.

    Returns metadata about each snapshotted skill.
    """
    skill_paths = find_project_skills(project_path)
    if not skill_paths:
        return []

    snapshot_dir = output_dir / "skills-snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    metadata: list[dict] = []
    root = Path(project_path)

    for skill_path in skill_paths:
        topic = skill_path.parent.name
        origin = classify_skill_origin(skill_path)

        try:
            text = skill_path.read_text()
        except OSError:
            continue

        status = _extract_status(text)

        # Preserve directory structure relative to project root
        rel = skill_path.relative_to(root)
        dest = snapshot_dir / rel.parent.name / rel.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_path, dest)

        metadata.append(
            {
                "path": str(skill_path),
                "topic": topic,
                "status": status,
                "origin": origin,
            }
        )

    return metadata

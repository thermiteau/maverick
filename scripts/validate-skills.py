#!/usr/bin/env python3
"""Validate that all skill references in SKILL.md and agent files resolve to real skills.

Checks:
  - **Depends on:** lines in SKILL.md files (comma-separated skill IDs)
  - Inline references: ``the <name> skill`` and ``the `<name>` skill``
  - skills: lists in agent YAML frontmatter

Exit codes: 0 = all valid, 1 = broken references found, 2 = usage error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Common English words that match 'the <word> skill' but aren't skill references.
_IGNORE_INLINE = frozenset({
    "best-practice", "calling", "generated", "project", "relevant",
    "required", "same", "specific",
})


def find_skill_ids(skills_dir: Path) -> set[str]:
    """Return set of valid skill IDs (directory names containing SKILL.md)."""
    ids: set[str] = set()
    if not skills_dir.is_dir():
        return ids
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            ids.add(entry.name)
    return ids


def parse_depends_on(line: str) -> list[str]:
    """Extract skill names from a **Depends on:** line."""
    match = re.match(r"\*\*Depends on:\*\*\s*(.*)", line)
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


def is_inside_code_fence(lines: list[str], line_idx: int) -> bool:
    """Check if line_idx is inside a ```...``` fenced code block."""
    inside = False
    for i in range(line_idx):
        if lines[i].rstrip().startswith("```"):
            inside = not inside
    return inside


def extract_inline_refs(lines: list[str], line_idx: int) -> list[str]:
    """Extract skill names from inline prose patterns.

    Matches:
      - the <name> skill / the `<name>` skill
      - the <name> skills / the `<name>` skills  (plural)
      - the X and <name> skill(s)  (second item in a conjunction)
    """
    line = lines[line_idx]
    if is_inside_code_fence(lines, line_idx):
        return []
    refs: list[str] = []
    # Match: the <name> skill(s)  or  the `<name>` skill(s)
    for m in re.finditer(r"the\s+`?([a-z][a-z0-9-]*)`?\s+skills?\b", line):
        name = m.group(1)
        if name not in _IGNORE_INLINE:
            refs.append(name)
    # Match: and <name> skill(s)  (second item after "the X and Y skill(s)")
    for m in re.finditer(r"and\s+`?([a-z][a-z0-9-]*)`?\s+skills?\b", line):
        name = m.group(1)
        if name not in _IGNORE_INLINE:
            refs.append(name)
    return refs


def parse_agent_skills(filepath: Path) -> list[tuple[int, str]]:
    """Extract skill names from agent YAML frontmatter 'skills:' list."""
    text = filepath.read_text()
    lines = text.splitlines()
    results: list[tuple[int, str]] = []

    in_frontmatter = False
    in_skills = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and stripped == "---":
            break
        if in_frontmatter and stripped == "skills:":
            in_skills = True
            continue
        if in_skills:
            match = re.match(r"\s*-\s+(.+)", line)
            if match:
                results.append((i + 1, match.group(1).strip()))
            else:
                in_skills = False
    return results


def validate(repo_root: Path) -> list[str]:
    """Validate all skill references. Returns list of error messages."""
    skills_dir = repo_root / "skills"
    agents_dir = repo_root / "agents"

    valid_ids = find_skill_ids(skills_dir)
    if not valid_ids:
        return [f"No skills found in {skills_dir}"]

    errors: list[str] = []

    # Validate SKILL.md files
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    for skill_file in skill_files:
        text = skill_file.read_text()
        lines = text.splitlines()
        rel = skill_file.relative_to(repo_root)

        for i, line in enumerate(lines):
            lineno = i + 1

            # Check Depends on
            deps = parse_depends_on(line)
            for dep in deps:
                if dep not in valid_ids:
                    errors.append(
                        f"{rel}:{lineno}: broken reference '{dep}' in Depends on"
                    )

            # Check inline references
            inline = extract_inline_refs(lines, i)
            for ref in inline:
                if ref not in valid_ids:
                    errors.append(
                        f"{rel}:{lineno}: broken reference '{ref}' in inline text"
                    )

    # Validate agent files
    agent_files = sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    for agent_file in agent_files:
        rel = agent_file.relative_to(repo_root)
        skills = parse_agent_skills(agent_file)
        for lineno, skill_name in skills:
            if skill_name not in valid_ids:
                errors.append(
                    f"{rel}:{lineno}: broken reference '{skill_name}' in skills frontmatter"
                )

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    skills_dir = repo_root / "skills"

    if not skills_dir.is_dir():
        print(f"Error: skills directory not found at {skills_dir}", file=sys.stderr)
        return 2

    errors = validate(repo_root)
    valid_ids = find_skill_ids(skills_dir)
    agents_dir = repo_root / "agents"
    agent_count = len(list(agents_dir.glob("*.md"))) if agents_dir.is_dir() else 0

    if errors:
        for err in errors:
            print(err)
        print(f"\nFound {len(errors)} broken reference(s).")
        return 1

    print(
        f"All skill references are valid "
        f"(checked {len(valid_ids)} skills, {agent_count} agents)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

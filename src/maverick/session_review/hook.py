#!/usr/bin/env python3
"""Post-commit hook — review the current session after a git commit.

Called by the Claude Code PostToolUse hook when a Bash tool call contains
``git commit``. Runs mechanical analysis only (fast) and prints a brief
summary that feeds back into Claude's context.

Usage:
    maverick review-session-hook <session_id> <project_path>

Environment variables (set by Claude Code hook runner):
    TOOL_INPUT — JSON string with the Bash tool's input parameters
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from maverick.session_review.analyzers import get_current_version, run_mechanical_analyzers
from maverick.session_review.parser import encode_project_path, parse_session
from maverick.session_review.reporter import REVIEWS_DIR, generate_report, write_report
from maverick.session_review.skills import find_project_skills, snapshot_skills


def _is_git_commit() -> bool:
    """Check if the triggering Bash command was a git commit."""
    tool_input = os.environ.get("TOOL_INPUT", "")
    if not tool_input:
        return False
    try:
        data = json.loads(tool_input)
        cmd = data.get("command", "")
        return "git commit" in cmd
    except (json.JSONDecodeError, TypeError):
        return False


def main() -> None:
    """Entry point for the post-commit hook."""
    # Only run when the Bash command is a git commit
    if not _is_git_commit():
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Usage: maverick review-session-hook <session_id> <project_path>")
        sys.exit(1)

    session_id = sys.argv[1]
    project_path = sys.argv[2]

    # Find the session .jsonl file
    encoded = encode_project_path(project_path)
    session_dir = Path.home() / ".claude" / "projects" / encoded
    session_file = session_dir / f"{session_id}.jsonl"

    if not session_file.is_file():
        # Session file may not exist yet if this is early in the session
        sys.exit(0)

    session = parse_session(session_file)

    # Run mechanical analysis
    current_version = get_current_version()
    project_skill_paths = [str(p) for p in find_project_skills(project_path)]
    findings = run_mechanical_analyzers(session, project_skill_paths, current_version)

    if not findings:
        print("[session-review] No issues detected.")
        sys.exit(0)

    # Snapshot skills and write report
    slug = Path(project_path).name or "unknown"
    session_prefix = session_id[:8]
    report_dir = REVIEWS_DIR / slug / session_prefix
    skill_meta = snapshot_skills(project_path, report_dir)

    report_text = generate_report(session, findings, skill_meta)
    report_path = write_report(report_text, slug, session_id)

    # Print brief summary to stdout (feeds back into Claude's context)
    critical = sum(1 for f in findings if f.severity == "critical")
    warnings = sum(1 for f in findings if f.severity == "warning")

    print(f"[session-review] {len(findings)} issues found ({critical} critical, {warnings} warnings)")
    for f in findings:
        if f.severity in ("critical", "warning"):
            print(f"  [{f.severity.upper()}] {f.title}")
    print(f"  Full report: {report_path}")


if __name__ == "__main__":
    main()

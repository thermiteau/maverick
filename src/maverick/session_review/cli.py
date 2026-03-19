"""CLI command handler for ``maverick review-sessions``."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from maverick.session_review.analyzers import (
    Finding,
    get_current_version,
    run_mechanical_analyzers,
)
from maverick.session_review.parser import (
    SessionData,
    find_sessions,
    parse_session,
)
from maverick.session_review.reporter import (
    REVIEWS_DIR,
    generate_batch_summary,
    generate_report,
    write_report,
)
from maverick.session_review.skills import find_project_skills, snapshot_skills


def _project_slug(project_path: str) -> str:
    return Path(project_path).name or "unknown"


def _filter_by_days(sessions: list[Path], days: int | None) -> list[Path]:
    """Filter session files to those modified within the last N days."""
    if days is None:
        return sessions

    cutoff = datetime.now(tz=timezone.utc).timestamp() - (days * 86400)
    return [s for s in sessions if s.stat().st_mtime >= cutoff]


def _filter_by_session_id(sessions: list[Path], session_id: str) -> list[Path]:
    """Filter to a specific session by ID prefix match."""
    return [s for s in sessions if s.stem.startswith(session_id)]


def main(args) -> None:
    """Run the review-sessions command."""
    project_path = str(Path(args.project).resolve())
    output_dir = Path(args.output_dir) if args.output_dir else REVIEWS_DIR
    slug = _project_slug(project_path)

    # Find session files
    sessions = find_sessions(project_path)
    if not sessions:
        print(f"No sessions found for project: {project_path}")
        sys.exit(1)

    # Apply filters
    if args.session:
        sessions = _filter_by_session_id(sessions, args.session)
        if not sessions:
            print(f"No session matching ID: {args.session}")
            sys.exit(1)

    if args.days is not None:
        sessions = _filter_by_days(sessions, args.days)
        if not sessions:
            print(f"No sessions found within the last {args.days} days")
            sys.exit(1)

    current_version = get_current_version()
    print(f"Reviewing {len(sessions)} session(s) for {project_path}...")
    print(f"Current Maverick version: {current_version}")

    # Discover project skills on disk
    project_skill_paths = [str(p) for p in find_project_skills(project_path)]

    reports: list[tuple[SessionData, list[Finding]]] = []

    for session_path in sessions:
        print(f"  Parsing {session_path.stem[:8]}...", end=" ")
        session = parse_session(session_path)

        # Run mechanical analyzers
        findings = run_mechanical_analyzers(session, project_skill_paths, current_version)

        # Snapshot project skills into the report directory
        session_prefix = session.session_id[:8]
        report_dir = output_dir / slug / session_prefix
        skill_meta = snapshot_skills(project_path, report_dir)

        # Generate and write report
        report_text = generate_report(session, findings, skill_meta)
        report_path = write_report(report_text, slug, session.session_id, output_dir)

        reports.append((session, findings))

        n_critical = sum(1 for f in findings if f.severity == "critical")
        print(f"{len(findings)} findings ({n_critical} critical) → {report_path}")

    # Generate batch summary if multiple sessions
    if len(reports) > 1:
        summary = generate_batch_summary(reports)
        today = datetime.now().strftime("%Y-%m-%d")
        summary_path = output_dir / slug / f"batch-summary-{today}.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary)
        print(f"\nBatch summary → {summary_path}")

    # Print overall summary to stdout
    total = sum(len(f) for _, f in reports)
    critical = sum(1 for _, findings in reports for f in findings if f.severity == "critical")
    print(f"\nDone. {total} total findings ({critical} critical) across {len(reports)} sessions.")

    if args.full:
        print(
            "\nNote: --full semantic analysis requires dispatching the "
            "agent-session-reviewer agent from within Claude Code. "
            "Run this from a Claude Code session for full analysis."
        )

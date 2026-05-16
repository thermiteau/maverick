"""Generate markdown reports from session analysis findings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from maverick.session_review.analyzers import MAVERICK_GAP, USER_BEHAVIOR, Finding
from maverick.session_review.parser import SessionData

REVIEWS_DIR = Path.home() / ".maverick" / "reviews"


def _duration(created: str, modified: str) -> str:
    """Compute human-readable duration between two ISO timestamps."""
    try:
        start = datetime.fromisoformat(created.replace("Z", "+00:00"))
        end = datetime.fromisoformat(modified.replace("Z", "+00:00"))
        delta = end - start
        minutes = int(delta.total_seconds() / 60)
        if minutes < 1:
            return "<1 minute"
        if minutes < 60:
            return f"{minutes} minutes"
        hours = minutes // 60
        remaining = minutes % 60
        return f"{hours}h {remaining}m"
    except (ValueError, TypeError):
        return "unknown"


def _tool_counts(session: SessionData) -> dict[str, int]:
    """Count tool calls by tool name."""
    counts: dict[str, int] = {}
    for tc in session.tool_calls:
        counts[tc.tool_name] = counts.get(tc.tool_name, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _severity_badge(severity: str) -> str:
    return f"[{severity.upper()}]"


def _project_slug(project_path: str) -> str:
    """Derive a short project slug from the path."""
    return Path(project_path).name or "unknown"


def generate_report(
    session: SessionData,
    findings: list[Finding],
    skill_snapshot_meta: list[dict] | None = None,
) -> str:
    """Generate a markdown report for a single session."""
    lines: list[str] = []

    lines.append(f"# Session Review: {session.session_id}")
    lines.append("")
    lines.append(f"**Project:** {session.project_path}")
    lines.append(f"**Branch:** {session.git_branch}")
    lines.append(f"**Date:** {session.created[:10] if session.created else 'unknown'}")
    lines.append(f"**Model:** {session.model}")
    lines.append(f"**Duration:** {_duration(session.created, session.modified)}")
    lines.append("")

    # Maverick usage section
    lines.append("## Maverick Usage")
    lines.append("")
    has_plugin = bool(session.skills_available)
    lines.append(f"**Plugin available:** {'Yes' if has_plugin else 'No'}")
    if session.maverick_version:
        lines.append(f"**Plugin version:** {session.maverick_version}")
    elif has_plugin:
        lines.append("**Plugin version:** unknown (pre-version plugin)")
    lines.append(
        f"**Skills invoked:** {', '.join(session.skills_invoked) or 'none'}"
    )
    lines.append(
        f"**Project skills loaded:** "
        f"{', '.join(Path(p).parent.name for p in session.project_skills_read) or 'none'}"
    )

    if skill_snapshot_meta:
        lines.append("**Project skills on disk (at review time):**")
        for meta in skill_snapshot_meta:
            lines.append(f"- {meta['topic']} ({meta['origin']})")
        lines.append("**Skills snapshot:** ./skills-snapshot/")
    else:
        lines.append("**Project skills on disk:** none")

    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")

    if findings:
        # Group by analyzer
        by_analyzer: dict[str, list[Finding]] = {}
        for f in findings:
            by_analyzer.setdefault(f.analyzer, []).append(f)

        lines.append("| Category | Findings | Severity |")
        lines.append("|----------|----------|----------|")
        for analyzer, group in by_analyzer.items():
            sev_counts: dict[str, int] = {}
            for f in group:
                sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1
            sev_str = ", ".join(f"{v} {k}" for k, v in sev_counts.items())
            lines.append(f"| {analyzer} | {len(group)} | {sev_str} |")

        critical = sum(1 for f in findings if f.severity == "critical")
        lines.append("")
        lines.append(f"**Score: {len(findings)} issues ({critical} critical)**")
    else:
        lines.append("No issues found.")
    lines.append("")

    # Detailed findings — split by category
    gap_findings = [f for f in findings if f.category == MAVERICK_GAP]
    user_findings = [f for f in findings if f.category == USER_BEHAVIOR]

    if gap_findings:
        lines.append("## Maverick Plugin Gaps")
        lines.append("")
        for f in gap_findings:
            lines.append(f"### {_severity_badge(f.severity)} {f.title}")
            lines.append("")
            lines.append(f.detail)
            lines.append("")
            if f.maverick_component:
                lines.append(f"**Component:** `{f.maverick_component}`")
                lines.append("")
            if f.recommendation:
                lines.append(f"**Suggested fix:** {f.recommendation}")
                lines.append("")
            if f.timestamp:
                lines.append(f"*Timestamp: {f.timestamp}*")
                lines.append("")

    if user_findings:
        lines.append("## User Behavior")
        lines.append("")
        for f in user_findings:
            lines.append(f"### {_severity_badge(f.severity)} {f.title}")
            lines.append("")
            lines.append(f.detail)
            lines.append("")
            if f.recommendation:
                lines.append(f"**Recommendation:** {f.recommendation}")
                lines.append("")

    # Statistics
    lines.append("## Session Statistics")
    lines.append("")
    tool_counts = _tool_counts(session)
    tool_summary = ", ".join(f"{name}: {count}" for name, count in tool_counts.items())
    lines.append(f"- Tool calls: {len(session.tool_calls)} ({tool_summary})")
    lines.append(f"- Files modified: {len(session.files_modified)}")
    lines.append(f"- User corrections: {len(session.user_messages)}")
    lines.append(f"- Errors encountered: {len(session.errors)}")
    lines.append(f"- Commits: {len(session.commits)}")
    lines.append(f"- Skills invoked: {', '.join(session.skills_invoked) or 'none'}")
    lines.append(
        f"- Project skills read: "
        f"{', '.join(Path(p).parent.name for p in session.project_skills_read) or 'none'}"
    )
    lines.append("")

    return "\n".join(lines)


def write_report(
    report: str,
    project_slug: str,
    session_id: str,
    output_dir: Path | None = None,
) -> Path:
    """Write a report to the reviews directory. Returns the report path."""
    base = output_dir or REVIEWS_DIR
    # Use first 8 chars of session ID as directory name
    session_prefix = session_id[:8] if len(session_id) > 8 else session_id
    report_dir = base / project_slug / session_prefix
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.md"
    report_path.write_text(report)
    return report_path


def generate_batch_summary(
    reports: list[tuple[SessionData, list[Finding]]],
) -> str:
    """Generate an aggregate summary with Maverick gaps prioritised.

    Findings are split into two categories:
    1. **Maverick Plugin Gaps** — improvements needed in skills/agents/hooks
    2. **User Behavior** — the user should change their workflow

    Within each category, findings are deduplicated on
    (analyzer, recommendation) so recurring issues bubble up by frequency.
    """
    lines: list[str] = []
    today = datetime.now().strftime("%Y-%m-%d")

    lines.append(f"# Batch Session Review — {today}")
    lines.append("")
    lines.append(f"**Sessions reviewed:** {len(reports)}")

    # Collect all findings with session context
    all_findings: list[tuple[SessionData, Finding]] = []
    for session, findings in reports:
        for f in findings:
            all_findings.append((session, f))

    total = len(all_findings)
    gap_count = sum(1 for _, f in all_findings if f.category == MAVERICK_GAP)
    user_count = sum(1 for _, f in all_findings if f.category == USER_BEHAVIOR)
    total_critical = sum(1 for _, f in all_findings if f.severity == "critical")
    sessions_with_issues = sum(1 for _, findings in reports if findings)

    lines.append(
        f"**Total findings:** {total} "
        f"({total_critical} critical) "
        f"across {sessions_with_issues}/{len(reports)} sessions"
    )
    lines.append(
        f"**Maverick gaps:** {gap_count} | "
        f"**User behavior:** {user_count}"
    )
    lines.append("")

    if not all_findings:
        lines.append("No issues found across any session.")
        return "\n".join(lines)

    # ---------------------------------------------------------------
    # Consolidate findings — dedupe on (category, analyzer, recommendation)
    # ---------------------------------------------------------------
    consolidated: dict[tuple[str, str, str], _ConsolidatedFinding] = {}
    for session, f in all_findings:
        key = (f.category, f.analyzer, f.recommendation)
        if key not in consolidated:
            consolidated[key] = _ConsolidatedFinding(
                analyzer=f.analyzer,
                severity=f.severity,
                category=f.category,
                title=f.title,
                detail=f.detail,
                recommendation=f.recommendation,
                maverick_component=f.maverick_component,
            )
        entry = consolidated[key]
        entry.count += 1
        entry.session_ids.add(session.session_id[:8])
        if _SEVERITY_RANK.get(f.severity, 9) < _SEVERITY_RANK.get(entry.severity, 9):
            entry.severity = f.severity

    gap_entries = sorted(
        [e for e in consolidated.values() if e.category == MAVERICK_GAP],
        key=lambda e: (_SEVERITY_RANK.get(e.severity, 9), -e.count),
    )
    user_entries = sorted(
        [e for e in consolidated.values() if e.category == USER_BEHAVIOR],
        key=lambda e: (_SEVERITY_RANK.get(e.severity, 9), -e.count),
    )

    # ---------------------------------------------------------------
    # Section 1: Maverick Plugin Gaps (primary focus)
    # ---------------------------------------------------------------
    lines.append("## Maverick Plugin Gaps")
    lines.append("")
    lines.append(
        "Improvements needed in Maverick's skills, agents, or hooks. "
        "Ranked by frequency — the most common gaps represent the "
        "highest-value improvements to implement."
    )
    lines.append("")

    if not gap_entries:
        lines.append("No Maverick plugin gaps detected.")
        lines.append("")
    else:
        for i, entry in enumerate(gap_entries, 1):
            sessions_str = _format_session_ids(entry.session_ids)
            lines.append(
                f"### {i}. {entry.title}"
            )
            lines.append("")
            lines.append(f"**Severity:** {entry.severity.upper()} | "
                         f"**Occurrences:** {entry.count} | "
                         f"**Sessions:** {sessions_str}")
            if entry.maverick_component:
                lines.append(f"**Component:** `{entry.maverick_component}`")
            lines.append("")
            lines.append(f"**Evidence:** {entry.detail}")
            lines.append("")
            lines.append(f"**Suggested fix:** {entry.recommendation}")
            lines.append("")

        # Maverick improvement roadmap — group by component
        lines.append("### Improvement Roadmap")
        lines.append("")
        lines.append(
            "Gaps grouped by Maverick component. Address components with "
            "the most findings first."
        )
        lines.append("")

        component_impact: dict[str, _ComponentImpact] = {}
        for entry in gap_entries:
            components = [
                c.strip() for c in entry.maverick_component.split(",")
            ] if entry.maverick_component else ["(unspecified)"]
            for comp in components:
                if comp not in component_impact:
                    component_impact[comp] = _ComponentImpact(comp)
                ci = component_impact[comp]
                ci.finding_count += entry.count
                ci.session_ids.update(entry.session_ids)
                ci.suggestions.append(entry.recommendation)
                if _SEVERITY_RANK.get(entry.severity, 9) < _SEVERITY_RANK.get(
                    ci.highest_severity, 9
                ):
                    ci.highest_severity = entry.severity

        sorted_components = sorted(
            component_impact.values(), key=lambda c: -c.finding_count
        )

        lines.append("| Component | Findings | Sessions | Severity |")
        lines.append("|-----------|----------|----------|----------|")
        for ci in sorted_components:
            lines.append(
                f"| `{ci.component}` "
                f"| {ci.finding_count} "
                f"| {len(ci.session_ids)} "
                f"| {ci.highest_severity.upper()} |"
            )
        lines.append("")

    # ---------------------------------------------------------------
    # Section 2: User Behavior (secondary, compact)
    # ---------------------------------------------------------------
    lines.append("## User Behavior")
    lines.append("")
    lines.append(
        "Findings where the user should change their workflow. "
        "Included for completeness — these are not actionable as "
        "Maverick improvements."
    )
    lines.append("")

    if not user_entries:
        lines.append("No user behavior findings.")
        lines.append("")
    else:
        lines.append("| # | Severity | Finding | Sessions |")
        lines.append("|---|----------|---------|----------|")
        for entry in user_entries:
            sessions_str = _format_session_ids(entry.session_ids)
            lines.append(
                f"| {entry.count} "
                f"| {entry.severity.upper()} "
                f"| {entry.title} "
                f"| {sessions_str} |"
            )
        lines.append("")

    # ---------------------------------------------------------------
    # Per-session summary (compact reference)
    # ---------------------------------------------------------------
    lines.append("## Per-Session Summary")
    lines.append("")
    lines.append("| Session | Date | Branch | Gaps | User | Critical |")
    lines.append("|---------|------|--------|------|------|----------|")
    for session, findings in reports:
        prefix = session.session_id[:8]
        date = session.created[:10] if session.created else "?"
        gaps = sum(1 for f in findings if f.category == MAVERICK_GAP)
        user = sum(1 for f in findings if f.category == USER_BEHAVIOR)
        critical = sum(1 for f in findings if f.severity == "critical")
        if not findings:
            continue  # skip clean sessions
        lines.append(
            f"| [{prefix}](./{prefix}/report.md) "
            f"| {date} "
            f"| {session.git_branch} "
            f"| {gaps} "
            f"| {user} "
            f"| {critical} |"
        )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Batch summary helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK: dict[str, int] = {"critical": 0, "warning": 1, "info": 2}


def _format_session_ids(session_ids: set[str], limit: int = 5) -> str:
    """Format a set of session ID prefixes for display."""
    sorted_ids = sorted(session_ids)
    result = ", ".join(sorted_ids[:limit])
    if len(sorted_ids) > limit:
        result += f" +{len(sorted_ids) - limit} more"
    return result


class _ConsolidatedFinding:
    """Accumulator for deduplicating findings across sessions."""

    __slots__ = (
        "analyzer", "severity", "category", "title", "detail",
        "recommendation", "maverick_component", "count", "session_ids",
    )

    def __init__(
        self,
        analyzer: str,
        severity: str,
        category: str,
        title: str,
        detail: str,
        recommendation: str,
        maverick_component: str,
    ) -> None:
        self.analyzer = analyzer
        self.severity = severity
        self.category = category
        self.title = title
        self.detail = detail
        self.recommendation = recommendation
        self.maverick_component = maverick_component
        self.count = 0
        self.session_ids: set[str] = set()


class _ComponentImpact:
    """Accumulator for grouping gaps by Maverick component."""

    __slots__ = (
        "component", "finding_count", "session_ids",
        "suggestions", "highest_severity",
    )

    def __init__(self, component: str) -> None:
        self.component = component
        self.finding_count = 0
        self.session_ids: set[str] = set()
        self.suggestions: list[str] = []
        self.highest_severity = "info"

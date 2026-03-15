"""Anti-pattern detection for Claude Code sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from maverick.session_review.parser import SessionData, ToolCall

# Finding categories
MAVERICK_GAP = "maverick_gap"
USER_BEHAVIOR = "user_behavior"


@dataclass
class Finding:
    analyzer: str
    severity: str  # "critical", "warning", "info"
    category: str  # MAVERICK_GAP or USER_BEHAVIOR
    title: str
    detail: str
    timestamp: str | None = None
    recommendation: str = ""
    # For maverick_gap findings: which skill/agent/hook needs changing
    maverick_component: str = ""


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_TEST_CMD_RE = re.compile(
    r"\b(pytest|jest|vitest|mocha|cargo\s+test|go\s+test|npm\s+test|yarn\s+test"
    r"|uv\s+run\s+pytest|make\s+test|bun\s+test)\b"
)
_LINT_CMD_RE = re.compile(
    r"\b(eslint|ruff|flake8|pylint|prettier|biome|clippy|golangci-lint"
    r"|npm\s+run\s+lint|yarn\s+lint|make\s+lint)\b"
)
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")

_CORRECTION_SIGNALS = re.compile(
    r"\b(no[,.]?\s|wrong|undo|revert|don'?t|instead|that'?s not|not what|go back"
    r"|try again|shouldn'?t|wasn'?t right|please fix|actually)\b",
    re.IGNORECASE,
)

_WORKFLOW_SKILLS = {"do-task-solo", "do-issue-solo", "do-issue-guided"}


def _bash_commands(session: SessionData) -> list[ToolCall]:
    """Return all Bash tool calls in order."""
    return [tc for tc in session.tool_calls if tc.tool_name == "Bash"]


def _maverick_loaded(session: SessionData) -> bool:
    """True if Maverick plugin was available in the session."""
    return any("maverick" in s.lower() or s.startswith("do-") or s.startswith("mav-")
               for s in session.skills_available)


def _workflow_invoked(session: SessionData) -> set[str]:
    """Return the set of Maverick workflow skills that were invoked."""
    return set(session.skills_invoked) & _WORKFLOW_SKILLS


# ---------------------------------------------------------------------------
# Mechanical Analyzers
# ---------------------------------------------------------------------------


def analyze_commit_without_verification(session: SessionData) -> list[Finding]:
    """Detect git commits not preceded by test or lint runs."""
    findings: list[Finding] = []
    bash_calls = _bash_commands(session)
    workflows = _workflow_invoked(session)
    mav_loaded = _maverick_loaded(session)

    unverified_count = 0

    for i, tc in enumerate(bash_calls):
        cmd = tc.input_data.get("command", "")
        if not _GIT_COMMIT_RE.search(cmd):
            continue

        # Look backwards for test/lint commands before this commit
        has_test = False
        has_lint = False
        for j in range(i - 1, max(i - 20, -1), -1):
            prev_cmd = bash_calls[j].input_data.get("command", "")
            if _TEST_CMD_RE.search(prev_cmd):
                has_test = True
            if _LINT_CMD_RE.search(prev_cmd):
                has_lint = True
            if _GIT_COMMIT_RE.search(prev_cmd):
                break

        if not has_test or not has_lint:
            unverified_count += 1

    if unverified_count == 0:
        return findings

    missing = "tests and linting" if unverified_count > 0 else "tests"

    if workflows:
        # Maverick workflow was active but didn't enforce verification
        findings.append(Finding(
            analyzer="CommitWithoutVerification",
            severity="critical",
            category=MAVERICK_GAP,
            title=f"Workflow did not enforce verification ({unverified_count} unverified commits)",
            detail=(
                f"Workflow skill(s) {', '.join(workflows)} were invoked but "
                f"{unverified_count} commit(s) were made without running {missing}. "
                f"The mav-local-verification dependency was not effective."
            ),
            recommendation=(
                "The workflow skills depend on mav-local-verification but it is "
                "advisory-only. Options: (1) add a PostToolUse hook on Bash that "
                "detects `git commit` and checks whether test/lint commands were run "
                "earlier in the session, blocking with a warning if not; (2) make "
                "the commit step in workflow skills conditional — require a prior "
                "verification pass before proceeding."
            ),
            maverick_component="mav-local-verification, workflow skills",
        ))
    elif mav_loaded:
        # Maverick was loaded but no workflow was used
        findings.append(Finding(
            analyzer="CommitWithoutVerification",
            severity="critical",
            category=MAVERICK_GAP,
            title=f"mav-local-verification did not prevent {unverified_count} unverified commits",
            detail=(
                f"{unverified_count} commit(s) were made without running {missing}. "
                f"The Maverick plugin was loaded but mav-local-verification is "
                f"advisory-only and had no enforcement mechanism."
            ),
            recommendation=(
                "mav-local-verification is a best-practice skill that relies on "
                "the LLM choosing to follow it. Add a PostToolUse hook on Bash "
                "that detects `git commit` and verifies test/lint execution in the "
                "session, or make it a non-optional step in the git-workflow skill."
            ),
            maverick_component="mav-local-verification",
        ))
    else:
        # Maverick not loaded — user behavior
        findings.append(Finding(
            analyzer="CommitWithoutVerification",
            severity="critical",
            category=USER_BEHAVIOR,
            title=f"{unverified_count} commits without running tests or linting",
            detail=(
                f"{unverified_count} commit(s) were made without running {missing}. "
                f"The Maverick plugin was not loaded for this session."
            ),
            recommendation=(
                "Load the Maverick plugin and use a workflow skill (do-task-solo, "
                "do-issue-solo) which includes verification steps."
            ),
        ))

    return findings


def analyze_file_churn(session: SessionData) -> list[Finding]:
    """Detect excessive edits to the same file."""
    findings: list[Finding] = []
    edit_counts: dict[str, int] = {}

    for tc in session.tool_calls:
        if tc.tool_name in ("Write", "Edit") and tc.file_path:
            edit_counts[tc.file_path] = edit_counts.get(tc.file_path, 0) + 1

    churned_files = [(p, c) for p, c in edit_counts.items() if c > 5]
    if not churned_files:
        return findings

    churned_files.sort(key=lambda x: -x[1])
    workflows = _workflow_invoked(session)
    mav_loaded = _maverick_loaded(session)

    file_list = "\n".join(
        f"- `{_short_path(p)}` ({c} edits)" for p, c in churned_files
    )

    if workflows:
        findings.append(Finding(
            analyzer="FileChurn",
            severity="warning",
            category=MAVERICK_GAP,
            title=f"High file churn despite workflow ({len(churned_files)} files with >5 edits)",
            detail=(
                f"A Maverick workflow was active but the following files had "
                f"excessive edits, suggesting trial-and-error coding:\n\n{file_list}"
            ),
            recommendation=(
                "The create-solution-design step in the workflow may not be "
                "producing sufficiently detailed designs, or the implementation "
                "phase is not following the design. Consider: (1) requiring the "
                "design to include per-file change descriptions before proceeding, "
                "(2) adding a mid-implementation checkpoint that compares progress "
                "against the design."
            ),
            maverick_component="mav-create-solution-design, workflow skills",
        ))
    elif mav_loaded:
        findings.append(Finding(
            analyzer="FileChurn",
            severity="warning",
            category=MAVERICK_GAP,
            title=f"High file churn — no workflow enforced design-first ({len(churned_files)} files)",
            detail=(
                f"The Maverick plugin was loaded but no workflow skill was invoked. "
                f"The following files had excessive edits:\n\n{file_list}"
            ),
            recommendation=(
                "When the plugin is loaded but no workflow is invoked, best-practice "
                "skills like mav-create-solution-design are not triggered. Consider "
                "making the non-invocable best-practice skills more assertive — e.g., "
                "the model-invocable description could instruct Claude to suggest a "
                "design step when it detects a multi-file task."
            ),
            maverick_component="mav-create-solution-design",
        ))
    else:
        findings.append(Finding(
            analyzer="FileChurn",
            severity="warning",
            category=USER_BEHAVIOR,
            title=f"High file churn ({len(churned_files)} files with >5 edits)",
            detail=f"The following files had excessive edits:\n\n{file_list}",
            recommendation=(
                "Design the solution before coding. Use a Maverick workflow "
                "skill which includes an upfront design step."
            ),
        ))

    return findings


def analyze_error_loops(session: SessionData) -> list[Finding]:
    """Detect repeated similar errors."""
    findings: list[Finding] = []
    error_texts: list[str] = []

    for err in session.errors:
        error_texts.append(err.get("error", "")[:200])

    # Group similar errors
    groups: list[list[int]] = []
    assigned: set[int] = set()

    for i, text_a in enumerate(error_texts):
        if i in assigned or not text_a.strip():
            continue
        group = [i]
        assigned.add(i)
        for j in range(i + 1, len(error_texts)):
            if j in assigned:
                continue
            if SequenceMatcher(None, text_a, error_texts[j]).ratio() > 0.6:
                group.append(j)
                assigned.add(j)
        groups.append(group)

    loop_groups = [g for g in groups if len(g) >= 3]
    if not loop_groups:
        return findings

    total_loops = len(loop_groups)
    total_errors = sum(len(g) for g in loop_groups)
    sample = error_texts[loop_groups[0][0]][:150]
    mav_loaded = _maverick_loaded(session)

    if mav_loaded:
        findings.append(Finding(
            analyzer="ErrorLoops",
            severity="warning",
            category=MAVERICK_GAP,
            title=f"Error loops not caught by mav-systematic-debugging ({total_loops} loops, {total_errors} errors)",
            detail=(
                f"{total_loops} error loop(s) detected ({total_errors} total repeated "
                f"errors). mav-systematic-debugging was available but did not "
                f"intervene.\n\nSample:\n```\n{sample}\n```"
            ),
            timestamp=session.errors[loop_groups[0][0]].get("timestamp"),
            recommendation=(
                "mav-systematic-debugging is a best-practice skill but nothing "
                "triggers it when errors repeat. Options: (1) add a PostToolUse "
                "hook on Bash that tracks recent errors and, after 3 similar "
                "failures, injects a system message instructing Claude to switch "
                "to the debugging skill; (2) add error-loop detection to the "
                "workflow skills so they pause implementation and invoke debugging."
            ),
            maverick_component="mav-systematic-debugging",
        ))
    else:
        findings.append(Finding(
            analyzer="ErrorLoops",
            severity="warning",
            category=USER_BEHAVIOR,
            title=f"Repeated errors ({total_loops} loops, {total_errors} errors)",
            detail=(
                f"{total_loops} error loop(s) detected. The same error pattern "
                f"appeared 3+ times without resolution.\n\n"
                f"Sample:\n```\n{sample}\n```"
            ),
            timestamp=session.errors[loop_groups[0][0]].get("timestamp"),
            recommendation=(
                "When errors repeat, stop and diagnose the root cause. Load the "
                "Maverick plugin for access to systematic-debugging guidance."
            ),
        ))

    return findings


def analyze_user_corrections(session: SessionData) -> list[Finding]:
    """Detect user messages that appear to correct Claude's work."""
    findings: list[Finding] = []
    corrections: list[dict] = []

    for msg in session.user_messages:
        text = msg.get("text", "")
        if _CORRECTION_SIGNALS.search(text) and len(text) > 5:
            corrections.append(msg)

    if len(corrections) >= 2:
        samples = [c["text"][:100] for c in corrections[:3]]
        findings.append(Finding(
            analyzer="UserCorrections",
            severity="warning",
            category=USER_BEHAVIOR,
            title=f"User corrections detected ({len(corrections)} messages)",
            detail=(
                f"The user appeared to correct or redirect Claude's work "
                f"{len(corrections)} times. Sample messages:\n\n"
                + "\n".join(f'- "{s}..."' for s in samples)
            ),
            recommendation=(
                "Use a Maverick workflow skill which includes a design/alignment "
                "step before implementation to reduce course corrections."
            ),
        ))

    return findings


def analyze_maverick_not_used(session: SessionData) -> list[Finding]:
    """Detect when Maverick skills were available but not invoked."""
    findings: list[Finding] = []

    if not session.skills_available:
        return findings

    mav_loaded = _maverick_loaded(session)
    maverick_invoked = [s for s in session.skills_invoked if "maverick" in s.lower()
                        or s.startswith("do-") or s.startswith("mav-")]

    if mav_loaded and not maverick_invoked:
        findings.append(Finding(
            analyzer="MaverickNotUsed",
            severity="info",
            category=USER_BEHAVIOR,
            title="Maverick plugin available but not used",
            detail=(
                "The Maverick plugin was loaded but no Maverick skills were "
                "invoked during this session."
            ),
            recommendation=(
                "Use a Maverick workflow skill (do-task-solo, do-issue-solo) "
                "for structured task execution with built-in verification and "
                "review steps."
            ),
        ))

    return findings


def analyze_maverick_partial_use(session: SessionData) -> list[Finding]:
    """Detect when Maverick was used but key steps were skipped."""
    findings: list[Finding] = []
    workflows = _workflow_invoked(session)

    if not workflows:
        return findings

    # Check if code-reviewer agent was dispatched
    agent_calls = [
        tc
        for tc in session.tool_calls
        if tc.tool_name == "Agent"
        and "code-review" in tc.input_data.get("subagent_type", "").lower()
    ]

    if not agent_calls:
        findings.append(Finding(
            analyzer="MaverickPartialUse",
            severity="warning",
            category=MAVERICK_GAP,
            title="Workflow completed without dispatching code-reviewer agent",
            detail=(
                f"Workflow skill(s) {', '.join(workflows)} were invoked "
                f"but no code-reviewer agent was dispatched. The review step "
                f"in the workflow was either skipped or not enforced."
            ),
            recommendation=(
                "The workflow skills instruct the LLM to dispatch the "
                "code-reviewer agent but this is advisory. Consider making the "
                "review step mandatory — e.g., the workflow could check for the "
                "agent dispatch before proceeding to PR creation, or a "
                "PreToolUse hook could block `gh pr create` unless a review "
                "agent has been dispatched in the session."
            ),
            maverick_component="workflow skills, agent-code-reviewer",
        ))

    # Check if verification was run
    bash_calls = _bash_commands(session)
    has_verification = any(
        _TEST_CMD_RE.search(tc.input_data.get("command", ""))
        or _LINT_CMD_RE.search(tc.input_data.get("command", ""))
        for tc in bash_calls
    )

    if not has_verification:
        findings.append(Finding(
            analyzer="MaverickPartialUse",
            severity="warning",
            category=MAVERICK_GAP,
            title="Workflow completed without any local verification",
            detail=(
                f"Workflow skill(s) {', '.join(workflows)} were invoked "
                f"but no test or lint commands were detected in the session."
            ),
            recommendation=(
                "mav-local-verification is a dependency of the workflow skills "
                "but it was not followed. The verification step needs stronger "
                "enforcement — either via a hook that blocks commits without "
                "prior test/lint runs, or by making the workflow skill explicitly "
                "run verification commands before the commit step."
            ),
            maverick_component="mav-local-verification, workflow skills",
        ))

    return findings


def analyze_project_skills_ignored(
    session: SessionData, project_skill_paths: list[str]
) -> list[Finding]:
    """Detect when project skills exist but weren't read during the session."""
    findings: list[Finding] = []

    if not project_skill_paths:
        return findings

    read_set = set(session.project_skills_read)
    ignored = [p for p in project_skill_paths if p not in read_set]

    if not ignored:
        return findings

    topics = [Path(p).parent.name for p in ignored]
    mav_loaded = _maverick_loaded(session)

    if mav_loaded:
        findings.append(Finding(
            analyzer="ProjectSkillsIgnored",
            severity="info",
            category=MAVERICK_GAP,
            title=f"Project skills not loaded by session ({len(ignored)} skills on disk)",
            detail=(
                "The following project-level skills exist on disk but were "
                "not read during this session:\n\n"
                + "\n".join(f"- {t} (`{p}`)" for t, p in zip(topics, ignored, strict=True))
            ),
            recommendation=(
                "Project skills generated by /upskill are not automatically "
                "loaded into sessions. The workflow skills should include a step "
                "that reads project skills from docs/maverick/skills/ at the "
                "start of execution, or a SessionStart hook could inject them "
                "into the system prompt."
            ),
            maverick_component="workflow skills, upskill",
        ))
    else:
        findings.append(Finding(
            analyzer="ProjectSkillsIgnored",
            severity="info",
            category=USER_BEHAVIOR,
            title=f"Project skills exist but weren't loaded ({len(ignored)} skills)",
            detail=(
                "The following project-level skills exist on disk but were "
                "not read during this session:\n\n"
                + "\n".join(f"- {t} (`{p}`)" for t, p in zip(topics, ignored, strict=True))
            ),
            recommendation=(
                "Load the Maverick plugin so that workflow skills can "
                "reference project-specific guidance."
            ),
        ))

    return findings


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------

_MECHANICAL_ANALYZERS = [
    analyze_commit_without_verification,
    analyze_file_churn,
    analyze_error_loops,
    analyze_user_corrections,
    analyze_maverick_not_used,
    analyze_maverick_partial_use,
    # analyze_project_skills_ignored requires extra args — called separately
]


def run_mechanical_analyzers(
    session: SessionData,
    project_skill_paths: list[str] | None = None,
) -> list[Finding]:
    """Run all mechanical (non-LLM) analyzers and return combined findings."""
    findings: list[Finding] = []
    for analyzer in _MECHANICAL_ANALYZERS:
        findings.extend(analyzer(session))

    # Project skills analyzer needs the on-disk paths
    if project_skill_paths is not None:
        findings.extend(analyze_project_skills_ignored(session, project_skill_paths))

    # Sort: maverick_gap first, then by severity
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    category_order = {MAVERICK_GAP: 0, USER_BEHAVIOR: 1}
    findings.sort(key=lambda f: (
        category_order.get(f.category, 9),
        severity_order.get(f.severity, 9),
    ))
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_path(path: str) -> str:
    """Shorten a file path for display."""
    parts = path.split("/")
    if len(parts) > 3:
        return "/".join(parts[-3:])
    return path

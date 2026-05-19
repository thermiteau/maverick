"""CLI sub-commands for do-issue-solo timing reports (#83).

Exposes a small command surface that the do-issue-solo skill body uses to
record timeline events during a run, plus a `generate` command that
renders the final markdown report.

Design notes:

- The rolling `maverick-task-progress` GitHub marker only carries the
  latest phase, so per-phase timestamps are not recoverable from
  GitHub. We capture phase boundaries (and other events) to a local
  JSONL file under `<main-repo>/.maverick/reports/`. The file is
  durable across worktree destruction because we resolve the **main**
  repo root via `git rev-parse --git-common-dir`.
- `append_event` is best-effort. A logging failure must never break a
  do-issue-solo run, so we swallow exceptions and warn on stderr.
- `render` is a pure function: it takes already-loaded data (events +
  git log + PR metadata + claim time) and returns a markdown string.
  The CLI command wires up I/O; tests exercise `render` directly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Event type values accepted by `maverick report log`. Unknown types
# parse and round-trip but are warned about and ignored at render time.
KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "phase-checkpoint",
        "subagent-start",
        "subagent-end",
        "skill-start",
        "skill-end",
        "question-start",
        "question-end",
        "commit",
        "resume",
    }
)

# Display labels for the report. Order mirrors do-issue-solo phases.
PHASE_LABELS: dict[str, str] = {
    "claimed": "Phase 0 — coordination",
    "design": "Phase 1-2 — understand + design",
    "tasks": "Phase 3 — create tasks",
    "branch": "Phase 4 — worktree + branch",
    "implement": "Phase 5 — execute tasks",
    "docs": "Phase 6 — documentation review",
    "security": "Phase 7 — cybersecurity review",
    "pr_open": "Phase 8 — open PR",
    "ci_green": "Phase 8 — CI green",
    "review": "Phase 9 — code review",
    "merged": "Phase 10 — merged",
    "complete": "Phase 10 — complete",
    "ejected": "Phase 11 — ejected",
}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _main_repo_root(cwd: Path | None = None) -> Path:
    """Resolve the main repo root, even when called from inside a worktree.

    `git rev-parse --git-common-dir` returns the **shared** `.git`
    directory for the main checkout (whereas `--git-dir` points at the
    worktree's `.git` file). The parent of the common dir is the main
    repo root. Falls back to ``cwd`` (or ``Path.cwd()``) when not in a
    git repo — keeps unit tests trivial.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        common_dir = Path(out.stdout.strip())
        if not common_dir.is_absolute():
            base = cwd or Path.cwd()
            common_dir = (base / common_dir).resolve()
        return common_dir.parent
    except (subprocess.CalledProcessError, FileNotFoundError):
        return cwd or Path.cwd()


def timeline_path(issue: int, repo_root: Path | None = None) -> Path:
    """Resolve the JSONL path for an issue's timeline."""
    root = repo_root or _main_repo_root()
    return root / ".maverick" / "reports" / f".do-issue-solo-{issue}.timeline.jsonl"


def report_path(issue: int, repo_root: Path | None = None) -> Path:
    """Resolve the rendered-report path for an issue."""
    root = repo_root or _main_repo_root()
    return root / ".maverick" / "reports" / f"do-issue-solo-{issue}.md"


# ---------------------------------------------------------------------------
# JSONL writer
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_event(
    issue: int,
    event: dict[str, Any],
    repo_root: Path | None = None,
) -> bool:
    """Append a single event to the issue's timeline JSONL.

    Returns True on success, False if the write failed for any reason.
    Never raises — logging must never break a do-issue-solo run.
    """
    try:
        path = timeline_path(issue, repo_root=repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(event)
        record.setdefault("ts", _now_iso())
        record.setdefault("issue", issue)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        return True
    except Exception as e:  # noqa: BLE001 — best-effort; warn-not-raise
        print(f"warning: report log append failed: {e}", file=sys.stderr)
        return False


def _validate_event(d: Any) -> bool:
    """Defensive validator. Returns False for malformed records (skipped
    at render time with a stderr warning)."""
    if not isinstance(d, dict):
        return False
    ts = d.get("ts")
    if not isinstance(ts, str) or not ts.endswith("Z"):
        return False
    if not isinstance(d.get("type"), str):
        return False
    return True


def load_timeline(path: Path) -> list[dict[str, Any]]:
    """Load and validate a JSONL timeline. Skips malformed lines."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            print(
                f"warning: skipping malformed JSON at {path}:{i}",
                file=sys.stderr,
            )
            continue
        if not _validate_event(d):
            print(
                f"warning: skipping invalid event at {path}:{i}: {raw[:80]}",
                file=sys.stderr,
            )
            continue
        events.append(d)
    events.sort(key=lambda e: e["ts"])
    return events


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _fmt_duration(seconds: float) -> str:
    """Human-readable duration. <1s shows '<1s'; otherwise compact form."""
    if seconds is None:
        return "—"
    secs = int(round(seconds))
    if secs < 1:
        return "<1s"
    if secs < 60:
        return f"{secs}s"
    minutes, secs = divmod(secs, 60)
    if minutes < 60:
        if secs == 0:
            return f"{minutes}m"
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _fmt_time(ts: str) -> str:
    """Render an ISO timestamp as YYYY-MM-DD HH:MM:SS (UTC).

    Including the date makes cross-day rows obvious instead of looking
    like time going backwards (#91).
    """
    try:
        return _parse_ts(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts


def _commit_rows(
    events: Sequence[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Extract commit events from the timeline as (sha, ts, subject) tuples.

    Phase attribution is intentionally not done here — `render` matches
    each commit's ts against the phase intervals from `_phase_intervals`.
    Doing it that way is correct under the do-issue-solo convention that
    a `phase-checkpoint` marks the **end** of its phase: a commit at
    time `t` belongs to the phase whose [start_ts, end_ts] contains `t`,
    i.e. the phase the agent was working on when the commit landed —
    not the previous phase that just finished.
    """
    out: list[tuple[str, str, str]] = []
    for e in events:
        if e.get("type") == "commit":
            out.append(
                (
                    str(e.get("sha", "")),
                    str(e.get("ts", "")),
                    str(e.get("subject", "")),
                )
            )
    return out


def _pair_intervals(
    events: Sequence[dict[str, Any]],
    start_type: str,
    end_type: str,
    key_field: str,
) -> list[tuple[str, str, str, str]]:
    """Pair start/end events by `key_field`. Returns
    [(key, start_ts, end_ts, owning_phase), ...]. Unmatched starts get
    end=start (zero duration); unmatched ends are ignored.
    """
    open_intervals: dict[str, tuple[str, str]] = {}
    out: list[tuple[str, str, str, str]] = []
    current_phase = ""
    for e in events:
        if e["type"] == "phase-checkpoint":
            current_phase = e.get("phase", "")
            continue
        if e["type"] == start_type:
            key = str(e.get(key_field, ""))
            open_intervals[key] = (e["ts"], current_phase)
        elif e["type"] == end_type:
            key = str(e.get(key_field, ""))
            opened = open_intervals.pop(key, None)
            if opened is None:
                continue
            start_ts, phase = opened
            out.append((key, start_ts, e["ts"], phase))
    for key, (start_ts, phase) in open_intervals.items():
        out.append((key, start_ts, start_ts, phase))
    return out


def _phase_intervals(
    events: Sequence[dict[str, Any]],
    claim_created_at: str | None,
) -> list[tuple[str, str, str]]:
    """Build [(phase, start_ts, end_ts), ...] from phase-checkpoint events.

    Each checkpoint marks the **end** of its phase. The first phase's
    start is `claim_created_at` (if available) or the first event's
    timestamp.
    """
    cps = [e for e in events if e["type"] == "phase-checkpoint"]
    if not cps:
        return []
    intervals: list[tuple[str, str, str]] = []
    prev_end = claim_created_at
    if not prev_end and events:
        prev_end = events[0]["ts"]
    for cp in cps:
        phase = cp.get("phase", "")
        start_ts = prev_end or cp["ts"]
        end_ts = cp["ts"]
        intervals.append((phase, start_ts, end_ts))
        prev_end = end_ts
    return intervals


def _seconds_between(start: str, end: str) -> float:
    try:
        return (_parse_ts(end) - _parse_ts(start)).total_seconds()
    except (ValueError, TypeError):
        return 0.0


def _facts_for_phase(
    phase: str,
    events: Sequence[dict[str, Any]],
    subagents: Sequence[tuple[str, str, str, str]],
    questions: Sequence[tuple[str, str, str, str]],
    skills: Sequence[tuple[str, str, str, str]],
) -> str:
    """Build the auto-generated facts portion of a phase's Activity cell."""
    pieces: list[str] = []
    for name, s, e, p in subagents:
        if p == phase:
            pieces.append(f"{name} ({_fmt_duration(_seconds_between(s, e))})")
    for name, s, e, p in skills:
        if p == phase:
            pieces.append(f"{name} ({_fmt_duration(_seconds_between(s, e))})")
    for topic, s, e, p in questions:
        if p == phase:
            pieces.append(f"question: {topic} ({_fmt_duration(_seconds_between(s, e))})")
    return " + ".join(pieces) if pieces else ""


def render(
    issue: int,
    events: Sequence[dict[str, Any]],
    commits: Sequence[dict[str, Any]] | None = None,
    pr: dict[str, Any] | None = None,
    claim_created_at: str | None = None,
) -> str:
    """Render the timing report to markdown.

    Pure function — all inputs are passed; no I/O. The CLI command
    `maverick report generate` fetches `commits`/`pr`/`claim_created_at`
    and calls this.

    - `events` — chronological timeline events (already validated/sorted).
    - `commits` — list of {sha, committed_at, subject} for Phase 5
      sub-rows. May be empty if branch info is unavailable.
    - `pr` — {created_at, merged_at, number} from `gh pr view`. May be None.
    - `claim_created_at` — ISO timestamp from the maverick-claim marker.
      Anchors the first phase's start.
    """
    if not events:
        return f"# Issue #{issue} — time breakdown\n\nNo timeline events recorded.\n"

    subagents = _pair_intervals(events, "subagent-start", "subagent-end", "name")
    questions = _pair_intervals(events, "question-start", "question-end", "topic")
    skills = _pair_intervals(events, "skill-start", "skill-end", "name")
    phases = _phase_intervals(events, claim_created_at)

    # Prefer event-sourced commits (deterministic, in-issue scope, per-phase
    # attribution). Fall back to git-log commits for older timelines that
    # pre-date #91. In both cases the renderer matches each commit's ts
    # against phase intervals — no hardcoded "implement" assumption.
    event_commits = _commit_rows(events)
    if event_commits:
        commit_rows = event_commits
        commits_from_events = True
    else:
        commit_rows = [
            (
                str(c.get("sha") or ""),
                str(c.get("committed_at") or ""),
                str(c.get("subject") or ""),
            )
            for c in (commits or [])
        ]
        commits_from_events = False

    first_ts = claim_created_at or events[0]["ts"]
    last_ts = events[-1]["ts"]
    total = _seconds_between(first_ts, last_ts)

    out: list[str] = []
    out.append(f"# Issue #{issue} — time breakdown")
    out.append("")
    commit_source = (
        "commit events in the timeline JSONL"
        if commits_from_events
        else "git-log fallback (legacy timeline)"
    )
    out.append(
        f"Wall-clock: **{_fmt_duration(total)}** from "
        f"{first_ts} to {last_ts}. All timestamps below are UTC. "
        "Phase boundaries come from `maverick task-progress` checkpoints; "
        f"commit sub-rows come from {commit_source}; "
        "PR open/merge timestamps come from `gh pr view`."
    )
    out.append("")
    out.append("## Phases")
    out.append("")
    out.append("| Phase | Activity | Start | End | Duration |")
    out.append("|---|---|---|---|---|")

    emitted_commit_indices: set[int] = set()
    for phase, s, e in phases:
        label = PHASE_LABELS.get(phase, phase)
        facts = _facts_for_phase(phase, events, subagents, questions, skills)
        activity = f"PLACEHOLDER — {facts}" if facts else "PLACEHOLDER"
        dur = _fmt_duration(_seconds_between(s, e))
        out.append(f"| {label} | {activity} | {_fmt_time(s)} | {_fmt_time(e)} | {dur} |")
        # Match each commit to the phase interval whose [start_ts, end_ts]
        # contains its ts. Each commit emits at most once — when a phase
        # repeats (e.g. implement → review → implement during recovery),
        # commits land under the first matching occurrence.
        phase_commits = [
            (i, sha, ts, subj)
            for i, (sha, ts, subj) in enumerate(commit_rows)
            if i not in emitted_commit_indices and ts and s <= ts <= e
        ]
        if phase_commits:
            prev_ts = s
            for i, sha, c_ts, subject in phase_commits:
                sub = subject.replace("|", "\\|")
                short_sha = sha[:7]
                dur_c = _fmt_duration(_seconds_between(prev_ts, c_ts)) if c_ts else "—"
                out.append(
                    f"| ↳ commit | `{short_sha}` — {sub} | "
                    f"{_fmt_time(prev_ts)} | {_fmt_time(c_ts)} | {dur_c} |"
                )
                prev_ts = c_ts
                emitted_commit_indices.add(i)

    out.append("")
    out.append("## Where the time actually went")
    out.append("")
    out.append("| Slice | Wall-clock |")
    out.append("|---|---|")

    subagent_total = sum(_seconds_between(s, e) for _, s, e, _ in subagents)
    skill_total = sum(_seconds_between(s, e) for _, s, e, _ in skills)
    question_total = sum(_seconds_between(s, e) for _, s, e, _ in questions)

    impl_total = 0.0
    if commit_rows and phases:
        for phase, s, e in phases:
            if phase != "implement":
                continue
            prev_ts = s
            for _sha, c_ts, _subj in commit_rows:
                if c_ts and s <= c_ts <= e:
                    impl_total += _seconds_between(prev_ts, c_ts)
                    prev_ts = c_ts
            break

    coord_total = total - subagent_total - skill_total - question_total - impl_total
    if coord_total < 0:
        coord_total = 0.0

    out.append(f"| Subagent compute | {_fmt_duration(subagent_total)} |")
    out.append(f"| Skill dispatches (do-cybersecurity-review etc.) | {_fmt_duration(skill_total)} |")
    out.append(f"| Implementation (commit-to-commit inside Phase 5) | {_fmt_duration(impl_total)} |")
    out.append(f"| User decision points | {_fmt_duration(question_total)} |")
    out.append(f"| Coordination / CLI / checkpoint overhead | {_fmt_duration(coord_total)} |")

    if pr:
        out.append("")
        out.append("## PR")
        out.append("")
        pr_num = pr.get("number")
        out.append(f"- PR #{pr_num}: opened {pr.get('created_at') or '?'} → merged {pr.get('merged_at') or '?'}")

    out.append("")
    out.append(
        "_Activity cells marked `PLACEHOLDER` are intended to be replaced "
        "with a one-sentence narrative of what happened in that phase. "
        "Re-run `maverick report generate` to regenerate from the timeline._"
    )
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# External data helpers (network/shell — not exercised in unit tests)
# ---------------------------------------------------------------------------


def _fetch_commits(branch: str | None, base: str | None) -> list[dict[str, Any]]:
    """Resolve commit log via `git log`. Returns [] on failure or when
    `branch`/`base` cannot be resolved."""
    if not branch:
        return []
    base = base or "origin/main"
    try:
        out = subprocess.run(
            ["git", "log", f"{base}..{branch}", "--reverse", "--pretty=%H|%cI|%s"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"warning: git log failed for {base}..{branch}: {e}", file=sys.stderr)
        return []
    commits: list[dict[str, Any]] = []
    for line in out.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, c_ts, subject = parts
        commits.append({"sha": sha, "committed_at": c_ts, "subject": subject})
    return commits


def _fetch_pr(repo: str, issue: int) -> dict[str, Any] | None:
    """Look up the PR for an issue via `gh pr list --search '<issue-ref>'`."""
    try:
        out = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "all",
                "--search",
                f"#{issue} in:body",
                "--json",
                "number,createdAt,mergedAt,state",
                "--limit",
                "5",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(out.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"warning: gh pr lookup failed: {e}", file=sys.stderr)
        return None
    if not data:
        return None
    # Prefer the most-recently-merged one; otherwise first.
    merged = [p for p in data if p.get("mergedAt")]
    chosen = merged[0] if merged else data[0]
    return {
        "number": chosen.get("number"),
        "created_at": chosen.get("createdAt"),
        "merged_at": chosen.get("mergedAt"),
    }


def _fetch_claim_created_at(repo: str, issue: int) -> str | None:
    """Read the claim marker's claimed_at field via `maverick gh-state read`."""
    try:
        from maverick import gh_state

        m = gh_state.latest_marker(repo, issue, "maverick-claim")
        if m and isinstance(m.payload, dict):
            return m.payload.get("claimed_at")
    except Exception as e:  # noqa: BLE001 — best-effort enrichment
        print(f"warning: claim marker lookup failed: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# CLI handlers
# ---------------------------------------------------------------------------


def _report_log(args: argparse.Namespace) -> int:
    event: dict[str, Any] = {"type": args.event_type}
    if args.name:
        event["name"] = args.name
    if args.topic:
        event["topic"] = args.topic
    if args.phase:
        event["phase"] = args.phase
    if args.sha:
        event["sha"] = args.sha
    if args.subject:
        event["subject"] = args.subject
    if args.task:
        event["task"] = args.task
    for raw in args.meta or []:
        if "=" not in raw:
            print(f"warning: ignoring --meta without '=': {raw}", file=sys.stderr)
            continue
        k, v = raw.split("=", 1)
        event[k] = v
    if args.event_type not in KNOWN_EVENT_TYPES:
        print(
            f"warning: unknown event type '{args.event_type}' (logging anyway)",
            file=sys.stderr,
        )
    append_event(args.issue, event)
    return 0


def _report_generate(args: argparse.Namespace) -> int:
    issue = args.issue
    repo_root = _main_repo_root()
    tpath = timeline_path(issue, repo_root=repo_root)
    events = load_timeline(tpath)
    if not events:
        print(f"no timeline data for issue {issue} at {tpath}", file=sys.stderr)
        return 2

    # New runs emit `commit` events into the timeline (#91), so the
    # git-log fallback is only consulted when no commit events were
    # recorded (e.g. older runs that pre-date the change).
    has_commit_events = any(e.get("type") == "commit" for e in events)
    if has_commit_events:
        commits: list[dict[str, Any]] = []
    else:
        branch = args.branch
        base = args.base or "origin/main"
        commits = _fetch_commits(branch, base)
    pr = _fetch_pr(args.repo, issue) if args.repo else None
    claim_ts = _fetch_claim_created_at(args.repo, issue) if args.repo else None

    md = render(
        issue=issue,
        events=events,
        commits=commits,
        pr=pr,
        claim_created_at=claim_ts,
    )

    out_path = Path(args.out) if args.out else report_path(issue, repo_root=repo_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(str(out_path))
    return 0


def _report_path(args: argparse.Namespace) -> int:
    print(str(timeline_path(args.issue)))
    return 0


# ---------------------------------------------------------------------------
# Subparser wiring
# ---------------------------------------------------------------------------


def build_subparsers(subparsers: argparse._SubParsersAction) -> None:
    r = subparsers.add_parser(
        "report",
        help="do-issue-solo timing reports (log events / render markdown)",
    )
    r_sub = r.add_subparsers(dest="report_cmd", required=True)

    p = r_sub.add_parser(
        "log",
        help="Append a timeline event for an issue (used by do-issue-solo)",
    )
    p.add_argument(
        "event_type",
        help="Event type, e.g. subagent-start, subagent-end, question-start",
    )
    p.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    p.add_argument("--name", help="Agent or skill name (subagent-* / skill-*)")
    p.add_argument("--topic", help="Question topic (question-*)")
    p.add_argument("--phase", help="Phase name (phase-checkpoint)")
    p.add_argument("--sha", help="Commit SHA (commit)")
    p.add_argument("--subject", help="Commit subject line (commit)")
    p.add_argument("--task", help="Task label (subagent-* / commit)")
    p.add_argument(
        "--meta",
        action="append",
        help="Extra key=value pair; may be repeated",
    )
    p.set_defaults(_handler=_report_log)

    p = r_sub.add_parser(
        "generate",
        help="Render the timing-report markdown to .maverick/reports/",
    )
    p.add_argument("repo", help="owner/repo (used to look up PR + claim metadata)")
    p.add_argument("issue", type=int)
    p.add_argument(
        "--branch",
        help="Feature branch (defaults to current branch via `git rev-parse`)",
    )
    p.add_argument(
        "--base",
        help="Base branch for git-log range (default: origin/main)",
    )
    p.add_argument("--out", help="Override output path (default: .maverick/reports/...)")
    p.set_defaults(_handler=_report_generate)

    p = r_sub.add_parser(
        "path",
        help="Print the resolved timeline JSONL path for an issue",
    )
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_report_path)


def dispatch(args: argparse.Namespace) -> int:
    handler = getattr(args, "_handler", None)
    if handler is None:
        print("no handler wired", file=sys.stderr)
        return 1
    return int(handler(args) or 0)


__all__ = [
    "KNOWN_EVENT_TYPES",
    "PHASE_LABELS",
    "append_event",
    "build_subparsers",
    "dispatch",
    "load_timeline",
    "render",
    "report_path",
    "timeline_path",
]

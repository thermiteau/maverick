"""CLI sub-commands for the Maverick workflow report (schema v1).

The Maverick workflow report records what happened during a `do-*` skill
run: which phases ran, which agents and skills were dispatched, which
commits landed, and what notes the agent left. The on-disk
representation is a JSONL timeline; the rendered Markdown report is a
pure function of that timeline.

## Schema (v1)

Every row in the timeline JSONL is a typed event conforming to
`Event` below. The schema is closed: unknown `action`/`phase`/`outcome`
values are rejected at write time. The renderer rejects malformed rows
at read time (and skips them with a warning).

Each row carries:
- `schema_version` — bump on any breaking change
- `action` — the discriminator; one of `ACTIONS`
- `start_ts` — wall-clock at which the CLI was invoked
- `end_ts` — wall-clock at interval close (`null` for atomic events
  and for intervals whose `end` has not yet fired)
- system fields — `instance_id`, `maverick_version`
- run fields — `issue`, `maverick_skill` (inherited from the
  `run-start` row), `maverick_agent`, `phase`
- outcome — `success | failure | blocked | skipped` (present only on
  rows whose `end_ts` is set)
- optional payload — `notes`, `sha`, `subject`

## Intervals are one row per interval

Interval events (`agent-dispatch`, `skill-dispatch`, `question`) cover
work that has duration. The CLI is called twice — `begin` and `end` —
but only **one** row is written, by the `end` call. The `begin` call
records `start_ts` to a transient sidecar (`.do-issue-solo-N.pending.json`)
in the reports dir; `end` reads it back, writes the final row with both
timestamps, and removes the pending entry.

This design honours two constraints:
1. JSONL rows are one-per-interval, with both timestamps in the same
   row (matches the rendered table's columns directly).
2. All timestamps come from `datetime.now(UTC)` at CLI invocation —
   never from repo events (`git log %cI`, ref ages, etc.). SHA and
   subject can come from git; the timestamp cannot.

If a `begin` is never closed (crash, eject, abort), the pending entry
remains as a diagnostic; `maverick report verify` surfaces dangling
intervals.

## Atomic events

`run-start`, `phase-boundary`, `commit`, `note`, `resume` are atomic —
one CLI call writes one row with `end_ts = null`. `phase-boundary`
rows mark the **end** of a phase; the renderer computes phase intervals
from successive `phase-boundary` rows.

## Authoritativeness

The JSONL is the authoritative record. The rendered Markdown is a pure
function of the JSONL — re-running `maverick report generate` produces
the same output. Narrative (agent commentary on what happened in a
phase) is emitted into the JSONL as `note` rows during the run, not
added post-hoc to the rendered file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from maverick.cli import _get_version
from maverick.coordinator import claude_session_id, instance_id
from maverick.gh_state import TASK_PROGRESS_PHASES
from maverick.session_review.parser import (
    UsageRecord,
    iter_session_usage,
    sessions_for_run,
)

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------


SCHEMA_VERSION = 1

# All actions the writer accepts. Atomic actions never carry `end_ts`;
# interval actions are written by `end` with both timestamps populated.
ACTIONS: frozenset[str] = frozenset(
    {
        "run-start",
        "phase-boundary",
        "agent-dispatch",
        "skill-dispatch",
        "commit",
        "question",
        "note",
        "resume",
    }
)

ATOMIC_ACTIONS: frozenset[str] = frozenset(
    {"run-start", "phase-boundary", "commit", "note", "resume"}
)

INTERVAL_ACTIONS: frozenset[str] = frozenset(
    {"agent-dispatch", "skill-dispatch", "question"}
)

OUTCOMES: frozenset[str] = frozenset({"success", "failure", "blocked", "skipped"})

PHASES: frozenset[str] = frozenset(TASK_PROGRESS_PHASES)

# Display split for the rendered Phases table.
# `PHASE_NUMBER` is the value of the table's `Phase` column.
# `PHASE_DESCRIPTOR` becomes the `<action> — <descriptor>` suffix in the
# Maverick Action column. Splitting the two lets us repeat the phase
# number across multiple rows for the same phase (one per action) without
# duplicating the descriptor on every row.
PHASE_NUMBER: dict[str, str] = {
    "claimed": "Phase 0",
    "design": "Phase 1-2",
    "tasks": "Phase 3",
    "branch": "Phase 4",
    "implement": "Phase 5",
    "docs": "Phase 6",
    "security": "Phase 7",
    "pr_open": "Phase 8",
    "ci_green": "Phase 8",
    "review": "Phase 9",
    "merged": "Phase 10",
    "complete": "Phase 10",
    "ejected": "Phase 11",
}

PHASE_DESCRIPTOR: dict[str, str] = {
    "claimed": "coordination",
    "design": "understand + design",
    "tasks": "create tasks",
    "branch": "worktree + branch",
    "implement": "execute tasks",
    "docs": "documentation review",
    "security": "cybersecurity review",
    "pr_open": "open PR",
    "ci_green": "CI green",
    "review": "code review",
    "merged": "merged",
    "complete": "complete",
    "ejected": "ejected",
}

# Kept for backwards compatibility with external callers that imported the
# combined labels. Internal render code uses the split dicts above.
PHASE_LABELS: dict[str, str] = {
    p: f"{PHASE_NUMBER[p]} — {PHASE_DESCRIPTOR[p]}" for p in PHASE_NUMBER
}

# Last-resort label used when no explicit `--llm`, no `MAVERICK_LLM` env
# var, and no prior run-start row carries a value. Generic on purpose:
# we know it's some Claude Code session but not which model.
FALLBACK_LLM: str = "claude-code"


class _RequiredEvent(TypedDict):
    """Fields present on every well-formed event."""

    schema_version: int
    action: str
    start_ts: str
    instance_id: str
    issue: int
    maverick_version: str
    phase: str


class Event(_RequiredEvent, total=False):
    """A single row in the timeline JSONL.

    Inherits the required fields from `_RequiredEvent` and adds optional
    payload that is meaningful only for some actions.

    `maverick_skill` is the **outer** /do-* skill driving the whole run
    (inherited from the `run-start` row on every event).
    `dispatched_skill` is the **inner** skill this row dispatches —
    required on `skill-dispatch` rows, optional on `agent-dispatch` rows
    when the agent is invoked under a named skill (e.g. agent-tech-docs-writer
    operating under do-docs).
    `llm` is the model identifier running this row's work. It is
    populated on every row at write time via the fallback chain in
    `_current_llm()` and can be overridden per-row with `--llm` so
    multi-model runs (e.g. Opus orchestrator + Sonnet subagents) render
    correctly. Optional in the schema so older v1 rows that lack it
    still load.
    """

    end_ts: str | None
    maverick_skill: str | None
    maverick_agent: str | None
    dispatched_skill: str | None
    llm: str | None
    outcome: str | None
    notes: str | None
    sha: str | None
    subject: str | None
    claude_session_id: str | None


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _main_repo_root(cwd: Path | None = None) -> Path:
    """Resolve the main repo root, even when called from inside a worktree.

    `git rev-parse --git-common-dir` returns the shared `.git` directory
    for the main checkout (whereas `--git-dir` points at the worktree's
    `.git` file). The parent of the common dir is the main repo root.
    Falls back to ``cwd`` when not in a git repo.
    """
    import subprocess as _sp

    try:
        out = _sp.run(
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
    except (_sp.CalledProcessError, FileNotFoundError):
        return cwd or Path.cwd()


def timeline_path(issue: int, repo_root: Path | None = None) -> Path:
    """JSONL timeline for an issue."""
    root = repo_root or _main_repo_root()
    return root / ".maverick" / "reports" / f".do-issue-solo-{issue}.timeline.jsonl"


def pending_path(issue: int, repo_root: Path | None = None) -> Path:
    """Sidecar holding open intervals (begin called, end not yet)."""
    root = repo_root or _main_repo_root()
    return root / ".maverick" / "reports" / f".do-issue-solo-{issue}.pending.json"


def report_path(issue: int, repo_root: Path | None = None) -> Path:
    """Rendered Markdown report for an issue."""
    root = repo_root or _main_repo_root()
    return root / ".maverick" / "reports" / f"do-issue-solo-{issue}.md"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC time in `YYYY-MM-DDTHH:MM:SSZ` form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _seconds_between(start: str, end: str) -> int:
    """Whole-seconds duration between two ISO timestamps."""
    try:
        return int(round((_parse_ts(end) - _parse_ts(start)).total_seconds()))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class SchemaError(ValueError):
    """Raised when an event violates the v1 schema."""


def _validate(event: dict[str, Any]) -> None:
    """Validate an event against the v1 schema. Raise SchemaError on any issue.

    Used both at write time (reject early) and at load time (skip + warn).
    """
    if not isinstance(event, dict):
        raise SchemaError("event must be a dict")

    sv = event.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise SchemaError(f"schema_version must be {SCHEMA_VERSION}, got {sv!r}")

    action = event.get("action")
    if action not in ACTIONS:
        raise SchemaError(
            f"action must be one of {sorted(ACTIONS)}, got {action!r}"
        )

    start_ts = event.get("start_ts")
    if not isinstance(start_ts, str) or not start_ts.endswith("Z"):
        raise SchemaError(f"start_ts must be ISO-8601 UTC string ending 'Z', got {start_ts!r}")

    end_ts = event.get("end_ts")
    if action in ATOMIC_ACTIONS:
        if end_ts is not None:
            raise SchemaError(f"atomic action {action!r} must not carry end_ts")
    elif action in INTERVAL_ACTIONS:
        if end_ts is None:
            # Interval rows are written by `end`, so end_ts should always be
            # set. A null end_ts here means a malformed row (or one that the
            # write path forgot to populate). Reject.
            raise SchemaError(f"interval action {action!r} requires end_ts")
        if not isinstance(end_ts, str) or not end_ts.endswith("Z"):
            raise SchemaError(f"end_ts must be ISO-8601 UTC string, got {end_ts!r}")

    phase = event.get("phase")
    if phase not in PHASES:
        raise SchemaError(f"phase must be one of {sorted(PHASES)}, got {phase!r}")

    outcome = event.get("outcome")
    if outcome is not None and outcome not in OUTCOMES:
        raise SchemaError(f"outcome must be one of {sorted(OUTCOMES)}, got {outcome!r}")
    if action in INTERVAL_ACTIONS and outcome is None:
        raise SchemaError(f"interval action {action!r} requires outcome")

    for required in ("instance_id", "issue", "maverick_version"):
        if required not in event or event[required] in (None, ""):
            raise SchemaError(f"missing required field {required!r}")

    if action == "commit":
        if not event.get("sha"):
            raise SchemaError("commit action requires sha")
        if not event.get("subject"):
            raise SchemaError("commit action requires subject")

    if action == "note":
        if not event.get("notes"):
            raise SchemaError("note action requires notes text")

    if action == "run-start":
        if not event.get("maverick_skill"):
            raise SchemaError("run-start action requires maverick_skill")

    if action == "skill-dispatch" and not event.get("dispatched_skill"):
        raise SchemaError("skill-dispatch action requires dispatched_skill")


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


def _system_fields(issue: int) -> dict[str, Any]:
    """Fields the writer fills in on every row."""
    return {
        "schema_version": SCHEMA_VERSION,
        "instance_id": instance_id(),
        "issue": issue,
        "maverick_version": _get_version(),
    }


def append_event(
    event: dict[str, Any],
    repo_root: Path | None = None,
) -> bool:
    """Validate and append an event to its issue's timeline JSONL.

    Returns True on success, False on validation or I/O failure. Errors
    are written to stderr but do not raise — a logging failure must never
    break a workflow run.
    """
    try:
        _validate(event)
    except SchemaError as e:
        print(f"warning: report event rejected: {e}", file=sys.stderr)
        return False
    try:
        path = timeline_path(event["issue"], repo_root=repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
        return True
    except OSError as e:
        print(f"warning: report log append failed: {e}", file=sys.stderr)
        return False


def load_timeline(path: Path) -> list[Event]:
    """Load a timeline JSONL. Skips malformed lines with a warning."""
    if not path.exists():
        return []
    events: list[Event] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            print(f"warning: skipping malformed JSON at {path}:{i}", file=sys.stderr)
            continue
        try:
            _validate(d)
        except SchemaError as e:
            print(f"warning: skipping invalid event at {path}:{i}: {e}", file=sys.stderr)
            continue
        events.append(d)
    events.sort(key=lambda e: e["start_ts"])
    return events


# ---------------------------------------------------------------------------
# Pending-interval sidecar (begin/end pairing)
# ---------------------------------------------------------------------------


def _pending_key(action: str, **identifiers: str | None) -> str:
    """Compose a key that uniquely identifies an open interval.

    do-issue-solo dispatches sequentially, so (action, identifier) is
    unique while the interval is open. The identifier is the most
    specific name field for the action — `agent` for agent-dispatch,
    `skill` for skill-dispatch, `topic` for question.
    """
    ident = identifiers.get("agent") or identifiers.get("skill") or identifiers.get("topic") or ""
    return f"{action}:{ident}"


def _read_pending(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: pending file unreadable ({e}); starting fresh", file=sys.stderr)
        return {}


def _write_pending(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Skill lookup (latest run-start row)
# ---------------------------------------------------------------------------


def _current_skill(issue: int, repo_root: Path | None = None) -> str | None:
    """Read the most recent `run-start` row for this issue."""
    events = load_timeline(timeline_path(issue, repo_root=repo_root))
    for e in reversed(events):
        if e.get("action") == "run-start":
            return e.get("maverick_skill")
    return None


_AGENT_MODEL_CACHE: dict[str, str | None] | None = None


def _agent_pinned_model(agent: str) -> str | None:
    """Look up an agent's pinned ``model`` from its AgentConfig.

    Returns the generation label (``"claude-sonnet"``/``"claude-opus"``/
    ``"claude-haiku"``) for agents whose config.py sets a ``model`` pin,
    or ``None`` if the agent inherits its model from the orchestrator.

    The registry's discovery scan is cached on first call; subsequent
    lookups are dict reads. Plugin agents are static at runtime, so a
    cache miss only happens on the very first event written per process.

    A best-effort fallback: any exception during discovery (missing
    template dir on an unusual install, broken config.py during a
    bisect, etc.) returns ``None`` so the caller falls through to the
    orchestrator's model rather than crashing the write.
    """
    global _AGENT_MODEL_CACHE
    if _AGENT_MODEL_CACHE is None:
        try:
            from maverick.registry import discover_agents

            _AGENT_MODEL_CACHE = {
                cfg.name: (f"claude-{cfg.model}" if cfg.model else None)
                for cfg in discover_agents()
            }
        except Exception:  # noqa: BLE001 — best-effort
            _AGENT_MODEL_CACHE = {}
    return _AGENT_MODEL_CACHE.get(agent)


def _current_llm(
    explicit: str | None = None,
    issue: int | None = None,
    repo_root: Path | None = None,
    agent: str | None = None,
    skill_name: str | None = None,
) -> str:
    """Resolve the LLM identifier for a row being written.

    Resolution chain, in priority order:

    1. Explicit ``--llm`` on the CLI call.
    2. ``MAVERICK_LLM`` env var (workflow-wide override).
    3. **Agent rows only:** explicit per-agent override in the merged
       ``llm.agents`` config block (user or repo), if present.
    4. **Agent rows only:** the agent's own pinned model from its
       ``AgentConfig.model`` field. This is the source of truth — the
       same value that gets rendered into the agent's frontmatter and
       therefore the same generation Claude Code actually dispatches.
    5. ``llm.default`` from the merged config (defaults → user → repo).
    6. Latest ``run-start`` row's ``llm`` for this issue (inherits
       across CLI invocations even if the orchestrator never opened
       the project config — useful for one-off runs).
    7. The ``FALLBACK_LLM`` literal.

    ``skill_name`` is accepted for API compatibility but no longer
    drives resolution: skills are instruction blocks loaded into the
    orchestrator's session and cannot run on a different model from it
    (#108). Skill-dispatch rows therefore land in step 5 (orchestrator
    default) unless an explicit per-skill override is set in the
    config's ``llm.skills`` block.
    """
    import os as _os

    if explicit:
        return explicit
    env_val = _os.environ.get("MAVERICK_LLM")
    if env_val:
        return env_val

    try:
        from maverick.config import read_llm_config
        llm_cfg = read_llm_config()
    except Exception:  # noqa: BLE001 — best-effort; fall through on any error
        llm_cfg = None

    if agent:
        if llm_cfg is not None and agent in llm_cfg["agents"]:
            return llm_cfg["agents"][agent]
        pinned = _agent_pinned_model(agent)
        if pinned:
            return pinned

    if skill_name and llm_cfg is not None and skill_name in llm_cfg["skills"]:
        return llm_cfg["skills"][skill_name]

    if llm_cfg is not None and llm_cfg["default"]:
        return llm_cfg["default"]

    if issue is not None:
        try:
            events = load_timeline(timeline_path(issue, repo_root=repo_root))
        except Exception:  # noqa: BLE001 — best-effort fallback lookup
            events = []
        for e in reversed(events):
            run_llm = e.get("llm")
            if e.get("action") == "run-start" and run_llm:
                return str(run_llm)
    return FALLBACK_LLM


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def _fmt_ts(ts: str | None) -> str:
    """Render an ISO timestamp as `YYYY-MM-DD HH:MM:SS` (UTC). `—` for None."""
    if not ts:
        return "—"
    try:
        return _parse_ts(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts


def _phase_intervals(events: Sequence[Event]) -> list[tuple[str, str, str]]:
    """Build [(phase, start_ts, end_ts), ...] from phase-boundary rows.

    Each phase-boundary row marks the **end** of its phase. The first
    phase's start is the first event's `start_ts`.
    """
    phase_boundaries = [e for e in events if e.get("action") == "phase-boundary"]
    if not phase_boundaries:
        return []
    out: list[tuple[str, str, str]] = []
    prev_end = events[0]["start_ts"] if events else None
    for pb in phase_boundaries:
        phase = pb.get("phase", "")
        start_ts = prev_end or pb["start_ts"]
        end_ts = pb["start_ts"]
        out.append((phase, start_ts, end_ts))
        prev_end = end_ts
    return out


def _phase_for_ts(ts: str, phases: Sequence[tuple[str, str, str]]) -> str | None:
    """Which phase interval contains this timestamp?"""
    for phase, s, e in phases:
        if s <= ts <= e:
            return phase
    return None


def _append_token_section(
    out: list[str],
    phases: Sequence[tuple[str, str, str]],
    usage: Sequence[UsageRecord],
) -> None:
    """Append the `## Token usage` section to `out`.

    Bins `usage` records into the supplied phase intervals via
    `_phase_for_ts` and emits a per-phase table plus a grand-total
    footer row. No-ops if `usage` is empty, if there are no phases, or
    if no record falls inside any phase interval — keeping the rendered
    Markdown unchanged for runs without session data.
    """
    if not usage or not phases:
        return

    sums: dict[str, list[int]] = {p: [0, 0, 0, 0] for p, _, _ in phases}
    matched = False
    for rec in usage:
        phase = _phase_for_ts(rec.timestamp, phases)
        if phase is None:
            continue
        matched = True
        bucket = sums[phase]
        bucket[0] += rec.input_tokens
        bucket[1] += rec.output_tokens
        bucket[2] += rec.cache_read_input_tokens
        bucket[3] += rec.cache_creation_input_tokens

    if not matched:
        return

    out.append("## Token usage")
    out.append("")
    out.append(
        "| Phase | Input | Output | Cache read | Cache create | Total |"
    )
    out.append("|---|---:|---:|---:|---:|---:|")

    grand = [0, 0, 0, 0]
    for phase, _, _ in phases:
        inp, outp, cr, cc = sums[phase]
        if inp == outp == cr == cc == 0:
            continue
        total = inp + outp + cr + cc
        label = PHASE_NUMBER.get(phase, phase)
        out.append(
            f"| {label} | {inp:,} | {outp:,} | {cr:,} | {cc:,} | {total:,} |"
        )
        grand[0] += inp
        grand[1] += outp
        grand[2] += cr
        grand[3] += cc

    g_total = sum(grand)
    out.append(
        f"| **Total** | **{grand[0]:,}** | **{grand[1]:,}** | "
        f"**{grand[2]:,}** | **{grand[3]:,}** | **{g_total:,}** |"
    )
    out.append("")


def _outcome_label(events: Sequence[Event]) -> str:
    """The run's overall outcome: PASS | FAIL-eject | BLOCKED | IN-PROGRESS."""
    phases_seen = {e.get("phase") for e in events if e.get("action") == "phase-boundary"}
    if "complete" in phases_seen:
        return "PASS"
    if "ejected" in phases_seen:
        return "FAIL-eject"
    return "IN-PROGRESS"


def render(
    issue: int,
    events: Sequence[Event],
    pr: dict[str, Any] | None = None,
    usage: Sequence[UsageRecord] = (),
) -> str:
    """Render the timeline as a Markdown workflow report.

    Pure function. The CLI handler loads `events` and optionally fetches
    `pr` metadata plus Claude Code `usage` records; this function is
    fully deterministic given its inputs.

    The Phases table emits one row per (phase, action) tuple in wall-clock
    order within each phase. A `phase-boundary` row appears only when no
    agent/skill dispatch fired in that phase. Commit rows show only the
    end timestamp (commits are atomic events).

    When `usage` is non-empty, a `## Token usage` section is inserted
    between `## Total Time` and `## Phases` with per-phase + grand-total
    rows. Records outside every phase interval are silently dropped (they
    represent pre-`run-start` noise or pause-window activity on resumed
    runs).
    """
    if not events:
        return f"# Maverick workflow report\n\nNo timeline events recorded for issue #{issue}.\n"

    root_skill = _current_skill_from_events(events) or "(unknown)"
    version = events[-1].get("maverick_version", "?")
    instances: list[str] = []
    seen: set[str] = set()
    for e in events:
        iid = e.get("instance_id")
        if iid and iid not in seen:
            seen.add(iid)
            instances.append(iid)

    phases = _phase_intervals(events)
    first_ts = events[0]["start_ts"]
    last_ts = phases[-1][2] if phases else events[-1].get("end_ts") or events[-1]["start_ts"]
    total_seconds = _seconds_between(first_ts, last_ts)

    out: list[str] = []
    out.append("# Maverick workflow report")
    out.append("")
    out.append(f"- Issue: #{issue}")
    if pr:
        pr_num = pr.get("number")
        merged_at = pr.get("merged_at")
        if pr_num is not None:
            line = f"- PR:    #{pr_num}"
            if merged_at:
                line += f" (merged {merged_at})"
            out.append(line)
    out.append(f"- Skill: {root_skill}")
    out.append(f"- Outcome: {_outcome_label(events)}")
    out.append(f"- Maverick: {version}")
    llms = _distinct_llms(events)
    if llms:
        if len(llms) == 1:
            out.append(f"- LLM: {llms[0]}")
        else:
            out.append(f"- LLMs: {', '.join(llms)}")
    if instances:
        if len(instances) == 1:
            out.append(f"- Instance: {instances[0]}")
        else:
            tail = ", ".join(f"{i} (resumed)" for i in instances[1:])
            out.append(f"- Instances: {instances[0]}, {tail}")
    out.append("")
    out.append("_All timestamps UTC. Durations in seconds._")
    out.append("")

    out.append("## Total Time")
    out.append("")
    out.append(f"seconds: {total_seconds}")
    out.append("")

    _append_token_section(out, phases, usage)

    out.append("## Phases")
    out.append("")
    out.append(
        "| Phase | LLM | Maverick Root Skill | Maverick Sub Agent | "
        "Maverick Skill | Start | End | Duration | Maverick Action |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")

    for phase, p_start, p_end in phases:
        rows = _rows_for_phase(events, phase, p_start, p_end)
        for row in rows:
            phase_number = PHASE_NUMBER.get(phase, phase)
            out.append(
                f"| {phase_number} | {row.llm} | {root_skill} | "
                f"{row.sub_agent} | {row.skill} | "
                f"{row.start} | {row.end} | {row.duration} | "
                f"{row.action} |"
            )

    out.append("")
    out.append("## Analysis")
    out.append("")
    _append_analysis_table(out, events, total_seconds)

    notes = [e for e in events if e.get("action") == "note"]
    if notes:
        out.append("")
        out.append("_Notes from the run, in order:_")
        out.append("")
        for n in notes:
            phase = n.get("phase", "")
            text = n.get("notes", "") or ""
            label = (
                f"{PHASE_NUMBER[phase]} — {PHASE_DESCRIPTOR[phase]}"
                if phase in PHASE_NUMBER
                else phase
            )
            out.append(f"- {label}: {text}")
    out.append("")
    return "\n".join(out)


@dataclass(frozen=True)
class _PhaseRow:
    """One rendered row of the Phases table."""

    llm: str
    sub_agent: str
    skill: str
    start: str
    end: str
    duration: str
    action: str
    sort_key: str  # the ts to order this row by within the phase


def _rows_for_phase(
    events: Sequence[Event],
    phase: str,
    phase_start: str,
    phase_end: str,
) -> list[_PhaseRow]:
    """Build the in-order list of rendered rows for a single phase.

    Rules:
    - For each interval event with `phase == this phase`, emit a row
      with both timestamps + duration.
    - For each commit event with `phase == this phase`, emit a row with
      only `end_ts` (commits are atomic).
    - If no **interval dispatch** fired in this phase, also emit a
      `phase-boundary` row spanning the whole phase. Commits alone
      don't suppress the boundary row — they describe what landed, not
      what was being done.
    - Sort by wall-clock so dispatches, commits, and boundary appear in
      the order they actually happened.
    """
    descriptor = PHASE_DESCRIPTOR.get(phase, phase)
    rows: list[_PhaseRow] = []
    has_dispatch = False
    for e in events:
        if e.get("phase") != phase:
            continue
        action = e.get("action")
        if action in INTERVAL_ACTIONS:
            has_dispatch = True
            start_ts = e["start_ts"]
            end_ts = e.get("end_ts") or start_ts
            rows.append(
                _PhaseRow(
                    llm=e.get("llm") or FALLBACK_LLM,
                    sub_agent=e.get("maverick_agent") or "—",
                    skill=e.get("dispatched_skill") or "—",
                    start=_fmt_ts(start_ts),
                    end=_fmt_ts(end_ts),
                    duration=str(_seconds_between(start_ts, end_ts)),
                    action=f"{action} — {descriptor}",
                    sort_key=start_ts,
                )
            )
        elif action == "commit":
            ts = e["start_ts"]
            sha = (e.get("sha") or "")[:7]
            subject = (e.get("subject") or "").replace("|", "\\|")
            rows.append(
                _PhaseRow(
                    llm=e.get("llm") or FALLBACK_LLM,
                    sub_agent="—",
                    skill="—",
                    start="—",
                    end=_fmt_ts(ts),
                    duration="—",
                    action=f"commit {sha} — {subject}",
                    sort_key=ts,
                )
            )
    if not has_dispatch:
        # Choose the llm for the synthesized phase-boundary row: prefer
        # the latest event in this phase that carries an llm; fall back
        # to FALLBACK_LLM.
        boundary_llm = FALLBACK_LLM
        for e in events:
            row_llm = e.get("llm")
            if e.get("phase") == phase and row_llm:
                boundary_llm = str(row_llm)
        rows.append(
            _PhaseRow(
                llm=boundary_llm,
                sub_agent="—",
                skill="—",
                start=_fmt_ts(phase_start),
                end=_fmt_ts(phase_end),
                duration=str(_seconds_between(phase_start, phase_end)),
                action=f"phase-boundary — {descriptor}",
                sort_key=phase_start,
            )
        )
    rows.sort(key=lambda r: r.sort_key)
    return rows


def _current_skill_from_events(events: Sequence[Event]) -> str | None:
    for e in reversed(events):
        if e.get("action") == "run-start":
            return e.get("maverick_skill")
    return None


def _distinct_llms(events: Sequence[Event]) -> list[str]:
    """Distinct llm values in first-seen order. Empty list if none recorded."""
    seen: set[str] = set()
    out: list[str] = []
    for e in events:
        llm = e.get("llm")
        if llm and llm not in seen:
            seen.add(llm)
            out.append(llm)
    return out


def _append_analysis_table(out: list[str], events: Sequence[Event], total: int) -> None:
    """The 'where the time went' summary table, in seconds.

    The slices are mutually exclusive by construction:
    - Agent dispatches / Skill dispatches / User decision points are the
      summed durations of those interval rows.
    - Implementation = wall-clock inside the implement phase that is NOT
      covered by any dispatch (so do-code / do-test wrapping moves time
      from this slice into Skill dispatches rather than double-counting).
    - Coordination = total minus everything above.
    """
    agent_total = sum(
        _seconds_between(e["start_ts"], e.get("end_ts") or e["start_ts"])
        for e in events
        if e.get("action") == "agent-dispatch"
    )
    skill_total = sum(
        _seconds_between(e["start_ts"], e.get("end_ts") or e["start_ts"])
        for e in events
        if e.get("action") == "skill-dispatch"
    )
    question_total = sum(
        _seconds_between(e["start_ts"], e.get("end_ts") or e["start_ts"])
        for e in events
        if e.get("action") == "question"
    )
    impl_total = _unwrapped_implementation_seconds(events)
    coord_total = max(0, total - agent_total - skill_total - question_total - impl_total)

    out.append("| Slice | Seconds |")
    out.append("|---|---|")
    out.append(f"| Agent dispatches | {agent_total} |")
    out.append(f"| Skill dispatches | {skill_total} |")
    out.append(f"| Implementation (unwrapped, inside Phase 5) | {impl_total} |")
    out.append(f"| User decision points | {question_total} |")
    out.append(f"| Coordination / CLI / checkpoint overhead | {coord_total} |")


def _unwrapped_implementation_seconds(events: Sequence[Event]) -> int:
    """Wall-clock inside the implement phase not covered by a dispatch.

    With do-code / do-test wrapping in Phase 5, most implementation time
    sits inside skill-dispatch intervals — that work is already counted
    in `Skill dispatches`. This slice surfaces the *uninstrumented* time
    inside Phase 5 (e.g. the gap between a `do-code` close and the next
    `do-code` open, or between the last `do-code` close and the phase's
    end). Computed as the implement phase's wall-clock minus the sum of
    dispatch durations that fall inside it.
    """
    phases = _phase_intervals(events)
    implement = next((p for p in phases if p[0] == "implement"), None)
    if not implement:
        return 0
    _, impl_start, impl_end = implement
    impl_total = _seconds_between(impl_start, impl_end)
    dispatched = 0
    for e in events:
        if e.get("action") not in INTERVAL_ACTIONS:
            continue
        if e.get("phase") != "implement":
            continue
        end_ts = e.get("end_ts")
        if not end_ts:
            continue
        dispatched += _seconds_between(e["start_ts"], end_ts)
    return max(0, impl_total - dispatched)


# ---------------------------------------------------------------------------
# External data helpers
# ---------------------------------------------------------------------------


def _fetch_pr(repo: str, issue: int) -> dict[str, Any] | None:
    """Look up the PR for an issue via `gh pr list --search '<issue-ref>'`."""
    import subprocess as _sp

    try:
        out = _sp.run(
            [
                "gh", "pr", "list", "--repo", repo, "--state", "all",
                "--search", f"#{issue} in:body",
                "--json", "number,createdAt,mergedAt,state",
                "--limit", "5",
            ],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(out.stdout)
    except (_sp.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"warning: gh pr lookup failed: {e}", file=sys.stderr)
        return None
    if not data:
        return None
    merged = [p for p in data if p.get("mergedAt")]
    chosen = merged[0] if merged else data[0]
    return {
        "number": chosen.get("number"),
        "created_at": chosen.get("createdAt"),
        "merged_at": chosen.get("mergedAt"),
    }


# ---------------------------------------------------------------------------
# CLI handlers
# ---------------------------------------------------------------------------


def _build_base(
    args: argparse.Namespace,
    action: str,
    *,
    agent: str | None = None,
    skill_name: str | None = None,
) -> dict[str, Any]:
    """Shared scaffold for every write — system fields, schema, action.

    ``agent`` and ``skill_name`` give context to the LLM resolver so that
    per-agent / per-skill config overrides apply. They default to None
    for atomic events that don't have an agent/skill identity (run-start,
    phase-boundary, commit, note, resume).
    """
    base = _system_fields(args.issue)
    base["action"] = action
    base["start_ts"] = _now_iso()
    skill = getattr(args, "skill", None)
    if not skill:
        skill = _current_skill(args.issue)
    if skill:
        base["maverick_skill"] = skill
    base["llm"] = _current_llm(
        explicit=getattr(args, "llm", None),
        issue=args.issue,
        agent=agent,
        skill_name=skill_name,
    )
    return base


def _report_run_start(args: argparse.Namespace) -> int:
    """Mark the start of a workflow run. Subsequent rows inherit `maverick_skill`."""
    event = _build_base(args, "run-start")
    event["maverick_skill"] = args.skill  # explicit even though base set it
    event["phase"] = args.phase or "claimed"
    sid = claude_session_id()
    if sid:
        event["claude_session_id"] = sid
    append_event(event)
    return 0


def _report_phase(args: argparse.Namespace) -> int:
    """Mark the end of a phase (atomic phase-boundary event)."""
    event = _build_base(args, "phase-boundary")
    event["phase"] = args.phase
    append_event(event)
    return 0


def _report_begin(args: argparse.Namespace) -> int:
    """Open an interval. Records start_ts to the pending sidecar."""
    if args.action not in INTERVAL_ACTIONS:
        print(f"error: `begin` only valid for interval actions: {sorted(INTERVAL_ACTIONS)}", file=sys.stderr)
        return 2
    pending = _read_pending(pending_path(args.issue))
    key = _pending_key(args.action, agent=args.agent, skill=args.skill_name, topic=args.topic)
    if key in pending:
        print(f"warning: `begin {args.action}` overwriting still-open interval ({key})", file=sys.stderr)
    pending[key] = {
        "start_ts": _now_iso(),
        "phase": args.phase,
        "agent": args.agent,
        "skill_name": args.skill_name,
        "topic": args.topic,
    }
    _write_pending(pending_path(args.issue), pending)
    return 0


def _report_end(args: argparse.Namespace) -> int:
    """Close an interval. Writes the final row with start_ts + end_ts + outcome."""
    if args.action not in INTERVAL_ACTIONS:
        print(f"error: `end` only valid for interval actions: {sorted(INTERVAL_ACTIONS)}", file=sys.stderr)
        return 2
    pending = _read_pending(pending_path(args.issue))
    key = _pending_key(args.action, agent=args.agent, skill=args.skill_name, topic=args.topic)
    open_iv = pending.pop(key, None)
    if open_iv is None:
        print(f"warning: `end {args.action}` with no matching open begin ({key}); skipping row", file=sys.stderr)
        return 1
    _write_pending(pending_path(args.issue), pending)

    agent_ctx = args.agent or open_iv.get("agent")
    inner_skill = args.skill_name or open_iv.get("skill_name")
    event = _build_base(args, args.action, agent=agent_ctx, skill_name=inner_skill)
    event["start_ts"] = open_iv["start_ts"]
    event["end_ts"] = _now_iso()
    event["phase"] = args.phase or open_iv.get("phase") or ""
    event["outcome"] = args.outcome
    if agent_ctx:
        event["maverick_agent"] = agent_ctx
    if inner_skill:
        event["dispatched_skill"] = inner_skill
    if args.notes:
        event["notes"] = args.notes
    append_event(event)
    return 0


def _report_commit(args: argparse.Namespace) -> int:
    event = _build_base(args, "commit")
    event["phase"] = args.phase
    event["sha"] = args.sha
    event["subject"] = args.subject
    append_event(event)
    return 0


def _report_note(args: argparse.Namespace) -> int:
    event = _build_base(args, "note")
    event["phase"] = args.phase
    event["notes"] = args.text
    append_event(event)
    return 0


def _report_resume(args: argparse.Namespace) -> int:
    event = _build_base(args, "resume")
    event["phase"] = args.phase
    sid = claude_session_id()
    if sid:
        event["claude_session_id"] = sid
    append_event(event)
    return 0


def _report_generate(args: argparse.Namespace) -> int:
    issue = args.issue
    repo_root = _main_repo_root()
    tpath = timeline_path(issue, repo_root=repo_root)
    events = load_timeline(tpath)
    if not events:
        print(f"no timeline data for issue {issue} at {tpath}", file=sys.stderr)
        return 2

    pr = _fetch_pr(args.repo, issue) if args.repo else None
    usage = _gather_usage(events, repo_root, no_tokens=args.no_tokens)
    md = render(issue=issue, events=events, pr=pr, usage=usage)

    out_path = Path(args.out) if args.out else report_path(issue, repo_root=repo_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(str(out_path))
    return 0


def _gather_usage(
    events: Sequence[Event], repo_root: Path, no_tokens: bool = False
) -> list[UsageRecord]:
    """Collect Claude Code token-usage records for a run.

    Returns an empty list when `no_tokens` is set, when no event carries
    a `claude_session_id`, or when the discovery / read path fails for
    any reason — token rendering is best-effort, matching the
    write-path's "logging failure never breaks a run" stance.
    """
    if no_tokens:
        return []
    sids = sorted({
        sid for e in events
        if (sid := e.get("claude_session_id"))
    })
    if not sids:
        return []
    try:
        records: list[UsageRecord] = []
        for path in sessions_for_run(str(repo_root), sids):
            records.extend(iter_session_usage(path))
        return records
    except OSError as e:
        print(f"warning: token-usage discovery failed: {e}", file=sys.stderr)
        return []


def _report_verify(args: argparse.Namespace) -> int:
    """Lint a timeline JSONL against the v1 schema."""
    tpath = timeline_path(args.issue)
    if not tpath.exists():
        print(f"no timeline at {tpath}", file=sys.stderr)
        return 2
    errors = 0
    for i, raw in enumerate(tpath.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"{tpath}:{i}: malformed JSON: {e}")
            errors += 1
            continue
        try:
            _validate(d)
        except SchemaError as e:
            print(f"{tpath}:{i}: schema violation: {e}")
            errors += 1
    pending = _read_pending(pending_path(args.issue))
    if pending:
        print(f"warning: {len(pending)} dangling open interval(s) in {pending_path(args.issue)}:")
        for key, state in pending.items():
            print(f"  {key} — started {state.get('start_ts')}")
    if errors:
        print(f"\n{errors} schema violation(s) found")
        return 1
    print("ok")
    return 0


def _report_path(args: argparse.Namespace) -> int:
    print(str(timeline_path(args.issue)))
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


def _add_issue(p: argparse.ArgumentParser) -> None:
    p.add_argument("--issue", type=int, required=True, help="GitHub issue number")


def _add_phase(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument(
        "--phase",
        required=required,
        choices=sorted(PHASES),
        help="Phase the event belongs to (closed enum)",
    )


def _add_llm(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--llm",
        help=(
            "LLM identifier for this row (e.g. claude-opus-4-7). Optional; "
            "falls back to MAVERICK_LLM env var, then to the latest run-start's "
            "llm, then to the literal 'claude-code'."
        ),
    )


def build_subparsers(subparsers: argparse._SubParsersAction) -> None:
    r = subparsers.add_parser(
        "report",
        help="Maverick workflow report (log events / render markdown)",
    )
    r_sub = r.add_subparsers(dest="report_cmd", required=True)

    # run-start
    p = r_sub.add_parser("run-start", help="Mark the start of a workflow run")
    p.add_argument("skill", help="The /do-* skill driving this run (e.g. do-issue-solo)")
    _add_issue(p)
    _add_phase(p, required=False)
    _add_llm(p)
    p.set_defaults(_handler=_report_run_start)

    # phase
    p = r_sub.add_parser("phase", help="Mark the end of a phase (phase-boundary event)")
    _add_phase(p)
    _add_issue(p)
    _add_llm(p)
    p.set_defaults(_handler=_report_phase)

    # begin
    p = r_sub.add_parser("begin", help="Open an interval (agent-dispatch / skill-dispatch / question)")
    p.add_argument("action", choices=sorted(INTERVAL_ACTIONS))
    _add_issue(p)
    _add_phase(p)
    p.add_argument("--agent", help="Agent name (for agent-dispatch)")
    p.add_argument("--skill-name", dest="skill_name", help="Skill name (for skill-dispatch)")
    p.add_argument("--topic", help="Question topic (for question)")
    _add_llm(p)
    p.set_defaults(_handler=_report_begin)

    # end
    p = r_sub.add_parser("end", help="Close an interval opened by `begin`")
    p.add_argument("action", choices=sorted(INTERVAL_ACTIONS))
    _add_issue(p)
    p.add_argument("--outcome", required=True, choices=sorted(OUTCOMES))
    p.add_argument("--phase", choices=sorted(PHASES))
    p.add_argument("--agent")
    p.add_argument("--skill-name", dest="skill_name")
    p.add_argument("--topic")
    p.add_argument("--notes")
    _add_llm(p)
    p.set_defaults(_handler=_report_end)

    # commit
    p = r_sub.add_parser("commit", help="Log a commit landing")
    _add_issue(p)
    _add_phase(p)
    p.add_argument("--sha", required=True)
    p.add_argument("--subject", required=True)
    _add_llm(p)
    p.set_defaults(_handler=_report_commit)

    # note
    p = r_sub.add_parser("note", help="Record narrative for the report's Analysis section")
    _add_issue(p)
    _add_phase(p)
    _add_llm(p)
    p.add_argument("--text", required=True)
    p.set_defaults(_handler=_report_note)

    # resume
    p = r_sub.add_parser("resume", help="Mark a workflow resume after a crash")
    _add_issue(p)
    _add_phase(p)
    _add_llm(p)
    p.set_defaults(_handler=_report_resume)

    # generate
    p = r_sub.add_parser("generate", help="Render the timing-report markdown")
    p.add_argument("repo", help="owner/repo (used to look up PR metadata)")
    p.add_argument("issue", type=int)
    p.add_argument("--out", help="Override output path")
    p.add_argument(
        "--no-tokens",
        action="store_true",
        help=(
            "Skip the Token usage section even when CLAUDE_CODE_SESSION_ID was "
            "captured. Useful for offline rendering or when ~/.claude/projects "
            "is not available."
        ),
    )
    p.set_defaults(_handler=_report_generate)

    # verify
    p = r_sub.add_parser("verify", help="Lint a timeline JSONL against the schema")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_report_verify)

    # path
    p = r_sub.add_parser("path", help="Print the timeline JSONL path for an issue")
    p.add_argument("issue", type=int)
    p.set_defaults(_handler=_report_path)


def dispatch(args: argparse.Namespace) -> int:
    handler = getattr(args, "_handler", None)
    if handler is None:
        print("no handler wired", file=sys.stderr)
        return 1
    return int(handler(args) or 0)


__all__ = [
    "ACTIONS",
    "ATOMIC_ACTIONS",
    "INTERVAL_ACTIONS",
    "OUTCOMES",
    "PHASES",
    "PHASE_LABELS",
    "SCHEMA_VERSION",
    "Event",
    "SchemaError",
    "append_event",
    "build_subparsers",
    "dispatch",
    "load_timeline",
    "pending_path",
    "render",
    "report_path",
    "timeline_path",
]

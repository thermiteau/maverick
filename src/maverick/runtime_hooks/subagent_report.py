"""Subagent/skill lifecycle handler — automatic report-interval bookkeeping.

Replaces most of the `report begin`/`report end` ceremony that
do-issue-solo used to carry as numbered prose steps (the modernization
review's H5: ~20 bookkeeping calls interleaved 1:1 with the real work,
routinely dropped under context pressure):

- **subagent start** → `report begin agent-dispatch --agent <name>`
- **subagent stop**  → `report end --auto --if-action agent-dispatch
  --if-agent <name> --outcome success` (the dispatch completed; workflow
  failures are recorded by their own events — eject, phase, notes)
- **skill tool call** → `report begin skill-dispatch --skill-name <name>`
  for the tracked inner workflow skills. Skill invocation has no paired
  completion event, so closing stays a single explicit obligation in the
  workflow: `report end --auto --outcome <success|failure>` — and
  `report generate` flushes anything dangling as outcome=unknown.

Guard: the handler acts only when this instance holds **exactly one**
active claim in ~/.maverick/active-claims.json — i.e. a do-issue-solo/do-epic
autonomous run, which is exactly where bookkeeping gets dropped. In
interactive sessions and other projects it is a silent no-op.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from maverick.runtime_hooks.adapters import HookInput
from maverick.runtime_hooks.claims import my_claims

TIMEOUT_SECONDS = 30

#: Inner workflow skills whose dispatch the report tracks. Entry-point
#: skills (do-issue-*, do-epic) are runs, not dispatches.
TRACKED_SKILLS = {
    "do-code",
    "do-test",
    "do-docs",
    "do-cybersecurity-review",
    "do-pullrequest-review",
}


def active_claim(
    env: dict[str, str],
    registry: Path | None = None,
    id_path: Path | None = None,
) -> tuple[str, int] | None:
    """(repo, issue) when this instance holds exactly one claim, else None."""
    mine = [
        c
        for c in my_claims(env, registry, id_path)
        if isinstance(c.get("repo"), str) and isinstance(c.get("issue"), int)
    ]
    if len(mine) != 1:
        return None  # zero: not autonomous; several: ambiguous — stay silent
    return mine[0]["repo"], mine[0]["issue"]


def report_args(
    event: HookInput,
    env: dict[str, str],
    registry: Path | None = None,
    id_path: Path | None = None,
) -> list[str] | None:
    """Decide the report command for one hook event (None = no-op)."""
    claim = active_claim(env, registry, id_path)
    if claim is None:
        return None
    _repo, issue = claim

    if event.event in ("subagent_start", "subagent_stop"):
        agent = event.agent
        if not agent or not agent.startswith("agent-"):
            return None  # only Maverick's own agents are tracked
        if event.event == "subagent_start":
            return ["begin", "agent-dispatch", "--issue", str(issue), "--agent", agent]
        return [
            "end",
            "--auto",
            "--issue",
            str(issue),
            "--if-action",
            "agent-dispatch",
            "--if-agent",
            agent,
            "--outcome",
            "success",
        ]

    if event.event == "tool_call" and event.tool and event.tool.kind == "skill":
        if event.tool.skill not in TRACKED_SKILLS:
            return None
        return [
            "begin",
            "skill-dispatch",
            "--issue",
            str(issue),
            "--skill-name",
            event.tool.skill,
        ]

    return None


def run_report(args: list[str]) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "maverick.cli", "report", *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:
        pass  # bookkeeping must never break the session


def handle(event: HookInput, env: dict[str, str]) -> None:
    args = report_args(event, env)
    if args:
        run_report(args)

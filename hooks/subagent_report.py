#!/usr/bin/env python3
"""Subagent/skill lifecycle hook — automatic report-interval bookkeeping.

Replaces most of the `report begin`/`report end` ceremony that
do-issue-solo used to carry as numbered prose steps (the modernization
review's H5: ~20 bookkeeping calls interleaved 1:1 with the real work,
routinely dropped under context pressure):

- **SubagentStart** → `report begin agent-dispatch --agent <name>`
- **SubagentStop**  → `report end --auto --if-action agent-dispatch
  --if-agent <name> --outcome success` (the dispatch completed; workflow
  failures are recorded by their own events — eject, phase, notes)
- **PreToolUse on the Skill tool** → `report begin skill-dispatch
  --skill-name <name>` for the tracked inner workflow skills. The Skill
  tool has no paired completion event, so closing stays a single explicit
  obligation in the workflow: `report end --auto --outcome
  <success|failure>` — and `report generate` flushes anything dangling as
  outcome=unknown.

Guard: the hook acts only when this instance holds **exactly one** active
claim in ~/.maverick/active-claims.json — i.e. a do-issue-solo/do-epic
autonomous run, which is exactly where bookkeeping gets dropped. In
interactive sessions and other projects it is a silent no-op.

Engineering contract (install_check.py standard): pure stdlib, never
crashes the session, always exits 0.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CLAIMS_REGISTRY = Path("~/.maverick/active-claims.json").expanduser()
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


def _instance_id(env: dict[str, str]) -> str | None:
    """Mirror coordinator.instance_id()'s env derivation (read-only)."""
    explicit = env.get("MAVERICK_INSTANCE_ID")
    if explicit:
        return explicit
    session = env.get("CLAUDE_CODE_SESSION_ID") or env.get("CLAUDE_SESSION_ID")
    if session:
        return hashlib.sha256(session.encode("utf-8")).hexdigest()[:10]
    return None


def active_claim(env: dict[str, str], registry: Path = CLAIMS_REGISTRY) -> tuple[str, int] | None:
    """(repo, issue) when this instance holds exactly one claim, else None."""
    instance = _instance_id(env)
    if not instance:
        return None
    try:
        claims = json.loads(registry.read_text()).get("claims", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    mine = [
        c
        for c in claims
        if isinstance(c, dict)
        and c.get("instance_id") == instance
        and isinstance(c.get("repo"), str)
        and isinstance(c.get("issue"), int)
    ]
    if len(mine) != 1:
        return None  # zero: not autonomous; several: ambiguous — stay silent
    return mine[0]["repo"], mine[0]["issue"]


def _agent_name(payload: dict) -> str | None:
    """Extract the subagent name from the hook payload, defensively."""
    for key in ("agent_type", "subagent_type", "agent_name", "agent", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _cli_command() -> list[str] | None:
    if shutil.which("maverick"):
        return ["maverick"]
    if shutil.which("uv") and Path("pyproject.toml").is_file():
        return ["uv", "run", "maverick"]
    return None


def _run_report(args: list[str]) -> None:
    cli = _cli_command()
    if cli is None:
        return
    try:
        subprocess.run(
            [*cli, "report", *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except Exception:
        pass  # bookkeeping must never break the session


def handle(payload: dict, env: dict[str, str], registry: Path = CLAIMS_REGISTRY) -> list[str] | None:
    """Decide the report command for one hook payload (None = no-op).

    Pure decision logic, separated from subprocess execution for tests.
    """
    claim = active_claim(env, registry)
    if claim is None:
        return None
    _repo, issue = claim
    event = payload.get("hook_event_name") or ""

    if event == "SubagentStart":
        agent = _agent_name(payload)
        if not agent or not agent.startswith("agent-"):
            return None  # only Maverick's own agents are tracked
        return ["begin", "agent-dispatch", "--issue", str(issue), "--agent", agent]

    if event == "SubagentStop":
        agent = _agent_name(payload)
        if not agent or not agent.startswith("agent-"):
            return None
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

    if event == "PreToolUse" and payload.get("tool_name") == "Skill":
        tool_input = payload.get("tool_input") or {}
        skill = str(tool_input.get("skill") or "").split(":")[-1]
        if skill not in TRACKED_SKILLS:
            return None
        return [
            "begin",
            "skill-dispatch",
            "--issue",
            str(issue),
            "--skill-name",
            skill,
        ]

    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    try:
        args = handle(payload, dict(os.environ))
    except Exception:
        return 0
    if args:
        _run_report(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

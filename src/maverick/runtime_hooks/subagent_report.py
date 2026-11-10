"""Subagent/skill lifecycle handler — automatic report-interval bookkeeping.

Replaces most of the `report begin`/`report end` ceremony that
do-issue-solo used to carry as numbered prose steps (the modernization
review's H5: ~20 bookkeeping calls interleaved 1:1 with the real work,
routinely dropped under context pressure):

- **agent dispatch** (Agent tool call) → `report begin agent-dispatch
  --agent <name>`
- **agent return** (Agent tool result) → `report end --auto --if-action agent-dispatch
  --if-agent <name> --outcome success` (the dispatch completed; workflow
  failures are recorded by their own events — eject, phase, notes)
- **skill tool call** → `report begin skill-dispatch --skill-name <name>`
  for the tracked inner workflow skills. Skill invocation has no paired
  completion event, so closing stays a single explicit obligation in the
  workflow: `report end --auto --outcome <success|failure>` — and
  `report generate` flushes anything dangling as outcome=unknown.

Attribution — which issue's timeline a row belongs to — is resolved per
event, in order:

1. A ``maverick-issue: <N>`` marker in the dispatch prompt (Agent tool) or
   the skill args, when <N> is one of this instance's claims. The workflow
   skills put this marker in every dispatch they make.
2. The only claim this instance holds.
3. The issue number in the git branch at the event's working directory
   (``<type>/<N>-<desc>``), when <N> is one of this instance's claims.

A do-epic session holds the epic's claim plus one per in-flight story, so
the old "exactly one claim, else stay silent" guard recorded nothing for
any epic run (every report showed zero dispatches). Steps 1 and 3 attribute
those dispatches to the right story. With no claims at all — interactive
sessions, other projects — the handler stays a silent no-op.

Agent dispatches are tracked on the Agent tool call (PreToolUse opens,
PostToolUse closes) because only the tool call carries the prompt, and so
the marker. SubagentStart/SubagentStop are still handled for plugin hook
configs that predate this, attributed by steps 2–3.

Each handled event also records the session's real model (see
:mod:`maverick.runtime_hooks.session_model`) so report rows stop carrying
a hard-coded model id.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from maverick.runtime_hooks import session_model
from maverick.runtime_hooks.adapters import HookInput
from maverick.runtime_hooks.claims import instance_id, my_claims

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


#: ``maverick-issue: 123`` / ``maverick-issue: #123`` anywhere in the text.
ISSUE_MARKER_RE = re.compile(r"maverick-issue:\s*#?(\d+)", re.IGNORECASE)

#: Story branches are ``<type>/<issue>-<desc>`` (mav-git-workflow).
_BRANCH_ISSUE_RE = re.compile(r"^[^/]+/(\d+)(?:-|$)")


def claimed_issues(
    env: dict[str, str],
    registry: Path | None = None,
    id_path: Path | None = None,
) -> list[int]:
    """Issues this instance holds claims on, in registry order."""
    return [
        c["issue"]
        for c in my_claims(env, registry, id_path)
        if isinstance(c.get("repo"), str) and isinstance(c.get("issue"), int)
    ]


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
        return None
    return mine[0]["repo"], mine[0]["issue"]


def marker_issue(text: str) -> int | None:
    """The issue named by a ``maverick-issue:`` marker in *text*, if any."""
    m = ISSUE_MARKER_RE.search(text or "")
    return int(m.group(1)) if m else None


def branch_issue(cwd: Path) -> int | None:
    """The issue number in the branch checked out at *cwd*, if any."""
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    m = _BRANCH_ISSUE_RE.match(out.stdout.strip())
    return int(m.group(1)) if m else None


def resolve_issue(
    event: HookInput,
    env: dict[str, str],
    registry: Path | None = None,
    id_path: Path | None = None,
) -> int | None:
    """Which claimed issue this event belongs to (None = not attributable)."""
    mine = claimed_issues(env, registry, id_path)
    if not mine:
        return None
    marked = marker_issue(event.tool.text if event.tool else "")
    if marked is not None and marked in mine:
        return marked
    if len(mine) == 1:
        return mine[0]
    cwd = event.tool.cwd if event.tool else event.cwd
    from_branch = branch_issue(cwd)
    if from_branch is not None and from_branch in mine:
        return from_branch
    return None  # several claims and nothing ties the event to one


def _end_agent(issue: int, agent: str) -> list[str]:
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


def report_args(
    event: HookInput,
    env: dict[str, str],
    registry: Path | None = None,
    id_path: Path | None = None,
) -> list[str] | None:
    """Decide the report command for one hook event (None = no-op)."""
    tool = event.tool
    agent: str | None = None
    opening = False
    if event.event in ("subagent_start", "subagent_stop"):
        agent, opening = event.agent, event.event == "subagent_start"
    elif tool is not None and tool.kind == "agent":
        if event.event == "tool_done" and tool.background:
            return None  # returned at launch, not completion; generate flushes it
        agent, opening = tool.agent, event.event == "tool_call"

    if event.event in ("subagent_start", "subagent_stop") or (
        tool is not None and tool.kind == "agent"
    ):
        if not agent or not agent.startswith("agent-"):
            return None  # only Maverick's own agents are tracked
        issue = resolve_issue(event, env, registry, id_path)
        if issue is None:
            return None
        if opening:
            return ["begin", "agent-dispatch", "--issue", str(issue), "--agent", agent]
        return _end_agent(issue, agent)

    if event.event == "tool_call" and tool is not None and tool.kind == "skill":
        if tool.skill not in TRACKED_SKILLS:
            return None
        issue = resolve_issue(event, env, registry, id_path)
        if issue is None:
            return None
        return [
            "begin",
            "skill-dispatch",
            "--issue",
            str(issue),
            "--skill-name",
            tool.skill,
        ]

    return None


def record_model(event: HookInput, env: dict[str, str], id_path: Path | None = None) -> None:
    """Remember the session's real model for report rows (best-effort)."""
    instance = instance_id(env, id_path)
    if not instance:
        return
    model = event.model
    if not model and event.transcript_path:
        model = session_model.model_from_transcript(event.transcript_path)
    if model:
        session_model.record(instance, model)


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
    try:
        record_model(event, env)
    except Exception:  # noqa: BLE001 — bookkeeping must never break the session
        pass
    args = report_args(event, env)
    if args:
        run_report(args)

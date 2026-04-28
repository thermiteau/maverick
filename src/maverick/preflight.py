"""Preflight checks — run by every action skill before it does anything.

A skill that needs to operate on a project (do-issue-solo, do-epic, etc.)
calls ``uv run maverick preflight <skill-name>`` as its first step. The
command checks that the project's prerequisites are met and exits 0 if so,
or exits 1 with a precise list of missing prerequisites otherwise. Each
skill body says "halt if preflight exits non-zero" — the exit code is the
gate, not the prose.

Three categories of prerequisite are checked:

  - ``flags``   — entries in the integration block of .maverick/config.json
                 (e.g., ``init``, ``code_review_workflow``). Recorded by
                 the skill that produced each milestone.
  - ``tools``   — commands that must be on PATH (e.g., ``gh``, ``uv``,
                 ``git``). Resolved via ``shutil.which``.
  - ``runtime`` — named functions registered below that perform a
                 dynamic check (e.g., is the Maverick GitHub App
                 configured, are git worktrees usable).

To extend: add a new entry to PREREQS for the skill that needs it. Adding
a new tool or runtime check is a one-line addition to TOOLS / RUNTIME_CHECKS.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from maverick.config import (
    CONFIG_DEFAULTS,
    project_config_path,
    read_integration_status,
)


@dataclass(frozen=True)
class Prereqs:
    """Per-skill prerequisite declaration."""

    flags: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    runtime: tuple[str, ...] = ()


PREREQS: dict[str, Prereqs] = {
    "do-init": Prereqs(
        # do-init produces every integration flag; its only prerequisite is
        # that a Maverick GitHub App is already configured by the user.
        # Maverick will not create the App — that is a manual human action
        # (see https://github.com/settings/apps/new). Failing here is the
        # only signal that pushes the user to perform it.
        runtime=("gh_app_configured",),
    ),
    "do-issue-solo": Prereqs(
        flags=("init", "code_review_workflow"),
        tools=("gh", "git", "uv"),
        runtime=("gh_app_configured",),
    ),
    "do-issue-guided": Prereqs(
        flags=("init", "code_review_workflow"),
        tools=("gh", "git", "uv"),
    ),
    "do-epic": Prereqs(
        flags=("init", "code_review_workflow"),
        tools=("gh", "git", "uv"),
        runtime=("gh_app_configured", "worktrees_enabled"),
    ),
    "do-upskill": Prereqs(
        flags=("init",),
        tools=("uv",),
    ),
    "do-docs": Prereqs(
        flags=("init",),
        tools=("uv",),
    ),
    "do-maverick-alignment": Prereqs(
        flags=("init",),
        tools=("uv",),
    ),
    "do-pullrequest-review": Prereqs(
        flags=("init",),
        tools=("gh", "uv"),
    ),
    "do-cybersecurity-review": Prereqs(
        flags=("init",),
        tools=("uv",),
    ),
}


# Bootstrap-class skills that produce the prerequisites and therefore must
# not require them. Listed for clarity; absence from PREREQS is what makes
# them exempt at runtime.
BOOTSTRAP_SKILLS: frozenset[str] = frozenset(
    {"do-install", "do-recommend", "do-adopt"}
)


# Per-flag remediation guidance. Surfaced when render_human() reports a
# missing integration flag, so the user gets a concrete next step instead
# of a generic "run the corresponding skill" hint. Every flag in
# CONFIG_DEFAULTS["integration"] must have an entry — enforced by tests.
FLAG_REMEDIATION: dict[str, str] = {
    "init": "Run /maverick:do-init",
    "alignment": "Run /maverick:do-maverick-alignment",
    "upskill": "Run /maverick:do-upskill",
    "tech_docs_scaffolded": "Run /maverick:do-docs",
    "code_review_workflow": (
        "Run /maverick:do-init (it scaffolds the workflow), or copy "
        "${CLAUDE_PLUGIN_ROOT}/skills/mav-bp-remote-code-review/code-review.yml "
        "into .github/workflows/, commit it, then "
        "`maverick integration set code_review_workflow true`"
    ),
    "cybersecurity_reviewed": "Run /maverick:do-cybersecurity-review",
}


# ---------------------------------------------------------------------------
# Runtime checks
# ---------------------------------------------------------------------------


def _check_gh_app_configured() -> tuple[bool, str]:
    """Return (ok, message). The GitHub App must report ``configured: true``.

    Uses ``maverick gh-app status`` so the check is consistent with what
    do-epic Phase 0 already runs. The subcommand emits JSON on stdout
    (e.g. ``{"configured": true, "app_id": 123, ...}``); we parse it
    rather than substring-match because the JSON form ``"configured":
    true`` is not a substring of any plain-text needle that includes
    the key without surrounding quotes.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "maverick", "gh-app", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, f"could not run `maverick gh-app status`: {e}"
    if result.returncode == 0 and (result.stdout or "").strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict) and payload.get("configured") is True:
            return True, ""
    return False, (
        "the Maverick GitHub App is not configured. Create a GitHub App at "
        "https://github.com/settings/apps/new (read access to contents and "
        "metadata; write access to pull-requests and issues), install it on "
        "the target repo, then add a `gh_app` block to ~/.maverick/config.json:\n"
        '            {\n'
        '              "gh_app": {\n'
        '                "app_id": <integer>,\n'
        '                "installation_id": <integer>,\n'
        '                "private_key_path": "~/.maverick/maverick-gh-app.pem"\n'
        '              }\n'
        '            }\n'
        "        Verify with `maverick gh-app status`"
    )


def _check_worktrees_enabled() -> tuple[bool, str]:
    """Return (ok, message). Worktrees must be usable in this checkout.

    `git worktree list` always exits 0 in a normal repo. The skill-level
    convention forbids worktree use unless explicitly enabled, so we also
    look for a `worktrees_enabled: true` marker in the project config.
    """
    if not Path(".git").exists():
        return False, "not inside a git working tree"
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, f"could not run `git worktree list`: {e}"
    if result.returncode != 0:
        return False, "git worktree list failed — worktrees are not usable here"
    return True, ""


RUNTIME_CHECKS: dict[str, Callable[[], tuple[bool, str]]] = {
    "gh_app_configured": _check_gh_app_configured,
    "worktrees_enabled": _check_worktrees_enabled,
}


# ---------------------------------------------------------------------------
# Preflight evaluation
# ---------------------------------------------------------------------------


@dataclass
class PreflightResult:
    """Outcome of a single preflight evaluation."""

    skill: str
    missing_flags: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    failing_runtime: list[tuple[str, str]] = field(default_factory=list)
    unknown_skill: bool = False

    @property
    def passed(self) -> bool:
        return (
            not self.missing_flags
            and not self.missing_tools
            and not self.failing_runtime
            and not self.unknown_skill
        )


def evaluate(skill_name: str) -> PreflightResult:
    """Run every prerequisite check declared for *skill_name*.

    Returns a structured result. Caller decides how to render and what
    exit code to use. Bootstrap skills (or anything not in PREREQS) pass
    trivially — they cannot have prerequisites because they produce them.
    """
    if skill_name in BOOTSTRAP_SKILLS:
        return PreflightResult(skill=skill_name)
    if skill_name not in PREREQS:
        return PreflightResult(skill=skill_name, unknown_skill=True)

    prereqs = PREREQS[skill_name]
    result = PreflightResult(skill=skill_name)

    if prereqs.flags:
        status = read_integration_status()
        valid_flag_keys = set(CONFIG_DEFAULTS["integration"].keys())
        for flag in prereqs.flags:
            if flag not in valid_flag_keys:
                # Defensive — should be caught by tests, but don't let a typo
                # in PREREQS silently pass.
                result.missing_flags.append(f"{flag} (unknown flag in PREREQS)")
                continue
            if not status.get(flag, False):
                result.missing_flags.append(flag)

    for tool in prereqs.tools:
        if shutil.which(tool) is None:
            result.missing_tools.append(tool)

    for check_name in prereqs.runtime:
        runner = RUNTIME_CHECKS.get(check_name)
        if runner is None:
            result.failing_runtime.append(
                (check_name, "unknown runtime check (typo in PREREQS?)")
            )
            continue
        ok, message = runner()
        if not ok:
            result.failing_runtime.append((check_name, message))

    return result


def render_human(result: PreflightResult) -> str:
    """Format a PreflightResult as a multi-line string for stderr."""
    lines: list[str] = []
    if result.unknown_skill:
        lines.append(
            f"preflight: skill {result.skill!r} has no declared prerequisites; "
            "either add an entry to maverick.preflight.PREREQS or check the spelling"
        )
        return "\n".join(lines)

    if result.passed:
        return f"preflight: {result.skill} OK"

    lines.append(f"preflight: {result.skill} cannot run — prerequisites not met")
    if result.missing_flags:
        lines.append("  Missing integration flags:")
        for flag in result.missing_flags:
            remedy = FLAG_REMEDIATION.get(
                flag, "no remediation registered (see maverick.preflight.FLAG_REMEDIATION)"
            )
            lines.append(f"    - {flag}: {remedy}")
        lines.append("  Inspect with: maverick integration get")
        lines.append(
            f"  Project config: {project_config_path()}"
        )
    if result.missing_tools:
        lines.append("  Missing PATH tools:")
        for tool in result.missing_tools:
            lines.append(f"    - {tool}")
    if result.failing_runtime:
        lines.append("  Failing runtime checks:")
        for name, message in result.failing_runtime:
            lines.append(f"    - {name}: {message}")
    return "\n".join(lines)

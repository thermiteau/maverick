#!/usr/bin/env python3
"""PreToolUse scope guard — mechanical enforcement of mav-scope-boundaries.

Reads the PreToolUse hook payload from stdin and evaluates it against the
four scope-boundary hard limits:

1. **Destructive git operations** — force pushes, hard resets, forced
   branch deletion, remote branch deletion, tree-wide discards, history
   rewriting, and commits/pushes on protected branches.
2. **Infrastructure changes** — edits to CI/CD workflow definitions,
   Dockerfiles, IaC templates, and orchestration manifests.
3. **Production systems** — commands or fetches matching per-project
   production patterns. Never allowed, in any mode.
4. **Session-auth integrity** — direct writes to
   ``.maverick/session-auth.json`` (only ``maverick coord authorize`` may
   write it, after verifying issue-level authorization).

Decision model (open design decision #1 in the modernization plan):

- **Interactive sessions**: rule hits emit ``permissionDecision: ask`` so
  the user grants or refuses in the moment — that *is* the "session
  consent" the policy requires.
- **Autonomous mode**: rule hits are denied (exit 2). A session is
  autonomous when ``MAVERICK_AUTONOMOUS=1`` is set (workers) or when this
  instance holds a claim in ``~/.maverick/active-claims.json`` (an
  instance that holds a claim is by definition running an autonomous
  workflow).
- **Production patterns** deny in every mode — the policy has no consent
  carve-out for production.
- Infrastructure edits are allowed in autonomous mode only when
  ``.maverick/session-auth.json`` records the ``infra`` scope, which
  ``maverick coord authorize`` writes after verifying the authorization on
  the GitHub issue itself.

Engineering contract (same standard as install_check.py): pure stdlib,
deterministic, and it must never crash the session — any internal error
fails open (allow) with a warning on stderr. Blocking is reserved for
confident rule hits.

Escape hatch: ``MAVERICK_GUARD_DISABLE=1`` disables the guard entirely.
Documented as unsafe for autonomous/CI use.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

ALLOW = "allow"
ASK = "ask"
DENY = "deny"


@dataclass
class Verdict:
    decision: str
    reason: str = ""
    # True when the rule must deny even in interactive sessions (production).
    always_deny: bool = False


_ALLOW = Verdict(ALLOW)

ESCALATION = (
    "This action is restricted by mav-scope-boundaries. If it is genuinely "
    "required, ask the user for consent in this session, or record issue-level "
    "authorization with `maverick coord authorize <repo> <issue> <scope>`."
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PROTECTED_BRANCHES = ("main", "master", "stable")

#: Builtin production markers — matched as substrings of Bash commands and
#: WebFetch URLs. Deliberately conservative; per-project patterns come from
#: .maverick/config.json -> scope_guards.production_patterns.
BUILTIN_PRODUCTION_PATTERNS = (
    "AWS_PROFILE=prod",
    "AWS_PROFILE=production",
    "--profile prod ",
    "--profile=prod ",
    "--profile production",
    "--profile=production",
)

#: Infra-file detection: path predicates over the edited/written path.
_INFRA_SEGMENT_RE = re.compile(
    r"(^|/)(\.github/workflows|k8s|kubernetes|helm|\.circleci)(/|$)"
)
_INFRA_FILENAME_RE = re.compile(
    r"(^|/)("
    r"Dockerfile[^/]*|docker-compose[^/]*|Jenkinsfile|"
    r"\.gitlab-ci\.ya?ml|azure-pipelines\.ya?ml|bitbucket-pipelines\.ya?ml|"
    r"serverless\.ya?ml|[^/]+\.tf|[^/]+\.tfvars|[^/]+\.template\.json"
    r")$"
)

SESSION_AUTH_REL = ".maverick/session-auth.json"

#: Bash substrings that indicate the command writes to a file it mentions.
_WRITE_MARKERS = (">", ">>", "tee ", "cp ", "mv ", "sed -i", "rm ", "truncate ")


def _load_project_guards(cwd: Path) -> dict:
    """Read scope_guards from .maverick/config.json, tolerating anything."""
    try:
        raw = json.loads((cwd / ".maverick" / "config.json").read_text())
        guards = raw.get("scope_guards", {})
        return guards if isinstance(guards, dict) else {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


def _instance_id_path() -> Path:
    """Where coordinator.instance_id() persists the per-user id."""
    return Path("~/.maverick/instance_id").expanduser()


def _instance_id(env: dict[str, str], id_path: Path | None = None) -> str | None:
    """Mirror coordinator.instance_id()'s derivation (read-only, never writes).

    The rungs must match ``coordinator.instance_id()`` exactly, or the hook
    and the coordinator can land on different ids and disagree about whether
    a claim belongs to this instance. In particular the file fallback is
    essential: hooks run in a separately-spawned subprocess that in some
    Claude Code versions does not receive the session-id env, so without it
    the hook would fall straight to ``None`` while the coordinator resolved a
    real id via the session hash (or the file). Read-only: the hook must
    never generate or persist an id — that is the coordinator's job.
    """
    explicit = env.get("MAVERICK_INSTANCE_ID")
    if explicit:
        return explicit
    session = env.get("CLAUDE_CODE_SESSION_ID") or env.get("CLAUDE_SESSION_ID")
    if session:
        return hashlib.sha256(session.encode("utf-8")).hexdigest()[:10]
    try:
        cached = (id_path or _instance_id_path()).read_text().strip()
        if cached:
            return cached
    except OSError:
        pass
    return None


def is_autonomous(
    env: dict[str, str],
    claims_path: Path | None = None,
    id_path: Path | None = None,
) -> bool:
    """Autonomous = explicit env flag, or this instance holds a local claim."""
    if env.get("MAVERICK_AUTONOMOUS") == "1":
        return True
    instance = _instance_id(env, id_path)
    if not instance:
        return False
    path = claims_path or Path("~/.maverick/active-claims.json").expanduser()
    try:
        claims = json.loads(path.read_text()).get("claims", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    return any(
        isinstance(c, dict) and c.get("instance_id") == instance for c in claims
    )


def _session_auth_scopes(cwd: Path) -> set[str]:
    try:
        raw = json.loads((cwd / SESSION_AUTH_REL).read_text())
        return {str(s) for s in raw.get("scopes", [])}
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


# ---------------------------------------------------------------------------
# Bash command analysis
# ---------------------------------------------------------------------------


def _split_subcommands(command: str) -> list[str]:
    """Split a compound shell command into rough sub-commands."""
    return [p.strip() for p in re.split(r"&&|\|\||;|\||\n", command) if p.strip()]


def _git_tokens(sub: str) -> list[str] | None:
    """If *sub* is a git invocation, return its tokens after global flags."""
    tokens = sub.split()
    # Strip leading env assignments (FOO=bar git push ...)
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens = tokens[1:]
    if not tokens or tokens[0] != "git":
        return None
    tokens = tokens[1:]
    # Skip global flags with values (-C <path>, -c <cfg>) and bare flags.
    out: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if not out and tok in ("-C", "-c"):
            skip_next = True
            continue
        if not out and tok.startswith("-"):
            continue
        out.append(tok)
    return out


def _current_branch(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = result.stdout.strip()
        return branch or None
    except Exception:
        return None


def _check_git(
    tokens: list[str], cwd: Path, protected: tuple[str, ...]
) -> Verdict | None:
    """Destructive-git and protected-branch rules for one git invocation."""
    if not tokens:
        return None
    verb, rest = tokens[0], tokens[1:]
    joined = " ".join(rest)

    if verb == "push":
        if "--force" in rest or "-f" in rest:
            return Verdict(ASK, "git push --force rewrites shared history")
        if any(t.startswith("--force-with-lease") for t in rest):
            return Verdict(ASK, "git push --force-with-lease rewrites shared history")
        if "--mirror" in rest:
            return Verdict(ASK, "git push --mirror rewrites the entire remote")
        if "--delete" in rest or "-d" in rest:
            return Verdict(ASK, "deleting a remote branch is irreversible")
        for tok in rest:
            if ":" in tok and not tok.startswith("-"):
                src, _, dst = tok.partition(":")
                if not src:
                    return Verdict(ASK, f"pushing an empty ref deletes remote {dst!r}")
                if dst in protected:
                    return Verdict(ASK, f"push targets protected branch {dst!r}")
        positional = [t for t in rest if not t.startswith("-")]
        if any(t in protected for t in positional[1:]):
            target = next(t for t in positional[1:] if t in protected)
            return Verdict(ASK, f"push targets protected branch {target!r}")
        branch = _current_branch(cwd)
        if branch in protected:
            return Verdict(ASK, f"push from protected branch {branch!r}")
        return None

    if verb == "commit":
        branch = _current_branch(cwd)
        if branch in protected:
            return Verdict(
                ASK, f"commit on protected branch {branch!r} — create a feature branch"
            )
        return None

    if verb == "reset" and "--hard" in rest:
        return Verdict(ASK, "git reset --hard discards work irreversibly")
    if verb == "branch" and "-D" in rest:
        return Verdict(ASK, "git branch -D force-deletes without merge check")
    if verb == "clean" and any(re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", t) for t in rest):
        return Verdict(ASK, "git clean -f deletes untracked files irreversibly")
    if verb in ("checkout", "restore") and (
        rest == ["."] or rest == ["--", "."] or joined.endswith(" .")
    ):
        return Verdict(ASK, f"git {verb} . discards all local modifications")
    if verb == "filter-branch":
        return Verdict(ASK, "git filter-branch rewrites history")
    return None


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


def _is_infra_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    normalized = re.sub(r"^(\./)+", "", normalized)  # strip ./ prefixes, keep dotfiles
    return bool(
        _INFRA_SEGMENT_RE.search(normalized) or _INFRA_FILENAME_RE.search(normalized)
    )


def _production_hit(text: str, extra_patterns: list) -> str | None:
    for pat in BUILTIN_PRODUCTION_PATTERNS:
        if pat.rstrip() in text:
            return pat.rstrip()
    for pat in extra_patterns:
        pat = str(pat)
        if pat.startswith("re:"):
            try:
                if re.search(pat[3:], text):
                    return pat
            except re.error:
                continue
        elif pat and pat in text:
            return pat
    return None


def decide(payload: dict) -> Verdict:
    """Evaluate one PreToolUse payload. Pure apart from git branch lookups."""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or ".")
    guards = _load_project_guards(cwd)
    protected = tuple(
        guards.get("protected_branches") or DEFAULT_PROTECTED_BRANCHES
    )
    production_patterns = guards.get("production_patterns") or []

    if tool == "WebFetch":
        url = str(tool_input.get("url") or "")
        hit = _production_hit(url, production_patterns)
        if hit:
            return Verdict(
                DENY,
                f"URL matches production pattern {hit!r} — production systems are "
                "off-limits in every mode, with no consent carve-out.",
                always_deny=True,
            )
        return _ALLOW

    if tool in ("Edit", "Write", "NotebookEdit"):
        path = str(
            tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        )
        normalized = path.replace("\\", "/")
        if normalized.endswith(SESSION_AUTH_REL):
            return Verdict(
                DENY,
                "session-auth.json may only be written by `maverick coord "
                "authorize`, which verifies authorization on the GitHub issue.",
                always_deny=True,
            )
        if _is_infra_path(path):
            return Verdict(
                ASK,
                f"{path} is infrastructure (CI/CD, containers, IaC) — "
                "explicit authorization required. " + ESCALATION,
            )
        return _ALLOW

    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        hit = _production_hit(command, production_patterns)
        if hit:
            return Verdict(
                DENY,
                f"Command matches production pattern {hit!r} — production systems "
                "are off-limits in every mode, with no consent carve-out.",
                always_deny=True,
            )
        writes = any(marker in command for marker in _WRITE_MARKERS)
        if SESSION_AUTH_REL in command and writes:
            return Verdict(
                DENY,
                "session-auth.json may only be written by `maverick coord "
                "authorize`, which verifies authorization on the GitHub issue.",
                always_deny=True,
            )
        for sub in _split_subcommands(command):
            tokens = _git_tokens(sub)
            if tokens is not None:
                verdict = _check_git(tokens, cwd, protected)
                if verdict:
                    return verdict
        if writes:
            for candidate in re.findall(r"[\w./\\-]+", command):
                if _is_infra_path(candidate):
                    return Verdict(
                        ASK,
                        f"command writes to infrastructure path {candidate!r} — "
                        "explicit authorization required. " + ESCALATION,
                    )
        return _ALLOW

    return _ALLOW


def resolve(verdict: Verdict, payload: dict, env: dict[str, str],
            claims_path: Path | None = None,
            id_path: Path | None = None) -> Verdict:
    """Apply the interactive-vs-autonomous policy to a rule hit."""
    if verdict.decision == ALLOW:
        return verdict
    if verdict.always_deny:
        return Verdict(DENY, verdict.reason, always_deny=True)

    cwd = Path(payload.get("cwd") or ".")
    # A recorded `infra` grant authorizes infrastructure edits in *any* mode.
    # `maverick coord authorize` only writes it after verifying issue-level
    # authorization, so an explicit grant should suppress the prompt whether
    # the run is classified interactive or autonomous — a misclassification
    # must not defeat an authorization the user has already recorded.
    if "infrastructure" in verdict.reason and "infra" in _session_auth_scopes(cwd):
        return _ALLOW
    if is_autonomous(env, claims_path, id_path):
        return Verdict(
            DENY,
            verdict.reason
            + " (autonomous mode: denied — no user is present to consent). "
            + ESCALATION,
        )
    # Interactive: surface the decision to the user.
    return Verdict(ASK, verdict.reason)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    if os.environ.get("MAVERICK_GUARD_DISABLE") == "1":
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # unparseable input — fail open, never break the session

    try:
        verdict = resolve(decide(payload), payload, dict(os.environ))
    except Exception as exc:  # noqa: BLE001 — fail open by contract
        print(f"maverick scope-guard: internal error ({exc}); allowing.", file=sys.stderr)
        return 0

    if verdict.decision == DENY:
        print(f"maverick scope-guard: BLOCKED — {verdict.reason}", file=sys.stderr)
        return 2
    if verdict.decision == ASK:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": (
                            f"maverick scope-guard: {verdict.reason}"
                        ),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

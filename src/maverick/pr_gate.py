"""Pre-merge gates for autonomous PR handling.

The auth-scan gate implements the mechanically checkable half of the
scope-boundaries auth limit: an autonomous workflow must never auto-merge
a PR that touches authentication/authorization surfaces (or CI workflow
definitions). Edit-time detection of auth changes stays advisory prose in
``mav-scope-boundaries``; this gate enforces the invariant at the one
deterministic point that matters — right before ``gh pr merge --auto``.

False positives are cheap by design: a hit ejects the PR to ``needs-human``
(a human review), never blocks a human decision.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

#: Path segments / filename tokens that mark a file as auth-sensitive.
#: Matched against whole path segments and ``[-_.]``-split filename tokens,
#: never as substrings — ``src/author/`` does not match ``auth``.
AUTH_SENSITIVE_TOKENS = frozenset(
    {
        "auth",
        "authn",
        "authz",
        "authentication",
        "authorization",
        "oauth",
        "oauth2",
        "sso",
        "saml",
        "oidc",
        "rbac",
        "acl",
        "permission",
        "permissions",
        "roles",
        "login",
        "credentials",
        "session",
        "sessions",
    }
)

#: Directory prefixes that are always gate-relevant (CI/CD definitions are
#: infrastructure riding along inside the PR).
GATED_PREFIXES = (".github/workflows/",)


def _project_extra_tokens(project_dir: Path) -> frozenset[str]:
    """Extra tokens from ``.maverick/config.json`` → ``scope_guards.auth_paths``.

    Read leniently with plain json — this must work in end-user projects
    with partial configs and must never raise.
    """
    try:
        raw = json.loads((project_dir / ".maverick" / "config.json").read_text())
        extra = raw.get("scope_guards", {}).get("auth_paths", [])
        return frozenset(str(t).lower() for t in extra if str(t).strip())
    except (OSError, json.JSONDecodeError, AttributeError):
        return frozenset()


def _path_tokens(path: str) -> set[str]:
    """All whole segments plus filename tokens for matching."""
    parts = [p.lower() for p in path.split("/") if p]
    tokens = set(parts)
    if parts:
        tokens.update(t for t in re.split(r"[-_.]", parts[-1]) if t)
    return tokens


def scan_paths(paths: list[str], project_dir: Path = Path(".")) -> list[str]:
    """Return the subset of *paths* that are auth-sensitive or CI-gated."""
    tokens = AUTH_SENSITIVE_TOKENS | _project_extra_tokens(project_dir)
    hits = []
    for path in paths:
        # Strip ./ prefixes without eating dotfile names (lstrip strips a
        # character set, which would turn ".github/..." into "github/...").
        normalized = re.sub(r"^(\./)+", "", path.strip())
        if not normalized:
            continue
        if normalized.startswith(GATED_PREFIXES) or _path_tokens(normalized) & tokens:
            hits.append(path)
    return hits


def pr_changed_files(repo: str, pr: str) -> list[str]:
    """List the files a PR touches via ``gh pr diff --name-only``."""
    result = subprocess.run(
        ["gh", "pr", "diff", pr, "--repo", repo, "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]

"""Pre-merge gates for autonomous PR handling.

The auth-scan gate implements the mechanically checkable half of the
scope-boundaries auth limit: an autonomous workflow must never auto-merge
a PR that touches authentication/authorization surfaces (or CI workflow
definitions). Edit-time detection of auth changes stays advisory prose in
``mav-scope-boundaries``; this gate enforces the invariant at the one
deterministic point that matters — right before ``gh pr merge --auto``.

False positives are cheap by design: a hit ejects the PR to ``needs-human``
(a human review), never blocks a human decision. They are not free, though —
a long autonomous run can strand most of its PRs on generic words — so the
scan narrows itself (#167):

- Executable test code is never auth-sensitive: code files under
  ``tests/``, ``test/`` or ``__tests__/``, ``*.test.<ext>`` and
  ``*.spec.<ext>`` with a code extension, and ``*_test.go``. Data and
  config files (``.json``, ``.yml``) never count as tests.
- A flagged file whose diff changes only comments or blank lines is cleared.
- ``scope_guards.auth_paths_exclude`` removes tokens a project uses in a
  non-auth sense (``roles``, ``credentials``, ``session``).
- ``scope_guards.auth_scan: "advisory"`` reports auth-path hits without
  gating, but only when the independent security reviewer returned PASS on
  the same diff (``--security-verdict PASS``). CI workflow definitions stay
  a hard gate in every mode.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
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

#: Files that are always gate-relevant. ``.maverick/config.json`` holds the
#: ``scope_guards`` that tune this gate and the scope guard; a PR must not
#: relax its own gate without a human seeing it (#167).
GATED_FILES = frozenset({".maverick/config.json"})


#: Filename patterns for test files, which cannot change runtime auth.
_CODE_EXT = r"(js|jsx|ts|tsx|mjs|cjs|py|rb|go|java|kt|cs|php|rs|swift)"
#: Executable test code only — data and config (``.json``, ``.yml``) never
#: count, even under a test directory, since runtime code can load them.
_TEST_FILE_RE = re.compile(
    rf"(^|/)(__tests__|tests?)/(.+/)?[^/]+\.{_CODE_EXT}$"
    rf"|\.(test|spec)\.{_CODE_EXT}$"
    r"|_test\.go$"
)

#: Whole-line comment forms by file extension, for the comment-only check.
#: Each regex must match the *entire* stripped line, so a line with code
#: after a comment (``/* x */ return true;``) never counts. Multi-line block
#: comment bodies (`` * text``) are deliberately not recognised: without
#: context they are indistinguishable from code such as ``*ptr = 0;``.
#: Anything not listed here is never treated as comment-only.
_C_STYLE = re.compile(r"//.*|/\*(?:(?!\*/).)*\*/")
_HASH = re.compile(r"#.*")
_COMMENT_RES: dict[str, re.Pattern[str]] = {}
for _exts, _pattern in (
    (("py", "rb", "sh", "bash", "yaml", "yml", "toml", "r", "pl"), _HASH),
    (
        ("js", "jsx", "ts", "tsx", "mjs", "cjs", "java", "kt", "kts", "go",
         "rs", "c", "h", "cc", "cpp", "hpp", "cs", "swift", "scala", "dart",
         "php"),
        _C_STYLE,
    ),
    (("sql", "lua", "hs"), re.compile(r"--.*")),
    (("html", "xml", "vue", "svelte"), re.compile(r"<!--(?:(?!-->).)*-->")),
):
    for _ext in _exts:
        _COMMENT_RES[_ext] = _pattern


def _project_guards(project_dir: Path) -> dict:
    """``scope_guards`` from ``.maverick/config.json``; ``{}`` on any problem.

    Read leniently with plain json — this must work in end-user projects
    with partial configs and must never raise.
    """
    try:
        raw = json.loads((project_dir / ".maverick" / "config.json").read_text())
        guards = raw.get("scope_guards", {})
        return guards if isinstance(guards, dict) else {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _token_list(guards: dict, key: str) -> frozenset[str]:
    values = guards.get(key, [])
    if not isinstance(values, list):
        return frozenset()
    return frozenset(str(t).strip().lower() for t in values if str(t).strip())


def _project_extra_tokens(project_dir: Path) -> frozenset[str]:
    """Extra tokens from ``.maverick/config.json`` → ``scope_guards.auth_paths``."""
    return _token_list(_project_guards(project_dir), "auth_paths")


def _path_tokens(path: str) -> set[str]:
    """All whole segments plus filename tokens for matching."""
    parts = [p.lower() for p in path.split("/") if p]
    tokens = set(parts)
    if parts:
        tokens.update(t for t in re.split(r"[-_.]", parts[-1]) if t)
    return tokens


def _normalize(path: str) -> str:
    # Strip ./ prefixes without eating dotfile names (lstrip strips a
    # character set, which would turn ".github/..." into "github/...").
    return re.sub(r"^(\./)+", "", path.strip())


def is_test_path(path: str) -> bool:
    return bool(_TEST_FILE_RE.search(_normalize(path)))


#: Comment text that changes how *neighbouring* lines parse, so a change
#: to it is never "comment only": a trailing backslash continues a C-style
#: line comment onto the next line (commenting out unchanged code), ``?>``
#: ends PHP mode inside a ``//`` or ``#`` comment, and a Python coding
#: cookie changes how the whole file decodes.
_CONTEXT_CHANGING = re.compile(r"\\\s*$|\?>|coding[:=]")


def _is_comment_or_blank(line: str, ext: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _CONTEXT_CHANGING.search(stripped):
        return False
    pattern = _COMMENT_RES.get(ext)
    return bool(pattern) and bool(pattern.fullmatch(stripped))


def comment_only(path: str, changed_lines: list[str] | None) -> bool:
    """True when every changed line of *path* is a comment or blank.

    ``None`` or an empty list (binary change, pure rename, mode change, or
    no diff available) is never comment-only.
    """
    if not changed_lines:
        return False
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    if ext not in _COMMENT_RES:
        return False
    return all(_is_comment_or_blank(line, ext) for line in changed_lines)


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def parse_diff(patch: str) -> dict[str, list[str]]:
    """Map each file in a unified diff to its added and removed lines.

    Hunk-aware: inside a hunk, lines are counted against the ``@@`` header's
    line counts, so an added line whose content starts with ``++ `` or
    ``-- `` is a change, never a file header. A malformed diff (a body line
    outside any hunk) raises ``ValueError`` — the caller then scans without
    comment-only clearing.
    """
    files: dict[str, list[str]] = {}
    current: list[str] | None = None
    old_path = ""
    old_left = new_left = 0
    for line in patch.splitlines():
        if old_left > 0 or new_left > 0:
            if current is None:
                raise ValueError("hunk without a file header")
            tag = line[:1]
            if tag == "\\":  # "\ No newline at end of file"
                continue
            if tag == "-":
                old_left -= 1
                current.append(line[1:])
            elif tag == "+":
                new_left -= 1
                current.append(line[1:])
            elif tag in (" ", ""):
                old_left -= 1
                new_left -= 1
            else:
                raise ValueError(f"unexpected line inside hunk: {line[:40]!r}")
            continue
        if line.startswith("diff --git "):
            current = None
            old_path = ""
        elif line.startswith("--- "):
            old_path = line[4:].removeprefix("a/")
        elif line.startswith("+++ "):
            new_path = line[4:].removeprefix("b/")
            path = old_path if new_path == "/dev/null" else new_path
            current = files.setdefault(path, [])
        elif match := _HUNK_RE.match(line):
            if current is None:
                raise ValueError("hunk without a file header")
            old_left = int(match.group(1) if match.group(1) is not None else 1)
            new_left = int(match.group(2) if match.group(2) is not None else 1)
        elif line.startswith(("+", "-")):
            raise ValueError(f"change line outside a hunk: {line[:40]!r}")
    return files


@dataclass
class ScanResult:
    """Outcome of an auth-path scan."""

    #: Auth-sensitive paths that still need a human.
    auth_hits: list[str] = field(default_factory=list)
    #: CI workflow definitions and guard config — a hard gate in every mode.
    ci_hits: list[str] = field(default_factory=list)
    #: Paths a token matched but the scan cleared, with the reason.
    cleared: dict[str, str] = field(default_factory=dict)

    @property
    def hits(self) -> list[str]:
        return self.ci_hits + self.auth_hits


def scan(
    paths: list[str],
    project_dir: Path = Path("."),
    diff: dict[str, list[str]] | None = None,
    guards: dict | None = None,
) -> ScanResult:
    """Classify *paths*; *diff* (from :func:`parse_diff`) enables the
    comment-only check. *guards* (from :func:`pr_base_guards`) overrides
    reading ``scope_guards`` from *project_dir*."""
    if guards is None:
        guards = _project_guards(project_dir)
    tokens = (AUTH_SENSITIVE_TOKENS | _token_list(guards, "auth_paths")) - _token_list(
        guards, "auth_paths_exclude"
    )
    result = ScanResult()
    for path in paths:
        normalized = _normalize(path)
        if not normalized:
            continue
        if normalized.startswith(GATED_PREFIXES) or normalized in GATED_FILES:
            result.ci_hits.append(path)
            continue
        matched = _path_tokens(normalized) & tokens
        if not matched:
            continue
        if is_test_path(normalized):
            result.cleared[path] = "test file"
        elif diff is not None and comment_only(normalized, diff.get(normalized)):
            result.cleared[path] = "comment or whitespace changes only"
        else:
            result.auth_hits.append(path)
    return result


def scan_paths(paths: list[str], project_dir: Path = Path(".")) -> list[str]:
    """Return the subset of *paths* that are auth-sensitive or CI-gated."""
    return scan(paths, project_dir).hits


def auth_scan_advisory(project_dir: Path = Path("."), guards: dict | None = None) -> bool:
    """True when the project set ``scope_guards.auth_scan: "advisory"``."""
    if guards is None:
        guards = _project_guards(project_dir)
    return str(guards.get("auth_scan", "")).lower() == "advisory"


def pr_base_guards(repo: str, pr: str) -> dict:
    """``scope_guards`` as committed on the PR's base branch, read from GitHub.

    The gate must not take its tuning from the local working tree, which
    the agent being gated can edit without committing. The base branch only
    changes through reviewed merges (and a PR that changes the file is hard
    gated). No config file on the base means defaults. Any other failure
    raises ``subprocess.CalledProcessError`` so the caller reports a scan
    error instead of scanning with the wrong settings.
    """
    base = subprocess.run(
        ["gh", "pr", "view", pr, "--repo", repo, "--json", "baseRefName", "-q", ".baseRefName"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = subprocess.run(
        [
            "gh", "api", f"repos/{repo}/contents/.maverick/config.json?ref={base}",
            "-H", "Accept: application/vnd.github.raw",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if "404" in result.stderr or "Not Found" in result.stderr:
            return {}
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    try:
        guards = json.loads(result.stdout).get("scope_guards", {})
    except (json.JSONDecodeError, AttributeError):
        return {}
    return guards if isinstance(guards, dict) else {}


def pr_diff(repo: str, pr: str) -> dict[str, list[str]]:
    """A PR's changed lines per file via ``gh pr diff``."""
    result = subprocess.run(
        ["gh", "pr", "diff", pr, "--repo", repo],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_diff(result.stdout)


def pr_changed_files(repo: str, pr: str) -> list[str]:
    """List the files a PR touches via ``gh pr diff --name-only``."""
    result = subprocess.run(
        ["gh", "pr", "diff", pr, "--repo", repo, "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]

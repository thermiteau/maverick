"""Pre-tool-use scope guard — mechanical enforcement of mav-scope-boundaries.

Evaluates one runtime-neutral :class:`~.adapters.ToolCall` against the four
scope-boundary hard limits:

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
- **Autonomous mode**: rule hits are denied. A tool call is autonomous
  when ``MAVERICK_AUTONOMOUS=1`` is set (workers, headless runs) or when it
  comes from a subagent (the runtime reports an agent id). Holding a
  coordination claim does *not* make a session autonomous: the coordinator
  session a user is typing into holds the epic and story claims, and a user
  there can consent (#167).
- **Production patterns** deny in every mode — the policy has no consent
  carve-out for production.
- Infrastructure edits are allowed in autonomous mode only when
  ``.maverick/session-auth.json`` records the ``infra`` scope, which
  ``maverick coord authorize`` writes after verifying the authorization on
  the GitHub issue itself.

Shell commands are tokenized with :mod:`shlex`, so only real write
targets count: redirect targets (``2>/dev/null`` and ``2>&1`` are not
writes), the files ``tee``/``sed -i``/``rm``/``truncate``/``touch`` act on,
the destination of ``cp``/``install``/``ln``, and every path ``mv``/``git
mv``/``git rm`` touch. Quoted prose — a ``grep`` pattern, a ``--body`` — is
never a write target. Unparseable commands fall back to the coarse
substring check.

Engineering contract: pure stdlib, deterministic, and it must never crash
the session — any internal error fails open (allow) with a warning on
stderr (see ``runtime_hooks.cli``). Blocking is reserved for confident rule
hits.

Escape hatch: ``MAVERICK_GUARD_DISABLE=1`` disables the guard entirely.
Documented as unsafe for autonomous/CI use.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from maverick.runtime_hooks.adapters import ToolCall

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

#: What the infra rule covers, quoted in its denial so a coordinator does
#: not over-generalise the guard to files it never matches (#167).
INFRA_COVERAGE = (
    "The guard matches only CI definitions (.github/workflows/, .circleci/, "
    ".gitlab-ci.yml, azure-pipelines.yml, bitbucket-pipelines.yml, "
    "Jenkinsfile), Dockerfile*, docker-compose*, k8s/, kubernetes/, helm/, "
    "*.tf, *.tfvars, *.template.json and serverless.yml; other files (CDK "
    "code, Makefiles, scripts) are not restricted."
)

SESSION_AUTH_REL = ".maverick/session-auth.json"

#: Bash substrings that indicate the command writes to a file it mentions.
#: Only used as the fallback when a command cannot be tokenized.
_WRITE_MARKERS = (">", ">>", "tee ", "cp ", "mv ", "sed -i", "rm ", "truncate ")

#: Redirect targets that are never files on disk.
_NULL_TARGETS = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"})

#: Commands that only read the files they are given. A command naming the
#: session-auth file that is not one of these is treated as a write.
_READ_ONLY_COMMANDS = frozenset(
    {"cat", "head", "tail", "less", "more", "jq", "grep", "rg", "ls", "stat",
     "wc", "diff", "file", "test", "[", "echo", "printf"}
)


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


def is_autonomous(env: dict[str, str], call: ToolCall | None = None) -> bool:
    """Autonomous = explicit env flag, or the call comes from a subagent.

    Claim ownership is deliberately not a signal: the interactive
    coordinator session holds claims too, and a user there can consent
    (#167). Workers and headless runs set ``MAVERICK_AUTONOMOUS=1``.
    """
    if env.get("MAVERICK_AUTONOMOUS") == "1":
        return True
    return bool(call is not None and call.subagent)


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
    """Split a compound shell command into rough sub-commands (fallback only)."""
    return [p.strip() for p in re.split(r"&&|\|\||;|\||\n", command) if p.strip()]


_PUNCT = "();<>|&\n"


def _shell_tokens(command: str) -> list[str] | None:
    """Tokenize *command* with shell quoting; ``None`` if it cannot be parsed.

    Operators come back as their own tokens (``&&``, ``;``, ``>``, ``2>&1``
    becomes ``2``, ``>&``, ``1``) and quoted text stays one token, so a
    ``>`` or a path inside a quoted argument is never mistaken for a write.
    Newlines are operators too (but survive inside quotes).
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCT)
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def _is_operator(token: str) -> bool:
    return bool(token) and all(c in _PUNCT for c in token)


@dataclass
class _Segment:
    """One simple command: its words, and the files it redirects output to."""

    words: list[str]
    redirect_targets: list[str]


def _segments(tokens: list[str]) -> list[_Segment]:
    """Split shell tokens into simple commands, peeling off redirections."""
    segments: list[_Segment] = []
    words: list[str] = []
    targets: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not _is_operator(tok):
            words.append(tok)
            i += 1
            continue
        op = tok.lstrip(";|()\n")
        if op.startswith("<"):
            i += 2  # input redirect / heredoc: skip its operand
            continue
        if ">" in op:
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            # N>&M and N>&- duplicate or close a descriptor: not a write.
            if not (op == ">&" and re.fullmatch(r"\d+-?|-", nxt)):
                if nxt and nxt not in _NULL_TARGETS and not _is_operator(nxt):
                    targets.append(nxt)
            if words and re.fullmatch(r"\d+", words[-1]) and op == tok:
                words.pop()  # the "2" of "2>file" is a descriptor, not an argument
            i += 2
            continue
        # A separator (&&, ||, ;, |, &, parentheses, newline).
        if words or targets:
            segments.append(_Segment(words, targets))
        words, targets = [], []
        i += 1
    if words or targets:
        segments.append(_Segment(words, targets))
    return segments


def _strip_prefix(words: list[str]) -> list[str]:
    """Drop env assignments and transparent wrappers (``sudo``, ``env``).

    Wrapper options are dropped too (``env -i``, ``env -u NAME``,
    ``sudo -u user``), so the wrapped command is what gets judged.
    """
    words = list(words)
    while words:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        elif Path(words[0]).name in ("sudo", "env", "command", "nohup", "time"):
            takes_value = _WRAPPER_VALUE_FLAGS.get(Path(words[0]).name, ())
            words = words[1:]
            while words and words[0].startswith("-"):
                flag = words.pop(0)
                if flag == "--":
                    break
                if flag in takes_value and words:
                    words.pop(0)
        else:
            break
    return words


_WRAPPER_VALUE_FLAGS: dict[str, tuple[str, ...]] = {
    "env": ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"),
    "sudo": ("-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"),
}


def _positionals(args: list[str], takes_value: tuple[str, ...] = ()) -> list[str]:
    """Non-flag arguments; ``takes_value`` flags consume the next argument."""
    out: list[str] = []
    skip = False
    end_of_flags = False
    for arg in args:
        if skip:
            skip = False
            continue
        if end_of_flags or not arg.startswith("-") or arg == "-":
            out.append(arg)
        elif arg == "--":
            end_of_flags = True
        elif arg in takes_value:
            skip = True
    return out


def _option_value(args: list[str], short: str, long: str) -> list[str]:
    """Values of ``-t X`` / ``--long=X`` / ``--long X`` style options."""
    values = []
    for i, arg in enumerate(args):
        if arg in (short, long) and i + 1 < len(args):
            values.append(args[i + 1])
        elif arg.startswith(long + "="):
            values.append(arg.split("=", 1)[1])
    return values


def _command_write_targets(words: list[str]) -> list[str]:
    """Files a simple command writes to, judged from its argv alone."""
    words = _strip_prefix(words)
    if not words:
        return []
    cmd, args = Path(words[0]).name, words[1:]
    if cmd == "tee":
        return _positionals(args)
    if cmd in ("rm", "rmdir", "unlink", "touch"):
        return _positionals(args)
    if cmd == "truncate":
        return _positionals(args, takes_value=("-s", "-r"))
    if cmd == "mv":
        return _positionals(args, takes_value=("-t", "-S")) + _option_value(
            args, "-t", "--target-directory"
        )
    if cmd in ("cp", "install", "ln"):
        pos = _positionals(args, takes_value=("-t", "-S", "-m", "-o", "-g"))
        explicit = _option_value(args, "-t", "--target-directory")
        return explicit or pos[-1:]
    if cmd == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    if cmd in ("perl", "ruby") and any(
        a.startswith("-") and not a.startswith("--") and "i" in a[1:] for a in args
    ):
        pos = _positionals(args, takes_value=("-e", "-E"))
        has_script_flag = any(
            a in ("-e", "-E") or (a.startswith("-") and a[-1:] in ("e", "E")) for a in args
        )
        return pos if has_script_flag else pos[1:]
    if cmd in ("awk", "gawk") and ("inplace" in args or "-i" in args):
        pos = [a for a in _positionals(args, takes_value=("-i", "-v", "-f")) if a != "inplace"]
        return pos[1:] if "-f" not in args else pos
    if cmd == "sed":
        in_place = any(
            a.startswith("--in-place")
            or (a.startswith("-") and not a.startswith("--") and "i" in a[1:])
            for a in args
        )
        if not in_place:
            return []
        pos = _positionals(args, takes_value=("-e", "-f", "--expression", "--file"))
        has_script_flag = any(
            a in ("-e", "-f") or a.startswith(("--expression", "--file")) for a in args
        )
        return pos if has_script_flag else pos[1:]
    if cmd == "git":
        tokens = _git_tokens(words)
        if tokens and tokens[0] in ("rm", "mv"):
            return _positionals(tokens[1:])
    return []


def _git_tokens(sub: str | list[str]) -> list[str] | None:
    """If *sub* is a git invocation, return its tokens after global flags."""
    tokens = sub.split() if isinstance(sub, str) else list(sub)
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


def _branch_is_redundant(cwd: Path, branch: str) -> bool:
    """True when deleting *branch* loses no commits.

    That is: every commit on it is reachable from another local branch or
    from any remote-tracking branch — which covers a branch with no commits
    beyond its base and one fully pushed or merged. Any doubt (unknown
    branch, git error) is False, so the rule still asks.
    """
    try:
        result = subprocess.run(
            [
                "git", "-C", str(cwd), "rev-list", "--count",
                f"refs/heads/{branch}", "--not",
                f"--exclude={branch}", "--branches", "--remotes",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    return result.returncode == 0 and result.stdout.strip() == "0"


def _git_dir(words: list[str], cwd: Path) -> Path | None:
    """The directory a git invocation runs in (``-C`` aware); None if unclear."""
    words = list(words)
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
        words = words[1:]
    path = cwd
    for i, tok in enumerate(words[1:], start=1):
        if tok == "-C" and i + 1 < len(words):
            target = words[i + 1]
            if "$" in target or "`" in target:
                return None
            path = path / target
        elif not tok.startswith("-"):
            break
    return path


def _short_flags(rest: list[str]) -> set[str]:
    """Letters from short-flag tokens (``-df`` → {d, f})."""
    letters: set[str] = set()
    for tok in rest:
        if re.fullmatch(r"-[A-Za-z]+", tok):
            letters.update(tok[1:])
    return letters


def _check_git(
    tokens: list[str], cwd: Path, protected: tuple[str, ...], known_dir: bool = True
) -> Verdict | None:
    """Destructive-git and protected-branch rules for one git invocation.

    ``known_dir`` is False when the command changes directory first, so
    checks that inspect the repository cannot trust ``cwd``.
    """
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
    flags = _short_flags(rest)
    if verb == "branch" and (
        "D" in flags
        or (("--delete" in rest or "d" in flags) and ("--force" in rest or "f" in flags))
    ):
        branches = [t for t in rest if not t.startswith("-")]
        unsafe = [
            b for b in branches if not (known_dir and _branch_is_redundant(cwd, b))
        ]
        if unsafe or not branches:
            return Verdict(
                ASK,
                f"git branch -D {' '.join(unsafe or branches)} force-deletes commits "
                "that no other branch or remote branch contains",
            )
        return None
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


def decide(call: ToolCall) -> Verdict:
    """Evaluate one tool call. Pure apart from git branch lookups."""
    cwd = call.cwd
    guards = _load_project_guards(cwd)
    protected = tuple(
        guards.get("protected_branches") or DEFAULT_PROTECTED_BRANCHES
    )
    production_patterns = guards.get("production_patterns") or []

    if call.kind == "fetch":
        url = call.url
        hit = _production_hit(url, production_patterns)
        if hit:
            return Verdict(
                DENY,
                f"URL matches production pattern {hit!r} — production systems are "
                "off-limits in every mode, with no consent carve-out.",
                always_deny=True,
            )
        return _ALLOW

    if call.kind == "write":
        path = call.path
        normalized = path.replace("\\", "/")
        if normalized.endswith(SESSION_AUTH_REL):
            return Verdict(
                DENY,
                "session-auth.json may only be written by `maverick coord "
                "authorize`, which verifies authorization on the GitHub issue.",
                always_deny=True,
            )
        if _is_guard_config(path):
            return Verdict(ASK, _GUARD_CONFIG_ASK)
        if _is_infra_path(path):
            return Verdict(
                ASK,
                f"{path} is infrastructure (CI/CD, containers, IaC) — "
                f"explicit authorization required. {INFRA_COVERAGE}",
            )
        return _ALLOW

    if call.kind == "shell":
        command = call.command
        hit = _production_hit(command, production_patterns)
        if hit:
            return Verdict(
                DENY,
                f"Command matches production pattern {hit!r} — production systems "
                "are off-limits in every mode, with no consent carve-out.",
                always_deny=True,
            )
        tokens = _shell_tokens(command)
        segments = _segments(tokens) if tokens is not None else None
        expanded = _expand_nested(segments)[0] if segments is not None else None
        plain = expanded is not None and _only_plain_reads(expanded)
        # Protected files are matched by name anywhere in the command, not
        # by parsed write target: a variable, a `cd` or a wrapper can hide
        # the real target from the parser (#167 security review). Names are
        # matched on the raw text and on the dequoted, brace-expanded words,
        # so quoting (`session-auth'.json'`), braces and globs can't hide them.
        names = _name_candidates(command, expanded)
        if not plain and _names_match(names, "session-auth.json"):
            return Verdict(DENY, _SESSION_AUTH_DENY, always_deny=True)
        if (
            not plain
            and _mentions_dir(names, ".maverick")
            and _names_match(names, "config.json")
        ):
            return Verdict(ASK, _GUARD_CONFIG_ASK)
        if tokens is None or segments is None or _unhandled_redirect(tokens):
            return _coarse_shell_verdict(command, cwd, protected)
        verdict = _shell_verdict(segments, cwd, protected)
        if verdict is None and expanded is not None and _is_opaque(expanded):
            coarse = _coarse_shell_verdict(command, cwd, protected)
            verdict = coarse if coarse.decision != ALLOW else None
        if verdict and len(segments) > 1 and not verdict.always_deny:
            verdict.reason = verdict.reason.rstrip(".") + (
                ". The whole compound command was blocked, so none of it ran — "
                "run the unrestricted parts on their own."
            )
        return verdict or _ALLOW

    return _ALLOW


_SESSION_AUTH_DENY = (
    "session-auth.json may only be written by `maverick coord "
    "authorize`, which verifies authorization on the GitHub issue."
)


def _infra_write_verdict(target: str) -> Verdict:
    return Verdict(
        ASK,
        f"command writes to infrastructure path {target!r} — explicit "
        f"authorization required. {INFRA_COVERAGE}",
    )


GUARD_CONFIG_REL = ".maverick/config.json"

#: Deliberately avoids the word "infrastructure": an ``infra`` grant must not
#: unlock edits to the file that defines what the guards allow.
_GUARD_CONFIG_ASK = (
    ".maverick/config.json holds scope_guards (auth_paths_exclude, "
    "auth_scan, protected_branches), so changing it can widen what the guards "
    "allow — a human must approve the change."
)

_NESTED_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_MAX_NESTING = 3


#: Commands that run another command or change where relative paths
#: point. Their real write targets are invisible to argv parsing, so a
#: command using one gets the coarse check as well.
_OPAQUE_COMMANDS = frozenset(
    {"cd", "pushd", "popd", "xargs", "timeout", "nice", "ionice", "stdbuf",
     "parallel", "watch", "flock", "su", "doas", "chroot", "unbuffer", "exec",
     "source", ".",
     # Interpreters running inline code: argv cannot show what they write.
     "python", "python3", "node", "deno", "bun", "php", "ruby", "perl"}
)


_MAX_BRACE_EXPANSION = 64


def _brace_expand(word: str) -> list[str]:
    """Expand ``{a,b}`` alternatives the way the shell would (bounded).

    Only comma lists are expanded. Callers must also check
    :func:`_brace_uncertain`: a sequence (``{a..z}``) or an expansion past
    the bound leaves braces in the result, and those words fail closed.
    """
    results = [word]
    for _ in range(8):  # nesting depth bound
        changed = False
        out: list[str] = []
        for item in results:
            match = re.search(r"\{([^{}]*,[^{}]*)\}", item)
            if not match:
                out.append(item)
                continue
            changed = True
            for alt in match.group(1).split(","):
                out.append(item[: match.start()] + alt + item[match.end():])
        results = out
        if len(results) > _MAX_BRACE_EXPANSION:
            return [word]
        if not changed:
            break
    return results


def _brace_uncertain(word: str) -> bool:
    """Brace expansion of *word* could not be fully resolved."""
    return any(re.search(r"\{[^{}]*(,|\.\.)[^{}]*\}", r) for r in _brace_expand(word))


def _brace_wildcard(word: str) -> str:
    """Replace every brace group with ``*`` (conservative glob stand-in)."""
    previous = None
    while previous != word:
        previous = word
        word = re.sub(r"\{[^{}]*\}", "*", word)
    return word


def _name_candidates(command: str, segments: list[_Segment] | None) -> list[str]:
    """Raw command text plus every dequoted, brace-expanded word.

    Each word with braces also contributes a version with every brace group
    turned into ``*``, so ranges and over-bound expansions still match
    protected names as globs.
    """
    names = [command]
    for seg in segments or []:
        for word in seg.words + seg.redirect_targets:
            names.extend(_brace_expand(word))
            if "{" in word:
                names.append(_brace_wildcard(word))
    return names


def _component_matches(component: str, literal: str) -> bool:
    """*component* is *literal*, contains it, or is a glob matching it.

    A glob needs at least three literal characters, so a bare ``*`` (or a
    ``{}`` placeholder turned into one) never matches.
    """
    if literal in component:
        return True
    if not re.search(r"[*?\[]", component):
        return False
    if len(re.sub(r"[*?\[\]]", "", component)) < 3:
        return False
    return fnmatch.fnmatchcase(literal, component)


def _names_match(names: list[str], filename: str) -> bool:
    """*filename* appears in a candidate literally, or as a glob basename.

    Glob matches count only when the command also names ``.maverick``
    (literally or as a glob), the directory the protected files live in,
    so ``prettier --write *.json`` does not trip it.
    """
    if any(filename in name for name in names):
        return True
    if not _mentions_dir(names, ".maverick"):
        return False
    return any(
        _component_matches(name.replace("\\", "/").rsplit("/", 1)[-1], filename)
        for name in names
    )


def _mentions_dir(names: list[str], dirname: str) -> bool:
    """Some path component of a candidate is *dirname*, literally or as a glob."""
    return any(
        _component_matches(part, dirname)
        for name in names
        for part in name.replace("\\", "/").split("/")
        if part
    )


def _unhandled_redirect(tokens: list[str]) -> bool:
    """Read-write (``<>``) or process-substitution operators: parse can't see targets."""
    return any(
        _is_operator(t) and ("<>" in t or ">(" in t or "<(" in t) for t in tokens
    )


def _is_opaque(segments: list[_Segment]) -> bool:
    """True when argv parsing cannot be trusted to find every write target."""
    for seg in segments:
        if any(re.search(r"[$`*?\[{}~]", t) for t in seg.redirect_targets):
            return True
        words = _strip_prefix(seg.words)
        if len(words) < len(seg.words) and any("$" in w for w in seg.words):
            return True
        if not words:
            # Only assignments: a variable that a later command may write to.
            if seg.words:
                return True
            continue
        name = Path(words[0]).name
        args = words[1:]
        if name in _OPAQUE_COMMANDS:
            return True
        if name == "find" and any(
            a in ("-exec", "-execdir", "-ok", "-okdir", "-delete") or a.startswith("-fprint")
            for a in args
        ):
            return True
        if name in ("perl", "ruby") and any(
            a.startswith("-") and not a.startswith("--") and "i" in a[1:] for a in args
        ):
            return True
        if name in ("awk", "gawk") and ("-i" in args or "inplace" in args):
            return True
        targets = _command_write_targets(words)
        if any(re.search(r"[$`*?\[{}~]", t) for t in targets):
            return True
    return False


def _only_plain_reads(segments: list[_Segment]) -> bool:
    """Every simple command is a known reader with no output redirection."""
    for seg in segments:
        if seg.redirect_targets:
            return False
        if seg.words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg.words[0]):
            return False
        words = _strip_prefix(seg.words)
        if not words:
            return False
        if Path(words[0]).name not in _READ_ONLY_COMMANDS:
            return False
    return True


def _is_guard_config(path: str) -> bool:
    normalized = re.sub(r"^(\./)+", "", path.replace("\\", "/"))
    return normalized == GUARD_CONFIG_REL or normalized.endswith("/" + GUARD_CONFIG_REL)


def _hands_file_to_writer(seg: _Segment, rel: str) -> bool:
    """A command that is not a known reader names *rel* in its arguments."""
    words = _strip_prefix(seg.words)
    return bool(
        words
        and Path(words[0]).name not in _READ_ONLY_COMMANDS
        and words[0] != "git"
        and any(rel in w for w in words[1:])
    )


#: Shell options whose value is the next argument (``bash -o pipefail``).
_SHELL_VALUE_FLAGS = frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"})

#: Sentinel: a ``-c`` is present but its script could not be identified.
_UNKNOWN_SCRIPT = "\x00unknown"


def _shell_c_script(args: list[str]) -> str | None:
    """The script of ``sh -c``, including combined flags (``-lc``, ``-xc``).

    Returns ``None`` when there is no ``-c`` at all, and ``_UNKNOWN_SCRIPT``
    when there is one but no script can be picked out — the caller then
    fails closed.
    """
    has_c = any(
        re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a) for a in args
    )
    if not has_c:
        return None
    seen_c = False
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in _SHELL_VALUE_FLAGS:
            skip = True
            continue
        if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):
            seen_c = True
            continue
        if arg.startswith(("-", "+")) and arg not in ("-", "--"):
            continue
        if arg == "--":
            continue
        if seen_c:
            return arg
        return _UNKNOWN_SCRIPT  # an operand before -c: shape we don't trust
    return _UNKNOWN_SCRIPT


def _expand_nested(
    segments: list[_Segment], depth: int = 0
) -> tuple[list[_Segment], list[str]]:
    """Add the commands inside ``bash -c '…'`` and ``eval …`` as segments.

    Returns the expanded segments and any nested scripts that could not be
    tokenized (those get the coarse check).
    """
    out: list[_Segment] = []
    unparsed: list[str] = []
    for seg in segments:
        out.append(seg)
        words = _strip_prefix(seg.words)
        if not words:
            continue
        name = Path(words[0]).name
        script = None
        if name in _NESTED_SHELLS:
            script = _shell_c_script(words[1:])
        elif name == "eval":
            script = " ".join(words[1:])
        if script == _UNKNOWN_SCRIPT:
            unparsed.append(" ".join(seg.words))  # fail closed: coarse check
            continue
        if not script:
            continue
        tokens = _shell_tokens(script) if depth < _MAX_NESTING else None
        if tokens is None or _unhandled_redirect(tokens):
            unparsed.append(script)
            continue
        inner, inner_unparsed = _expand_nested(_segments(tokens), depth + 1)
        out.extend(inner)
        unparsed.extend(inner_unparsed)
    return out, unparsed


def _shell_verdict(
    segments: list[_Segment], cwd: Path, protected: tuple[str, ...]
) -> Verdict | None:
    """Rule hits for a tokenized shell command, judged per simple command."""
    segments, unparsed = _expand_nested(segments)
    for inner in unparsed:
        verdict = _coarse_shell_verdict(inner, cwd, protected)
        if verdict.decision != ALLOW:
            return verdict
    for seg in segments:
        targets = seg.redirect_targets + _command_write_targets(seg.words)
        if any(t.replace("\\", "/").endswith(SESSION_AUTH_REL) for t in targets):
            return Verdict(DENY, _SESSION_AUTH_DENY, always_deny=True)
        if _hands_file_to_writer(seg, SESSION_AUTH_REL):
            # An interpreter or unknown tool handed the file: assume a write.
            return Verdict(DENY, _SESSION_AUTH_DENY, always_deny=True)
    for seg in segments:
        targets = seg.redirect_targets + _command_write_targets(seg.words)
        if any(_is_guard_config(t) for t in targets) or _hands_file_to_writer(
            seg, GUARD_CONFIG_REL
        ):
            return Verdict(ASK, _GUARD_CONFIG_ASK)
    moves_dir = any(
        (w := _strip_prefix(seg.words)) and Path(w[0]).name in ("cd", "pushd", "popd")
        for seg in segments
    )
    for seg in segments:
        tokens = _git_tokens(seg.words)
        if tokens is not None:
            git_cwd = None if moves_dir else _git_dir(seg.words, cwd)
            verdict = _check_git(tokens, git_cwd or cwd, protected, known_dir=git_cwd is not None)
            if verdict:
                return verdict
    for seg in segments:
        for raw in seg.redirect_targets + _command_write_targets(seg.words):
            if _brace_uncertain(raw):
                return Verdict(
                    ASK,
                    f"cannot resolve the brace expansion in write target {raw!r}, so "
                    f"it may be infrastructure — explicit authorization required. "
                    f"{INFRA_COVERAGE}",
                )
            for target in _brace_expand(raw):
                if _is_infra_path(target):
                    return _infra_write_verdict(target)
    return None


def _coarse_shell_verdict(
    command: str, cwd: Path, protected: tuple[str, ...]
) -> Verdict:
    """Fallback for commands shlex cannot parse (unbalanced quotes).

    Conservative by design: substring write markers, and any token that
    looks like an infra path counts.
    """
    # Descriptor plumbing (2>/dev/null, 2>&1) is never a file write.
    stripped = re.sub(r"\d*>>?\s*/dev/null|\d*>&\d+|&>\s*/dev/null", " ", command)
    writes = any(marker in stripped for marker in _WRITE_MARKERS)
    if SESSION_AUTH_REL in command and writes:
        return Verdict(DENY, _SESSION_AUTH_DENY, always_deny=True)
    if ".maverick" in command and "config.json" in command and writes:
        return Verdict(ASK, _GUARD_CONFIG_ASK)
    for sub in _split_subcommands(command):
        tokens = _git_tokens(sub)
        if tokens is not None:
            verdict = _check_git(tokens, cwd, protected)
            if verdict:
                return verdict
    if writes:
        for candidate in re.findall(r"[\w./\\-]+", command):
            if _is_infra_path(candidate):
                return _infra_write_verdict(candidate)
    return _ALLOW


def resolve(verdict: Verdict, call: ToolCall, env: dict[str, str]) -> Verdict:
    """Apply the interactive-vs-autonomous policy to a rule hit.

    Rules return only *why* an action is restricted; the escalation
    guidance (``ESCALATION``) is added here, exactly once, to every
    decision that needs consent. Rules that also appended it produced a
    message repeating the guidance twice (#151).
    """
    if verdict.decision == ALLOW:
        return verdict
    if verdict.always_deny:
        return Verdict(DENY, verdict.reason, always_deny=True)

    cwd = call.cwd
    # A recorded `infra` grant authorizes infrastructure edits in *any* mode.
    # `maverick coord authorize` only writes it after verifying issue-level
    # authorization, so an explicit grant should suppress the prompt whether
    # the run is classified interactive or autonomous — a misclassification
    # must not defeat an authorization the user has already recorded.
    if "infrastructure" in verdict.reason and "infra" in _session_auth_scopes(cwd):
        return _ALLOW
    if is_autonomous(env, call):
        who = "a subagent" if call.subagent else "MAVERICK_AUTONOMOUS=1"
        return Verdict(
            DENY,
            f"{verdict.reason} (autonomous mode via {who}: denied — no user "
            f"can consent to this call). {ESCALATION}",
        )
    # Interactive: surface the decision to the user.
    return Verdict(ASK, f"{verdict.reason} {ESCALATION}")

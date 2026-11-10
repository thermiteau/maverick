#!/usr/bin/env python3
"""Close the issues a release resolves.

PRs land on ``main``, but the repository's default branch is ``stable``.
GitHub only honours closing keywords (``Closes #N``) for PRs that target
the default branch, and it doesn't even link them for PRs into ``main``.
So issues fixed by merged PRs stayed open. This script runs in
``release-finalize.yml`` after the GitHub Release is created and closes
them itself:

1. Take the squash-merged PRs between the previous ``v*`` tag and the new
   one (each squash subject ends ``(#N)``).
2. Parse each merged PR's body for closing keywords followed by ``#N`` or
   an issue URL in this repository. A PR whose body was edited after it
   merged is skipped: the body is read at release time, and only the
   version the merger saw is trusted — otherwise anyone able to edit a
   merged PR (including a fork's author) could make the release close
   arbitrary issues.
3. Close each referenced issue that is still open, with a "Released in"
   comment. Pull requests and already-closed issues are skipped.

Usage: close_released_issues.py <tag> [--repo owner/name] [--dry-run]

Pure stdlib plus the ``gh`` and ``git`` CLIs. Exits 0 unless the inputs
are unusable; a failure on one issue is reported and the rest continue.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

#: Squash-merge subjects end with the PR number: "feat: thing (#146)".
#: Some carry an issue ref before it — "(#147) (#148)" — so take the last.
_SUBJECT_PR_RE = re.compile(r"\(#(\d+)\)\s*$")

_KEYWORDS = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"


def pr_numbers(subjects: list[str]) -> list[int]:
    """PR numbers from squash-merge commit subjects, in order, de-duplicated."""
    seen: list[int] = []
    for subject in subjects:
        m = _SUBJECT_PR_RE.search(subject)
        if m and int(m.group(1)) not in seen:
            seen.append(int(m.group(1)))
    return seen


def closing_refs(body: str, repo: str) -> list[int]:
    """Issue numbers *body* says it closes, in this repository only.

    Accepts ``Closes #N``, ``Fixes: #N``, ``resolved owner/repo#N`` (this
    repo) and ``Closes https://github.com/owner/repo/issues/N``. References
    to other repositories are ignored.
    """
    repo_re = re.escape(repo)
    pattern = re.compile(
        rf"\b{_KEYWORDS}\s*:?\s+"
        rf"(?:(?P<slug>[\w.-]+/[\w.-]+)?#(?P<n1>\d+)"
        rf"|https://github\.com/(?P<urlrepo>[\w.-]+/[\w.-]+)/issues/(?P<n2>\d+))",
        re.IGNORECASE,
    )
    found: list[int] = []
    for m in pattern.finditer(body or ""):
        target = m.group("slug") or m.group("urlrepo")
        if target and not re.fullmatch(repo_re, target, re.IGNORECASE):
            continue
        number = int(m.group("n1") or m.group("n2"))
        if number not in found:
            found.append(number)
    return found


def body_trusted(pr: dict) -> bool:
    """True when the PR merged and its body was not edited after the merge.

    *pr* has GraphQL ``state``, ``mergedAt`` and ``lastEditedAt`` (ISO 8601
    UTC, same format, so string order is time order).
    """
    if pr.get("state") != "MERGED" or not pr.get("mergedAt"):
        return False
    edited = pr.get("lastEditedAt")
    return not edited or edited <= pr["mergedAt"]


_PR_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)"
    "{pullRequest(number:$number){body state mergedAt lastEditedAt}}}"
)


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def previous_tag(tag: str) -> str | None:
    try:
        out = _run(["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", f"{tag}^"])
    except subprocess.CalledProcessError:
        return None
    return out.strip() or None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tag", help="The release tag just created, e.g. v5.2.0")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--dry-run", action="store_true", help="Print, don't close")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"v\d+\.\d+\.\d+", args.tag):
        print(f"not a release tag: {args.tag!r}", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        print("--repo owner/name is required (or GITHUB_REPOSITORY)", file=sys.stderr)
        return 2

    prev = previous_tag(args.tag)
    if prev is None:
        print(f"no tag before {args.tag}; nothing to do")
        return 0
    subjects = _run(["git", "log", "--format=%s", f"{prev}..{args.tag}"]).splitlines()
    prs = pr_numbers(subjects)
    print(f"{prev}..{args.tag}: PRs {', '.join(f'#{p}' for p in prs) or 'none'}")

    failures = 0
    for pr in prs:
        owner, name = args.repo.split("/", 1)
        try:
            info = json.loads(_run([
                "gh", "api", "graphql", "-f", f"query={_PR_QUERY}",
                "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={pr}",
                "--jq", ".data.repository.pullRequest",
            ]))
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            print(f"#{pr}: could not read PR ({exc}); skipped", file=sys.stderr)
            failures += 1
            continue
        if not isinstance(info, dict) or info.get("state") != "MERGED":
            continue
        if not body_trusted(info):
            print(
                f"#{pr}: body edited after merge ({info.get('lastEditedAt')} > "
                f"{info.get('mergedAt')}); its closing references are ignored",
                file=sys.stderr,
            )
            continue
        for issue in closing_refs(info.get("body") or "", args.repo):
            try:
                data = json.loads(_run(["gh", "api", f"repos/{args.repo}/issues/{issue}"]))
            except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                print(f"#{issue} (from #{pr}): could not read ({exc}); skipped", file=sys.stderr)
                failures += 1
                continue
            if "pull_request" in data:
                continue  # "Closes #N" naming a PR
            if data.get("state") != "open":
                print(f"#{issue} (from #{pr}): already closed")
                continue
            comment = (
                f"Released in [{args.tag}](https://github.com/{args.repo}/releases/tag/{args.tag})"
                f" via #{pr}."
            )
            if args.dry_run:
                print(f"#{issue} (from #{pr}): would close — {comment}")
                continue
            try:
                _run([
                    "gh", "issue", "close", str(issue), "--repo", args.repo,
                    "--reason", "completed", "--comment", comment,
                ])
                print(f"#{issue} (from #{pr}): closed")
            except subprocess.CalledProcessError as exc:
                print(f"#{issue} (from #{pr}): close failed: {exc.stderr.strip()}", file=sys.stderr)
                failures += 1
    if failures:
        print(f"{failures} lookup(s) or close(s) failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

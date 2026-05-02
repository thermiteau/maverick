"""Per-project issue close policy — what happens to a GitHub issue once
its PR has merged.

#46 originally hard-coded "always close on PR merge". That works for
trunk-based and GitHub Flow, but is wrong for repos that:

- Use Gitflow and treat issues as "resolved" only after promotion to
  the default/release branch (not after merge to ``develop``).
- Run a ``develop → staging → main`` chain with environment-specific
  gates and want issues to track promotion state rather than PR state.
- Have policy reasons to keep issues open until a release tag
  (compliance, customer-facing changelog, manual sign-off).

This module externalises the close decision to a per-project config
field so different repos can run the same skill with different policies.
The audit comment and the ``merged-to-<branch>`` label fire
unconditionally — that piece of the trail is policy-independent so
``label:merged-to-develop`` lets humans find work pending promotion
even when the close itself is deferred.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from maverick.config import ISSUE_CLOSE_POLICIES, init_config

DEFAULT_POLICY = "on_pr_merge"


@dataclass
class CloseDecision:
    """Outcome of an issue-close-on-merge run, returned to the caller for
    audit-trail JSON output."""

    policy: str
    target_branch: str
    default_branch: str
    closed: bool
    skip_reason: str  # empty when closed=True
    comment_posted: bool
    label_applied: str  # the label name actually applied


def get_policy(cfg: dict[str, Any] | None = None) -> str:
    """Return the project's issue close policy. Falls back to the default
    if the field is missing or unrecognised. Never raises — `init_config`
    handles missing files and `_apply_defaults` fills missing keys.
    """
    loaded: Any = cfg if cfg is not None else init_config(require_aws=False)
    raw = loaded.get("issue_lifecycle", {}).get("close_policy", DEFAULT_POLICY)
    if raw not in ISSUE_CLOSE_POLICIES:
        return DEFAULT_POLICY
    return raw


def decide_close(
    policy: str, target_branch: str, default_branch: str
) -> tuple[bool, str]:
    """Pure decision function — given the policy and the branch the PR
    merged into, return ``(should_close, skip_reason)``. ``skip_reason``
    is empty when ``should_close`` is True.

    Centralised here (rather than inlined in ``close_on_merge``) so the
    decision is independently testable and so other surfaces (e.g.
    ``do-epic`` Phase 6) can reuse the same logic.
    """
    if policy == "manual":
        return False, "policy=manual"
    if policy == "on_default_branch_merge":
        if target_branch == default_branch:
            return True, ""
        return (
            False,
            f"policy=on_default_branch_merge and target {target_branch!r} "
            f"is not the default branch {default_branch!r}",
        )
    # on_pr_merge (and any unrecognised value, which get_policy already
    # collapses to the default).
    return True, ""


def _label_for_branch(target_branch: str) -> str:
    """The label applied to every closed-or-pending issue, naming the
    branch the PR merged into. Lets ``gh issue list -l merged-to-develop``
    surface work pending promotion when ``manual`` or
    ``on_default_branch_merge`` defers the close.
    """
    return f"merged-to-{target_branch}"


def close_on_merge(
    repo: str,
    issue: int,
    pr_num: int,
    target_branch: str,
    default_branch: str,
    *,
    cfg: dict[str, Any] | None = None,
    gh_runner: Any = None,
) -> CloseDecision:
    """Run the post-merge issue-lifecycle steps and return what was done.

    Always (regardless of policy):
      1. Posts an audit comment on the issue:
         "Resolved in PR #<P>; merged to <branch>."
      2. Applies the ``merged-to-<branch>`` label.

    Then, per policy, optionally closes the issue. ``gh issue close`` on
    an already-closed issue is a no-op, so this is safe even on
    default-branch merges where GitHub's native ``Closes #N`` already
    closed it.

    `gh_runner` is the function used to execute `gh` (default: subprocess).
    Tests can inject a fake to avoid network calls.
    """
    if gh_runner is None:
        gh_runner = _default_gh_runner

    label = _label_for_branch(target_branch)
    comment = f"Resolved in PR #{pr_num}; merged to {target_branch}."

    # Audit comment + label fire unconditionally so the trail is
    # policy-independent.
    gh_runner(
        "issue", "comment", str(issue), "--repo", repo, "--body", comment
    )
    # `gh` exits non-zero if the label doesn't exist. Create-if-missing
    # is part of the contract: humans can grep for `merged-to-<branch>`
    # without having to seed the label set in advance.
    _ensure_label(repo, label, gh_runner=gh_runner)
    gh_runner(
        "issue", "edit", str(issue), "--repo", repo, "--add-label", label
    )

    policy = get_policy(cfg)
    should_close, skip_reason = decide_close(policy, target_branch, default_branch)
    if should_close:
        gh_runner("issue", "close", str(issue), "--repo", repo)

    return CloseDecision(
        policy=policy,
        target_branch=target_branch,
        default_branch=default_branch,
        closed=should_close,
        skip_reason=skip_reason,
        comment_posted=True,
        label_applied=label,
    )


def _default_gh_runner(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the user's ``gh`` (not the App's ``gh-app gh``) — issue close +
    comment are author-attributed actions and the App identity is
    deliberately reserved for review/merge gates.
    """
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    )


def _ensure_label(repo: str, label: str, gh_runner: Any) -> None:
    """Create the label if it doesn't already exist on the repo. ``gh
    label create`` exits non-zero if the label is already present, so
    catch that and proceed.
    """
    try:
        gh_runner("label", "create", label, "--repo", repo, "--color", "ededed")
    except subprocess.CalledProcessError:
        # Already exists — fine.
        pass


def decision_to_json(d: CloseDecision) -> str:
    """JSON serialisation for the CLI surface — emits a stable shape so
    skill bodies can parse and audit the outcome."""
    return json.dumps(
        {
            "policy": d.policy,
            "target_branch": d.target_branch,
            "default_branch": d.default_branch,
            "closed": d.closed,
            "skip_reason": d.skip_reason,
            "comment_posted": d.comment_posted,
            "label_applied": d.label_applied,
        },
        indent=2,
        sort_keys=True,
    )

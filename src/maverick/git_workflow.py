"""Per-project git workflow configuration — resolves branching parameters
from ``.maverick/config.json`` so skills don't hard-code ``main``.

The pain point: ``do-issue-solo`` Phase 8 PRs to ``main``, worktree
bases default to ``main``, and ``mav-git-workflow`` branch creation
assumes ``main``.  All three read from the ``git_workflow`` config
block instead.

Design decision: explicit config wins over auto-detect.  ``maverick
init`` proposes values from detection (default branch, recent PR
history) and writes them to disk; at runtime the config is read
verbatim with no re-detection.
"""

from __future__ import annotations

from typing import Any

from maverick.config import _DEFAULT_BRANCH_PREFIXES, init_config


def _get_gw(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load the ``git_workflow`` block, falling back to defaults."""
    loaded: Any = cfg if cfg is not None else init_config(require_aws=False)
    return loaded.get("git_workflow", {})


def get_story_base(cfg: dict[str, Any] | None = None) -> str:
    """Branch to create feature/fix branches from (e.g. ``develop``)."""
    return _get_gw(cfg).get("story_base", "main") or "main"


def get_pr_target(cfg: dict[str, Any] | None = None) -> str:
    """Default ``--base`` for ``gh pr create``."""
    return _get_gw(cfg).get("pr_target", "main") or "main"


def get_promotion_chain(cfg: dict[str, Any] | None = None) -> list[str]:
    """Ordered list of promotion branches."""
    chain = _get_gw(cfg).get("promotion_chain", ["main"])
    if isinstance(chain, list) and chain:
        return chain
    return ["main"]


def get_branch_prefix(label: str, cfg: dict[str, Any] | None = None) -> str:
    """Resolve a branch prefix for a given issue label or keyword.

    Returns the configured prefix for the label, or ``"feat"`` as the
    default when no mapping exists.
    """
    prefixes = _get_gw(cfg).get("branch_prefixes", _DEFAULT_BRANCH_PREFIXES)
    if not isinstance(prefixes, dict):
        prefixes = _DEFAULT_BRANCH_PREFIXES
    return prefixes.get(label.lower(), "feat")


def get_branch_prefixes(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Return the full label → prefix mapping."""
    prefixes = _get_gw(cfg).get("branch_prefixes", _DEFAULT_BRANCH_PREFIXES)
    if isinstance(prefixes, dict):
        return prefixes
    return dict(_DEFAULT_BRANCH_PREFIXES)

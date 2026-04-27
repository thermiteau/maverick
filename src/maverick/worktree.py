"""Git worktree helpers — create, destroy, list.

Maverick uses one worktree per story so stories in a wave can run in parallel
without stepping on each other. Worktrees live under `.maverick/worktrees/`
at the repo root so they are easy to find and clean up.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

WORKTREE_ROOT = Path(".maverick/worktrees")


@dataclass
class Worktree:
    path: Path
    branch: str
    head: str


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, cwd=cwd
    )
    return result.stdout


def repo_root() -> Path:
    """Absolute path to the repo's top-level working directory."""
    return Path(_git("rev-parse", "--show-toplevel").strip())


def default_branch() -> str:
    """Best-effort lookup of the repo's default branch via `gh`, falling back
    to `origin/HEAD`. Callers should treat this as the base to branch from.
    """
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    out = _git("symbolic-ref", "refs/remotes/origin/HEAD").strip()
    return out.rsplit("/", 1)[-1] if out else "main"


def create(branch: str, base: str | None = None) -> Worktree:
    """Create a worktree at `.maverick/worktrees/<branch>` on a new branch
    off `base` (default: the repo's default branch).
    """
    if base is None:
        base = default_branch()
    # Refresh base so we branch off the tip of origin/<base>
    _git("fetch", "origin", base)
    root = repo_root()
    path = root / WORKTREE_ROOT / branch.replace("/", "__")
    path.parent.mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-b", branch, str(path), f"origin/{base}", cwd=root)
    head = _git("rev-parse", "HEAD", cwd=path).strip()
    return Worktree(path=path, branch=branch, head=head)


def destroy(path: Path, force: bool = False) -> None:
    """Remove a worktree. Use `force=True` only if a clean removal fails
    because the working tree is dirty."""
    root = repo_root()
    args = ["worktree", "remove", str(path)]
    if force:
        args.insert(2, "--force")
    _git(*args, cwd=root)


def list_worktrees() -> list[Worktree]:
    """List all worktrees managed by the repo, parsed from `git worktree list --porcelain`."""
    out = _git("worktree", "list", "--porcelain")
    trees: list[Worktree] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            if current.get("worktree"):
                trees.append(
                    Worktree(
                        path=Path(current["worktree"]),
                        branch=current.get("branch", "").removeprefix("refs/heads/"),
                        head=current.get("HEAD", ""),
                    )
                )
            current = {}
            continue
        if line.startswith("worktree "):
            current["worktree"] = line.removeprefix("worktree ").strip()
        elif line.startswith("HEAD "):
            current["HEAD"] = line.removeprefix("HEAD ").strip()
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch ").strip()
    if current.get("worktree"):
        trees.append(
            Worktree(
                path=Path(current["worktree"]),
                branch=current.get("branch", "").removeprefix("refs/heads/"),
                head=current.get("HEAD", ""),
            )
        )
    return trees


def ensure_available() -> None:
    """Verify `git worktree` is usable in this checkout. Raises RuntimeError
    if worktrees cannot be created (e.g. inside a shallow clone or unsupported
    git version).
    """
    try:
        _git("worktree", "list")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git worktree unavailable: {e.stderr.strip()}") from e

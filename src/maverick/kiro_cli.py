"""``maverick kiro install|uninstall|status`` — manage Maverick's Kiro bundle.

Kiro has no plugin format that can carry agents (Powers hold only skills and
MCP config), so the CLI installs the bundle itself: it renders the KIRO
target from the skill/agent sources shipped in this package and copies the
result into ``~/.kiro/skills/`` and ``~/.kiro/agents/``. Rendering from the
installed CLI keeps the bundle and the CLI on the same version.

``~/.kiro/maverick/manifest.json`` records what Maverick installed, so an
upgrade removes skills/agents a newer version dropped, an uninstall removes
only Maverick's files, and a user's own skill or agent with the same name is
never overwritten without ``--force``.

The project-level scope guard is separate: ``maverick init --runtime kiro``.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path

from maverick.targets import KIRO, KIRO_HOME, KIRO_MANIFEST


@dataclass
class Manifest:
    version: str = ""
    skills: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, home: Path) -> Manifest | None:
        try:
            raw = json.loads((home / KIRO_MANIFEST).read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        return cls(
            version=str(raw.get("version") or ""),
            skills=[str(s) for s in raw.get("skills") or []],
            agents=[str(a) for a in raw.get("agents") or []],
        )

    def save(self, home: Path) -> None:
        path = home / KIRO_MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": self.version, "skills": self.skills, "agents": self.agents}
        path.write_text(json.dumps(data, indent=2) + "\n")


@dataclass
class InstallResult:
    installed_skills: list[str] = field(default_factory=list)
    installed_agents: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # foreign files kept


def _cli_version() -> str:
    from maverick.cli import _get_version

    return _get_version()


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def install(home: Path, force: bool = False) -> InstallResult:
    """Render the Kiro bundle and install it under *home* (normally ~/.kiro)."""
    from maverick.registry import render_target

    previous = Manifest.load(home) or Manifest()
    owned_skills, owned_agents = set(previous.skills), set(previous.agents)
    result = InstallResult()

    with tempfile.TemporaryDirectory(prefix="maverick-kiro-") as tmp:
        staging = Path(tmp)
        render_target(KIRO, staging)
        new_skills = sorted(p.name for p in (staging / KIRO.skills_dir).iterdir() if p.is_dir())
        new_agents = sorted(p.name for p in (staging / KIRO.agents_dir).glob("*.md"))

        # Drop what an older Maverick installed and this version no longer ships.
        for name in sorted(owned_skills - set(new_skills)):
            _remove(home / KIRO.skills_dir / name)
            result.removed.append(f"{KIRO.skills_dir}/{name}")
        for name in sorted(owned_agents - set(new_agents)):
            _remove(home / KIRO.agents_dir / name)
            result.removed.append(f"{KIRO.agents_dir}/{name}")

        for kind, names, owned, bucket in (
            (KIRO.skills_dir, new_skills, owned_skills, result.installed_skills),
            (KIRO.agents_dir, new_agents, owned_agents, result.installed_agents),
        ):
            for name in names:
                dest = home / kind / name
                if dest.exists() and name not in owned and not force:
                    result.skipped.append(f"{kind}/{name}")
                    continue
                _remove(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = staging / kind / name
                if src.is_dir():
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
                bucket.append(name)

    Manifest(
        version=_cli_version(),
        skills=result.installed_skills,
        agents=result.installed_agents,
    ).save(home)
    return result


def uninstall(home: Path) -> list[str]:
    """Remove everything the manifest says Maverick installed. Returns paths removed."""
    manifest = Manifest.load(home)
    if manifest is None:
        return []
    removed = []
    for kind, names in ((KIRO.skills_dir, manifest.skills), (KIRO.agents_dir, manifest.agents)):
        for name in names:
            path = home / kind / name
            if path.exists():
                _remove(path)
                removed.append(f"{kind}/{name}")
    manifest_path = home / KIRO_MANIFEST
    manifest_path.unlink()
    try:
        manifest_path.parent.rmdir()  # only if empty
    except OSError:
        pass
    return removed


def main(args: Namespace) -> int:
    home = Path(args.home).expanduser() if args.home else Path(KIRO_HOME).expanduser()

    if args.kiro_action == "install":
        result = install(home, force=args.force)
        print(
            f"Installed Maverick {_cli_version()} for Kiro into {home}: "
            f"{len(result.installed_skills)} skills, {len(result.installed_agents)} agents."
        )
        for path in result.removed:
            print(f"  removed (no longer shipped): {path}")
        if result.skipped:
            print(
                "  skipped (exists and was not installed by Maverick; "
                "re-run with --force to replace):",
                file=sys.stderr,
            )
            for path in result.skipped:
                print(f"    {path}", file=sys.stderr)
        print(
            "For the scope guard, run `maverick init --runtime kiro` in each project."
        )
        return 0

    if args.kiro_action == "uninstall":
        removed = uninstall(home)
        if not removed:
            print(f"Nothing to uninstall: no Maverick manifest in {home}.")
        else:
            print(f"Removed {len(removed)} Maverick skills/agents from {home}.")
        return 0

    manifest = Manifest.load(home)
    if manifest is None:
        print(f"Maverick is not installed for Kiro in {home}. Run `maverick kiro install`.")
        return 1
    cli = _cli_version()
    print(
        f"Maverick {manifest.version} for Kiro in {home}: "
        f"{len(manifest.skills)} skills, {len(manifest.agents)} agents."
    )
    if manifest.version != cli:
        print(
            f"The installed CLI is {cli}; run `maverick kiro install` to update the bundle.",
            file=sys.stderr,
        )
        return 1
    return 0

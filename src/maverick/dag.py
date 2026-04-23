"""Epic DAG — parse, persist, walk.

An epic's dependency graph is persisted to its `maverick-dag` marker as JSON.
This module parses that payload, walks it for descendants and waves, and
provides helpers used by `do-epic` and `mav-block-propagation`.

Payload shape:

    {
        "epic": 123,
        "stories": {
            "140": {"deps": [], "files": ["app/src/boot.ts"]},
            "142": {"deps": ["140"], "files": ["app/src/admin/guard.ts"]},
            "143": {"deps": ["140"], "files": ["app/src/admin/panel.ts"]},
            "150": {"deps": ["142", "143"], "files": ["app/src/admin/index.ts"]}
        }
    }

Story IDs are strings in the payload (GitHub issue numbers as strings) to
survive the JSON round-trip cleanly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maverick.gh_state import latest_marker, post_marker, update_marker


@dataclass
class Dag:
    epic: int
    stories: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"epic": self.epic, "stories": self.stories}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Dag:
        return cls(epic=int(payload["epic"]), stories=dict(payload.get("stories") or {}))

    def deps_of(self, story: str) -> list[str]:
        node = self.stories.get(story)
        if not node:
            return []
        return list(node.get("deps") or [])

    def dependents_of(self, story: str) -> list[str]:
        """Direct children — every story whose deps list contains `story`."""
        return [sid for sid, node in self.stories.items() if story in (node.get("deps") or [])]

    def transitive_descendants(self, story: str) -> set[str]:
        """Every story reachable downstream from `story` via deps edges."""
        seen: set[str] = set()
        frontier = [story]
        while frontier:
            current = frontier.pop()
            for child in self.dependents_of(current):
                if child in seen:
                    continue
                seen.add(child)
                frontier.append(child)
        return seen

    def waves(self) -> list[list[str]]:
        """Topologically group stories so that each wave's members have no
        un-satisfied deps on later waves. Stories with all deps in earlier
        waves share a wave. Cycle-safe: stories that would cycle are left
        out of all waves (callers should treat the set-difference as broken).
        """
        placed: dict[str, int] = {}
        remaining = set(self.stories.keys())
        wave_index = 0
        # bounded by the number of stories — prevents infinite loop on cycles
        for _ in range(len(self.stories) + 1):
            if not remaining:
                break
            next_wave: list[str] = []
            for sid in sorted(remaining):
                deps = self.deps_of(sid)
                if all(d in placed for d in deps):
                    next_wave.append(sid)
            if not next_wave:
                break  # cycle or all deps external — stop cleanly
            for sid in next_wave:
                placed[sid] = wave_index
            remaining -= set(next_wave)
            wave_index += 1
        grouped: dict[int, list[str]] = defaultdict(list)
        for sid, wave in placed.items():
            grouped[wave].append(sid)
        return [sorted(grouped[i]) for i in sorted(grouped.keys())]

    def shares_files(self, a: str, b: str) -> bool:
        """True if stories `a` and `b` declare any overlapping file paths."""
        fa = set(self.stories.get(a, {}).get("files") or [])
        fb = set(self.stories.get(b, {}).get("files") or [])
        return bool(fa & fb)


def load_dag(repo: str, epic: int) -> Dag | None:
    """Fetch the current DAG from the epic's `maverick-dag` marker."""
    m = latest_marker(repo, epic, "maverick-dag")
    if m is None:
        return None
    return Dag.from_payload(m.payload)


def persist_dag(
    repo: str, dag: Dag, env: dict[str, str] | None = None, preamble: str = ""
) -> int:
    """Post or update the `maverick-dag` marker on the epic issue."""
    existing = latest_marker(repo, dag.epic, "maverick-dag")
    if existing is None:
        return post_marker(
            repo, dag.epic, "maverick-dag", dag.to_payload(), preamble=preamble, env=env
        )
    update_marker(
        repo, existing.comment_id, "maverick-dag", dag.to_payload(), preamble=preamble, env=env
    )
    return existing.comment_id

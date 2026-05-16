"""Epic-state persistence — local cache at .claude/epic-state.json mirrored
to a rolling `maverick-state` comment on the epic issue.

GitHub is the source of truth; the local file is a cache to reduce API
traffic during a single session. Any instance can reconstruct the full
state by reading only the GitHub marker.

Schema:

    {
        "epic": 123,
        "stories": {
            "140": "merged",
            "142": "in_flight",
            "143": "ejected",
            "150": "blocked"
        },
        "updated_at": "2026-04-23T10:15:00Z"
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from maverick.gh_state import latest_marker, upsert_marker

Status = Literal["pending", "in_flight", "merged", "ejected", "blocked"]

LOCAL_STATE_PATH = Path(".claude/epic-state.json")


@dataclass
class EpicState:
    epic: int
    stories: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "epic": self.epic,
            "stories": dict(self.stories),
            "updated_at": self.updated_at or _now_iso(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> EpicState:
        return cls(
            epic=int(payload["epic"]),  # type: ignore[arg-type]
            stories=dict(payload.get("stories") or {}),  # type: ignore[arg-type]
            updated_at=str(payload.get("updated_at") or ""),
        )

    def set_status(self, story: str, status: Status) -> None:
        self.stories[story] = status
        self.updated_at = _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_local(path: Path = LOCAL_STATE_PATH) -> EpicState | None:
    if not path.exists():
        return None
    return EpicState.from_payload(json.loads(path.read_text()))


def save_local(state: EpicState, path: Path = LOCAL_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_payload(), indent=2, sort_keys=True))
    tmp.replace(path)


def hydrate_from_gh(repo: str, epic: int) -> EpicState | None:
    """Pull the latest `maverick-state` marker from GitHub; return None if absent."""
    m = latest_marker(repo, epic, "maverick-state")
    if m is None:
        return None
    return EpicState.from_payload(m.payload)


def mirror_to_gh(
    repo: str, state: EpicState, env: dict[str, str] | None = None
) -> int:
    """Upsert the `maverick-state` marker on the epic issue; return comment id."""
    return upsert_marker(
        repo,
        state.epic,
        "maverick-state",
        state.to_payload(),
        preamble="<!-- maverick epic-state snapshot -->",
        env=env,
    )


def transition(
    repo: str,
    state: EpicState,
    story: str,
    status: Status,
    env: dict[str, str] | None = None,
) -> None:
    """Update status, mirror to GH, cache locally — the canonical state write."""
    state.set_status(story, status)
    save_local(state)
    mirror_to_gh(repo, state, env=env)

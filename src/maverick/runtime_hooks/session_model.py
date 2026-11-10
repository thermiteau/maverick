"""Record which model a session is actually running on.

Workflow reports used to label every row with ``llm.default`` from the
config — a hard-coded model id — so a report could not say which model did
the work. The runtime knows: Claude Code puts the model on the SessionStart
payload, and every assistant turn in the session transcript names its
model. Hooks record it here, keyed by instance id, and
``report_cli._current_llm`` reads it back.

Everything in this module is best-effort: a failure to detect or record a
model must never break a hook or a report write.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

#: How much of the transcript tail to scan for the latest assistant turn.
_TAIL_BYTES = 512 * 1024

#: Placeholder models the runtime writes for non-model turns.
_IGNORED = frozenset({"<synthetic>", ""})


def registry_path() -> Path:
    return Path("~/.maverick/session-models.json").expanduser()


def model_from_transcript(transcript: str | Path) -> str | None:
    """The model of the most recent assistant turn in a JSONL transcript."""
    path = Path(transcript)
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > _TAIL_BYTES:
                fh.seek(size - _TAIL_BYTES)
                fh.readline()  # drop the partial first line
            lines = fh.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"model"' not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = row.get("message") if isinstance(row, dict) else None
        model = message.get("model") if isinstance(message, dict) else None
        if isinstance(model, str) and model not in _IGNORED:
            return model
    return None


def _load(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def record(instance: str, model: str, path: Path | None = None) -> None:
    """Store *model* as the current model for *instance* (atomic write)."""
    if not instance or not model or model in _IGNORED:
        return
    target = path or registry_path()
    data = _load(target)
    if data.get(instance, {}).get("model") == model:
        return
    data[instance] = {"model": model, "updated": int(time.time())}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".session-models.")
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, target)
    except OSError:
        pass


def lookup(instance: str | None, path: Path | None = None) -> str | None:
    """The recorded model for *instance*, or None."""
    if not instance:
        return None
    entry = _load(path or registry_path()).get(instance)
    model = entry.get("model") if isinstance(entry, dict) else None
    return model if isinstance(model, str) and model else None

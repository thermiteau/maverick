"""Tests for maverick.epic_state — local cache round-trip."""

import json
from pathlib import Path

from maverick import epic_state as es
from maverick.epic_state import EpicState, load_local, save_local


class TestEpicState:
    def test_set_status_updates_timestamp(self):
        s = EpicState(epic=1)
        s.set_status("140", "merged")
        assert s.stories["140"] == "merged"
        assert s.updated_at != ""

    def test_payload_round_trip(self):
        s = EpicState(epic=42, stories={"1": "merged", "2": "in_flight"})
        s.updated_at = "2026-04-23T10:00:00Z"
        restored = EpicState.from_payload(s.to_payload())
        assert restored.epic == 42
        assert restored.stories == {"1": "merged", "2": "in_flight"}
        assert restored.updated_at == "2026-04-23T10:00:00Z"


class TestLocalPersistence:
    def test_save_then_load(self, tmp_path: Path):
        p = tmp_path / "epic-state.json"
        s = EpicState(epic=99, stories={"x": "blocked"}, updated_at="2026-04-23T00:00:00Z")
        save_local(s, path=p)
        loaded = load_local(path=p)
        assert loaded is not None
        assert loaded.epic == 99
        assert loaded.stories == {"x": "blocked"}

    def test_load_returns_none_when_missing(self, tmp_path: Path):
        assert load_local(path=tmp_path / "nope.json") is None

    def test_save_is_atomic(self, tmp_path: Path):
        p = tmp_path / "state.json"
        s = EpicState(epic=1, stories={"a": "merged"})
        save_local(s, path=p)
        assert p.exists()
        # tmp file should have been renamed away
        assert not (tmp_path / "state.json.tmp").exists()
        assert "merged" in json.loads(p.read_text())["stories"].values()


class TestLocalCachePath:
    """The cache is runtime-neutral (.maverick/), not under Claude's .claude/."""

    def test_saves_under_maverick_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        es.save_local(es.EpicState(epic=7, stories={"8": "pending"}))
        assert (tmp_path / ".maverick" / "epic-state.json").is_file()
        assert not (tmp_path / ".claude").exists()

    def test_reads_legacy_cache(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        es.save_local(es.EpicState(epic=7, stories={"8": "merged"}), es.LEGACY_LOCAL_STATE_PATH)
        state = es.load_local()
        assert state is not None and state.stories == {"8": "merged"}

    def test_new_cache_wins_over_legacy(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        es.save_local(es.EpicState(epic=7, stories={"8": "pending"}), es.LEGACY_LOCAL_STATE_PATH)
        es.save_local(es.EpicState(epic=7, stories={"8": "merged"}))
        assert es.load_local().stories == {"8": "merged"}

"""Tests for the session-release handler — must never raise."""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from maverick.runtime_hooks import session_release


@pytest.fixture
def registry(tmp_path):
    return tmp_path / "active-claims.json"


def _write_claims(registry, claims):
    registry.write_text(json.dumps({"claims": claims}))


class TestSessionRelease:
    def test_no_registry_is_silent_noop(self, registry):
        with patch.object(session_release.subprocess, "run") as run:
            out = session_release.handle(registry)
        run.assert_not_called()
        assert out.stdout == "" and out.stderr == ""

    def test_empty_claims_is_noop(self, registry):
        _write_claims(registry, [])
        with patch.object(session_release.subprocess, "run") as run:
            session_release.handle(registry)
        run.assert_not_called()

    def test_runs_release_all_when_claims_exist(self, registry):
        _write_claims(registry, [{"repo": "o/r", "issue": 1, "instance_id": "x"}])
        with patch.object(session_release.subprocess, "run") as run:
            run.return_value.stdout = "1 claim(s) released"
            out = session_release.handle(registry)
        args = run.call_args[0][0]
        assert args == [
            sys.executable, "-m", "maverick.cli",
            "coord", "release-all", "--reason", "session-end",
        ]
        assert "1 claim(s) released" in out.stderr

    def test_cli_error_never_raises(self, registry):
        _write_claims(registry, [{"repo": "o/r", "issue": 1, "instance_id": "x"}])
        with patch.object(session_release.subprocess, "run", side_effect=OSError("boom")):
            out = session_release.handle(registry)
        assert "lease expiry" in out.stderr

    def test_corrupt_registry_is_noop(self, registry):
        registry.write_text("{corrupt")
        with patch.object(session_release.subprocess, "run") as run:
            session_release.handle(registry)
        run.assert_not_called()

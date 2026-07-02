"""Tests for the SessionEnd release hook — must always exit 0."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "maverick"
    / "hooks"
    / "session_release.py"
)


@pytest.fixture
def hook(tmp_path):
    spec = importlib.util.spec_from_file_location("session_release_hook", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.CLAIMS_REGISTRY = tmp_path / "active-claims.json"
    yield module
    sys.modules.pop(spec.name, None)


def _write_claims(hook, claims):
    hook.CLAIMS_REGISTRY.write_text(json.dumps({"claims": claims}))


class TestSessionRelease:
    def test_no_registry_is_silent_noop(self, hook):
        with patch.object(hook.subprocess, "run") as run:
            assert hook.main() == 0
        run.assert_not_called()

    def test_empty_claims_is_noop(self, hook):
        _write_claims(hook, [])
        with patch.object(hook.subprocess, "run") as run:
            assert hook.main() == 0
        run.assert_not_called()

    def test_runs_release_all_when_claims_exist(self, hook):
        _write_claims(hook, [{"repo": "o/r", "issue": 1, "instance_id": "x"}])
        with (
            patch.object(hook, "_cli_command", return_value=["maverick"]),
            patch.object(hook.subprocess, "run") as run,
        ):
            run.return_value.stdout = "1 claim(s) released"
            assert hook.main() == 0
        args = run.call_args[0][0]
        assert args == ["maverick", "coord", "release-all", "--reason", "session-end"]

    def test_cli_missing_still_exits_zero(self, hook, capsys):
        _write_claims(hook, [{"repo": "o/r", "issue": 1, "instance_id": "x"}])
        with patch.object(hook, "_cli_command", return_value=None):
            assert hook.main() == 0
        assert "lease expiry" in capsys.readouterr().err

    def test_cli_error_still_exits_zero(self, hook):
        _write_claims(hook, [{"repo": "o/r", "issue": 1, "instance_id": "x"}])
        with (
            patch.object(hook, "_cli_command", return_value=["maverick"]),
            patch.object(hook.subprocess, "run", side_effect=OSError("boom")),
        ):
            assert hook.main() == 0

    def test_corrupt_registry_is_noop(self, hook):
        hook.CLAIMS_REGISTRY.write_text("{corrupt")
        with patch.object(hook.subprocess, "run") as run:
            assert hook.main() == 0
        run.assert_not_called()

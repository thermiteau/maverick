"""Tests for maverick.cli — argument parsing and command dispatch."""

from __future__ import annotations

import pytest

from maverick.cli import main


class TestCliParsing:
    """Test that the CLI parser accepts and rejects the expected arguments."""

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            from unittest.mock import patch

            with patch("sys.argv", ["maverick"]):
                main()

    def test_init_dry_run(self, monkeypatch: pytest.MonkeyPatch):
        from unittest.mock import MagicMock, patch

        mock_init = MagicMock()
        monkeypatch.setattr("sys.argv", ["maverick", "init", "--dry-run"])

        with patch("maverick.init.main", mock_init):
            main()
        assert mock_init.called
        args = mock_init.call_args[0][0]
        assert args.dry_run is True

    def test_init_with_override(self, monkeypatch: pytest.MonkeyPatch):
        from unittest.mock import MagicMock, patch

        mock_init = MagicMock()
        monkeypatch.setattr("sys.argv", ["maverick", "init", "--override", "nodejs", "python"])

        with patch("maverick.init.main", mock_init):
            main()
        args = mock_init.call_args[0][0]
        assert args.override == ["nodejs", "python"]

    def test_plugin_install(self, monkeypatch: pytest.MonkeyPatch):
        from unittest.mock import MagicMock, patch

        mock_plugin = MagicMock()
        monkeypatch.setattr("sys.argv", ["maverick", "plugin", "install", "--dev"])

        with patch("maverick.plugin.main", mock_plugin):
            main()
        mock_plugin.assert_called_once_with("install", dev=True, clean=False)

    def test_clean_dry_run(self, monkeypatch: pytest.MonkeyPatch):
        from unittest.mock import MagicMock, patch

        mock_clean = MagicMock()
        monkeypatch.setattr("sys.argv", ["maverick", "clean", "--dry-run"])

        with patch("maverick.init.clean", mock_clean):
            main()
        mock_clean.assert_called_once_with(dry_run=True)

    def test_invalid_plugin_action(self):
        from unittest.mock import patch

        with patch("sys.argv", ["maverick", "plugin", "invalid"]):
            with pytest.raises(SystemExit):
                main()

    @pytest.mark.parametrize(
        "argv",
        [
            ["maverick", "issue", "policy"],
            ["maverick", "task-progress", "read", "owner/repo", "1"],
            ["maverick", "coord", "read", "owner/repo", "1"],
        ],
    )
    def test_subcommand_dispatches_to_coord_cli(self, monkeypatch, argv):
        """All coord_cli-owned top-level subcommands must be in the dispatch
        allow-list in cli.py. Regression for the silent-exit bug where
        `maverick issue policy` would exit 0 without running anything
        because the subcommand wasn't routed."""
        from unittest.mock import MagicMock, patch

        mock_dispatch = MagicMock(return_value=0)
        monkeypatch.setattr("sys.argv", argv)

        with patch("maverick.coord_cli.dispatch", mock_dispatch):
            with pytest.raises(SystemExit) as excinfo:
                main()

        assert excinfo.value.code == 0
        assert mock_dispatch.called

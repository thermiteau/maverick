"""Tests for maverick.cli — argument parsing and command dispatch."""

from __future__ import annotations

import pytest

from maverick.cli import main


class TestCliParsing:
    """Test that the CLI parser accepts and rejects the expected arguments."""

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            import sys
            from unittest.mock import patch

            with patch("sys.argv", ["maverick"]):
                main()

    def test_init_dry_run(self, monkeypatch: pytest.MonkeyPatch):
        import sys
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
        import sys
        from unittest.mock import patch

        with patch("sys.argv", ["maverick", "plugin", "invalid"]):
            with pytest.raises(SystemExit):
                main()

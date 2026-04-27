"""Tests for maverick.gh_state — marker parser and formatter."""

import pytest

from maverick.gh_state import MARKER_KINDS, format_marker, parse_body


class TestParseBody:
    def test_returns_none_when_marker_absent(self):
        assert parse_body("just a comment, no markers here", "maverick-state") is None

    def test_extracts_simple_marker(self):
        body = """Hello.

```maverick-state
{"epic": 123, "stories": {}}
```
"""
        assert parse_body(body, "maverick-state") == {"epic": 123, "stories": {}}

    def test_ignores_different_kind(self):
        body = """
```maverick-dag
{"epic": 1}
```
"""
        assert parse_body(body, "maverick-state") is None

    def test_returns_first_marker_when_multiple_of_kind(self):
        body = """
```maverick-state
{"epic": 1}
```
then
```maverick-state
{"epic": 2}
```
"""
        assert parse_body(body, "maverick-state") == {"epic": 1}

    def test_raises_on_malformed_json(self):
        body = """
```maverick-state
{not valid json}
```
"""
        with pytest.raises(ValueError, match="malformed"):
            parse_body(body, "maverick-state")

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="unknown marker kind"):
            parse_body("", "maverick-not-a-thing")


class TestFormatMarker:
    def test_round_trip(self):
        payload = {"epic": 123, "stories": {"140": "merged", "142": "in_flight"}}
        block = format_marker("maverick-state", payload)
        assert parse_body(block, "maverick-state") == payload

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="unknown marker kind"):
            format_marker("maverick-bad", {})


class TestMarkerKinds:
    def test_all_expected_kinds_present(self):
        assert set(MARKER_KINDS) == {
            "maverick-dag",
            "maverick-state",
            "maverick-claim",
            "maverick-lease",
            "maverick-bprop",
        }

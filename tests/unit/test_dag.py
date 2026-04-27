"""Tests for maverick.dag — DAG parse/walk helpers."""

from maverick.dag import Dag


def _sample() -> Dag:
    return Dag(
        epic=123,
        stories={
            "140": {"deps": [], "files": ["boot.ts"]},
            "142": {"deps": ["140"], "files": ["guard.ts"]},
            "143": {"deps": ["140"], "files": ["panel.ts"]},
            "150": {"deps": ["142", "143"], "files": ["index.ts", "guard.ts"]},
        },
    )


class TestDeps:
    def test_deps_of_root(self):
        assert _sample().deps_of("140") == []

    def test_deps_of_leaf(self):
        assert _sample().deps_of("150") == ["142", "143"]

    def test_dependents_of_root(self):
        assert set(_sample().dependents_of("140")) == {"142", "143"}

    def test_dependents_of_leaf(self):
        assert _sample().dependents_of("150") == []


class TestTransitiveDescendants:
    def test_root_reaches_all(self):
        assert _sample().transitive_descendants("140") == {"142", "143", "150"}

    def test_mid_reaches_only_own_subtree(self):
        assert _sample().transitive_descendants("142") == {"150"}

    def test_leaf_reaches_nothing(self):
        assert _sample().transitive_descendants("150") == set()


class TestWaves:
    def test_siblings_share_a_wave(self):
        waves = _sample().waves()
        assert waves == [["140"], ["142", "143"], ["150"]]

    def test_empty_dag(self):
        assert Dag(epic=1, stories={}).waves() == []

    def test_cycle_does_not_hang(self):
        d = Dag(
            epic=1,
            stories={
                "a": {"deps": ["b"]},
                "b": {"deps": ["a"]},
            },
        )
        # Cycle stories get left out of waves rather than infinite loop.
        assert d.waves() == []


class TestSharesFiles:
    def test_disjoint_files(self):
        assert _sample().shares_files("142", "143") is False

    def test_overlapping_files(self):
        assert _sample().shares_files("142", "150") is True


class TestPayloadRoundTrip:
    def test_round_trip(self):
        d = _sample()
        assert Dag.from_payload(d.to_payload()).to_payload() == d.to_payload()

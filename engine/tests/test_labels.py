"""Tests for labels.recompute_labels (RUL-19)."""

from __future__ import annotations

from rulso.labels import (
    CHAINED,
    CURSED,
    GENEROUS,
    LABEL_NAMES,
    LEADER,
    MARKED,
    WOUNDED,
    recompute_labels,
)
from rulso.state import GameState, Player


def _player(pid: str, *, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=0, chips=chips, vp=vp)


def _state(*players: Player) -> GameState:
    return GameState(players=players)


def test_returns_all_label_keys() -> None:
    """Every label name appears in the result, even when stubbed."""
    state = _state(_player("p0"))
    out = recompute_labels(state)
    assert set(out) == set(LABEL_NAMES)


def test_single_leader_max_vp() -> None:
    state = _state(
        _player("p0", vp=0),
        _player("p1", vp=2),
        _player("p2", vp=1),
    )
    out = recompute_labels(state)
    assert out[LEADER] == frozenset({"p1"})


def test_tied_leaders_all_hold_label() -> None:
    state = _state(
        _player("p0", vp=2),
        _player("p1", vp=2),
        _player("p2", vp=1),
    )
    out = recompute_labels(state)
    assert out[LEADER] == frozenset({"p0", "p1"})


def test_single_wounded_min_chips() -> None:
    state = _state(
        _player("p0", chips=50),
        _player("p1", chips=10),
        _player("p2", chips=30),
    )
    out = recompute_labels(state)
    assert out[WOUNDED] == frozenset({"p1"})


def test_tied_wounded_all_hold_label() -> None:
    state = _state(
        _player("p0", chips=10),
        _player("p1", chips=10),
        _player("p2", chips=30),
    )
    out = recompute_labels(state)
    assert out[WOUNDED] == frozenset({"p0", "p1"})


def test_all_zero_vp_means_every_player_is_leader() -> None:
    """When every player ties at vp=0, all hold LEADER (ties → all)."""
    state = _state(_player("p0"), _player("p1"), _player("p2"))
    out = recompute_labels(state)
    assert out[LEADER] == frozenset({"p0", "p1", "p2"})


def test_all_equal_chips_means_every_player_is_wounded() -> None:
    state = _state(_player("p0"), _player("p1"), _player("p2"))
    out = recompute_labels(state)
    assert out[WOUNDED] == frozenset({"p0", "p1", "p2"})


def test_empty_player_set_returns_all_empty_frozensets() -> None:
    out = recompute_labels(GameState())
    assert all(out[name] == frozenset() for name in LABEL_NAMES)
    assert set(out) == set(LABEL_NAMES)


def test_m2_stub_labels_are_empty() -> None:
    """GENEROUS / CURSED / MARKED / CHAINED stay empty until M2 wiring."""
    state = _state(_player("p0", vp=2, chips=10), _player("p1", vp=0, chips=50))
    out = recompute_labels(state)
    assert out[GENEROUS] == frozenset()
    assert out[CURSED] == frozenset()
    assert out[MARKED] == frozenset()
    assert out[CHAINED] == frozenset()


def test_returns_frozensets() -> None:
    """Caller contract: values must be frozenset, not set."""
    state = _state(_player("p0", vp=1), _player("p1", chips=5))
    out = recompute_labels(state)
    for name in LABEL_NAMES:
        assert isinstance(out[name], frozenset)


def test_pure_function_does_not_mutate_state() -> None:
    state = _state(_player("p0", vp=1), _player("p1", vp=2))
    snapshot = state.model_copy()
    recompute_labels(state)
    assert state == snapshot

"""Tests for labels.recompute_labels (RUL-19, extended by RUL-33)."""

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
from rulso.state import GameState, Player, PlayerHistory, PlayerStatus


def _player(
    pid: str,
    *,
    chips: int = 50,
    vp: int = 0,
    burn: int = 0,
    cards_given: int = 0,
) -> Player:
    return Player(
        id=pid,
        seat=0,
        chips=chips,
        vp=vp,
        status=PlayerStatus(burn=burn),
        history=PlayerHistory(cards_given_this_game=cards_given),
    )


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


def test_single_generous_max_cards_given() -> None:
    state = _state(
        _player("p0", cards_given=0),
        _player("p1", cards_given=3),
        _player("p2", cards_given=1),
    )
    out = recompute_labels(state)
    assert out[GENEROUS] == frozenset({"p1"})


def test_tied_generous_all_hold_label() -> None:
    state = _state(
        _player("p0", cards_given=2),
        _player("p1", cards_given=2),
        _player("p2", cards_given=1),
    )
    out = recompute_labels(state)
    assert out[GENEROUS] == frozenset({"p0", "p1"})


def test_generous_all_zero_means_empty() -> None:
    """ADR-0001: zero → empty for GENEROUS (no card has been given)."""
    state = _state(_player("p0"), _player("p1"), _player("p2"))
    out = recompute_labels(state)
    assert out[GENEROUS] == frozenset()


def test_generous_all_equal_positive_means_all_tied() -> None:
    state = _state(
        _player("p0", cards_given=2),
        _player("p1", cards_given=2),
        _player("p2", cards_given=2),
    )
    out = recompute_labels(state)
    assert out[GENEROUS] == frozenset({"p0", "p1", "p2"})


def test_single_cursed_max_burn() -> None:
    state = _state(
        _player("p0", burn=0),
        _player("p1", burn=2),
        _player("p2", burn=1),
    )
    out = recompute_labels(state)
    assert out[CURSED] == frozenset({"p1"})


def test_tied_cursed_all_hold_label() -> None:
    state = _state(
        _player("p0", burn=3),
        _player("p1", burn=3),
        _player("p2", burn=1),
    )
    out = recompute_labels(state)
    assert out[CURSED] == frozenset({"p0", "p1"})


def test_cursed_no_burn_means_empty() -> None:
    """ADR-0001: zero → empty for CURSED (no player has been burned)."""
    state = _state(_player("p0"), _player("p1"), _player("p2"))
    out = recompute_labels(state)
    assert out[CURSED] == frozenset()


def test_cursed_all_equal_burn_means_all_tied() -> None:
    state = _state(
        _player("p0", burn=4),
        _player("p1", burn=4),
        _player("p2", burn=4),
    )
    out = recompute_labels(state)
    assert out[CURSED] == frozenset({"p0", "p1", "p2"})


def test_marked_and_chained_remain_empty() -> None:
    """MARKED / CHAINED still wait on the M2 status-apply ticket."""
    state = _state(
        _player("p0", vp=2, chips=10, burn=2, cards_given=3),
        _player("p1", vp=0, chips=50, burn=0, cards_given=0),
    )
    out = recompute_labels(state)
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

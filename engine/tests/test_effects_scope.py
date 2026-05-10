"""Scope-mode dispatch tests for ``effects._scope_subject`` and
``effects.resolve_if_rule`` (RUL-41, ADR-0003).

Covers:
  * ``singular`` — current path stays exact (regression backstop).
  * ``existential`` (``ANYONE``) — single fire with the satisfying subset as
    targets (ADR-0003 example 1). Empty subset → no fire.
  * ``iterative`` (``EACH_PLAYER``) — every match fires as a discrete event
    in seat order from ``state.active_seat``.
  * Empty-match and no-player edge cases.
  * Seat-order helper wrap-around determinism.
"""

from __future__ import annotations

from rulso.effects import _scope_subject, _seat_ordered_players, resolve_if_rule
from rulso.state import (
    Card,
    CardType,
    GameState,
    Player,
    RuleBuilder,
    RuleKind,
    ScopeMode,
    Slot,
)

# RUL-39 dispatcher pin — every GameState in this file pins ``revealed_effect``
# to the canonical ``GAIN_VP:1`` so existential/iterative assertions
# (``vp += 1``) reach a registered handler instead of returning the input
# state unchanged. RUL-23 lesson: scope-mode tests without this pin silently
# pass nothing through dispatch_effect and mask the contract.
_GAIN_VP_1 = Card(id="eff.vp.gain.1", type=CardType.EFFECT, name="GAIN_VP:1")


def _subject(name: str, scope_mode: ScopeMode = "singular") -> Card:
    return Card(
        id=f"sub_{name.lower().replace(' ', '_')}",
        type=CardType.SUBJECT,
        name=name,
        scope_mode=scope_mode,
    )


def _quant(op: str, n: int) -> Card:
    return Card(id=f"q_{op}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


def _noun(name: str) -> Card:
    return Card(id=f"n_{name.lower()}", type=CardType.NOUN, name=name)


def _if_rule(subject: Card, quant: Card, noun: Card) -> RuleBuilder:
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=subject),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=quant),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=noun),
        ),
    )


def _player(pid: str, seat: int, *, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=seat, chips=chips, vp=vp)


def _seated_state(
    players: tuple[Player, ...],
    *,
    active_seat: int = 0,
    revealed_effect: Card | None = _GAIN_VP_1,
) -> GameState:
    return GameState(players=players, active_seat=active_seat, revealed_effect=revealed_effect)


# --- _scope_subject — singular (regression) ----------------------------------


def test_scope_subject_singular_label_lookup() -> None:
    labels = {"THE LEADER": frozenset({"p2"})}
    state = _seated_state((_player("p0", 0), _player("p1", 1), _player("p2", 2)))
    assert _scope_subject(state, _subject("THE LEADER"), labels) == frozenset({"p2"})


def test_scope_subject_singular_literal_player_id() -> None:
    state = _seated_state((_player("p0", 0), _player("p1", 1)))
    assert _scope_subject(state, _subject("p1"), {}) == frozenset({"p1"})


def test_scope_subject_singular_unknown_id_is_empty() -> None:
    state = _seated_state((_player("p0", 0),))
    assert _scope_subject(state, _subject("nobody"), {}) == frozenset()


# --- _scope_subject — existential / iterative candidate sets -----------------


def test_scope_subject_existential_returns_all_candidates() -> None:
    state = _seated_state((_player("p0", 0), _player("p1", 1), _player("p2", 2)))
    candidates = _scope_subject(state, _subject("ANYONE", "existential"), {})
    assert candidates == frozenset({"p0", "p1", "p2"})


def test_scope_subject_iterative_returns_all_candidates() -> None:
    state = _seated_state((_player("p0", 0), _player("p1", 1), _player("p2", 2)))
    candidates = _scope_subject(state, _subject("EACH_PLAYER", "iterative"), {})
    assert candidates == frozenset({"p0", "p1", "p2"})


def test_scope_subject_polymorphic_no_players_is_empty() -> None:
    state = GameState(revealed_effect=_GAIN_VP_1)
    assert _scope_subject(state, _subject("ANYONE", "existential"), {}) == frozenset()
    assert _scope_subject(state, _subject("EACH_PLAYER", "iterative"), {}) == frozenset()


# --- _seat_ordered_players helper --------------------------------------------


def test_seat_ordered_players_starts_at_active_seat() -> None:
    players = (_player("p0", 0), _player("p1", 1), _player("p2", 2), _player("p3", 3))
    state = _seated_state(players, active_seat=2)
    assert tuple(p.id for p in _seat_ordered_players(state)) == ("p2", "p3", "p0", "p1")


def test_seat_ordered_players_empty_roster() -> None:
    assert _seat_ordered_players(GameState()) == ()


def test_seat_ordered_players_active_seat_zero_preserves_order() -> None:
    players = (_player("p0", 0), _player("p1", 1), _player("p2", 2))
    state = _seated_state(players, active_seat=0)
    assert tuple(p.id for p in _seat_ordered_players(state)) == ("p0", "p1", "p2")


# --- resolve_if_rule — existential (ANYONE) ----------------------------------
#
# ADR-0003: existential narrows the candidate set to the satisfying subset and
# fires the effect once with that subset as targets. Cardinality may be > 1
# when multiple players match — they all receive the effect from a single
# resolution event.


def test_existential_adr_example_1_fires_once_with_satisfying_subset() -> None:
    """ADR-0003 example 1: ``IF ANYONE HAS GT 10 CHIPS → +1 VP`` with
    p0=15, p1=12, p2=5, p3=8 → p0 and p1 each receive +1 VP from one event.
    """
    players = (
        _player("p0", 0, chips=15),
        _player("p1", 1, chips=12),
        _player("p2", 2, chips=5),
        _player("p3", 3, chips=8),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("ANYONE", "existential"), _quant("GT", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 1
    assert new.players[2].vp == 0
    assert new.players[3].vp == 0


def test_existential_active_seat_does_not_filter_subset() -> None:
    """Existential fires once with every satisfying player, regardless of where
    ``active_seat`` lies. Both p0 and p2 match; both receive +1 VP."""
    players = (
        _player("p0", 0, chips=20),
        _player("p1", 1, chips=5),
        _player("p2", 2, chips=20),
        _player("p3", 3, chips=5),
    )
    state = _seated_state(players, active_seat=2)
    rule = _if_rule(_subject("ANYONE", "existential"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0
    assert new.players[2].vp == 1
    assert new.players[3].vp == 0


def test_existential_single_match_fires_for_that_player() -> None:
    players = (
        _player("p0", 0, chips=5),
        _player("p1", 1, chips=20),
        _player("p2", 2, chips=5),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("ANYONE", "existential"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 0
    assert new.players[1].vp == 1
    assert new.players[2].vp == 0


def test_existential_no_match_no_fire() -> None:
    """ADR-0003 example 3: empty satisfying subset → rule does not fire."""
    players = (_player("p0", 0, chips=5), _player("p1", 1, chips=5))
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("ANYONE", "existential"), _quant("GE", 100), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


def test_existential_empty_player_set_no_fire() -> None:
    state = _seated_state((), active_seat=0)
    rule = _if_rule(_subject("ANYONE", "existential"), _quant("GE", 0), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


# --- resolve_if_rule — iterative (EACH_PLAYER) -------------------------------


def test_iterative_fires_per_matching_player() -> None:
    """EACH_PLAYER: every matching player gains +1 VP independently; non-
    matchers are unaffected."""
    players = (
        _player("p0", 0, chips=20),
        _player("p1", 1, chips=5),
        _player("p2", 2, chips=20),
        _player("p3", 3, chips=20),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0
    assert new.players[2].vp == 1
    assert new.players[3].vp == 1


def test_iterative_all_players_match_all_fire() -> None:
    players = (_player("p0", 0, vp=2), _player("p1", 1, vp=1))
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 3
    assert new.players[1].vp == 2


def test_iterative_no_match_returns_state_unchanged() -> None:
    players = (_player("p0", 0, chips=5), _player("p1", 1, chips=5))
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 100), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


def test_iterative_empty_player_set_no_fire() -> None:
    state = _seated_state((), active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 0), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


def test_iterative_evaluates_against_input_state_not_intermediate() -> None:
    """Per-iteration HAS evaluation reads the input state, not the running
    accumulator. With NOUN=VP and threshold=0, p0's first +1 VP must not
    affect later iterations' conditions (they all use the original VP)."""
    players = (_player("p0", 0, vp=0), _player("p1", 1, vp=0), _player("p2", 2, vp=0))
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("EQ", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    assert (new.players[0].vp, new.players[1].vp, new.players[2].vp) == (1, 1, 1)


# --- resolve_if_rule — singular regression -----------------------------------


def test_singular_label_path_unchanged_after_dispatch() -> None:
    """Singular SUBJECT with a multi-holder label still applies the effect to
    every holder in one event (matches RUL-22 behaviour). LEADER is computed
    by ``recompute_labels`` on the input state — p0 and p1 tie on VP."""
    players = (_player("p0", 0, vp=2), _player("p1", 1, vp=2), _player("p2", 2, vp=1))
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("THE LEADER"), _quant("GE", 0), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 3
    assert new.players[1].vp == 3
    assert new.players[2].vp == 1


def test_singular_literal_seat_path_unchanged() -> None:
    players = (_player("p0", 0, chips=20), _player("p1", 1, chips=20))
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("p0"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0

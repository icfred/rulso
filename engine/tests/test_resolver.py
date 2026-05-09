"""Tests for grammar.render_if_rule and effects.resolve_if_rule (RUL-9)."""

import pytest

from rulso.effects import resolve_if_rule
from rulso.grammar import IfRule, render_if_rule
from rulso.state import (
    Card,
    CardType,
    GameState,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- Helpers ------------------------------------------------------------------


def _subject(name: str) -> Card:
    return Card(id=f"sub_{name.lower().replace(' ', '_')}", type=CardType.SUBJECT, name=name)


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


def _state(*players: Player) -> GameState:
    return GameState(players=players)


def _player(pid: str, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=0, chips=chips, vp=vp)


# --- grammar.render_if_rule ---------------------------------------------------


def test_render_if_rule_returns_correct_cards() -> None:
    sub = _subject("p0")
    q = _quant("GE", 10)
    n = _noun("CHIPS")
    rule = render_if_rule(_if_rule(sub, q, n))
    assert isinstance(rule, IfRule)
    assert rule.subject == sub
    assert rule.quant == q
    assert rule.noun == n


def test_render_if_rule_rejects_non_if_template() -> None:
    rule = RuleBuilder(
        template=RuleKind.WHEN,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=_subject("p0")),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=_quant("GE", 5)),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=_noun("CHIPS")),
        ),
    )
    with pytest.raises(ValueError, match="IF template"):
        render_if_rule(rule)


def test_render_if_rule_rejects_missing_slot() -> None:
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=_subject("p0")),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=_quant("GE", 5)),
            # NOUN slot absent
        ),
    )
    with pytest.raises(ValueError, match="missing slot"):
        render_if_rule(rule)


def test_render_if_rule_rejects_unfilled_slot() -> None:
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=_subject("p0")),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=_quant("GE", 5)),
            Slot(name="NOUN", type=CardType.NOUN),  # unfilled
        ),
    )
    with pytest.raises(ValueError, match="unfilled"):
        render_if_rule(rule)


# --- effects.resolve_if_rule — scope: single player --------------------------


def test_scope_single_player_has_true_fires_effect() -> None:
    """Specific-player SUBJECT: player satisfies HAS → +1 chip."""
    p0 = _player("p0", chips=20)
    p1 = _player("p1", chips=20)
    state = _state(p0, p1)
    rule = _if_rule(_subject("p0"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].chips == 21
    assert new.players[1].chips == 20  # unscoped


def test_scope_single_player_has_false_skips_effect() -> None:
    """Specific-player SUBJECT: player does not satisfy HAS → no change."""
    p0 = _player("p0", chips=5)
    state = _state(p0, _player("p1"))
    rule = _if_rule(_subject("p0"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new == state


def test_scope_single_player_unknown_id_is_no_match() -> None:
    """SUBJECT name not matching any player id → no scope → no effect."""
    state = _state(_player("p0"), _player("p1"))
    rule = _if_rule(_subject("nobody"), _quant("GE", 0), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new == state


# --- effects.resolve_if_rule — scope: unassigned label (no-op) ---------------


def test_label_subject_the_leader_is_unassigned_no_effect() -> None:
    """Labels are unassigned in M1 (labels.py stub) → no matches → no effect."""
    state = _state(_player("p0"), _player("p1"))
    rule = _if_rule(_subject("THE LEADER"), _quant("GE", 0), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new == state


def test_label_subject_the_wounded_is_unassigned_no_effect() -> None:
    state = _state(_player("p0"), _player("p1"))
    rule = _if_rule(_subject("THE WOUNDED"), _quant("LT", 999), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new == state


def test_label_subject_the_generous_is_unassigned_no_effect() -> None:
    state = _state(_player("p0"), _player("p1"))
    rule = _if_rule(_subject("THE GENEROUS"), _quant("GE", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    assert new == state


def test_label_subject_the_cursed_is_unassigned_no_effect() -> None:
    state = _state(_player("p0"), _player("p1"))
    rule = _if_rule(_subject("THE CURSED"), _quant("GT", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    assert new == state


# --- effects.resolve_if_rule — various HAS comparators -----------------------


def test_has_gt_true() -> None:
    state = _state(_player("p0", chips=11))
    rule = _if_rule(_subject("p0"), _quant("GT", 10), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].chips == 12


def test_has_gt_false_on_equal() -> None:
    state = _state(_player("p0", chips=10))
    rule = _if_rule(_subject("p0"), _quant("GT", 10), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


def test_has_le_true() -> None:
    state = _state(_player("p0", chips=10))
    rule = _if_rule(_subject("p0"), _quant("LE", 10), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].chips == 11


def test_has_lt_true() -> None:
    state = _state(_player("p0", chips=9))
    rule = _if_rule(_subject("p0"), _quant("LT", 10), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].chips == 10


def test_has_eq_true() -> None:
    state = _state(_player("p0", chips=7))
    rule = _if_rule(_subject("p0"), _quant("EQ", 7), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].chips == 8


def test_noun_vp() -> None:
    """NOUN CHIPS vs VP are both supported M1 resources."""
    state = _state(_player("p0", vp=2))
    rule = _if_rule(_subject("p0"), _quant("EQ", 2), _noun("VP"))
    assert resolve_if_rule(state, rule).players[0].chips == 51


# --- Immutability check -------------------------------------------------------


def test_resolve_if_rule_returns_new_state_and_does_not_mutate_input() -> None:
    p0 = _player("p0", chips=50)
    state = _state(p0)
    rule = _if_rule(_subject("p0"), _quant("GE", 50), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new is not state
    assert state.players[0].chips == 50
    assert new.players[0].chips == 51

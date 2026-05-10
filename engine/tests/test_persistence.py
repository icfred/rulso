"""Persistence dispatch surface (RUL-26 + RUL-32).

Covers ``add_persistent_rule`` capacity / FIFO eviction (RUL-26) and the
WHEN/WHILE fire logic (RUL-32): WHILE persistence + dormancy, WHEN
fire-and-discard, FIFO ordering, depth-cap recursion termination, and
WHILE+WHEN coexistence in a single tick.
"""

from __future__ import annotations

import pytest

from rulso.labels import recompute_labels
from rulso.persistence import (
    add_persistent_rule,
    check_when_triggers,
    tick_while_rules,
)
from rulso.state import (
    MAX_PERSISTENT_RULES,
    PLAYER_COUNT,
    Card,
    CardType,
    GameState,
    PersistentRule,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)


def _state(round_number: int = 0) -> GameState:
    players = tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT))
    return GameState(players=players, round_number=round_number, dealer_seat=0)


def _rule(kind: RuleKind = RuleKind.WHEN) -> RuleBuilder:
    return RuleBuilder(template=kind)


def _subject(name: str) -> Card:
    return Card(id=f"sub_{name.lower().replace(' ', '_')}", type=CardType.SUBJECT, name=name)


def _quant(op: str, n: int) -> Card:
    return Card(id=f"q_{op}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


def _noun(name: str) -> Card:
    return Card(id=f"n_{name.lower()}", type=CardType.NOUN, name=name)


def _has_rule(subject_name: str, op: str, n: int, noun_name: str, kind: RuleKind) -> RuleBuilder:
    return RuleBuilder(
        template=kind,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=_subject(subject_name)),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=_quant(op, n)),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=_noun(noun_name)),
        ),
    )


def _persistent(
    rule: RuleBuilder, kind: RuleKind, *, created_round: int = 1, created_by: str = "p0"
) -> PersistentRule:
    return PersistentRule(kind=kind, rule=rule, created_round=created_round, created_by=created_by)


def _state_with_rules(*persisted: PersistentRule) -> GameState:
    return _state().model_copy(update={"persistent_rules": persisted})


# --- add_persistent_rule (RUL-26) -------------------------------------------


def test_tick_while_rules_returns_state_unchanged_when_no_persistent_rules() -> None:
    state = _state()
    out = tick_while_rules(state, labels={})
    assert out is state


def test_check_when_triggers_returns_state_unchanged_when_no_persistent_rules() -> None:
    state = _state()
    out = check_when_triggers(state, labels={})
    assert out is state


def test_add_persistent_rule_appends_when_under_capacity() -> None:
    state = _state(round_number=2)
    out = add_persistent_rule(state, _rule(RuleKind.WHEN), RuleKind.WHEN)
    assert len(out.persistent_rules) == 1
    persisted = out.persistent_rules[0]
    assert persisted.kind is RuleKind.WHEN
    assert persisted.created_round == 2
    assert persisted.created_by == "p0"


def test_add_persistent_rule_evicts_oldest_at_capacity() -> None:
    """A 6th add evicts the oldest entry (FIFO) per design/state.md."""
    state = _state(round_number=1)
    for i in range(MAX_PERSISTENT_RULES):
        state = state.model_copy(update={"round_number": i + 1})
        state = add_persistent_rule(state, _rule(), RuleKind.WHILE)
    assert len(state.persistent_rules) == MAX_PERSISTENT_RULES
    oldest_round = state.persistent_rules[0].created_round
    state = state.model_copy(update={"round_number": MAX_PERSISTENT_RULES + 1})
    state = add_persistent_rule(state, _rule(), RuleKind.WHEN)
    assert len(state.persistent_rules) == MAX_PERSISTENT_RULES
    assert state.persistent_rules[0].created_round != oldest_round
    assert state.persistent_rules[-1].created_round == MAX_PERSISTENT_RULES + 1
    assert state.persistent_rules[-1].kind is RuleKind.WHEN


def test_add_persistent_rule_rejects_if_kind() -> None:
    state = _state()
    with pytest.raises(ValueError, match="WHEN or WHILE"):
        add_persistent_rule(state, _rule(RuleKind.IF), RuleKind.IF)


# --- tick_while_rules (RUL-32) ----------------------------------------------


def test_tick_while_rules_fires_when_scope_matches() -> None:
    """WHILE with non-empty scope + true HAS → +1 VP and rule persists."""
    rule = _has_rule("p0", "GE", 0, "VP", RuleKind.WHILE)
    state = _state_with_rules(_persistent(rule, RuleKind.WHILE))
    out = tick_while_rules(state, recompute_labels(state))
    assert out.players[0].vp == 1
    assert out.players[1].vp == 0
    assert len(out.persistent_rules) == 1
    assert out.persistent_rules[0].kind is RuleKind.WHILE


def test_tick_while_rules_persists_across_multiple_ticks() -> None:
    """WHILE fires every tick; rule never leaves persistent_rules."""
    rule = _has_rule("p0", "GE", 0, "VP", RuleKind.WHILE)
    state = _state_with_rules(_persistent(rule, RuleKind.WHILE))
    for _ in range(3):
        state = tick_while_rules(state, recompute_labels(state))
    assert state.players[0].vp == 3
    assert len(state.persistent_rules) == 1


def test_tick_while_rules_dormant_label_no_op() -> None:
    """WHILE referencing CURSED (M1.5 stub → empty) sits dormant; no fire."""
    rule = _has_rule("THE CURSED", "GE", 0, "VP", RuleKind.WHILE)
    state = _state_with_rules(_persistent(rule, RuleKind.WHILE))
    out = tick_while_rules(state, recompute_labels(state))
    assert out.players == state.players
    assert out.persistent_rules == state.persistent_rules


def test_tick_while_rules_skips_when_kind_rules() -> None:
    """tick_while_rules walks WHILE only; WHEN rules in the list are ignored."""
    while_rule = _has_rule("p0", "GE", 0, "VP", RuleKind.WHILE)
    when_rule = _has_rule("p1", "GE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(
        _persistent(when_rule, RuleKind.WHEN),
        _persistent(while_rule, RuleKind.WHILE),
    )
    out = tick_while_rules(state, recompute_labels(state))
    assert out.players[0].vp == 1
    assert out.players[1].vp == 0
    assert len(out.persistent_rules) == 2


# --- check_when_triggers (RUL-32) -------------------------------------------


def test_check_when_triggers_fires_once_and_discards() -> None:
    """WHEN with matching scope + true HAS: fires once, discarded from list."""
    rule = _has_rule("p0", "GE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(_persistent(rule, RuleKind.WHEN))
    out = check_when_triggers(state, recompute_labels(state))
    assert out.players[0].vp == 1
    assert out.persistent_rules == ()


def test_check_when_triggers_unknown_subject_id_is_no_op() -> None:
    """Empty scope (unknown player id) → no fire, rule stays in the list."""
    rule = _has_rule("nobody", "GE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(_persistent(rule, RuleKind.WHEN))
    out = check_when_triggers(state, recompute_labels(state))
    assert out is state
    assert len(out.persistent_rules) == 1


def test_check_when_triggers_dormant_label_no_op() -> None:
    """WHEN referencing CURSED (empty in M1.5) sits dormant; doesn't discard."""
    rule = _has_rule("THE CURSED", "GE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(_persistent(rule, RuleKind.WHEN))
    out = check_when_triggers(state, recompute_labels(state))
    assert out is state
    assert len(out.persistent_rules) == 1


def test_check_when_triggers_recursion_terminates_at_depth_3() -> None:
    """4 always-matching WHENs: first 3 fire FIFO, 4th survives the depth cap."""
    state = _state_with_rules(
        _persistent(_has_rule("p0", "GE", 0, "VP", RuleKind.WHEN), RuleKind.WHEN, created_round=10),
        _persistent(_has_rule("p1", "GE", 0, "VP", RuleKind.WHEN), RuleKind.WHEN, created_round=20),
        _persistent(_has_rule("p2", "GE", 0, "VP", RuleKind.WHEN), RuleKind.WHEN, created_round=30),
        _persistent(_has_rule("p3", "GE", 0, "VP", RuleKind.WHEN), RuleKind.WHEN, created_round=40),
    )
    out = check_when_triggers(state, recompute_labels(state))
    assert out.players[0].vp == 1
    assert out.players[1].vp == 1
    assert out.players[2].vp == 1
    assert out.players[3].vp == 0
    assert len(out.persistent_rules) == 1
    assert out.persistent_rules[0].created_round == 40


def test_check_when_triggers_fires_in_fifo_order() -> None:
    """FIFO: rule A fires first, mutating state so rule B no longer matches."""
    # Both rules: SUBJECT=p0, HAS LE 0 VP. Firing gives p0 +1 VP, breaking the
    # condition for any later rule.
    rule_a = _has_rule("p0", "LE", 0, "VP", RuleKind.WHEN)
    rule_b = _has_rule("p0", "LE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(
        _persistent(rule_a, RuleKind.WHEN, created_round=1),
        _persistent(rule_b, RuleKind.WHEN, created_round=99),
    )
    out = check_when_triggers(state, recompute_labels(state))
    assert out.players[0].vp == 1
    assert len(out.persistent_rules) == 1
    # The later-inserted rule (created_round=99) survives because the earlier
    # one fired first and broke the HAS condition.
    assert out.persistent_rules[0].created_round == 99


def test_check_when_triggers_skips_while_kind_rules() -> None:
    """check_when_triggers walks WHEN only; WHILE rules in the list are ignored."""
    while_rule = _has_rule("p0", "GE", 0, "VP", RuleKind.WHILE)
    when_rule = _has_rule("p1", "GE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(
        _persistent(while_rule, RuleKind.WHILE, created_round=1),
        _persistent(when_rule, RuleKind.WHEN, created_round=2),
    )
    out = check_when_triggers(state, recompute_labels(state))
    assert out.players[0].vp == 0
    assert out.players[1].vp == 1
    # WHEN discarded; WHILE persists.
    assert len(out.persistent_rules) == 1
    assert out.persistent_rules[0].kind is RuleKind.WHILE


# --- coexistence -------------------------------------------------------------


def test_tick_while_and_check_when_coexist() -> None:
    """A round_start tick + resolve check together: both fire per their semantics."""
    while_rule = _has_rule("p0", "GE", 0, "VP", RuleKind.WHILE)
    when_rule = _has_rule("p1", "GE", 0, "VP", RuleKind.WHEN)
    state = _state_with_rules(
        _persistent(while_rule, RuleKind.WHILE, created_round=1),
        _persistent(when_rule, RuleKind.WHEN, created_round=2),
    )
    after_while = tick_while_rules(state, recompute_labels(state))
    assert after_while.players[0].vp == 1
    assert after_while.players[1].vp == 0
    assert len(after_while.persistent_rules) == 2
    after_when = check_when_triggers(after_while, recompute_labels(after_while))
    assert after_when.players[0].vp == 1  # WHEN didn't touch p0
    assert after_when.players[1].vp == 1
    # WHEN discarded; WHILE persists.
    assert len(after_when.persistent_rules) == 1
    assert after_when.persistent_rules[0].kind is RuleKind.WHILE

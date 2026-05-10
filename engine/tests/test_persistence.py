"""Persistence scaffolding (RUL-26).

Covers the M2 dispatch surface: capacity / FIFO eviction for
``add_persistent_rule`` and the empty-state no-op contract for
``tick_while_rules`` and ``check_when_triggers``.
"""

from __future__ import annotations

import pytest

from rulso.persistence import (
    add_persistent_rule,
    check_when_triggers,
    tick_while_rules,
)
from rulso.state import (
    MAX_PERSISTENT_RULES,
    PLAYER_COUNT,
    GameState,
    Player,
    RuleBuilder,
    RuleKind,
)


def _state(round_number: int = 0) -> GameState:
    players = tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT))
    return GameState(players=players, round_number=round_number, dealer_seat=0)


def _rule(kind: RuleKind = RuleKind.WHEN) -> RuleBuilder:
    return RuleBuilder(template=kind)


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
    # Oldest evicted; newest at the tail.
    assert state.persistent_rules[0].created_round != oldest_round
    assert state.persistent_rules[-1].created_round == MAX_PERSISTENT_RULES + 1
    assert state.persistent_rules[-1].kind is RuleKind.WHEN


def test_add_persistent_rule_rejects_if_kind() -> None:
    state = _state()
    with pytest.raises(ValueError, match="WHEN or WHILE"):
        add_persistent_rule(state, _rule(RuleKind.IF), RuleKind.IF)

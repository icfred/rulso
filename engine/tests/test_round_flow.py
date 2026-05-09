"""Round flow phase machine tests.

Covers RUL-8 acceptance scenarios:
* game-start to first build
* build with all slots filled -> resolve
* build with unfilled slot -> failed rule -> next round_start
* dealer rotation across 4 rounds
"""

from __future__ import annotations

import pytest

from rulso.rules import (
    advance_phase,
    enter_resolve,
    force_pass,
    play_card,
    start_game,
)
from rulso.state import Card, Config

# Avoid the shop check across multi-round tests; M1 raises NotImplementedError there.
_NO_SHOP = Config(shop_interval=10**9)


def _placeholder(card_type: str, name: str = "x") -> Card:
    return Card(id=f"test_{card_type}_{name}", type=card_type, text="test")


def test_start_game_sets_round_start() -> None:
    state = start_game(seed=1, config=_NO_SHOP)

    assert state.phase == "round_start"
    assert state.round_number == 0
    assert state.dealer_seat == 0
    assert len(state.players) == _NO_SHOP.player_count
    for p in state.players:
        assert p.chips == _NO_SHOP.starting_chips
        assert p.vp == 0
        assert len(p.hand) == _NO_SHOP.hand_size


def test_advance_from_round_start_enters_build() -> None:
    state = advance_phase(start_game(seed=1, config=_NO_SHOP))

    assert state.phase == "build"
    assert state.round_number == 1
    assert state.active_seat == (state.dealer_seat + 1) % state.config.player_count
    assert state.build_turns_taken == 0
    assert state.active_rule is not None
    # Dealer pre-filled slot 0; remaining 2 slots open.
    filled = [s for s in state.active_rule.slots if s.filled_by is not None]
    assert len(filled) == 1
    assert state.active_rule.plays[0].seat == state.dealer_seat
    assert state.revealed_effect is not None


def test_build_all_slots_filled_transitions_to_resolve() -> None:
    state = advance_phase(start_game(seed=2, config=_NO_SHOP))
    pc = state.config.player_count

    # Two non-dealer plays fill the remaining slots; remaining seats force-pass.
    state = play_card(state, _placeholder("NOUN", "n1"), "noun")
    state = play_card(state, _placeholder("MODIFIER", "m1"), "modifier")
    while state.build_turns_taken < pc:
        state = force_pass(state)

    state = advance_phase(state)

    assert state.phase == "round_start"  # resolve completed and looped to next round_start
    assert (
        state.round_number == 1
    )  # resolve hasn't bumped round yet — that's the next round_start's job
    assert state.dealer_seat == 1  # rotated after successful resolve
    assert state.active_rule is None


def test_build_unfilled_slot_fails_back_to_round_start() -> None:
    state = advance_phase(start_game(seed=3, config=_NO_SHOP))
    initial_dealer = state.dealer_seat
    pc = state.config.player_count

    while state.build_turns_taken < pc:
        state = force_pass(state)

    state = advance_phase(state)

    assert state.phase == "round_start"
    assert state.round_number == 1
    assert state.dealer_seat == (initial_dealer + 1) % pc
    assert state.active_rule is None


def test_dealer_rotates_across_four_rounds() -> None:
    state = start_game(seed=4, config=_NO_SHOP)
    pc = state.config.player_count
    dealers: list[int] = []

    for _ in range(pc):
        # Enter round_start -> build.
        state = advance_phase(state)
        dealers.append(state.dealer_seat)
        # Force-pass through build (rule fails, dealer rotates).
        while state.build_turns_taken < pc:
            state = force_pass(state)
        state = advance_phase(state)

    assert dealers == [0, 1, 2, 3]
    assert state.dealer_seat == 0  # wrapped after 4 rotations


def test_play_card_outside_build_raises() -> None:
    state = start_game(seed=5, config=_NO_SHOP)
    with pytest.raises(ValueError):
        play_card(state, _placeholder("NOUN"), "noun")


def test_force_pass_outside_build_raises() -> None:
    state = start_game(seed=5, config=_NO_SHOP)
    with pytest.raises(ValueError):
        force_pass(state)


def test_advance_build_before_full_revolution_raises() -> None:
    state = advance_phase(start_game(seed=6, config=_NO_SHOP))
    state = force_pass(state)
    with pytest.raises(ValueError):
        advance_phase(state)


def test_shop_round_raises_not_implemented() -> None:
    # shop_interval=3: round 3 triggers M2 stub.
    state = start_game(seed=7, config=Config(shop_interval=3))
    state = advance_phase(state)  # round 1 -> build
    while state.build_turns_taken < state.config.player_count:
        state = force_pass(state)
    state = advance_phase(state)  # round_start (round 2 next)
    state = advance_phase(state)  # round 2 -> build
    while state.build_turns_taken < state.config.player_count:
        state = force_pass(state)
    state = advance_phase(state)  # round_start (round 3 next, hits shop)
    with pytest.raises(NotImplementedError, match="M2"):
        advance_phase(state)


def test_winner_short_circuits_to_end_phase() -> None:
    state = advance_phase(start_game(seed=8, config=_NO_SHOP))
    pc = state.config.player_count

    # Crown seat 2 by directly bumping VP to VP_TO_WIN.
    bumped = tuple(
        p.model_copy(update={"vp": state.config.vp_to_win}) if p.seat == 2 else p
        for p in state.players
    )
    state = state.model_copy(update={"players": bumped})

    state = play_card(state, _placeholder("NOUN", "n1"), "noun")
    state = play_card(state, _placeholder("MODIFIER", "m1"), "modifier")
    while state.build_turns_taken < pc:
        state = force_pass(state)

    state = enter_resolve(state)

    assert state.phase == "end"
    assert state.winner_seat == 2

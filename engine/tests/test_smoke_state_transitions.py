"""Cross-cutting state-transition smoke (RUL-12).

Drives the round-flow phase machine end-to-end and asserts the integration
contract: every phase boundary fires in the expected order and leaves the
state coherent. Per-transition unit assertions live in ``test_round_flow.py``;
this file watches them compose.

Hand-injected fixture: ``rules.play_card`` does not validate hand membership
in M1, but the realistic build → resolve path requires that the active player
*has* a slot-compatible card. The fixture builds a ``GameState`` directly with
hands populated, then drives ``play_card`` from each non-dealer player.
"""

from __future__ import annotations

from rulso.rules import advance_phase, pass_turn, play_card, start_game
from rulso.state import (
    PLAYER_COUNT,
    Card,
    CardType,
    GameState,
    Phase,
    Player,
)


def _card(cid: str, type_: CardType) -> Card:
    return Card(id=cid, type=type_, name=cid)


def _hand_for(seat: int) -> tuple[Card, ...]:
    """Give every non-dealer seat a card matching the slot it will fill in M1.

    Slot order in the M1 stub rule (rules.py): subject, noun, modifier, noun_2.
    Slot 0 is filled by the dealer in ``enter_round_start``; seats 1..3 fill
    slots 1..3 in turn order.
    """
    if seat == 1:
        return (_card("h1_noun", CardType.NOUN),)
    if seat == 2:
        return (_card("h2_mod", CardType.MODIFIER),)
    if seat == 3:
        return (_card("h3_noun", CardType.NOUN),)
    return ()


def _start_with_hands() -> GameState:
    """``start_game`` followed by injecting hands per ``_hand_for``."""
    state = start_game()
    new_players = tuple(p.model_copy(update={"hand": _hand_for(p.seat)}) for p in state.players)
    return state.model_copy(update={"players": new_players})


# --- lobby → round_start ----------------------------------------------------


def test_full_phase_sequence_lobby_to_resolve_via_hand_injected_fixture() -> None:
    """One cohesive integration walk: LOBBY → ROUND_START → BUILD → RESOLVE.

    Asserts each phase boundary in sequence so a regression in any one
    transition trips this test rather than just its unit counterpart.
    """
    # LOBBY: explicit construction; ``start_game`` skips this step.
    lobby = GameState(
        phase=Phase.LOBBY,
        players=tuple(Player(id=f"p{i}", seat=i, hand=_hand_for(i)) for i in range(PLAYER_COUNT)),
    )
    assert lobby.phase is Phase.LOBBY
    assert lobby.round_number == 0

    # LOBBY → ROUND_START → BUILD (advance_phase composes both).
    state = advance_phase(lobby)
    assert state.phase is Phase.BUILD
    assert state.round_number == 1
    assert state.dealer_seat == 0
    assert state.active_seat == 1
    assert state.active_rule is not None
    # Dealer fragment occupies slot 0; seats 1..3 must fill slots 1..3.
    assert state.active_rule.slots[0].filled_by is not None
    assert all(s.filled_by is None for s in state.active_rule.slots[1:])

    # BUILD: each non-dealer seat plays its hand card into the next open slot.
    state = play_card(state, state.players[1].hand[0], "noun")
    assert state.phase is Phase.BUILD
    assert state.active_seat == 2
    state = play_card(state, state.players[2].hand[0], "modifier")
    assert state.phase is Phase.BUILD
    assert state.active_seat == 3
    state = play_card(state, state.players[3].hand[0], "noun_2")
    # Three non-dealer plays consumed; dealer's build turn (a forced pass under
    # M1 since slot 0 is already filled) closes the revolution.
    assert state.phase is Phase.BUILD
    assert state.active_seat == 0

    # BUILD → RESOLVE.
    state = pass_turn(state)
    assert state.phase is Phase.RESOLVE
    assert state.active_rule is not None
    assert all(s.filled_by is not None for s in state.active_rule.slots)
    assert state.build_turns_taken == PLAYER_COUNT


# --- build → round_start (failed-rule path) ---------------------------------


def test_build_fails_back_to_round_start_when_any_slot_unfilled() -> None:
    """Drive a build revolution where one seat passes; rule fails cleanly."""
    state = _start_with_hands()
    state = advance_phase(state)  # ROUND_START → BUILD
    assert state.phase is Phase.BUILD

    state = play_card(state, state.players[1].hand[0], "noun")
    state = pass_turn(state)  # seat 2 forced pass — modifier slot stays open
    state = play_card(state, state.players[3].hand[0], "noun_2")
    state = pass_turn(state)  # dealer closes the revolution

    assert state.phase is Phase.ROUND_START
    assert state.active_rule is None
    assert state.dealer_seat == 1  # rotated on fail
    assert state.revealed_effect is None
    # Dealer fragment + two non-dealer fragments → 3 in discard; modifier card
    # never left seat 2's hand and is therefore not discarded.
    assert len(state.discard) == 3


# --- 4-round dealer rotation as full integration ----------------------------


def test_dealer_rotates_one_full_revolution_over_four_failed_rounds() -> None:
    """Walk the phase machine for ``PLAYER_COUNT`` rounds via failed rules.

    Cross-cutting check that the round counter, dealer seat, and active-rule
    lifecycle stay coherent over a full rotation. Per-step assertions live in
    ``test_round_flow.test_dealer_rotates_across_four_rounds_via_failed_rules``;
    this test additionally asserts the round counter and rule clearing on
    each iteration.
    """
    state = start_game()  # empty hands → every build will fail
    dealers: list[int] = []
    rounds: list[int] = []
    for _ in range(PLAYER_COUNT):
        state = advance_phase(state)  # ROUND_START → BUILD
        assert state.phase is Phase.BUILD
        assert state.active_rule is not None
        dealers.append(state.dealer_seat)
        rounds.append(state.round_number)
        for _ in range(PLAYER_COUNT):
            state = advance_phase(state)  # BUILD ticks → fail → ROUND_START
        assert state.phase is Phase.ROUND_START
        assert state.active_rule is None
        assert state.revealed_effect is None
    assert dealers == [0, 1, 2, 3]
    assert rounds == [1, 2, 3, 4]
    # One full revolution returns the dealer seat to its starting value.
    assert state.dealer_seat == 0


# --- round_start → build (active_seat invariant) ----------------------------


def test_round_start_to_build_sets_active_seat_left_of_dealer() -> None:
    """``active_seat`` after every ROUND_START is ``(dealer + 1) % PLAYER_COUNT``.

    Validated across a full dealer rotation so the invariant is checked at
    every dealer position, not just seat 0.
    """
    state = start_game()
    for expected_dealer in range(PLAYER_COUNT):
        state = advance_phase(state)
        assert state.phase is Phase.BUILD
        assert state.dealer_seat == expected_dealer
        assert state.active_seat == (expected_dealer + 1) % PLAYER_COUNT
        for _ in range(PLAYER_COUNT):
            state = advance_phase(state)

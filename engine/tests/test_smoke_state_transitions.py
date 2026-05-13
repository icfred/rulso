"""Cross-cutting state-transition smoke (RUL-12, refreshed for RUL-18).

Drives the round-flow phase machine end-to-end and asserts the integration
contract: every phase boundary fires in the expected order and leaves the
state coherent. Per-transition unit assertions live in ``test_round_flow.py``;
this file watches them compose.

Post-RUL-18, ``start_game`` deals real hands and slot defs come from the
CONDITION card (``SUBJECT / QUANT / NOUN``). Tests inject deterministic hands
into the dealt state so phase transitions are predictable regardless of the
RNG-driven deal order.
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


def _override_hand(state: GameState, seat: int, hand: tuple[Card, ...]) -> GameState:
    new_players = tuple(
        p.model_copy(update={"hand": hand}) if p.seat == seat else p for p in state.players
    )
    return state.model_copy(update={"players": new_players})


def _seat_one_card_hands() -> dict[int, tuple[Card, ...]]:
    """Hands that fill QUANT (seat 1) + NOUN (seat 2) + SUBJECT (seat 3).

    RUL-75: dealer no longer pre-fills slot 0. SUBJECT now needs to be played
    during BUILD by some seat; here seat 3 holds it, dealer is empty.
    """
    return {
        0: (),
        1: (_card("h1_quant", CardType.MODIFIER),),
        2: (_card("h2_noun", CardType.NOUN),),
        3: (_card("h3_subj", CardType.SUBJECT),),
    }


# --- lobby → round_start ----------------------------------------------------


def test_full_phase_sequence_lobby_to_resolve_via_hand_injected_fixture() -> None:
    """One cohesive integration walk: LOBBY → ROUND_START → BUILD → RESOLVE."""
    hands = _seat_one_card_hands()
    lobby = GameState(
        phase=Phase.LOBBY,
        players=tuple(Player(id=f"p{i}", seat=i, hand=hands[i]) for i in range(PLAYER_COUNT)),
    )
    assert lobby.phase is Phase.LOBBY
    assert lobby.round_number == 0

    state = advance_phase(lobby)
    assert state.phase is Phase.BUILD
    assert state.round_number == 1
    assert state.dealer_seat == 0
    assert state.active_seat == 1
    assert state.active_rule is not None
    assert tuple(s.name for s in state.active_rule.slots) == ("SUBJECT", "QUANT", "NOUN")
    # RUL-75: all slots start unfilled.
    assert all(s.filled_by is None for s in state.active_rule.slots)

    state = play_card(state, state.players[1].hand[0], "QUANT")
    assert state.phase is Phase.BUILD
    assert state.active_seat == 2
    state = play_card(state, state.players[2].hand[0], "NOUN")
    assert state.phase is Phase.BUILD
    assert state.active_seat == 3
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
    assert state.phase is Phase.BUILD
    assert state.active_seat == 0
    state = pass_turn(state)  # dealer pass — all slots already filled
    assert state.phase is Phase.RESOLVE
    assert state.active_rule is not None
    assert all(s.filled_by is not None for s in state.active_rule.slots)


# --- build → round_start (failed-rule path) ---------------------------------


def test_build_fails_back_to_round_start_when_any_slot_unfilled() -> None:
    """One slot stays open across the revolution → rule fails cleanly.

    RUL-75: dealer no longer pre-fills slot 0. Inject SUBJECT into seat 3 +
    QUANT into seat 1 so two slots fill but NOUN never does.
    """
    state = start_game()
    state = _override_hand(state, 0, ())
    state = _override_hand(state, 1, (_card("h1_quant", CardType.MODIFIER),))
    state = _override_hand(state, 2, ())
    state = _override_hand(state, 3, (_card("h3_subj", CardType.SUBJECT),))
    state = advance_phase(state)
    assert state.phase is Phase.BUILD

    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = pass_turn(state)  # seat 2 forced pass
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
    state = pass_turn(state)  # dealer forced pass

    assert state.phase is Phase.ROUND_START
    assert state.active_rule is None
    assert state.dealer_seat == 1  # rotated on fail
    assert state.revealed_effect is None
    # QUANT + SUBJECT plays → 2 in discard; NOUN slot stayed empty.
    assert len(state.discard) == 2


# --- 4-round dealer rotation as full integration ----------------------------


def test_dealer_rotates_one_full_revolution_over_four_failed_rounds() -> None:
    """Walk the phase machine for ``PLAYER_COUNT`` rounds via failed rules.

    RUL-75: empty hands now enter BUILD (no dealer seed-fill); the rule fails
    at end-of-revolution with all slots unfilled and the dealer rotates.

    RUL-56: ``shop_pool`` overridden to empty so the SHOP cadence (round 3)
    skips and the unfilled-slot rotation is the only path exercised.
    """
    state = start_game()
    state = state.model_copy(update={"shop_pool": ()})
    for seat in range(PLAYER_COUNT):
        state = _override_hand(state, seat, ())
    dealers: list[int] = []
    rounds: list[int] = []
    for _ in range(PLAYER_COUNT):
        prior_dealer = state.dealer_seat
        prior_round = state.round_number
        state = advance_phase(state)
        assert state.phase is Phase.BUILD
        for _ in range(PLAYER_COUNT):
            state = pass_turn(state)
        assert state.phase is Phase.ROUND_START
        assert state.active_rule is None
        dealers.append(prior_dealer)
        rounds.append(prior_round + 1)
    assert dealers == [0, 1, 2, 3]
    assert rounds == [1, 2, 3, 4]
    # One full revolution returns the dealer seat to its starting value.
    assert state.dealer_seat == 0


# --- round_start → build (active_seat invariant) ----------------------------


def test_round_start_to_build_sets_active_seat_left_of_dealer() -> None:
    """``active_seat`` after every successful ROUND_START is ``(dealer + 1) % PLAYER_COUNT``.

    RUL-56: ``shop_pool`` overridden to empty so the SHOP cadence (round 3)
    does not intercept ROUND_START → BUILD on the third dealer rotation.
    RUL-75: dealer no longer needs to hold a SUBJECT — hands can be empty.
    """
    state = start_game()
    state = state.model_copy(update={"shop_pool": ()})
    for seat in range(PLAYER_COUNT):
        state = _override_hand(state, seat, ())
    for expected_dealer in range(PLAYER_COUNT):
        state = advance_phase(state)
        assert state.phase is Phase.BUILD
        assert state.dealer_seat == expected_dealer
        assert state.active_seat == (expected_dealer + 1) % PLAYER_COUNT
        # Drive the full revolution of forced passes to fail and rotate.
        for _ in range(PLAYER_COUNT):
            state = pass_turn(state)

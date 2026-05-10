import random

import pytest

from rulso.cards import load_condition_templates
from rulso.rules import (
    advance_phase,
    enter_resolve,
    pass_turn,
    play_card,
    start_game,
)
from rulso.state import (
    HAND_SIZE,
    PLAYER_COUNT,
    Card,
    CardType,
    GameState,
    Phase,
    Player,
)


def _card(cid: str, type_: CardType) -> Card:
    return Card(id=cid, type=type_, name=cid)


def _drive_to_first_build(seed: int = 0) -> GameState:
    state = start_game(seed)
    return advance_phase(state)


def _override_player_hand(state: GameState, seat: int, hand: tuple[Card, ...]) -> GameState:
    new_players = tuple(
        p.model_copy(update={"hand": hand}) if p.seat == seat else p for p in state.players
    )
    return state.model_copy(update={"players": new_players})


def test_start_game_initializes_round_start_at_round_zero() -> None:
    state = start_game()
    assert state.phase is Phase.ROUND_START
    assert state.round_number == 0
    assert state.dealer_seat == 0
    assert len(state.players) == PLAYER_COUNT
    assert all(state.players[i].seat == i for i in range(PLAYER_COUNT))
    assert state.active_rule is None


def test_start_game_deals_full_hands_per_seat() -> None:
    state = start_game(seed=0)
    for player in state.players:
        assert len(player.hand) == HAND_SIZE


def test_start_game_is_deterministic_under_same_seed() -> None:
    s1 = start_game(seed=42)
    s2 = start_game(seed=42)
    assert tuple(p.hand for p in s1.players) == tuple(p.hand for p in s2.players)
    assert s1.deck == s2.deck


def test_start_game_differs_across_seeds() -> None:
    """Two distinct seeds must produce at least one differing hand."""
    s1 = start_game(seed=0)
    s2 = start_game(seed=1)
    diffs = [p1.hand != p2.hand for p1, p2 in zip(s1.players, s2.players, strict=True)]
    assert any(diffs)


def test_start_game_uses_no_cards_outside_main_deck() -> None:
    """Every dealt + remaining card sums to the main deck size."""
    from rulso.cards import build_default_deck

    decks = build_default_deck()
    state = start_game(seed=0)
    dealt_count = sum(len(p.hand) for p in state.players)
    remaining = len(state.deck)
    assert dealt_count + remaining == len(decks.main)


def test_advance_from_round_start_enters_build_with_dealer_first_slot_filled() -> None:
    state = _drive_to_first_build(seed=0)
    assert state.phase is Phase.BUILD
    assert state.round_number == 1
    assert state.dealer_seat == 0
    assert state.active_seat == 1
    assert state.build_turns_taken == 0
    assert state.revealed_effect is not None
    assert state.active_rule is not None
    slots = state.active_rule.slots
    # Slot defs come from the CONDITION template; M1.5 has IF (3 slots).
    assert tuple(s.name for s in slots) == ("SUBJECT", "QUANT", "NOUN")
    assert slots[0].filled_by is not None
    assert slots[0].filled_by.type is CardType.SUBJECT
    assert all(s.filled_by is None for s in slots[1:])
    assert state.active_rule.plays[0].player_id == "p0"


def test_round_start_slot_defs_match_condition_template() -> None:
    """Slot defs are driven by the CONDITION card, not hardcoded in rules.py."""
    template = load_condition_templates()[0]
    state = _drive_to_first_build(seed=0)
    rule = state.active_rule
    assert rule is not None
    assert rule.template is template.kind
    assert tuple(s.name for s in rule.slots) == tuple(cs.name for cs in template.slots)
    assert tuple(s.type for s in rule.slots) == tuple(cs.type for cs in template.slots)


def test_dealer_first_slot_card_came_from_dealer_hand() -> None:
    state = start_game(seed=0)
    dealer_hand_before = state.players[0].hand
    state = advance_phase(state)
    chosen = state.active_rule.slots[0].filled_by
    assert chosen is not None
    assert chosen in dealer_hand_before
    # That card is now removed from the dealer's hand.
    assert state.players[0].hand.count(chosen) == dealer_hand_before.count(chosen) - 1


def test_round_start_fails_immediately_when_dealer_has_no_seed_card() -> None:
    """No SUBJECT in dealer hand → consumes the round, rotates dealer, returns to ROUND_START."""
    state = start_game(seed=0)
    # Strip every SUBJECT from seat 0 (current dealer).
    dealer = state.players[0]
    no_subject_hand = tuple(c for c in dealer.hand if c.type is not CardType.SUBJECT)
    state = _override_player_hand(state, 0, no_subject_hand)
    state = advance_phase(state)
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1  # rotated
    assert state.round_number == 1  # round was consumed
    assert state.active_rule is None
    assert state.revealed_effect is None


def test_play_card_fills_slot_and_advances_active_seat() -> None:
    state = _drive_to_first_build(seed=0)
    # Inject a NOUN card into seat 1 so we can deterministically play it.
    noun_card = _card("n1", CardType.NOUN)
    state = _override_player_hand(state, 1, (noun_card,))
    state = play_card(state, noun_card, "NOUN")
    assert state.active_rule.slots[2].filled_by.id == "n1"
    assert state.active_seat == 2
    assert state.build_turns_taken == 1
    assert state.phase is Phase.BUILD


def test_play_card_removes_card_from_active_player_hand() -> None:
    state = _drive_to_first_build(seed=0)
    noun_card = _card("n1", CardType.NOUN)
    state = _override_player_hand(state, 1, (noun_card,))
    state = play_card(state, noun_card, "NOUN")
    assert state.players[1].hand == ()


def test_play_card_rejects_type_mismatch() -> None:
    state = _drive_to_first_build(seed=0)
    bad_card = _card("bad", CardType.SUBJECT)
    state = _override_player_hand(state, 1, (bad_card,))
    with pytest.raises(ValueError, match="does not match slot type"):
        play_card(state, bad_card, "NOUN")


def test_play_card_rejects_filled_slot() -> None:
    state = _drive_to_first_build(seed=0)
    dup = _card("dup", CardType.SUBJECT)
    state = _override_player_hand(state, 1, (dup,))
    with pytest.raises(ValueError, match="already filled"):
        play_card(state, dup, "SUBJECT")


def test_play_card_rejects_unknown_slot() -> None:
    state = _drive_to_first_build(seed=0)
    noun = _card("n1", CardType.NOUN)
    state = _override_player_hand(state, 1, (noun,))
    with pytest.raises(ValueError, match="unknown slot"):
        play_card(state, noun, "no_such_slot")


def test_play_card_outside_build_raises() -> None:
    state = start_game()
    with pytest.raises(ValueError, match="requires phase=BUILD"):
        play_card(state, _card("n1", CardType.NOUN), "NOUN")


def test_build_with_all_slots_filled_transitions_to_resolve() -> None:
    state = _drive_to_first_build(seed=0)
    # Inject one matching card into each non-dealer seat.
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("filler", CardType.NOUN),))
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = pass_turn(state)  # seat 3 forced pass — no remaining open slot
    state = pass_turn(state)  # dealer's build turn — all slots already filled
    assert state.phase is Phase.RESOLVE
    assert state.build_turns_taken == PLAYER_COUNT
    assert all(s.filled_by is not None for s in state.active_rule.slots)


def test_build_with_unfilled_slot_fails_back_to_round_start() -> None:
    state = _drive_to_first_build(seed=0)
    # All non-dealer seats start without injected hands → all forced passes.
    # Strip seat 1..3 hands so the random hands don't accidentally fill slots.
    for seat in (1, 2, 3):
        state = _override_player_hand(state, seat, ())
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1
    assert state.active_rule is None
    # Only the dealer's SUBJECT fragment is in discard; QUANT and NOUN slots
    # were never filled.
    assert len(state.discard) == 1


def test_resolve_transitions_to_round_start_and_rotates_dealer() -> None:
    state = _drive_to_first_build(seed=0)
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("filler", CardType.NOUN),))
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = pass_turn(state)
    state = pass_turn(state)
    assert state.phase is Phase.RESOLVE
    state = enter_resolve(state, rng=random.Random(0))
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1
    assert state.active_rule is None
    assert state.revealed_effect is None
    # Three filled slots → three discarded fragments.
    assert len(state.discard) == 3


def test_advance_phase_from_resolve_invokes_enter_resolve() -> None:
    state = _drive_to_first_build(seed=0)
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("filler", CardType.NOUN),))
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = pass_turn(state)
    state = pass_turn(state)
    state = advance_phase(state, rng=random.Random(0))
    assert state.phase in (Phase.ROUND_START, Phase.END)


def test_dealer_rotates_across_four_rounds_via_failed_rules() -> None:
    """Inject all-empty hands so every round fails; assert dealer rotates 0,1,2,3."""
    state = start_game()
    for seat in range(PLAYER_COUNT):
        state = _override_player_hand(state, seat, ())
    seen_dealers: list[int] = []
    seen_rounds: list[int] = []
    for _ in range(PLAYER_COUNT):
        # No cards anywhere → enter_round_start hits the dealer-no-seed path.
        # That returns to ROUND_START directly without entering BUILD.
        prior = state.dealer_seat
        prior_round = state.round_number
        state = advance_phase(state)
        assert state.phase is Phase.ROUND_START
        seen_dealers.append(prior)
        seen_rounds.append(prior_round + 1)
    assert seen_dealers == [0, 1, 2, 3]
    assert seen_rounds == [1, 2, 3, 4]


def test_advance_from_lobby_enters_round_start() -> None:
    """LOBBY → ROUND_START → BUILD via advance_phase composes cleanly when the
    dealer holds a SUBJECT card."""
    seed_card = Card(id="held_subj", type=CardType.SUBJECT, name="p0")
    state = GameState(
        phase=Phase.LOBBY,
        players=tuple(
            Player(id=f"p{i}", seat=i, hand=(seed_card,) if i == 0 else ())
            for i in range(PLAYER_COUNT)
        ),
    )
    state = advance_phase(state)
    assert state.phase is Phase.BUILD
    assert state.round_number == 1


def test_advance_from_shop_raises_not_implemented() -> None:
    state = GameState(
        phase=Phase.SHOP,
        players=tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT)),
    )
    with pytest.raises(NotImplementedError, match="shop"):
        advance_phase(state)


def test_advance_from_end_is_idempotent() -> None:
    state = GameState(phase=Phase.END)
    assert advance_phase(state) == state


def test_burn_tick_drains_chips_and_clears_mute_at_round_start() -> None:
    from rulso.state import PlayerStatus

    state = start_game()
    burned = state.players[0].model_copy(
        update={
            "chips": 30,
            "status": PlayerStatus(burn=2, mute=True),
        }
    )
    state = state.model_copy(update={"players": (burned,) + state.players[1:]})
    state = advance_phase(state)
    p0 = state.players[0]
    assert p0.chips == 30 - 5 * 2
    assert p0.status.burn == 2  # BURN persists; only the chip drain ticks.
    assert p0.status.mute is False


# --- RUL-18 additions: refill mid-game --------------------------------------


def test_refill_replenishes_hands_to_hand_size_after_resolve() -> None:
    """After enter_resolve, every player's hand returns to HAND_SIZE while the
    deck is non-empty."""
    state = _drive_to_first_build(seed=0)
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("filler", CardType.NOUN),))
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = pass_turn(state)
    state = pass_turn(state)
    state = enter_resolve(state, rng=random.Random(0))
    for player in state.players:
        assert len(player.hand) == HAND_SIZE


def test_refill_shuffles_discard_back_when_deck_empties() -> None:
    """When the deck has fewer cards than needed for refill, shuffle the
    discard pile back into the deck and continue drawing."""
    state = _drive_to_first_build(seed=0)
    # Drain seat 1's hand (so refill needs HAND_SIZE cards for them).
    state = _override_player_hand(state, 1, ())
    # Exhaust the deck — push every card to discard with only a small refill
    # need. Fabricate a discard pile larger than the deck.
    big_discard = tuple(_card(f"disc_{i}", CardType.NOUN) for i in range(10))
    # Park cards: deck=empty, discard=10 cards.
    state = state.model_copy(update={"deck": (), "discard": big_discard})
    # Drive build → resolve. Seats 1..3 forced-pass; dealer pass closes.
    for seat in (2, 3):
        state = _override_player_hand(state, seat, ())
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    # Build failed (only dealer fragment filled). The dealer fragment + the
    # 10 fabricated discards become discard; deck is still empty pre-refill.
    assert state.phase is Phase.ROUND_START
    # Now we need to drive a full round to test refill at resolve. Easier:
    # call enter_resolve on a synthetic RESOLVE state. Build a minimal one.
    # Simpler: just check that refill works in isolation via _refill_hands.
    from rulso.rules import _refill_hands

    rng = random.Random(99)
    # Strip everyone's hand to expose refill behaviour.
    state = state.model_copy(
        update={
            "deck": (),
            "discard": tuple(_card(f"d{i}", CardType.NOUN) for i in range(8)),
            "players": tuple(p.model_copy(update={"hand": ()}) for p in state.players),
        }
    )
    refilled = _refill_hands(state, rng)
    # 8 cards / 4 players = 2 cards each (deck fully drained).
    drawn_total = sum(len(p.hand) for p in refilled.players)
    assert drawn_total == 8
    assert refilled.discard == ()

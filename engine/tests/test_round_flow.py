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
    # RUL-75: dealer no longer pre-fills slot 0, so round_start always
    # reaches BUILD regardless of dealer hand. No injection needed.
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


def test_advance_from_round_start_enters_build_with_unfilled_slots() -> None:
    """RUL-75: dealer no longer pre-fills slot 0. All condition slots start
    unfilled; any player can play a matching card during BUILD."""
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
    assert all(s.filled_by is None for s in slots)
    assert state.active_rule.plays == ()


def test_round_start_slot_defs_match_condition_template() -> None:
    """Slot defs are driven by the CONDITION card, not hardcoded in rules.py."""
    template = load_condition_templates()[0]
    state = _drive_to_first_build(seed=0)
    rule = state.active_rule
    assert rule is not None
    assert rule.template is template.kind
    assert tuple(s.name for s in rule.slots) == tuple(cs.name for cs in template.slots)
    assert tuple(s.type for s in rule.slots) == tuple(cs.type for cs in template.slots)


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
    # Fill SUBJECT with one player, then try to overwrite from another seat.
    first = _card("first_subj", CardType.SUBJECT)
    state = _override_player_hand(state, 1, (first,))
    state = play_card(state, first, "SUBJECT")
    dup = _card("dup", CardType.SUBJECT)
    state = _override_player_hand(state, 2, (dup,))
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
    """RUL-75: SUBJECT must now be played during BUILD too — dealer no longer
    pre-fills it. Inject one matching card per slot across the three non-dealer
    seats; dealer forced-passes."""
    state = _drive_to_first_build(seed=0)
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("subj_p1", CardType.SUBJECT),))
    state = _override_player_hand(state, 0, ())
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
    state = pass_turn(state)  # dealer's build turn — all slots already filled
    assert state.phase is Phase.RESOLVE
    assert state.build_turns_taken == PLAYER_COUNT
    assert all(s.filled_by is not None for s in state.active_rule.slots)


def test_build_with_unfilled_slot_fails_back_to_round_start() -> None:
    state = _drive_to_first_build(seed=0)
    # Strip every hand so all four seats forced-pass → rule fails with no
    # slots filled. RUL-75: no dealer pre-fill, so discard ends empty.
    for seat in range(PLAYER_COUNT):
        state = _override_player_hand(state, seat, ())
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1
    assert state.active_rule is None
    assert state.discard == ()


def test_resolve_transitions_to_round_start_and_rotates_dealer() -> None:
    state = _drive_to_first_build(seed=0)
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("subj_p1", CardType.SUBJECT),))
    state = _override_player_hand(state, 0, ())
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
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
    state = _override_player_hand(state, 3, (_card("subj_p1", CardType.SUBJECT),))
    state = _override_player_hand(state, 0, ())
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
    state = pass_turn(state)
    state = advance_phase(state, rng=random.Random(0))
    assert state.phase in (Phase.ROUND_START, Phase.END)


def test_dealer_rotates_across_four_rounds_via_failed_rules() -> None:
    """Inject all-empty hands so every round fails; assert dealer rotates 0,1,2,3.

    RUL-75: empty hands now enter BUILD (no dealer seed-fill) and fail at
    end-of-revolution with all slots unfilled. Drive the full revolution per
    round.

    RUL-56: ``shop_pool`` overridden to empty so the SHOP cadence (round 3)
    skips and the test exercises only the unfilled-slot rotation path.
    """
    state = start_game()
    state = state.model_copy(update={"shop_pool": ()})
    for seat in range(PLAYER_COUNT):
        state = _override_player_hand(state, seat, ())
    seen_dealers: list[int] = []
    seen_rounds: list[int] = []
    for _ in range(PLAYER_COUNT):
        prior = state.dealer_seat
        prior_round = state.round_number
        state = advance_phase(state)
        assert state.phase is Phase.BUILD
        for _ in range(PLAYER_COUNT):
            state = pass_turn(state)
        assert state.phase is Phase.ROUND_START
        seen_dealers.append(prior)
        seen_rounds.append(prior_round + 1)
    assert seen_dealers == [0, 1, 2, 3]
    assert seen_rounds == [1, 2, 3, 4]


def test_advance_from_lobby_enters_build() -> None:
    """LOBBY → ROUND_START → BUILD via advance_phase. RUL-75: dealer no longer
    needs to hold a SUBJECT — slots all start unfilled."""
    state = GameState(
        phase=Phase.LOBBY,
        players=tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT)),
    )
    state = advance_phase(state)
    assert state.phase is Phase.BUILD
    assert state.round_number == 1


def test_advance_from_shop_with_empty_offer_resumes_round_start() -> None:
    """RUL-51: SHOP can be entered manually with no offers; advance_phase
    treats the empty offer as "all unsold" and resumes round_start steps 6-8.

    RUL-75: with no dealer seed-fill, the stub state now reaches BUILD
    cleanly. All four seats forced-pass → rule fails → ROUND_START with
    rotated dealer.
    """
    state = GameState(
        phase=Phase.SHOP,
        players=tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT)),
    )
    out = advance_phase(state)
    assert out.phase is Phase.BUILD
    for _ in range(PLAYER_COUNT):
        out = pass_turn(out)
    assert out.phase is Phase.ROUND_START
    assert out.dealer_seat == 1


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
    state = _override_player_hand(state, 3, (_card("subj_p1", CardType.SUBJECT),))
    state = _override_player_hand(state, 0, ())
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
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


# --- RUL-47 additions: effect-deck draw and discard -------------------------


def test_round_start_reveals_real_card_from_seeded_effect_deck() -> None:
    """Step 6 pops the top of ``effect_deck`` into ``revealed_effect`` and the
    deck shortens by one (no NOOP placeholder)."""
    state = start_game(seed=0)
    seeded_effect_deck = state.effect_deck
    assert len(seeded_effect_deck) > 0  # cards.yaml seeds 12 effect cards.
    expected_card = seeded_effect_deck[-1]  # _draw_effect_card pops the tail.

    state = _drive_to_first_build(seed=0)
    assert state.revealed_effect == expected_card
    assert state.revealed_effect.type is CardType.EFFECT
    assert len(state.effect_deck) == len(seeded_effect_deck) - 1
    assert state.effect_discard == ()


def test_round_start_pop_is_deterministic_under_seed() -> None:
    """Same seed ⇒ same revealed_effect at first round_start."""
    s1 = _drive_to_first_build(seed=42)
    s2 = _drive_to_first_build(seed=42)
    assert s1.revealed_effect == s2.revealed_effect


def test_resolve_appends_consumed_effect_to_effect_discard() -> None:
    """Step 10 pushes the round's revealed_effect to effect_discard and clears
    revealed_effect (mirrors fragment cleanup)."""
    state = _drive_to_first_build(seed=0)
    consumed = state.revealed_effect
    assert consumed is not None
    state = _override_player_hand(
        state, 1, (Card(id="quant_le_5", type=CardType.MODIFIER, name="LE:5"),)
    )
    state = _override_player_hand(
        state, 2, (Card(id="noun_chips", type=CardType.NOUN, name="CHIPS"),)
    )
    state = _override_player_hand(state, 3, (_card("subj_p1", CardType.SUBJECT),))
    state = _override_player_hand(state, 0, ())
    state = play_card(state, state.players[1].hand[0], "QUANT")
    state = play_card(state, state.players[2].hand[0], "NOUN")
    state = play_card(state, state.players[3].hand[0], "SUBJECT")
    state = pass_turn(state)
    state = enter_resolve(state, rng=random.Random(0))
    assert state.revealed_effect is None
    assert consumed in state.effect_discard


def test_failed_rule_pushes_revealed_effect_to_effect_discard() -> None:
    """Build-fail path (slot unfilled after the revolution) discards the
    revealed_effect rather than losing it."""
    state = _drive_to_first_build(seed=0)
    consumed = state.revealed_effect
    assert consumed is not None
    # All non-dealer seats forced-pass → unfilled NOUN/QUANT → fail.
    for seat in (1, 2, 3):
        state = _override_player_hand(state, seat, ())
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    state = pass_turn(state)
    assert state.phase is Phase.ROUND_START
    assert state.revealed_effect is None
    assert consumed in state.effect_discard


def test_effect_deck_recycles_when_empty() -> None:
    """When effect_deck is empty at step 6, effect_discard reshuffles back."""
    from rulso.rules import _draw_effect_card

    discard = (
        Card(id="eff.a", type=CardType.EFFECT, name="GAIN_VP:1"),
        Card(id="eff.b", type=CardType.EFFECT, name="GAIN_CHIPS:5"),
    )
    rng = random.Random(0)
    drawn, deck, new_discard = _draw_effect_card((), discard, rng)
    assert drawn is not None
    assert drawn in discard
    assert new_discard == ()  # all moved into deck before pop.
    assert len(deck) == 1


def test_effect_deck_recycle_is_seed_deterministic() -> None:
    """Same seed ⇒ same recycle order ⇒ same drawn card."""
    from rulso.rules import _draw_effect_card

    discard = tuple(
        Card(id=f"eff.{i}", type=CardType.EFFECT, name=f"GAIN_VP:{i}") for i in range(6)
    )
    a = _draw_effect_card((), discard, random.Random(7))
    b = _draw_effect_card((), discard, random.Random(7))
    assert a == b


def test_effect_deck_recycle_when_both_piles_empty_returns_none() -> None:
    """Edge case: both piles empty → revealed_effect stays None."""
    from rulso.rules import _draw_effect_card

    drawn, deck, discard = _draw_effect_card((), (), random.Random(0))
    assert drawn is None
    assert deck == ()
    assert discard == ()


def test_multi_round_game_conserves_effect_card_total() -> None:
    """Across many rounds (some succeed, some fail), the count of cards in
    effect_deck + effect_discard + (1 if revealed_effect else 0) equals the
    seeded total. No card is silently lost."""
    initial = start_game(seed=0)
    total = len(initial.effect_deck)
    state = initial
    for _ in range(20):
        state = advance_phase(state, rng=random.Random(state.round_number))
        # Drive any active build to a passed revolution to reach RESOLVE / fail.
        guard = 0
        while state.phase is Phase.BUILD and guard < PLAYER_COUNT * 2:
            state = pass_turn(state)
            guard += 1
        if state.phase is Phase.RESOLVE:
            state = enter_resolve(state, rng=random.Random(state.round_number + 1))
        if state.phase is Phase.END:
            break
        in_play = 1 if state.revealed_effect is not None else 0
        assert len(state.effect_deck) + len(state.effect_discard) + in_play == total

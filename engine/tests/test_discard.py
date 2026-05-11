"""``rules.discard_redraw`` substrate (RUL-68).

Pins the BUILD-phase discard pipeline: chip cost, hand→discard movement,
replacement draw from ``state.deck``, recycle path when the deck exhausts,
and the three ValueError surfaces (out-of-turn, unknown card, insufficient
chips). Mirrors the disjoint-rng pattern of :func:`rules._refill_hands` —
``refill_rng`` is required only when the recycle fires.
"""

from __future__ import annotations

import random

import pytest

from rulso.rules import (
    advance_phase,
    discard_redraw,
    start_game,
)
from rulso.state import (
    DISCARD_COST,
    HAND_SIZE,
    Card,
    CardType,
    GameState,
    Phase,
)


def _card(cid: str, type_: CardType = CardType.NOUN) -> Card:
    return Card(id=cid, type=type_, name=cid)


def _drive_to_first_build(seed: int = 0) -> GameState:
    state = start_game(seed)
    # Inject a SUBJECT into the dealer's hand so round_start step 7 doesn't
    # fail. Mirrors test_round_flow's helper.
    seed_subject = Card(id="subj.p0", type=CardType.SUBJECT, name="p0")
    dealer = state.players[state.dealer_seat]
    new_dealer = dealer.model_copy(update={"hand": (seed_subject,) + dealer.hand})
    new_players = tuple(new_dealer if p.seat == state.dealer_seat else p for p in state.players)
    state = state.model_copy(update={"players": new_players})
    return advance_phase(state)


def _override_hand(state: GameState, seat: int, hand: tuple[Card, ...]) -> GameState:
    new_players = tuple(
        p.model_copy(update={"hand": hand}) if p.seat == seat else p for p in state.players
    )
    return state.model_copy(update={"players": new_players})


def _override_chips(state: GameState, seat: int, chips: int) -> GameState:
    new_players = tuple(
        p.model_copy(update={"chips": chips}) if p.seat == seat else p for p in state.players
    )
    return state.model_copy(update={"players": new_players})


def _stock_deck(state: GameState, replacements: tuple[Card, ...]) -> GameState:
    """Put ``replacements`` at the tail of the deck so they pop first.

    ``_draw_n`` pops from the right; the last element gets drawn first.
    """
    return state.model_copy(update={"deck": state.deck + replacements})


def test_discard_single_card_costs_DISCARD_COST_and_redraws_one() -> None:
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    card_to_drop = _card("drop1")
    other = _card("keep")
    state = _override_hand(state, seat, (card_to_drop, other))
    state = _override_chips(state, seat, DISCARD_COST + 1)
    replacement = _card("repl")
    state = _stock_deck(state, (replacement,))
    chips_before = state.players[seat].chips
    discard_before = len(state.discard)

    out = discard_redraw(
        state, state.players[seat].id, (card_to_drop.id,), refill_rng=random.Random(0)
    )

    actor = out.players[seat]
    assert actor.chips == chips_before - DISCARD_COST
    hand_ids = {c.id for c in actor.hand}
    assert card_to_drop.id not in hand_ids
    assert other.id in hand_ids
    assert replacement.id in hand_ids
    assert any(c.id == card_to_drop.id for c in out.discard[discard_before:])


def test_discard_two_cards_costs_two_units() -> None:
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    a, b, c = _card("a"), _card("b"), _card("c")
    state = _override_hand(state, seat, (a, b, c))
    state = _override_chips(state, seat, DISCARD_COST * 2 + 1)
    repls = (_card("r1"), _card("r2"))
    state = _stock_deck(state, repls)
    out = discard_redraw(state, state.players[seat].id, (a.id, b.id), refill_rng=random.Random(0))
    assert out.players[seat].chips == DISCARD_COST * 2 + 1 - DISCARD_COST * 2
    hand_ids = {c.id for c in out.players[seat].hand}
    assert {"c", "r1", "r2"} <= hand_ids
    assert "a" not in hand_ids and "b" not in hand_ids


def test_discard_three_cards_costs_three_units() -> None:
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    cards = tuple(_card(f"d{i}") for i in range(4))
    state = _override_hand(state, seat, cards)
    state = _override_chips(state, seat, DISCARD_COST * 3 + 2)
    repls = (_card("r1"), _card("r2"), _card("r3"))
    state = _stock_deck(state, repls)
    out = discard_redraw(
        state,
        state.players[seat].id,
        (cards[0].id, cards[1].id, cards[2].id),
        refill_rng=random.Random(0),
    )
    assert out.players[seat].chips == 2
    hand_ids = {c.id for c in out.players[seat].hand}
    assert {"d3", "r1", "r2", "r3"} == hand_ids


def test_discard_replacements_come_from_deck_tail_in_order() -> None:
    """``_draw_n`` pops from the right, so the deck's last card lands first."""
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    drop = _card("drop")
    state = _override_hand(state, seat, (drop,))
    state = _override_chips(state, seat, DISCARD_COST)
    # Clear the deck and stock exactly one replacement so we can pin it.
    state = state.model_copy(update={"deck": ()})
    sentinel = _card("sentinel")
    state = _stock_deck(state, (sentinel,))
    out = discard_redraw(state, state.players[seat].id, (drop.id,), refill_rng=random.Random(0))
    assert out.players[seat].hand == (sentinel,)


def test_discard_recycle_when_deck_empty_uses_refill_rng() -> None:
    """Deck empty + non-empty discard ⇒ recycle via ``refill_rng``.

    The just-discarded card lands in the discard pile alongside any other
    cards there; the recycle path shuffles the pile back into the deck
    and pops the replacement. Two same-seed rngs produce identical draws.
    """
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    drop = _card("drop")
    state = _override_hand(state, seat, (drop,))
    state = _override_chips(state, seat, DISCARD_COST)
    # Seed the deck empty and stuff existing discard with a marker card.
    marker = _card("recycle_marker")
    state = state.model_copy(update={"deck": (), "discard": (marker,)})
    out_a = discard_redraw(state, state.players[seat].id, (drop.id,), refill_rng=random.Random(7))
    out_b = discard_redraw(state, state.players[seat].id, (drop.id,), refill_rng=random.Random(7))
    # Same rng → same outcome. The drawn card came from the recycled pile
    # (either the marker or the just-discarded drop).
    drawn_a = out_a.players[seat].hand
    drawn_b = out_b.players[seat].hand
    assert drawn_a == drawn_b
    assert len(drawn_a) == 1
    assert drawn_a[0].id in {"recycle_marker", "drop"}


def test_discard_recycle_without_rng_raises() -> None:
    """Reaching the recycle path with ``refill_rng=None`` raises (RUL-54 rule)."""
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    drop = _card("drop")
    state = _override_hand(state, seat, (drop,))
    state = _override_chips(state, seat, DISCARD_COST)
    state = state.model_copy(update={"deck": (), "discard": (_card("marker"),)})
    with pytest.raises(ValueError, match="seeded rng required"):
        discard_redraw(state, state.players[seat].id, (drop.id,), refill_rng=None)


def test_discard_out_of_turn_raises() -> None:
    state = _drive_to_first_build(seed=0)
    other_seat = (state.active_seat + 1) % len(state.players)
    other_id = state.players[other_seat].id
    drop = _card("drop")
    state = _override_hand(state, other_seat, (drop,))
    state = _override_chips(state, other_seat, DISCARD_COST)
    with pytest.raises(ValueError, match="out-of-turn"):
        discard_redraw(state, other_id, (drop.id,), refill_rng=random.Random(0))


def test_discard_unknown_card_raises() -> None:
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    state = _override_hand(state, seat, (_card("real"),))
    state = _override_chips(state, seat, DISCARD_COST)
    with pytest.raises(ValueError, match="not in"):
        discard_redraw(state, state.players[seat].id, ("ghost",), refill_rng=random.Random(0))


def test_discard_insufficient_chips_raises() -> None:
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    a, b = _card("a"), _card("b")
    state = _override_hand(state, seat, (a, b))
    state = _override_chips(state, seat, DISCARD_COST * 2 - 1)
    with pytest.raises(ValueError, match="cannot afford"):
        discard_redraw(state, state.players[seat].id, (a.id, b.id), refill_rng=random.Random(0))


def test_discard_outside_build_phase_raises() -> None:
    state = start_game(seed=0)
    assert state.phase is Phase.ROUND_START
    pid = state.players[state.active_seat].id
    drop_id = state.players[state.active_seat].hand[0].id
    with pytest.raises(ValueError, match="requires phase=BUILD"):
        discard_redraw(state, pid, (drop_id,), refill_rng=random.Random(0))


def test_discard_empty_card_ids_raises() -> None:
    state = _drive_to_first_build(seed=0)
    pid = state.players[state.active_seat].id
    with pytest.raises(ValueError, match="at least one card_id"):
        discard_redraw(state, pid, (), refill_rng=random.Random(0))


def test_discard_advances_active_seat() -> None:
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    drop = _card("drop")
    state = _override_hand(state, seat, (drop,))
    state = _override_chips(state, seat, DISCARD_COST)
    out = discard_redraw(state, state.players[seat].id, (drop.id,), refill_rng=random.Random(0))
    assert out.active_seat == (seat + 1) % len(state.players)
    assert out.build_turns_taken == state.build_turns_taken + 1


def test_discard_hand_size_preserved_when_deck_has_cards() -> None:
    """Discard-then-redraw keeps the hand at its pre-discard size."""
    state = _drive_to_first_build(seed=0)
    seat = state.active_seat
    cards = tuple(_card(f"x{i}") for i in range(HAND_SIZE))
    state = _override_hand(state, seat, cards)
    state = _override_chips(state, seat, DISCARD_COST * 3)
    repls = tuple(_card(f"r{i}") for i in range(3))
    state = _stock_deck(state, repls)
    out = discard_redraw(
        state,
        state.players[seat].id,
        (cards[0].id, cards[1].id, cards[2].id),
        refill_rng=random.Random(0),
    )
    assert len(out.players[seat].hand) == HAND_SIZE

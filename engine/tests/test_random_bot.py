"""Tests for bots/random.py — random-legal bot."""

from __future__ import annotations

import random

import pytest

from rulso.bots.random import PLAY_BIAS, choose_action
from rulso.legality import DiscardRedraw, Pass, PlayCard
from rulso.state import (
    Card,
    CardType,
    GameState,
    Phase,
    Player,
    PlayerStatus,
    RuleBuilder,
    RuleKind,
    Slot,
)


def _build_state(
    player_hand: tuple[Card, ...],
    slots: tuple[Slot, ...],
    *,
    chips: int = 50,
    mute: bool = False,
    active_seat: int = 1,
    dealer_seat: int = 0,
) -> GameState:
    players = tuple(
        Player(
            id=f"p{i}",
            seat=i,
            chips=chips if i == active_seat else 50,
            hand=player_hand if i == active_seat else (),
            status=PlayerStatus(mute=mute) if i == active_seat else PlayerStatus(),
        )
        for i in range(4)
    )
    rule = RuleBuilder(template=RuleKind.IF, slots=slots)
    return GameState(
        phase=Phase.BUILD,
        round_number=1,
        dealer_seat=dealer_seat,
        active_seat=active_seat,
        players=players,
        active_rule=rule,
    )


# --- M1 empty-hand baseline ---------------------------------------------------


def test_pass_when_hand_empty() -> None:
    state = _build_state(
        player_hand=(),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
    )
    assert isinstance(choose_action(state, "p1", random.Random(0)), Pass)


# --- Slot-compatibility filter ------------------------------------------------


def test_legal_play_uses_type_compatible_slot() -> None:
    subj = Card(id="s1", type=CardType.SUBJECT, name="ANYONE")
    noun = Card(id="n1", type=CardType.NOUN, name="A_GOLD_BAG")
    state = _build_state(
        player_hand=(subj, noun),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=0,  # no discards so the only option is to play the SUBJECT card
    )
    rng = random.Random(0)
    action = choose_action(state, "p1", rng)
    assert isinstance(action, PlayCard)
    assert action.card_id == "s1"
    assert action.slot == "subject"
    assert action.dice is None


def test_pass_when_no_type_match_and_no_chips() -> None:
    noun = Card(id="n1", type=CardType.NOUN, name="A_GOLD_BAG")
    state = _build_state(
        player_hand=(noun,),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=0,
    )
    assert isinstance(choose_action(state, "p1", random.Random(7)), Pass)


def test_filled_slot_not_offered() -> None:
    subj = Card(id="s1", type=CardType.SUBJECT, name="ANYONE")
    noun = Card(id="n1", type=CardType.NOUN, name="A_GOLD_BAG")
    state = _build_state(
        player_hand=(subj, noun),
        slots=(
            Slot(name="subject", type=CardType.SUBJECT, filled_by=subj),  # already filled
            Slot(name="noun", type=CardType.NOUN),
        ),
        chips=0,
    )
    action = choose_action(state, "p1", random.Random(0))
    assert isinstance(action, PlayCard)
    assert action.slot == "noun"
    assert action.card_id == "n1"


# --- MUTE check ---------------------------------------------------------------


def test_mute_blocks_modifier_plays() -> None:
    mod = Card(id="m1", type=CardType.MODIFIER, name="MORE-THAN")
    state = _build_state(
        player_hand=(mod,),
        slots=(Slot(name="modifier", type=CardType.MODIFIER),),
        chips=0,
        mute=True,
    )
    assert isinstance(choose_action(state, "p1", random.Random(0)), Pass)


def test_unmuted_player_can_play_modifier() -> None:
    mod = Card(id="m1", type=CardType.MODIFIER, name="MORE-THAN")
    state = _build_state(
        player_hand=(mod,),
        slots=(Slot(name="modifier", type=CardType.MODIFIER),),
        chips=0,
        mute=False,
    )
    action = choose_action(state, "p1", random.Random(0))
    assert isinstance(action, PlayCard)
    assert action.card_id == "m1"


# --- Dice for comparator MODIFIERs --------------------------------------------


def test_modifier_play_always_has_dice() -> None:
    mod = Card(id="m1", type=CardType.MODIFIER, name="MORE-THAN")
    state = _build_state(
        player_hand=(mod,),
        slots=(Slot(name="modifier", type=CardType.MODIFIER),),
        chips=0,
    )
    for seed in range(20):
        action = choose_action(state, "p1", random.Random(seed))
        assert isinstance(action, PlayCard)
        assert action.dice in (1, 2)


def test_modifier_dice_includes_both_values_across_seeds() -> None:
    mod = Card(id="m1", type=CardType.MODIFIER, name="MORE-THAN")
    state = _build_state(
        player_hand=(mod,),
        slots=(Slot(name="modifier", type=CardType.MODIFIER),),
        chips=0,
    )
    seen = {choose_action(state, "p1", random.Random(s)).dice for s in range(50)}  # type: ignore[union-attr]
    assert seen == {1, 2}


def test_non_modifier_play_has_no_dice() -> None:
    subj = Card(id="s1", type=CardType.SUBJECT, name="ANYONE")
    state = _build_state(
        player_hand=(subj,),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=0,
    )
    action = choose_action(state, "p1", random.Random(0))
    assert isinstance(action, PlayCard)
    assert action.dice is None


# --- Discard availability -----------------------------------------------------


def test_discard_offered_when_chips_sufficient() -> None:
    noun = Card(id="n1", type=CardType.NOUN, name="A_GOLD_BAG")
    state = _build_state(
        player_hand=(noun,),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),  # no compatible slot
        chips=50,
    )
    # Only legal action is discard; bot must return DiscardRedraw, not Pass.
    seen_discard = any(
        isinstance(choose_action(state, "p1", random.Random(s)), DiscardRedraw) for s in range(30)
    )
    assert seen_discard


def test_discard_blocked_when_chips_zero() -> None:
    noun = Card(id="n1", type=CardType.NOUN, name="A_GOLD_BAG")
    state = _build_state(
        player_hand=(noun,),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=0,
    )
    assert isinstance(choose_action(state, "p1", random.Random(0)), Pass)


def test_discard_card_ids_subset_of_hand() -> None:
    cards = tuple(Card(id=f"c{i}", type=CardType.NOUN, name=f"N{i}") for i in range(5))
    state = _build_state(
        player_hand=cards,
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=50,
    )
    hand_ids = {c.id for c in cards}
    for seed in range(50):
        action = choose_action(state, "p1", random.Random(seed))
        if isinstance(action, DiscardRedraw):
            assert set(action.card_ids) <= hand_ids
            assert 1 <= len(action.card_ids) <= 3
            assert len(action.card_ids) == len(set(action.card_ids)), "duplicate card ids"


# --- Determinism --------------------------------------------------------------


def test_deterministic_with_same_seed() -> None:
    cards = (
        Card(id="s1", type=CardType.SUBJECT, name="A"),
        Card(id="n1", type=CardType.NOUN, name="B"),
        Card(id="m1", type=CardType.MODIFIER, name="C"),
    )
    state = _build_state(
        player_hand=cards,
        slots=(
            Slot(name="subject", type=CardType.SUBJECT),
            Slot(name="noun", type=CardType.NOUN),
            Slot(name="modifier", type=CardType.MODIFIER),
        ),
        chips=50,
    )
    result_a = choose_action(state, "p1", random.Random(999))
    result_b = choose_action(state, "p1", random.Random(999))
    assert result_a == result_b


# --- Never-illegal invariant over many seeds ----------------------------------


def test_invariant_never_returns_illegal_action() -> None:
    cards = (
        Card(id="s1", type=CardType.SUBJECT, name="A"),
        Card(id="n1", type=CardType.NOUN, name="B"),
        Card(id="n2", type=CardType.NOUN, name="C"),
        Card(id="m1", type=CardType.MODIFIER, name="D"),
        Card(id="m2", type=CardType.MODIFIER, name="E"),
    )
    filled_subj = Card(id="s0", type=CardType.SUBJECT, name="ANYONE")
    slots = (
        Slot(name="subject", type=CardType.SUBJECT, filled_by=filled_subj),
        Slot(name="noun", type=CardType.NOUN),
        Slot(name="modifier", type=CardType.MODIFIER),
    )
    state = _build_state(player_hand=cards, slots=slots, chips=15)
    open_slots = {s.name: s.type for s in slots if s.filled_by is None}
    hand_ids = {c.id: c for c in cards}

    for seed in range(1000):
        action = choose_action(state, "p1", random.Random(seed))
        if isinstance(action, PlayCard):
            assert action.slot in open_slots, f"seed={seed}: illegal slot {action.slot!r}"
            card = hand_ids.get(action.card_id)
            assert card is not None, f"seed={seed}: card_id {action.card_id!r} not in hand"
            assert card.type == open_slots[action.slot], (
                f"seed={seed}: type mismatch: card {card.type} vs slot {open_slots[action.slot]}"
            )
            if card.type is CardType.MODIFIER:
                assert action.dice in (1, 2), f"seed={seed}: MODIFIER play missing dice"
            else:
                assert action.dice is None, f"seed={seed}: unexpected dice on non-MODIFIER"
        elif isinstance(action, DiscardRedraw):
            assert 1 <= len(action.card_ids) <= 3, f"seed={seed}: bad discard count"
            assert all(cid in hand_ids for cid in action.card_ids), (
                f"seed={seed}: discard contains unknown card"
            )
            assert len(action.card_ids) == len(set(action.card_ids)), (
                f"seed={seed}: duplicate card in discard"
            )
        else:
            assert isinstance(action, Pass), f"seed={seed}: unexpected action type {type(action)}"
            pytest.fail(f"seed={seed}: Pass returned but legal plays exist")


# --- Play-over-discard bias ---------------------------------------------------


def test_play_preferred_over_discard_when_both_legal() -> None:
    """When both pools are non-empty the bot picks plays >70% of the time.

    Threshold is loose enough to absorb sampling noise (expected rate is
    ``PLAY_BIAS`` = 0.85; std over 1000 trials ≈ 1.1pp), tight enough to
    catch a regression to uniform sampling.
    """
    cards = (
        Card(id="s1", type=CardType.SUBJECT, name="A"),
        Card(id="n1", type=CardType.NOUN, name="B"),
    )
    slots = (
        Slot(name="subject", type=CardType.SUBJECT),
        Slot(name="noun", type=CardType.NOUN),
    )
    state = _build_state(player_hand=cards, slots=slots, chips=50)
    play_count = sum(
        1
        for seed in range(1000)
        if isinstance(choose_action(state, "p1", random.Random(seed)), PlayCard)
    )
    assert play_count > 700, (
        f"play_card chosen {play_count}/1000; expected ~{int(PLAY_BIAS * 1000)} "
        f"(bias missing or reverted to uniform)"
    )


# --- Non-BUILD phase ----------------------------------------------------------


def test_returns_pass_outside_build_phase() -> None:
    subj = Card(id="s1", type=CardType.SUBJECT, name="ANYONE")
    state = _build_state(player_hand=(subj,), slots=()).model_copy(
        update={"phase": Phase.ROUND_START}
    )
    assert isinstance(choose_action(state, "p1", random.Random(0)), Pass)

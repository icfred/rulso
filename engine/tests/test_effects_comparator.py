"""Tests for OP-only comparator dice flow per ADR-0002 (RUL-42).

Covers:
* Each operator (LT/LE/GT/GE/EQ) baked from a ``last_roll`` value evaluates
  correctly inside ``effects.resolve_if_rule``.
* 1d6 (dice_count=1) and 2d6 (dice_count=2) paths read the same ``value``
  field — dice_count is an audit field, not consumed by evaluation.
* Boundary cases (HAS-true, HAS-false) per operator.
* Missing ``last_roll`` raises a clear error.
* Baked-N comparators ignore ``last_roll`` (M1.5 grandfathered path).
* ``rules.play_card`` records ``LastRoll`` when an OP-only comparator is
  played; non-OP-only plays leave ``last_roll`` untouched.
"""

from __future__ import annotations

import pytest

from rulso.effects import resolve_if_rule
from rulso.rules import play_card
from rulso.state import (
    Card,
    CardType,
    GameState,
    LastRoll,
    Phase,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- Helpers ----------------------------------------------------------------


def _subject(name: str) -> Card:
    return Card(id=f"sub_{name.lower()}", type=CardType.SUBJECT, name=name)


def _quant_op_only(op: str) -> Card:
    return Card(id=f"q_{op.lower()}", type=CardType.MODIFIER, name=op)


def _quant_baked(op: str, n: int) -> Card:
    return Card(id=f"q_{op.lower()}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


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


def _player(pid: str, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=0, chips=chips, vp=vp)


_GAIN_VP_1 = Card(id="eff.vp.gain.1", type=CardType.EFFECT, name="GAIN_VP:1")


def _state_with_roll(value: int, *, dice_count: int = 2, players: tuple[Player, ...]) -> GameState:
    return GameState(
        players=players,
        last_roll=LastRoll(player_id="p0", value=value, dice_count=dice_count),
        revealed_effect=_GAIN_VP_1,
    )


# --- Per-operator OP-only resolution ----------------------------------------


def test_op_only_lt_true_with_dice_value() -> None:
    """LT bakes ``last_roll.value`` as N — chips < N fires."""
    state = _state_with_roll(10, players=(_player("p0", chips=5),))
    rule = _if_rule(_subject("p0"), _quant_op_only("LT"), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1


def test_op_only_lt_false_on_equal_with_dice_value() -> None:
    """LT is strict — chips == N does not fire."""
    state = _state_with_roll(10, players=(_player("p0", chips=10),))
    rule = _if_rule(_subject("p0"), _quant_op_only("LT"), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


def test_op_only_le_true_on_equal_with_dice_value() -> None:
    """LE is non-strict — chips == N fires."""
    state = _state_with_roll(7, players=(_player("p0", chips=7),))
    rule = _if_rule(_subject("p0"), _quant_op_only("LE"), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1


def test_op_only_gt_true_with_dice_value() -> None:
    state = _state_with_roll(5, players=(_player("p0", chips=6),))
    rule = _if_rule(_subject("p0"), _quant_op_only("GT"), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].vp == 1


def test_op_only_gt_false_on_equal_with_dice_value() -> None:
    state = _state_with_roll(5, players=(_player("p0", chips=5),))
    rule = _if_rule(_subject("p0"), _quant_op_only("GT"), _noun("CHIPS"))
    assert resolve_if_rule(state, rule) == state


def test_op_only_ge_true_on_equal_with_dice_value() -> None:
    state = _state_with_roll(50, players=(_player("p0", chips=50),))
    rule = _if_rule(_subject("p0"), _quant_op_only("GE"), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].vp == 1


def test_op_only_eq_true_with_dice_value() -> None:
    state = _state_with_roll(3, players=(_player("p0", vp=3),))
    rule = _if_rule(_subject("p0"), _quant_op_only("EQ"), _noun("VP"))
    assert resolve_if_rule(state, rule).players[0].vp == 4  # +1 from stub


def test_op_only_eq_false_off_by_one() -> None:
    state = _state_with_roll(3, players=(_player("p0", vp=4),))
    rule = _if_rule(_subject("p0"), _quant_op_only("EQ"), _noun("VP"))
    assert resolve_if_rule(state, rule) == state


# --- 1d6 vs 2d6 audit ---------------------------------------------------------


def test_op_only_1d6_path_reads_same_value_field() -> None:
    """dice_count=1 (1d6) — value drives evaluation, dice_count is audit only."""
    state = _state_with_roll(4, dice_count=1, players=(_player("p0", chips=3),))
    rule = _if_rule(_subject("p0"), _quant_op_only("LT"), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.last_roll is not None
    assert new.last_roll.dice_count == 1


def test_op_only_2d6_path_reads_same_value_field() -> None:
    """dice_count=2 (2d6) — value=12 is a valid 2d6 high; LE 12 always fires."""
    state = _state_with_roll(12, dice_count=2, players=(_player("p0", chips=12),))
    rule = _if_rule(_subject("p0"), _quant_op_only("LE"), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.last_roll is not None
    assert new.last_roll.dice_count == 2


# --- Error path -------------------------------------------------------------


def test_op_only_without_last_roll_raises() -> None:
    """OP-only quant with no ``state.last_roll`` is a wiring bug — raise."""
    state = GameState(players=(_player("p0"),))
    rule = _if_rule(_subject("p0"), _quant_op_only("LT"), _noun("CHIPS"))
    with pytest.raises(ValueError, match="OP-only comparator"):
        resolve_if_rule(state, rule)


# --- Backward compat: baked-N path ignores last_roll -------------------------


def test_baked_n_quant_ignores_last_roll() -> None:
    """``LT:5`` (M1.5 grandfathered) reads N from card.name, not last_roll."""
    # last_roll says 50 (would always fire LT) but baked card says LT:5.
    state = _state_with_roll(50, players=(_player("p0", chips=5),))
    rule = _if_rule(_subject("p0"), _quant_baked("LT", 5), _noun("CHIPS"))
    # chips=5, threshold=5, LT strict → no fire (regardless of last_roll).
    assert resolve_if_rule(state, rule) == state


def test_baked_n_quant_with_no_last_roll_still_works() -> None:
    """Baked-N path is independent of last_roll presence (M1.5 path)."""
    state = GameState(players=(_player("p0", chips=4),), revealed_effect=_GAIN_VP_1)
    rule = _if_rule(_subject("p0"), _quant_baked("LT", 5), _noun("CHIPS"))
    assert resolve_if_rule(state, rule).players[0].vp == 1


# --- play_card last_roll wiring ---------------------------------------------


def _build_state_for_play(
    *,
    quant_card: Card,
    seat: int = 0,
) -> GameState:
    """Construct a BUILD-phase state with ``quant_card`` in seat 0's hand and
    a 3-slot IF rule with QUANT open.
    """
    players = tuple(
        Player(
            id=f"p{i}",
            seat=i,
            chips=50,
            hand=(quant_card,) if i == seat else (),
        )
        for i in range(4)
    )
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(
                name="SUBJECT",
                type=CardType.SUBJECT,
                filled_by=Card(id="subj.p0", type=CardType.SUBJECT, name="p0"),
            ),
            Slot(name="QUANT", type=CardType.MODIFIER),
            Slot(
                name="NOUN",
                type=CardType.NOUN,
                filled_by=Card(id="noun.chips", type=CardType.NOUN, name="CHIPS"),
            ),
        ),
    )
    return GameState(
        phase=Phase.BUILD,
        round_number=1,
        dealer_seat=0,
        active_seat=seat,
        players=players,
        active_rule=rule,
        build_turns_taken=0,
        revealed_effect=_GAIN_VP_1,
    )


def test_play_card_records_last_roll_for_op_only_comparator() -> None:
    quant = _quant_op_only("GT")
    state = _build_state_for_play(quant_card=quant)
    new = play_card(state, quant, "QUANT", dice_mode=2, dice_roll=8)
    assert new.last_roll is not None
    assert new.last_roll.value == 8
    assert new.last_roll.dice_count == 2
    assert new.last_roll.player_id == "p0"


def test_play_card_op_only_without_dice_raises() -> None:
    quant = _quant_op_only("LT")
    state = _build_state_for_play(quant_card=quant)
    with pytest.raises(ValueError, match="dice_mode and dice_roll"):
        play_card(state, quant, "QUANT")


def test_play_card_op_only_rejects_invalid_dice_mode() -> None:
    quant = _quant_op_only("EQ")
    state = _build_state_for_play(quant_card=quant)
    with pytest.raises(ValueError, match="dice_mode must be 1 or 2"):
        play_card(state, quant, "QUANT", dice_mode=3, dice_roll=5)


def test_play_card_baked_n_ignores_dice_kwargs() -> None:
    """Baked-N plays leave last_roll untouched; dice kwargs are ignored."""
    quant = _quant_baked("LT", 5)
    state = _build_state_for_play(quant_card=quant)
    new = play_card(state, quant, "QUANT", dice_mode=2, dice_roll=8)
    assert new.last_roll is None  # baked-N path doesn't stamp


def test_play_card_non_modifier_ignores_dice_kwargs() -> None:
    """SUBJECT/NOUN plays don't stamp last_roll even if dice kwargs set."""
    subj = Card(id="subj.p1", type=CardType.SUBJECT, name="p1")
    state = _build_state_for_play(quant_card=subj).model_copy(
        update={
            "active_rule": RuleBuilder(
                template=RuleKind.IF,
                slots=(
                    Slot(name="SUBJECT", type=CardType.SUBJECT),
                    Slot(name="QUANT", type=CardType.MODIFIER),
                    Slot(name="NOUN", type=CardType.NOUN),
                ),
            ),
        }
    )
    new = play_card(state, subj, "SUBJECT", dice_mode=2, dice_roll=8)
    assert new.last_roll is None


# --- End-to-end: play + resolve loop -----------------------------------------


def test_play_then_resolve_op_only_threads_dice() -> None:
    """play_card stamps last_roll; resolve_if_rule reads it back."""
    quant = _quant_op_only("LT")
    state = _build_state_for_play(quant_card=quant)
    after_play = play_card(state, quant, "QUANT", dice_mode=2, dice_roll=10)
    # Synthesise a fully-built rule for the resolver (subject/quant/noun all
    # filled). after_play.active_rule has QUANT filled by the OP-only card.
    rule = after_play.active_rule
    assert rule is not None
    new = resolve_if_rule(after_play, rule)
    # p0 has 50 chips; LT 10 → false; nothing fires.
    assert new == after_play
    # Now flip: chips=5 < 10 → fires.
    flipped = after_play.model_copy(
        update={"players": tuple(p.model_copy(update={"chips": 5}) for p in after_play.players)},
    )
    fired = resolve_if_rule(flipped, rule)
    assert fired.players[0].vp == 1

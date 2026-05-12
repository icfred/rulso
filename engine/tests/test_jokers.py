"""JOKER attachment (RUL-45 / M2 Phase 3 J).

Covers the four JOKER variants per ``design/cards-inventory.md``:

* ``JOKER:PERSIST_WHEN`` — promote IF rule into a WHEN persistent rule.
* ``JOKER:PERSIST_WHILE`` — promote IF rule into a WHILE persistent rule.
* ``JOKER:DOUBLE`` — dispatched effect runs twice on the matching scope.
* ``JOKER:ECHO`` — re-fire next round via the WHEN trigger path.

Plus an integration sweep that drives each variant through
``rules.enter_resolve`` + ``rules.enter_round_start`` and asserts the
end-state evolution.
"""

from __future__ import annotations

import random

import pytest

from rulso.bots.random import choose_action
from rulso.legality import PlayJoker, can_attach_joker
from rulso.rules import (
    enter_resolve,
    play_joker,
    start_game,
)
from rulso.state import (
    Card,
    CardType,
    GameState,
    Phase,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# Mirrors the resolver / persistence test fixtures (RUL-23 lesson — pin the
# revealed_effect so +VP assertions exercise the dispatcher rather than the
# default no-revealed-effect short-circuit).
_GAIN_VP_1 = Card(id="eff.vp.gain.1", type=CardType.EFFECT, name="GAIN_VP:1")


# --- Helpers ----------------------------------------------------------------


def _subject(name: str) -> Card:
    return Card(id=f"sub_{name.lower().replace(' ', '_')}", type=CardType.SUBJECT, name=name)


def _quant(op: str, n: int) -> Card:
    return Card(id=f"q_{op}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


def _noun(name: str) -> Card:
    return Card(id=f"n_{name.lower()}", type=CardType.NOUN, name=name)


def _joker(variant: str) -> Card:
    return Card(id=f"jkr.{variant.lower().split(':')[1]}", type=CardType.JOKER, name=variant)


def _player(pid: str, seat: int = 0, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=seat, chips=chips, vp=vp)


def _if_rule(
    subject: Card,
    quant: Card,
    noun: Card,
    *,
    joker: Card | None = None,
) -> RuleBuilder:
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=subject),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=quant),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=noun),
        ),
        joker_attached=joker,
    )


def _resolve_state(*players: Player, rule: RuleBuilder) -> GameState:
    return GameState(
        phase=Phase.RESOLVE,
        players=players,
        active_rule=rule,
        revealed_effect=_GAIN_VP_1,
    )


# --- PERSIST_WHEN -----------------------------------------------------------


def test_persist_when_promotes_rule_into_persistent_rules() -> None:
    """JOKER:PERSIST_WHEN converts the resolved IF into a WHEN persistent rule.

    Effect still fires once this round (per state.md step 4 → step 5 ordering);
    the rule then locks into ``persistent_rules`` instead of discarding.
    """
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:PERSIST_WHEN"),
    )
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    new = enter_resolve(state)
    # Effect fired once for p0 this round.
    assert new.players[0].vp == 1
    # Rule lodged as a WHEN persistent rule.
    assert len(new.persistent_rules) == 1
    persistent = new.persistent_rules[0]
    assert persistent.kind is RuleKind.WHEN
    assert persistent.rule.template is RuleKind.WHEN
    # Joker is consumed on promotion (no infinite re-doubling on next fires).
    assert persistent.rule.joker_attached is None
    # Slot fragments preserved on the persisted rule.
    assert tuple(s.filled_by.name for s in persistent.rule.slots) == ("p0", "GE:0", "VP")


def test_persist_when_skips_fragment_discard() -> None:
    """Persisted rules keep fragments — the discard pile gets nothing this round."""
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:PERSIST_WHEN"),
    )
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    assert len(state.discard) == 0
    new = enter_resolve(state)
    assert len(new.discard) == 0


# --- PERSIST_WHILE ----------------------------------------------------------


def test_persist_while_promotes_rule_into_persistent_rules() -> None:
    """JOKER:PERSIST_WHILE converts the resolved IF into a WHILE persistent rule."""
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:PERSIST_WHILE"),
    )
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    new = enter_resolve(state)
    assert new.players[0].vp == 1  # effect fires once this round
    assert len(new.persistent_rules) == 1
    persistent = new.persistent_rules[0]
    assert persistent.kind is RuleKind.WHILE
    assert persistent.rule.template is RuleKind.WHILE
    assert persistent.rule.joker_attached is None


# --- DOUBLE -----------------------------------------------------------------


def test_double_applies_effect_twice() -> None:
    """JOKER:DOUBLE doubles the dispatched effect — GAIN_VP:1 → +2 VP for p0."""
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:DOUBLE"),
    )
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    new = enter_resolve(state, rng=random.Random(0))
    assert new.players[0].vp == 2  # +1 +1
    # DOUBLE leaves no persistent residue — fragments discard normally.
    assert len(new.persistent_rules) == 0


def test_double_doubles_for_every_match_in_scope() -> None:
    """JOKER:DOUBLE doubles per matching player, not just per dispatch."""
    rule = _if_rule(
        _subject("THE LEADER"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:DOUBLE"),
    )
    state = _resolve_state(
        _player("p0", vp=2),
        _player("p1", vp=2, seat=1),
        _player("p2", vp=1, seat=2),
        rule=rule,
    )
    # RUL-73 bumped VP_TO_WIN 3→5; before the bump the +2 doubled effect put
    # p0/p1 at 4 VP which terminated the game before step 12 (refill). Now the
    # round continues into refill, which needs a seeded rng to recycle the
    # discard pile if mid-refill exhaustion occurs.
    new = enter_resolve(state, rng=random.Random(0))
    # p0 and p1 tie for LEADER (vp=2); each receives the doubled effect.
    assert new.players[0].vp == 4
    assert new.players[1].vp == 4
    assert new.players[2].vp == 1


# --- ECHO -------------------------------------------------------------------


def test_echo_fires_current_and_next_round() -> None:
    """JOKER:ECHO fires once this round, then once on the next resolve step.

    Implementation detail: ECHO promotes the rule to a one-shot WHEN. Next
    round's ``check_when_triggers`` re-evaluates HAS against current state and,
    if still true, fires the effect (and removes the WHEN per FIFO semantics).
    """
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:ECHO"),
    )
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    after_resolve = enter_resolve(state)
    # Current-round fire.
    assert after_resolve.players[0].vp == 1
    # Echo lodged as a WHEN for next round.
    assert len(after_resolve.persistent_rules) == 1
    assert after_resolve.persistent_rules[0].kind is RuleKind.WHEN
    # Simulate next round's resolve step 6 (WHEN trigger check). round-flow
    # rebinds ``revealed_effect`` at next round_start step 6 — restore it
    # here so the WHEN fire dispatches the same effect kind. Minimal harness
    # rather than full enter_round_start trip (which needs a dealer-seed
    # card).
    from rulso.labels import recompute_labels
    from rulso.persistence import check_when_triggers

    next_round = after_resolve.model_copy(
        update={"round_number": 2, "revealed_effect": _GAIN_VP_1},
    )
    fired = check_when_triggers(next_round, recompute_labels(next_round))
    assert fired.players[0].vp == 2
    # WHEN consumed after firing per FIFO discard.
    assert len(fired.persistent_rules) == 0


def test_echo_does_not_double_fire_in_current_round() -> None:
    """ECHO must not collapse into "fires twice this round" — step ordering."""
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:ECHO"),
    )
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    after_resolve = enter_resolve(state)
    # Exactly one fire in the current round (not two).
    assert after_resolve.players[0].vp == 1


# --- Validation -------------------------------------------------------------


def test_play_joker_rejects_non_joker_card() -> None:
    """play_joker validates card.type — passing a SUBJECT raises."""
    rule = RuleBuilder(template=RuleKind.IF, slots=(Slot(name="SUBJECT", type=CardType.SUBJECT),))
    state = GameState(
        phase=Phase.BUILD,
        players=(
            _player("p0"),
            _player("p1", seat=1),
            _player("p2", seat=2),
            _player("p3", seat=3),
        ),
        active_rule=rule,
    )
    with pytest.raises(ValueError, match="JOKER"):
        play_joker(state, _subject("p0"))


def test_play_joker_rejects_when_joker_already_attached() -> None:
    """One joker per rule per design/state.md."""
    joker = _joker("JOKER:DOUBLE")
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(Slot(name="SUBJECT", type=CardType.SUBJECT),),
        joker_attached=joker,
    )
    p0 = Player(id="p0", seat=0, hand=(_joker("JOKER:ECHO"),))
    state = GameState(
        phase=Phase.BUILD,
        players=(p0, _player("p1", seat=1), _player("p2", seat=2), _player("p3", seat=3)),
        active_rule=rule,
    )
    with pytest.raises(ValueError, match="already has a JOKER"):
        play_joker(state, _joker("JOKER:ECHO"))


def test_play_joker_attaches_card_and_advances_turn() -> None:
    joker = _joker("JOKER:DOUBLE")
    rule = RuleBuilder(template=RuleKind.IF, slots=(Slot(name="SUBJECT", type=CardType.SUBJECT),))
    p0 = Player(id="p0", seat=0, hand=(joker,))
    state = GameState(
        phase=Phase.BUILD,
        players=(p0, _player("p1", seat=1), _player("p2", seat=2), _player("p3", seat=3)),
        active_rule=rule,
        active_seat=0,
    )
    new = play_joker(state, joker)
    assert new.active_rule is not None
    assert new.active_rule.joker_attached is joker
    # Joker removed from the active player's hand.
    assert joker not in new.players[0].hand
    # _build_tick advances the active seat.
    assert new.active_seat == 1
    # JOKER play recorded in plays history.
    assert any(p.card.id == joker.id and p.slot == "JOKER" for p in new.active_rule.plays)


def test_play_joker_requires_build_phase() -> None:
    joker = _joker("JOKER:DOUBLE")
    rule = RuleBuilder(template=RuleKind.IF, slots=(Slot(name="SUBJECT", type=CardType.SUBJECT),))
    p0 = Player(id="p0", seat=0, hand=(joker,))
    state = GameState(
        phase=Phase.RESOLVE,
        players=(p0, _player("p1", seat=1)),
        active_rule=rule,
    )
    with pytest.raises(ValueError, match="phase=BUILD"):
        play_joker(state, joker)


# --- Legality predicate -----------------------------------------------------


def test_can_attach_joker_requires_joker_type() -> None:
    rule = RuleBuilder(template=RuleKind.IF)
    assert can_attach_joker(rule, _subject("p0")) is False
    assert can_attach_joker(rule, _joker("JOKER:DOUBLE")) is True


def test_can_attach_joker_blocked_when_joker_already_present() -> None:
    rule = RuleBuilder(
        template=RuleKind.IF,
        joker_attached=_joker("JOKER:DOUBLE"),
    )
    assert can_attach_joker(rule, _joker("JOKER:ECHO")) is False


def test_can_attach_joker_requires_active_rule() -> None:
    assert can_attach_joker(None, _joker("JOKER:DOUBLE")) is False


# --- Bot enumeration --------------------------------------------------------


def test_bot_enumerates_play_joker_when_legal() -> None:
    joker = _joker("JOKER:DOUBLE")
    rule = RuleBuilder(template=RuleKind.IF, slots=(Slot(name="NOUN", type=CardType.NOUN),))
    # Hand has only a JOKER and a card with no matching slot — joker must be
    # the chosen action when other plays/discards are unavailable.
    p0 = Player(id="p0", seat=0, chips=0, hand=(joker,))
    state = GameState(
        phase=Phase.BUILD,
        players=(p0, _player("p1", seat=1), _player("p2", seat=2), _player("p3", seat=3)),
        active_rule=rule,
        active_seat=0,
    )
    action = choose_action(state, "p0", random.Random(0))
    assert isinstance(action, PlayJoker)
    assert action.card_id == joker.id


def test_bot_skips_joker_when_one_already_attached() -> None:
    joker_in_hand = _joker("JOKER:ECHO")
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(Slot(name="NOUN", type=CardType.NOUN),),
        joker_attached=_joker("JOKER:DOUBLE"),
    )
    p0 = Player(id="p0", seat=0, chips=0, hand=(joker_in_hand,))
    state = GameState(
        phase=Phase.BUILD,
        players=(p0, _player("p1", seat=1), _player("p2", seat=2), _player("p3", seat=3)),
        active_rule=rule,
        active_seat=0,
    )
    # No legal play, no chips for discard → forced pass.
    from rulso.legality import Pass

    action = choose_action(state, "p0", random.Random(0))
    assert isinstance(action, Pass)


# --- Integration: full game with each variant -------------------------------


def _build_with_joker(variant: str) -> RuleBuilder:
    return _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker(variant),
    )


@pytest.mark.parametrize(
    "variant,expected_p0_vp,expect_persistent",
    [
        ("JOKER:PERSIST_WHEN", 1, True),
        ("JOKER:PERSIST_WHILE", 1, True),
        ("JOKER:DOUBLE", 2, False),
        ("JOKER:ECHO", 1, True),
    ],
)
def test_enter_resolve_drives_each_joker_variant(
    variant: str, expected_p0_vp: int, expect_persistent: bool
) -> None:
    """End-to-end through ``enter_resolve`` for each JOKER variant.

    Asserts post-resolve VP reflects the variant's effect-application
    semantics (DOUBLE = ×2; PERSIST_*/ECHO = single fire) and that
    persistent_rules carries the promoted rule for the persistence variants.
    """
    rule = _build_with_joker(variant)
    state = _resolve_state(_player("p0"), _player("p1", seat=1), rule=rule)
    new = enter_resolve(state, rng=random.Random(0))
    assert new.players[0].vp == expected_p0_vp
    if expect_persistent:
        assert len(new.persistent_rules) == 1
    else:
        assert len(new.persistent_rules) == 0


def test_full_game_round_trip_with_persistent_when_joker() -> None:
    """Drive a real start_game state through a synthetic resolve with a JOKER.

    Verifies that ``enter_resolve`` accepts a JOKER-bearing rule on top of
    a real start_game state (not just a hand-built test fixture) — guards
    against cleanup paths that assume non-joker rules.
    """
    state = start_game(seed=0)
    # Synthesise a resolve-ready state with a JOKER-bearing rule overlaid.
    rule = _if_rule(
        _subject("p0"),
        _quant("GE", 0),
        _noun("VP"),
        joker=_joker("JOKER:PERSIST_WHEN"),
    )
    state = state.model_copy(
        update={
            "phase": Phase.RESOLVE,
            "active_rule": rule,
            "revealed_effect": _GAIN_VP_1,
        }
    )
    new = enter_resolve(state, rng=random.Random(1))
    # Effect fired this round + rule persisted.
    assert new.players[0].vp == 1
    assert len(new.persistent_rules) == 1
    assert new.persistent_rules[0].kind is RuleKind.WHEN
    # Round transitions to ROUND_START with no winner.
    assert new.phase is Phase.ROUND_START
    assert new.winner is None

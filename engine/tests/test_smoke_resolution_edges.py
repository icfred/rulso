"""Resolver-corner smoke (RUL-12, label-aware after RUL-22).

Two cross-cutting invariants from M1's DoD:
  * Failed-rule path leaves player chips/VP and active goals untouched, then
    rotates the dealer. (Driven through ``rules.py``.)
  * M2-stub label SUBJECT (GENEROUS / CURSED / MARKED / CHAINED) resolves to
    no matches and no state mutation. (Driven directly through
    ``effects.resolve_if_rule`` with a grammar-compatible ``RuleBuilder`` —
    the M1 stub rule in ``rules.py`` uses different slot names; reconciliation
    is RUL-18's job.)

LEADER and WOUNDED are live (RUL-19) and now actually fire (RUL-22), so they
are exercised in ``test_resolver.py`` instead.
"""

from __future__ import annotations

from rulso.effects import resolve_if_rule
from rulso.rules import advance_phase, pass_turn, play_card, start_game
from rulso.state import (
    PLAYER_COUNT,
    Card,
    CardType,
    GameState,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# M2-stub labels: still empty frozenset until their derivations land.
_M2_STUB_LABELS = ("THE GENEROUS", "THE CURSED", "THE MARKED", "THE CHAINED")


# --- Grammar-compatible RuleBuilder fixture ---------------------------------


def _if_rule(subject_name: str, op: str, n: int, noun_name: str) -> RuleBuilder:
    """Build a SUBJECT/QUANT/NOUN-slotted IF rule the resolver can render directly."""
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(
                name="SUBJECT",
                type=CardType.SUBJECT,
                filled_by=Card(
                    id=f"sub_{subject_name.lower().replace(' ', '_')}",
                    type=CardType.SUBJECT,
                    name=subject_name,
                ),
            ),
            Slot(
                name="QUANT",
                type=CardType.MODIFIER,
                filled_by=Card(
                    id=f"q_{op}_{n}",
                    type=CardType.MODIFIER,
                    name=f"{op}:{n}",
                ),
            ),
            Slot(
                name="NOUN",
                type=CardType.NOUN,
                filled_by=Card(
                    id=f"n_{noun_name.lower()}",
                    type=CardType.NOUN,
                    name=noun_name,
                ),
            ),
        ),
    )


def _state_with_goals(goal_count: int = 3) -> GameState:
    players = tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT))
    goals = tuple(Card(id=f"g{i}", type=CardType.NOUN, name=f"GOAL_{i}") for i in range(goal_count))
    return GameState(players=players, active_goals=goals)


# --- M2-stub label SUBJECT: empty scope, no effect, no goal claim -----------


def test_each_m2_stub_label_subject_leaves_state_identical() -> None:
    """M2-stub labels are still empty → resolve is a state-equality no-op."""
    state = _state_with_goals()
    for label in _M2_STUB_LABELS:
        rule = _if_rule(label, "GE", 0, "CHIPS")
        new_state = resolve_if_rule(state, rule)
        # Equality on the frozen Pydantic state covers players, goals, decks,
        # and every other field — a single assertion enforces "no mutation".
        assert new_state == state, f"label {label!r} unexpectedly mutated state"


def test_live_label_firing_does_not_consume_active_goals() -> None:
    """Goals are face-up substrate; resolver firing must not discard or replace them."""
    state = _state_with_goals(goal_count=3)
    # All four default players tie at vp=0, so all hold THE LEADER and the
    # rule fires for each. Goal substrate should still be untouched in M1.5
    # (real goal-claim machinery is M2).
    rule = _if_rule("THE LEADER", "GE", 0, "CHIPS")
    new_state = resolve_if_rule(state, rule)
    assert new_state.active_goals == state.active_goals
    assert new_state.goal_discard == state.goal_discard


# --- Failed-rule path: no effect, no goal claim, dealer rotates -------------


def _drive_one_failed_round(state: GameState) -> GameState:
    """Walk one round to its fail-and-rotate point. Hands are empty → all pass."""
    state = advance_phase(state)  # ROUND_START → BUILD
    assert state.phase.value == "build"
    for _ in range(PLAYER_COUNT):
        state = pass_turn(state)
    return state


def test_failed_rule_does_not_mutate_chips_or_vp() -> None:
    """A round that fails on unfilled slots must not touch any player's chips or VP."""
    state = start_game()
    chips_before = tuple(p.chips for p in state.players)
    vp_before = tuple(p.vp for p in state.players)
    state = _drive_one_failed_round(state)
    assert state.phase.value == "round_start"
    assert tuple(p.chips for p in state.players) == chips_before
    assert tuple(p.vp for p in state.players) == vp_before


def test_failed_rule_does_not_claim_goals() -> None:
    """Active goals stay face-up across a failed round; nothing moves to ``goal_discard``."""
    state = start_game()
    goals_before = state.active_goals
    discard_before = state.goal_discard
    state = _drive_one_failed_round(state)
    assert state.active_goals == goals_before
    assert state.goal_discard == discard_before


def test_failed_rule_advances_dealer_one_seat() -> None:
    """Dealer rotates ``(dealer + 1) % PLAYER_COUNT`` on the fail-and-rotate path."""
    state = start_game()
    starting_dealer = state.dealer_seat
    state = _drive_one_failed_round(state)
    assert state.dealer_seat == (starting_dealer + 1) % PLAYER_COUNT
    assert state.active_rule is None
    assert state.revealed_effect is None


def test_failed_rule_via_play_card_partial_fill_still_no_effect() -> None:
    """Even when *some* fragments land, an unfilled slot fails the rule cleanly.

    Exercises the partial-fill branch of ``_fail_rule_and_rotate``: discarded
    fragments include the played cards, but no resolver runs and no chip / VP
    delta lands on any player.
    """
    state = start_game()
    # Inject a NOUN card for seat 1 only — modifier and noun_2 stay unfilled.
    seat1_hand = (Card(id="held_noun", type=CardType.NOUN, name="held_noun"),)
    new_players = tuple(
        p.model_copy(update={"hand": seat1_hand}) if p.seat == 1 else p for p in state.players
    )
    state = state.model_copy(update={"players": new_players})

    chips_before = tuple(p.chips for p in state.players)
    state = advance_phase(state)  # → BUILD
    state = play_card(state, seat1_hand[0], "noun")
    state = pass_turn(state)  # seat 2
    state = pass_turn(state)  # seat 3
    state = pass_turn(state)  # dealer closes revolution

    assert state.phase.value == "round_start"
    assert state.active_rule is None
    assert state.dealer_seat == 1
    assert tuple(p.chips for p in state.players) == chips_before
    # Dealer fragment + the one played NOUN → 2 in discard.
    assert len(state.discard) == 2

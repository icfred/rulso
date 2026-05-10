"""Goal-card claim resolver per ``design/goals-inventory.md``.

Public surface:

* :func:`check_claims` — evaluate every face-up goal against every player at
  ``resolve`` step 7. Awards ``vp_award`` to the matching player(s); discards
  + replenishes single-claim goals from ``GameState.goal_deck``; renewable
  goals stay face-up.

The predicate registry maps ``GoalCard.claim_condition`` (a snake_case id) to
a pure function ``(player, state) → bool``. Predicates read player + game
state only; they MUST NOT read decks or transient phase fields (see the spike
"Predicate vocabulary" section).

Tie-break for single-claim goals (per the spike): ascending VP, ties on chips,
ties on seat order starting at ``dealer_seat``. CHAINED players are filtered
out before the tie-break runs and never claim.

Pure function: input ``GameState`` is never mutated; a new state is returned.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from rulso.state import (
    HAND_SIZE,
    PLAYER_COUNT,
    GameState,
    GoalCard,
    Player,
)

GoalPredicate = Callable[[Player, GameState], bool]


def _chips_at_least_75(player: Player, state: GameState) -> bool:
    return player.chips >= 75


def _chips_under_10(player: Player, state: GameState) -> bool:
    return player.chips < 10


def _rules_completed_at_least_3(player: Player, state: GameState) -> bool:
    return player.history.rules_completed_this_game >= 3


def _gifts_at_least_2(player: Player, state: GameState) -> bool:
    return player.history.cards_given_this_game >= 2


def _burn_at_least_2(player: Player, state: GameState) -> bool:
    return player.status.burn >= 2


def _free_agent(player: Player, state: GameState) -> bool:
    s = player.status
    return (
        state.round_number >= 5
        and s.burn == 0
        and not s.mute
        and not s.blessed
        and not s.marked
        and not s.chained
    )


def _full_hand(player: Player, state: GameState) -> bool:
    return len(player.hand) >= HAND_SIZE


_PREDICATES: Final[dict[str, GoalPredicate]] = {
    "chips_at_least_75": _chips_at_least_75,
    "chips_under_10": _chips_under_10,
    "rules_completed_at_least_3": _rules_completed_at_least_3,
    "gifts_at_least_2": _gifts_at_least_2,
    "burn_at_least_2": _burn_at_least_2,
    "free_agent": _free_agent,
    "full_hand": _full_hand,
}


def predicate(name: str) -> GoalPredicate:
    """Return the predicate registered under ``name``.

    Raises ``KeyError`` with the unknown id if the predicate is missing — better
    to surface a malformed goal-card definition loudly than silently no-op.
    """
    if name not in _PREDICATES:
        raise KeyError(f"unknown goal predicate {name!r}")
    return _PREDICATES[name]


def check_claims(state: GameState) -> GameState:
    """Run ``resolve`` step 7 — evaluate every active goal and award VP.

    Iterates ``state.active_goals`` left-to-right (per ``state.md``: "Multi-goal
    triggers in one round: award left-to-right"). Each goal's resolution
    commits before the next evaluates — a player's VP raised by goal A may
    newly satisfy or newly fail goal B's predicate within the same step.

    Single-claim goals discard + replenish from ``state.goal_deck``; if the
    deck is empty the discard pile is recycled in place (without an rng — the
    goal-deck shuffle on initial seed is the only randomised goal-pile op).
    Renewable goals stay face-up and award ``vp_award`` to every matching
    non-CHAINED player.
    """
    if not state.active_goals:
        return state
    for index in range(len(state.active_goals)):
        goal = state.active_goals[index]
        if goal is None:
            continue
        state = _resolve_one_goal(state, index, goal)
    return state


def _resolve_one_goal(state: GameState, index: int, goal: GoalCard) -> GameState:
    """Evaluate one face-up goal at ``index``; return state after award."""
    pred = predicate(goal.claim_condition)
    eligible = tuple(p for p in state.players if not p.status.chained and pred(p, state))
    if not eligible:
        return state
    if goal.claim_kind == "renewable":
        return _award_vp(state, tuple(p.id for p in eligible), goal.vp_award)
    winner = _tie_break_single(eligible, state.dealer_seat)
    awarded = _award_vp(state, (winner.id,), goal.vp_award)
    return _discard_and_replenish(awarded, index)


def _tie_break_single(candidates: tuple[Player, ...], dealer_seat: int) -> Player:
    """Pick the single-claim winner per the spike's catch-up tie-break.

    Ascending VP → ascending chips → seat order starting at ``dealer_seat``.
    """

    def seat_distance(seat: int) -> int:
        return (seat - dealer_seat) % PLAYER_COUNT

    return min(candidates, key=lambda p: (p.vp, p.chips, seat_distance(p.seat)))


def _award_vp(state: GameState, ids: tuple[str, ...], vp: int) -> GameState:
    if not ids:
        return state
    id_set = frozenset(ids)
    new_players = tuple(
        p.model_copy(update={"vp": p.vp + vp}) if p.id in id_set else p for p in state.players
    )
    return state.model_copy(update={"players": new_players})


def _discard_and_replenish(state: GameState, index: int) -> GameState:
    """Move the goal at ``index`` to ``goal_discard`` and draw a replacement.

    Replacement is drawn from the top of ``goal_deck`` (the rightmost element
    — the seed-time shuffle establishes order). When ``goal_deck`` is empty,
    the discard pile is recycled in place; the slot is left empty when both
    piles are exhausted (``state.md`` allows ``len(active_goals) < 3``).
    """
    discarded = state.active_goals[index]
    assert discarded is not None
    deck = list(state.goal_deck)
    new_discard = state.goal_discard
    discarded_was_recycled = False
    if not deck and state.goal_discard:
        # No rng on this path; recycle deterministically by stacking the
        # prior discard pile on top of the just-discarded goal so the
        # claimer's own card is drawn last. ``check_claims`` is mid-resolve;
        # threading an rng through would couple goal-claim to the resolve
        # rng contract — see ``design/goals-inventory.md`` "Replenishment".
        deck = [discarded, *state.goal_discard]
        new_discard = ()
        discarded_was_recycled = True
    replacement: GoalCard | None = deck.pop() if deck else None
    new_active = state.active_goals[:index] + (replacement,) + state.active_goals[index + 1 :]
    if not discarded_was_recycled:
        new_discard = new_discard + (discarded,)
    return state.model_copy(
        update={
            "active_goals": new_active,
            "goal_deck": tuple(deck),
            "goal_discard": new_discard,
        }
    )

"""Floating-label computation per ``design/state.md``.

Labels are computed each round, never stored on ``GameState``. ``recompute_labels``
is a pure function over ``GameState`` returning a label-name → frozenset[player_id]
mapping.

M1.5 (RUL-19): LEADER and WOUNDED are live.
M2 (RUL-33): GENEROUS and CURSED are live. MARKED and CHAINED stay empty
until the M2 status-apply ticket lands their ``Player.status`` mechanics.

Tie-break policy (per ADR-0001): ties → all tied players hold the label.
For GENEROUS / CURSED specifically, an all-zero population yields an empty
holder set (the label has no holder when no player has given a card / taken
a burn).
"""

from __future__ import annotations

from rulso.state import GameState

LEADER: str = "THE LEADER"
WOUNDED: str = "THE WOUNDED"
GENEROUS: str = "THE GENEROUS"
CURSED: str = "THE CURSED"
MARKED: str = "THE MARKED"
CHAINED: str = "THE CHAINED"

LABEL_NAMES: tuple[str, ...] = (LEADER, WOUNDED, GENEROUS, CURSED, MARKED, CHAINED)


def recompute_labels(state: GameState) -> dict[str, frozenset[str]]:
    """Compute label assignments for the current ``state``.

    Returns a dict keyed by every label in ``LABEL_NAMES``; values are frozensets
    of player ids holding the label this round.

    Coverage:
      * ``LEADER`` — players with the maximum ``vp``. Ties → all tied players.
      * ``WOUNDED`` — players with the minimum ``chips``. Ties → all tied players.
      * ``GENEROUS`` — players with the maximum
        ``history.cards_given_this_game``. Ties → all; zero → empty.
      * ``CURSED`` — players with the maximum ``status.burn``. Ties → all;
        zero → empty.
      * ``MARKED`` — empty (M2 status-apply ticket: derive from
        ``Player.status.marked``).
      * ``CHAINED`` — empty (M2 status-apply ticket: derive from
        ``Player.status.chained``).

    Empty player set → every label is an empty frozenset.
    """
    players = state.players
    if not players:
        return {name: frozenset() for name in LABEL_NAMES}

    max_vp = max(p.vp for p in players)
    min_chips = min(p.chips for p in players)
    max_given = max(p.history.cards_given_this_game for p in players)
    max_burn = max(p.status.burn for p in players)

    generous = (
        frozenset(p.id for p in players if p.history.cards_given_this_game == max_given)
        if max_given > 0
        else frozenset()
    )
    cursed = (
        frozenset(p.id for p in players if p.status.burn == max_burn)
        if max_burn > 0
        else frozenset()
    )

    return {
        LEADER: frozenset(p.id for p in players if p.vp == max_vp),
        WOUNDED: frozenset(p.id for p in players if p.chips == min_chips),
        GENEROUS: generous,
        CURSED: cursed,
        MARKED: frozenset(),
        CHAINED: frozenset(),
    }

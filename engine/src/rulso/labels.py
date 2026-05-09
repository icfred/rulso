"""Floating-label computation per ``design/state.md``.

Labels are computed each round, never stored on ``GameState``. ``recompute_labels``
is a pure function over ``GameState`` returning a label-name → frozenset[player_id]
mapping.

M1.5 (RUL-19): LEADER and WOUNDED are live. The remaining labels return empty
frozensets and land with M2 alongside the player-history pipeline and the status
token wiring.

Tie-break policy (per Linear RUL-19): ties → all tied players hold the label.
This diverges from ``design/state.md``'s "ties → unassigned"; Linear is the
source of truth for the engine.
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

    M1.5 coverage:
      * ``LEADER`` — players with the maximum ``vp``. Ties → all tied players.
      * ``WOUNDED`` — players with the minimum ``chips``. Ties → all tied players.
      * ``GENEROUS`` — empty (M2: derive from ``Player.history.cards_given_this_game``).
      * ``CURSED`` — empty (M2: derive from ``Player.status.burn``).
      * ``MARKED`` — empty (M2: derive from ``Player.status.marked``).
      * ``CHAINED`` — empty (M2: derive from ``Player.status.chained``).

    Empty player set → every label is an empty frozenset.
    """
    players = state.players
    if not players:
        return {name: frozenset() for name in LABEL_NAMES}

    max_vp = max(p.vp for p in players)
    min_chips = min(p.chips for p in players)

    return {
        LEADER: frozenset(p.id for p in players if p.vp == max_vp),
        WOUNDED: frozenset(p.id for p in players if p.chips == min_chips),
        GENEROUS: frozenset(),
        CURSED: frozenset(),
        MARKED: frozenset(),
        CHAINED: frozenset(),
    }

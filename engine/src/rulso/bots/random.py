"""Random-legal bot.

Picks a uniformly-random legal action for the active player, biased toward
``play_card`` over ``discard_redraw`` when both are legal. M1 baseline; M3
ISMCTS uses this for rollouts and as a baseline opponent. Pure function:
state in, action out, RNG injected. No module-level mutable state.

Action shapes (``PlayCard`` / ``DiscardRedraw`` / ``Pass`` / ``PlayJoker``)
and the underlying legal-action enumeration live in :mod:`rulso.legality` —
the canonical home for the engine's action surface. This module owns only
the *bot* layer: bias-tuning and RNG-driven selection.
"""

from __future__ import annotations

import random

from rulso.legality import (
    Action,
    DiscardRedraw,
    Pass,
    PlayCard,
    PlayJoker,
    _enumerate_discards,
    _enumerate_plays,
)
from rulso.state import GameState, Phase, Player

# Probability of picking from the play_card pool when both play_card and
# discard_redraw are legal. With hand=7 and chips=50, the discard space
# (C(7,1..3) = 63 actions) swamps the play space (1..4 actions); uniform
# sampling makes the bot discard ~84% of the time and rules rarely fill.
#
# RUL-55 (Phase 3.5 polish): tuned 0.85 → 0.75. Slightly more discards
# accelerate SUBJECT-card cycling out of stalled hands, shrinking the
# dealer-no-seed-card cap-hit fraction and lifting the deterministic
# winner count from 5/10 → 7/10 across seeds 0..9 at rounds=200 in
# ``test_m2_watchable``. Probed monotonically: 0.7 → 5, 0.72 → 5,
# 0.75 → 7, 0.78 → 7, 0.80 → 6, 0.85 → 5 (baseline). Stable at rounds=300.
PLAY_BIAS = 0.75


def choose_action(state: GameState, player_id: str, rng: random.Random) -> Action:
    """Return a legal action for ``player_id`` with a play-over-discard bias.

    When both play actions (``play_card`` / ``play_joker``) and
    ``discard_redraw`` are legal, a play action is chosen with probability
    :data:`PLAY_BIAS`, otherwise the bot picks uniformly within whichever pool
    is non-empty. Falls back to :class:`Pass` when neither is legal.
    Deterministic given ``rng``: same RNG state in, same action out. Pure
    function — no global state, no mutation of inputs.
    """
    player = _find_player(state, player_id)
    if state.phase is not Phase.BUILD:
        return Pass()
    plays: list[PlayCard | PlayJoker] = _enumerate_plays(state, player)
    discards: list[DiscardRedraw] = _enumerate_discards(player)
    if plays and discards:
        if rng.random() < PLAY_BIAS:
            return rng.choice(plays)
        return rng.choice(discards)
    if plays:
        return rng.choice(plays)
    if discards:
        return rng.choice(discards)
    return Pass()


def _find_player(state: GameState, player_id: str) -> Player:
    for p in state.players:
        if p.id == player_id:
            return p
    raise ValueError(f"unknown player {player_id!r}")


def select_purchase(state: GameState, player_id: str, rng: random.Random) -> int | None:
    """Pick a SHOP offer index for ``player_id``, or ``None`` to skip (RUL-51).

    Heuristic per the RUL-51 hand-over: cheapest affordable offer wins; ties
    broken by lowest offer index (stable, deterministic). Skips when no
    affordable offer exists. The ``rng`` parameter is accepted to keep the
    bot-driver signature uniform with :func:`choose_action`; it is not
    consumed by the current heuristic (all decisions are deterministic given
    the offer set).
    """
    if state.phase is not Phase.SHOP:
        return None
    player = _find_player(state, player_id)
    cheapest_index: int | None = None
    cheapest_price: int | None = None
    for i, offer in enumerate(state.shop_offer):
        if offer.price > player.chips:
            continue
        if cheapest_price is None or offer.price < cheapest_price:
            cheapest_price = offer.price
            cheapest_index = i
    return cheapest_index

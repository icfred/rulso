"""Random-legal bot.

Picks a uniformly-random legal action for the active player, biased toward
``play_card`` over ``discard_redraw`` when both are legal. M1 baseline; M3
ISMCTS uses this for rollouts and as a baseline opponent. Pure function:
state in, action out, RNG injected. No module-level mutable state.

The ``Action`` type is defined here for now — ``state.py`` does not yet model
player actions. Future tickets can promote it once the surface stabilises
(e.g. when the protocol layer needs to (de)serialise actions).

Legal-action enumeration applies the design-spec filters: slot type
compatibility, hand membership, MUTE blocks MODIFIER plays, and discard
affordability via chip count.
"""

from __future__ import annotations

import itertools
import random
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from rulso.effects import is_operator_modifier
from rulso.legality import can_attach_joker
from rulso.state import (
    DISCARD_COST,
    CardType,
    GameState,
    Phase,
    Player,
)

_FROZEN = ConfigDict(frozen=True)

# Probability of picking from the play_card pool when both play_card and
# discard_redraw are legal. With hand=7 and chips=50, the discard space
# (C(7,1..3) = 63 actions) swamps the play space (1..4 actions); uniform
# sampling makes the bot discard ~84% of the time and rules rarely fill.
# 0.85 keeps the bot mostly constructive while preserving exploration.
PLAY_BIAS = 0.85

# RUL-42 (G): OP-only comparator MODIFIERs per ADR-0002. The bot picks 2d6 by
# default for these (wider range = more strategic neutral) without offering a
# 1d6 alternative. M1.5 baked-N comparators (``LT:5``, etc.) and other
# MODIFIER-shaped cards continue to enumerate both dice modes via the legacy
# branch below — additive, not a replacement.
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})
_OP_ONLY_DEFAULT_DICE: Literal[1, 2] = 2


class PlayCard(BaseModel):
    """Play one card from hand into one open slot.

    ``dice`` is 1 (1d6) or 2 (2d6) when the card is a MODIFIER — under the M1
    stub every MODIFIER play is treated as a comparator. ``None`` otherwise.
    """

    model_config = _FROZEN

    kind: Literal["play_card"] = "play_card"
    card_id: str
    slot: str
    dice: Literal[1, 2] | None = None


class DiscardRedraw(BaseModel):
    """Spend chips to discard 1..3 cards and redraw."""

    model_config = _FROZEN

    kind: Literal["discard_redraw"] = "discard_redraw"
    card_ids: tuple[str, ...]


class Pass(BaseModel):
    """Forced pass — no legal play and no affordable discard."""

    model_config = _FROZEN

    kind: Literal["pass"] = "pass"


class PlayJoker(BaseModel):
    """Attach a JOKER from hand to the active rule (RUL-45).

    JOKERs do not fill a slot; they bind to ``RuleBuilder.joker_attached``
    via ``rules.play_joker``. One joker per rule per ``design/state.md``.
    """

    model_config = _FROZEN

    kind: Literal["play_joker"] = "play_joker"
    card_id: str


Action = Annotated[
    PlayCard | DiscardRedraw | Pass | PlayJoker,
    Field(discriminator="kind"),
]


def enumerate_legal_actions(
    state: GameState, player: Player
) -> list[PlayCard | PlayJoker | DiscardRedraw]:
    """Return every legal non-Pass action for ``player`` in the BUILD phase.

    Bot-side ``choose_action`` already discriminates plays vs discards via
    ``PLAY_BIAS``; the human-seat driver (``rulso.bots.human``) needs the raw
    union for menu rendering. Pure structural enumeration: same predicates as
    the bot, no RNG, no ``Pass`` (caller picks ``Pass`` when the list is empty).
    """
    if state.phase is not Phase.BUILD:
        return []
    return [*_enumerate_plays(state, player), *_enumerate_discards(player)]


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
    plays = _enumerate_plays(state, player)
    discards = _enumerate_discards(player)
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


def _enumerate_plays(state: GameState, player: Player) -> list[PlayCard | PlayJoker]:
    if state.active_rule is None:
        return []
    muted = player.status.mute
    plays: list[PlayCard | PlayJoker] = []
    for slot in state.active_rule.slots:
        if slot.filled_by is not None:
            continue
        for card in player.hand:
            if card.type is not slot.type:
                continue
            if muted and card.type is CardType.MODIFIER:
                continue
            if card.type is CardType.MODIFIER:
                # RUL-43: operator MODIFIERs (BUT/AND/OR/MORE_THAN/AT_LEAST)
                # share CardType.MODIFIER with comparators but attach to a
                # filled slot's ``modifiers`` tuple, not ``filled_by``. The
                # dedicated "play_operator" action shape lands when ADR-0004's
                # legality extension does — until then the bot leaves them in
                # hand rather than crash ``_parse_quant`` on QUANT.
                if is_operator_modifier(card):
                    continue
                # RUL-42 (G): OP-only comparator (ADR-0002) → bot defaults to
                # 2d6; do not enumerate 1d6. Additive branch — falls through to
                # the legacy both-modes path for every other comparator MODIFIER.
                if card.name in _OP_ONLY_COMPARATOR_NAMES:
                    plays.append(
                        PlayCard(card_id=card.id, slot=slot.name, dice=_OP_ONLY_DEFAULT_DICE)
                    )
                    continue
                # Treat comparator MODIFIERs uniformly: offer both dice options.
                plays.append(PlayCard(card_id=card.id, slot=slot.name, dice=1))
                plays.append(PlayCard(card_id=card.id, slot=slot.name, dice=2))
            else:
                plays.append(PlayCard(card_id=card.id, slot=slot.name, dice=None))
    # RUL-45 (J): JOKER attachment as a 4th BUILD-phase play type. Additive —
    # JOKERs don't fill a slot (no JOKER slot exists in CONDITION templates),
    # so they sit outside the slot loop. Enumerated when an active rule is
    # joker-free and the player holds a JOKER in hand. MUTE does NOT block
    # JOKER plays per design/state.md "Status Tokens" (MUTE blocks only
    # MODIFIER cards).
    rule = state.active_rule
    if rule.joker_attached is None:
        seen_joker_ids: set[str] = set()
        for card in player.hand:
            if card.id in seen_joker_ids:
                continue
            if can_attach_joker(rule, card):
                plays.append(PlayJoker(card_id=card.id))
                seen_joker_ids.add(card.id)
    return plays


def _enumerate_discards(player: Player) -> list[DiscardRedraw]:
    if not player.hand or player.chips < DISCARD_COST:
        return []
    max_k = min(3, len(player.hand), player.chips // DISCARD_COST)
    discards: list[DiscardRedraw] = []
    for k in range(1, max_k + 1):
        for combo in itertools.combinations(player.hand, k):
            discards.append(DiscardRedraw(card_ids=tuple(c.id for c in combo)))
    return discards


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

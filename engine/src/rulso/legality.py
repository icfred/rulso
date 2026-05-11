"""Shared legality predicates and action surface.

Pure helpers used by ``rules.py`` (dealer's first-slot pick at
``enter_round_start``), ``bots/random.py`` (legal-action enumeration), the
human-seat driver (``bots/human.py``), and the WebSocket protocol layer
(``protocol.py``). Lives in its own module so callers don't reach into
``bots/`` for a shared check.

No state mutation; no I/O. Type-match only — MUTE / BLESSED / dice options and
discard affordability stay below in :func:`enumerate_legal_actions` because
they bear on action shape, not on "is this card legal in this slot?".

The action shapes (:class:`PlayCard`, :class:`DiscardRedraw`, :class:`Pass`,
:class:`PlayJoker`, :data:`Action`) live here so the engine, bots, and wire
protocol all resolve to the same Pydantic class objects — :mod:`rulso.protocol`
imports them verbatim to guarantee the WS envelope and the engine's internal
action model never structurally drift (ADR-0008).
"""

from __future__ import annotations

import itertools
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from rulso.effects import is_operator_modifier
from rulso.state import (
    DISCARD_COST,
    Card,
    CardType,
    GameState,
    Phase,
    Player,
    RuleBuilder,
)

_FROZEN = ConfigDict(frozen=True)

# RUL-42 (G): OP-only comparator MODIFIERs per ADR-0002. The bot picks 2d6 by
# default for these (wider range = more strategic neutral) without offering a
# 1d6 alternative. M1.5 baked-N comparators (``LT:5``, etc.) and other
# MODIFIER-shaped cards continue to enumerate both dice modes via the legacy
# branch below — additive, not a replacement.
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})
_OP_ONLY_DEFAULT_DICE: Literal[1, 2] = 2


def first_card_of_type(hand: tuple[Card, ...], card_type: CardType) -> Card | None:
    """Return the first card in ``hand`` whose ``type`` matches ``card_type``.

    Order-stable: callers (e.g. the dealer's auto-pick at round_start) get the
    leftmost matching card, which keeps deterministic behaviour given a
    deterministic deal. ``None`` when no match — caller decides the failure
    handling (rules.py uses this to fail-and-rotate the dealer).
    """
    return next((c for c in hand if c.type is card_type), None)


# RUL-45 (J): JOKER attachment as a 4th BUILD-phase play type, alongside
# play_card / discard_redraw / declare_pass. Additive — does not modify
# existing predicates above.
def can_attach_joker(rule: RuleBuilder | None, card: Card) -> bool:
    """Return ``True`` if ``card`` (a JOKER) may attach to ``rule`` right now.

    Legal only when the rule exists, is not yet joker-bearing (one joker per
    rule per ``design/state.md`` "JOKER attachment"), and the card is itself a
    JOKER. Slot-fullness is irrelevant — JOKERs attach to the rule as a whole
    via ``RuleBuilder.joker_attached``, not to a slot.
    """
    if rule is None:
        return False
    if rule.joker_attached is not None:
        return False
    return card.type is CardType.JOKER


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
    """Forced pass — no legal play and no affordable discard.

    Server-side-only: the engine selects ``Pass`` automatically when
    :func:`enumerate_legal_actions` returns an empty list. Clients never
    submit it over the wire (ADR-0008 excludes it from ``ClientAction``).
    """

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

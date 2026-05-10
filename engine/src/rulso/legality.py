"""Shared legality predicates.

Tiny pure helpers used by both ``rules.py`` (dealer's first-slot pick at
``enter_round_start``) and — eventually — ``bots/random.py`` (legal-action
enumeration). Lives in its own module to avoid ``rules.py`` reaching into
``bots/`` for a shared check.

No state mutation; no I/O. Type-match only — MUTE / BLESSED / dice options and
discard affordability stay in the bot since they bear on action shape, not on
"is this card legal in this slot?".
"""

from __future__ import annotations

from rulso.state import Card, CardType, RuleBuilder


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

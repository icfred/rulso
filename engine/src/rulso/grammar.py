"""IF rule grammar.

Renders a ``RuleBuilder`` into a structured rule object the resolver can read.
M1 supports the canonical IF shape ``IF [SUBJECT] HAS [QUANT] [NOUN]`` — slots
named ``SUBJECT``, ``QUANT``, ``NOUN``. Polymorphic grammar across all rule
shapes lands with M2.

No string formatting lives here — narration belongs to the CLI ticket.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from rulso.state import Card, CardType, RuleBuilder, RuleKind

_SUBJECT_SLOT: str = "SUBJECT"
_QUANT_SLOT: str = "QUANT"
_NOUN_SLOT: str = "NOUN"


class IfRule(BaseModel):
    """Structured view over a built IF rule.

    Slot cards are surfaced as ``Card`` references so the resolver can read
    semantic content (player id, comparator, resource name) without re-walking
    the slot list.
    """

    model_config = ConfigDict(frozen=True)

    subject: Card
    quant: Card
    noun: Card


def render_if_rule(rule: RuleBuilder) -> IfRule:
    """Pull SUBJECT / QUANT / NOUN slot contents off ``rule``.

    Raises ``ValueError`` if the template is not IF, a required slot is
    missing, a slot's declared type does not match, or a required slot is
    unfilled.
    """
    if rule.template is not RuleKind.IF:
        raise ValueError(f"render_if_rule requires IF template, got {rule.template}")
    return IfRule(
        subject=_filled(rule, _SUBJECT_SLOT, CardType.SUBJECT),
        quant=_filled(rule, _QUANT_SLOT, CardType.MODIFIER),
        noun=_filled(rule, _NOUN_SLOT, CardType.NOUN),
    )


def _filled(rule: RuleBuilder, name: str, expected_type: CardType) -> Card:
    slot = next((s for s in rule.slots if s.name == name), None)
    if slot is None:
        raise ValueError(f"IF rule missing slot {name!r}")
    if slot.type is not expected_type:
        raise ValueError(f"slot {name!r} has type {slot.type}, expected {expected_type}")
    if slot.filled_by is None:
        raise ValueError(f"slot {name!r} is unfilled")
    return slot.filled_by

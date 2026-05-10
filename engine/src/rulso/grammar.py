"""IF rule grammar.

Renders a ``RuleBuilder`` into a structured rule object the resolver can read.
M1 supports the canonical IF shape ``IF [SUBJECT] HAS [QUANT] [NOUN]`` — slots
named ``SUBJECT``, ``QUANT``, ``NOUN``. Polymorphic grammar across all rule
shapes lands with M2.

No string formatting lives here — narration belongs to the CLI ticket.

RUL-43 (ADR-0004) extension: ``IfRule`` surfaces each slot's
``modifiers`` tuple alongside its filled card. The resolver walks these in
(op, rhs-card) pairs (SUBJECT/NOUN) or as standalone overrides (QUANT). Slots
with no operator MODIFIERs round-trip an empty tuple — singular-path
behaviour is unchanged from M1.5.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from rulso.state import Card, CardType, RuleBuilder, RuleKind, Slot

_SUBJECT_SLOT: str = "SUBJECT"
_QUANT_SLOT: str = "QUANT"
_NOUN_SLOT: str = "NOUN"


class IfRule(BaseModel):
    """Structured view over a built IF rule.

    Slot cards are surfaced as ``Card`` references so the resolver can read
    semantic content (player id, comparator, resource name) without re-walking
    the slot list. Per-slot ``modifiers`` tuples carry attached operator
    MODIFIERs (ADR-0004) in play order; empty when no operator was attached.
    """

    model_config = ConfigDict(frozen=True)

    subject: Card
    subject_modifiers: tuple[Card, ...] = ()
    quant: Card
    quant_modifiers: tuple[Card, ...] = ()
    noun: Card
    noun_modifiers: tuple[Card, ...] = ()


def render_if_rule(rule: RuleBuilder) -> IfRule:
    """Pull SUBJECT / QUANT / NOUN slot contents off ``rule``.

    Each slot's ``modifiers`` tuple is preserved verbatim on the returned
    ``IfRule`` so the resolver can fold operator MODIFIERs (ADR-0004).

    Raises ``ValueError`` if the template is not IF, a required slot is
    missing, a slot's declared type does not match, or a required slot is
    unfilled.
    """
    if rule.template is not RuleKind.IF:
        raise ValueError(f"render_if_rule requires IF template, got {rule.template}")
    sub = _slot(rule, _SUBJECT_SLOT, CardType.SUBJECT)
    q = _slot(rule, _QUANT_SLOT, CardType.MODIFIER)
    n = _slot(rule, _NOUN_SLOT, CardType.NOUN)
    return IfRule(
        subject=sub.filled_by,  # type: ignore[arg-type]
        subject_modifiers=sub.modifiers,
        quant=q.filled_by,  # type: ignore[arg-type]
        quant_modifiers=q.modifiers,
        noun=n.filled_by,  # type: ignore[arg-type]
        noun_modifiers=n.modifiers,
    )


def _slot(rule: RuleBuilder, name: str, expected_type: CardType) -> Slot:
    slot = next((s for s in rule.slots if s.name == name), None)
    if slot is None:
        raise ValueError(f"IF rule missing slot {name!r}")
    if slot.type is not expected_type:
        raise ValueError(f"slot {name!r} has type {slot.type}, expected {expected_type}")
    if slot.filled_by is None:
        raise ValueError(f"slot {name!r} is unfilled")
    return slot

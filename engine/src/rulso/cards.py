"""Card catalogue loader.

Reads ``design/cards.yaml`` and exposes the M1.5 + M2 card vocabulary as
immutable Pydantic models. Read-only consumer of :mod:`rulso.state` — does
not edit the substrate.

Public surface:

* :func:`load_cards` — every main-deck-eligible card in the yaml as a frozen
  tuple of :class:`rulso.state.Card`. Covers SUBJECT, NOUN, MODIFIER (both
  comparator and operator), and JOKER. Excludes CONDITION (own deck), EFFECT
  (own deck), and goal cards (own type).
* :func:`load_condition_templates` — every CONDITION template as a frozen
  tuple of :class:`ConditionTemplate`. CONDITION cards cannot be ``Card``
  instances because :class:`rulso.state.CardType` does not include CONDITION;
  conditions live in their own deck (the dealer's first play each round).
* :func:`load_effect_cards` — every EFFECT card as a frozen tuple of
  :class:`rulso.state.Card` with ``type=CardType.EFFECT``. Mirrors
  :func:`load_condition_templates` shape — EFFECTs seed
  ``GameState.effect_deck``, never the main deck.
* :func:`load_goal_cards` — every goal card as a frozen tuple of
  :class:`rulso.state.GoalCard`. Goals seed ``GameState.goal_deck`` and feed
  ``active_goals`` slots.
* :func:`build_default_deck` — bundles the multiplied-by-copies main deck
  with the condition deck into a :class:`Decks` namedtuple. Effect and goal
  decks are loaded by their own helpers — they live in separate game-state
  fields, so coupling them to ``Decks`` would mislead callers.

Schema validation runs through Pydantic; malformed yaml raises
:class:`ValueError` with the underlying validation error chained.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal, NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rulso.state import Card, CardType, GoalCard, RuleKind, ScopeMode

# engine/src/rulso/cards.py → parents[3] = repo root
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_DEFAULT_PATH: Path = _REPO_ROOT / "design" / "cards.yaml"

_FROZEN = ConfigDict(frozen=True)

_OperatorTarget = Literal["SUBJECT", "NOUN", "QUANT"]


class ConditionSlot(BaseModel):
    """One slot definition on a CONDITION template."""

    model_config = _FROZEN

    name: str
    type: CardType


class ConditionTemplate(BaseModel):
    """A CONDITION card — owns a rule's lifetime + slot shape.

    Not a :class:`rulso.state.Card` subtype: ``state.CardType`` deliberately
    omits CONDITION. The condition deck is drawn separately from the main
    deck; the dealer plays one CONDITION per round to seed ``active_rule``.
    """

    model_config = _FROZEN

    id: str
    name: str
    kind: RuleKind
    slots: tuple[ConditionSlot, ...]


class Decks(NamedTuple):
    """Bundled output of :func:`build_default_deck`.

    ``main`` is the playable draw deck (multiplied by per-id copy counts from
    cards.yaml). ``conditions`` is the separate condition deck — one template
    per kind, no copies. Effect and goal decks are loaded by their own helpers
    (they seed ``GameState.effect_deck`` / ``goal_deck``).
    """

    main: tuple[Card, ...]
    conditions: tuple[ConditionTemplate, ...]


class _CardEntry(BaseModel):
    model_config = _FROZEN
    id: str
    name: str


class _SubjectEntry(BaseModel):
    model_config = _FROZEN
    id: str
    name: str
    scope_mode: ScopeMode = "singular"


class _OperatorEntry(BaseModel):
    model_config = _FROZEN
    id: str
    name: str
    targets: tuple[_OperatorTarget, ...] = Field(min_length=1)


class _DeckEntry(BaseModel):
    model_config = _FROZEN
    id: str
    copies: int = Field(gt=0)


class _Schema(BaseModel):
    model_config = _FROZEN
    condition_cards: tuple[ConditionTemplate, ...]
    subject_cards: tuple[_SubjectEntry, ...]
    noun_cards: tuple[_CardEntry, ...]
    modifier_cards: tuple[_CardEntry, ...]
    operator_modifier_cards: tuple[_OperatorEntry, ...] = ()
    joker_cards: tuple[_CardEntry, ...] = ()
    effect_cards: tuple[_CardEntry, ...] = ()
    goal_cards: tuple[GoalCard, ...] = ()
    deck: tuple[_DeckEntry, ...]


def load_cards(path: Path | None = None) -> tuple[Card, ...]:
    """Return every main-deck-eligible card defined in ``cards.yaml``.

    Cards appear once each (no copy multiplication). Covers SUBJECT, NOUN,
    MODIFIER (comparator and operator), and JOKER. To get the playable
    multi-copy deck, call :func:`build_default_deck`. CONDITION templates,
    EFFECT cards, and goal cards each have dedicated loaders.
    """
    return _flatten_main_cards(_read(path))


def load_condition_templates(path: Path | None = None) -> tuple[ConditionTemplate, ...]:
    """Return every CONDITION template defined in ``cards.yaml``."""
    return _read(path).condition_cards


def load_effect_cards(path: Path | None = None) -> tuple[Card, ...]:
    """Return every EFFECT card defined in ``cards.yaml``.

    Effect cards seed ``GameState.effect_deck``; they are revealed at
    ``round_start`` step 6 and applied to matched players when the round's
    rule resolves (per ``design/effects-inventory.md``). They are NOT part
    of the main deck.
    """
    schema = _read(path)
    return tuple(
        Card(id=entry.id, name=entry.name, type=CardType.EFFECT) for entry in schema.effect_cards
    )


def load_goal_cards(path: Path | None = None) -> tuple[GoalCard, ...]:
    """Return every goal card defined in ``cards.yaml``.

    Goal cards seed ``GameState.goal_deck``; ``active_goals`` holds up to
    ``ACTIVE_GOALS = 3`` of them face-up at any time (per
    ``design/goals-inventory.md``). They are NOT part of the main deck.
    """
    return _read(path).goal_cards


def build_default_deck(
    cards: Iterable[Card] | None = None,
    *,
    path: Path | None = None,
) -> Decks:
    """Build the M1.5 + M2 starter :class:`Decks` from ``cards.yaml``.

    The main deck multiplies each card id by the ``copies`` count from the
    yaml's ``deck:`` section. ``cards`` filters which card definitions are
    eligible; defaults to every main-deck-eligible card in the yaml.

    Raises :class:`ValueError` if a ``deck:`` entry references an id missing
    from ``cards`` (or from the yaml when ``cards`` is unset).
    """
    schema = _read(path)
    pool = tuple(cards) if cards is not None else _flatten_main_cards(schema)
    by_id: dict[str, Card] = {c.id: c for c in pool}
    main: list[Card] = []
    for entry in schema.deck:
        card = by_id.get(entry.id)
        if card is None:
            raise ValueError(f"deck entry references unknown card id {entry.id!r}")
        main.extend(card for _ in range(entry.copies))
    return Decks(main=tuple(main), conditions=schema.condition_cards)


def _read(path: Path | None) -> _Schema:
    target = path if path is not None else _DEFAULT_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise FileNotFoundError(f"cards.yaml not found at {target}") from e
    if raw is None:
        raise ValueError(f"cards.yaml at {target} is empty")
    try:
        return _Schema.model_validate(raw)
    except ValidationError as e:
        raise ValueError(f"cards.yaml schema validation failed: {e}") from e


def _flatten_main_cards(schema: _Schema) -> tuple[Card, ...]:
    out: list[Card] = []
    for subj in schema.subject_cards:
        out.append(
            Card(
                id=subj.id,
                name=subj.name,
                type=CardType.SUBJECT,
                scope_mode=subj.scope_mode,
            )
        )
    for entry in schema.noun_cards:
        out.append(Card(id=entry.id, name=entry.name, type=CardType.NOUN))
    for entry in schema.modifier_cards:
        out.append(Card(id=entry.id, name=entry.name, type=CardType.MODIFIER))
    for op in schema.operator_modifier_cards:
        out.append(Card(id=op.id, name=op.name, type=CardType.MODIFIER))
    for jkr in schema.joker_cards:
        out.append(Card(id=jkr.id, name=jkr.name, type=CardType.JOKER))
    return tuple(out)

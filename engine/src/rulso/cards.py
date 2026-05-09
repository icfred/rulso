"""Card catalogue loader.

Reads ``design/cards.yaml`` and exposes the M1.5 starter card set as immutable
Pydantic models. Read-only consumer of :mod:`rulso.state` — does not edit the
substrate.

Public surface:

* :func:`load_cards` — every non-CONDITION card in the yaml as a frozen tuple
  of :class:`rulso.state.Card`.
* :func:`load_condition_templates` — every CONDITION template as a frozen
  tuple of :class:`ConditionTemplate`. CONDITION cards cannot be ``Card``
  instances because :class:`rulso.state.CardType` does not include CONDITION;
  conditions live in their own deck (the dealer's first play each round).
* :func:`build_default_deck` — bundles the multiplied-by-copies playable deck
  with the condition deck into a :class:`Decks` namedtuple.

Schema validation runs through Pydantic; malformed yaml raises
:class:`ValueError` with the underlying validation error chained.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rulso.state import Card, CardType, RuleKind

# engine/src/rulso/cards.py → parents[3] = repo root
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_DEFAULT_PATH: Path = _REPO_ROOT / "design" / "cards.yaml"

_FROZEN = ConfigDict(frozen=True)


class ConditionSlot(BaseModel):
    """One slot definition on a CONDITION template."""

    model_config = _FROZEN

    name: str
    type: CardType


class ConditionTemplate(BaseModel):
    """A CONDITION card — owns a rule's lifetime and slot shape.

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

    ``main`` is the playable draw deck (SUBJECT/NOUN/MODIFIER cards multiplied
    by per-id copy counts from cards.yaml). ``conditions`` is the separate
    condition deck — one template per kind, no copies.
    """

    main: tuple[Card, ...]
    conditions: tuple[ConditionTemplate, ...]


class _CardEntry(BaseModel):
    model_config = _FROZEN
    id: str
    name: str


class _DeckEntry(BaseModel):
    model_config = _FROZEN
    id: str
    copies: int = Field(gt=0)


class _Schema(BaseModel):
    model_config = _FROZEN
    condition_cards: tuple[ConditionTemplate, ...]
    subject_cards: tuple[_CardEntry, ...]
    noun_cards: tuple[_CardEntry, ...]
    modifier_cards: tuple[_CardEntry, ...]
    deck: tuple[_DeckEntry, ...]


def load_cards(path: Path | None = None) -> tuple[Card, ...]:
    """Return every non-CONDITION card defined in ``cards.yaml``.

    Cards appear once each (no copy multiplication). To get the playable
    multi-copy deck, call :func:`build_default_deck`. CONDITION templates are
    loaded by :func:`load_condition_templates`.
    """
    return _flatten_cards(_read(path))


def load_condition_templates(path: Path | None = None) -> tuple[ConditionTemplate, ...]:
    """Return every CONDITION template defined in ``cards.yaml``."""
    return _read(path).condition_cards


def build_default_deck(
    cards: Iterable[Card] | None = None,
    *,
    path: Path | None = None,
) -> Decks:
    """Build the M1.5 starter :class:`Decks` from ``cards.yaml``.

    The main deck multiplies each card id by the ``copies`` count from the
    yaml's ``deck:`` section. ``cards`` filters which card definitions are
    eligible; defaults to every non-CONDITION card in the yaml.

    Raises :class:`ValueError` if a ``deck:`` entry references an id missing
    from ``cards`` (or from the yaml when ``cards`` is unset).
    """
    schema = _read(path)
    pool = tuple(cards) if cards is not None else _flatten_cards(schema)
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


def _flatten_cards(schema: _Schema) -> tuple[Card, ...]:
    out: list[Card] = []
    for entry in schema.subject_cards:
        out.append(Card(id=entry.id, name=entry.name, type=CardType.SUBJECT))
    for entry in schema.noun_cards:
        out.append(Card(id=entry.id, name=entry.name, type=CardType.NOUN))
    for entry in schema.modifier_cards:
        out.append(Card(id=entry.id, name=entry.name, type=CardType.MODIFIER))
    return tuple(out)

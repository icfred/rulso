"""Tests for the cards.yaml loader (RUL-17)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from rulso.cards import (
    ConditionTemplate,
    Decks,
    build_default_deck,
    load_cards,
    load_condition_templates,
)
from rulso.state import Card, CardType, RuleKind

# --- Default cards.yaml -------------------------------------------------------


def test_load_cards_returns_frozen_tuple_of_cards() -> None:
    cards = load_cards()
    assert isinstance(cards, tuple)
    assert all(isinstance(c, Card) for c in cards)
    with pytest.raises(ValidationError):
        cards[0].name = "MUTATED"  # type: ignore[misc]


def test_load_cards_unique_ids() -> None:
    cards = load_cards()
    ids = [c.id for c in cards]
    assert len(ids) == len(set(ids)), "card ids must be unique across the yaml"


def test_load_cards_covers_all_non_condition_card_types() -> None:
    cards = load_cards()
    types = {c.type for c in cards}
    assert types == {CardType.SUBJECT, CardType.NOUN, CardType.MODIFIER}


def test_load_cards_count_matches_inventory_subset() -> None:
    cards = load_cards()
    by_type: dict[CardType, list[Card]] = {t: [] for t in CardType}
    for c in cards:
        by_type[c.type].append(c)
    # M1.5 starter subset: 6 SUBJECT, 2 NOUN, 12 MODIFIER comparator.
    assert len(by_type[CardType.SUBJECT]) == 6
    assert len(by_type[CardType.NOUN]) == 2
    assert len(by_type[CardType.MODIFIER]) == 12
    assert len(by_type[CardType.JOKER]) == 0


def test_subject_names_match_handover_spec() -> None:
    subjects = {c.name for c in load_cards() if c.type is CardType.SUBJECT}
    assert subjects == {"seat_0", "seat_1", "seat_2", "seat_3", "LEADER", "WOUNDED"}


def test_noun_names_match_resolver_vocabulary() -> None:
    nouns = {c.name for c in load_cards() if c.type is CardType.NOUN}
    assert nouns == {"CHIPS", "VP"}


def test_modifier_names_follow_op_n_form_with_known_ops() -> None:
    mods = [c for c in load_cards() if c.type is CardType.MODIFIER]
    valid_ops = {"GE", "GT", "LE", "LT", "EQ"}
    seen_ops: set[str] = set()
    for m in mods:
        op, _, n = m.name.partition(":")
        assert op in valid_ops, f"modifier {m.name!r} has unknown OP {op!r}"
        assert n.isdigit(), f"modifier {m.name!r} threshold {n!r} not an int"
        seen_ops.add(op)
    # The hand-over mandates all 5 OPs are represented in the M1.5 subset.
    assert seen_ops == valid_ops


# --- Condition templates ------------------------------------------------------


def test_load_condition_templates_returns_only_if_in_m15() -> None:
    templates = load_condition_templates()
    assert isinstance(templates, tuple)
    assert len(templates) == 1
    template = templates[0]
    assert isinstance(template, ConditionTemplate)
    assert template.kind is RuleKind.IF
    assert template.name == "IF"


def test_condition_slots_match_grammar_render_if_rule_contract() -> None:
    template = load_condition_templates()[0]
    slot_names = tuple(s.name for s in template.slots)
    slot_types = tuple(s.type for s in template.slots)
    # grammar.render_if_rule reads slot names SUBJECT / QUANT / NOUN.
    assert slot_names == ("SUBJECT", "QUANT", "NOUN")
    assert slot_types == (CardType.SUBJECT, CardType.MODIFIER, CardType.NOUN)


# --- Default deck -------------------------------------------------------------


def test_build_default_deck_returns_decks_namedtuple() -> None:
    decks = build_default_deck()
    assert isinstance(decks, Decks)
    assert isinstance(decks.main, tuple)
    assert isinstance(decks.conditions, tuple)


def test_default_main_deck_excludes_condition_cards() -> None:
    decks = build_default_deck()
    # state.CardType doesn't include CONDITION; the strongest assertion is
    # that no Card in main deck has the CONDITION-template ids.
    condition_ids = {t.id for t in decks.conditions}
    main_ids = {c.id for c in decks.main}
    assert condition_ids.isdisjoint(main_ids)


def test_default_main_deck_multiplies_copies() -> None:
    decks = build_default_deck()
    counts: dict[str, int] = {}
    for c in decks.main:
        counts[c.id] = counts.get(c.id, 0) + 1
    # Sanity: 6 SUBJECT × 3 + 2 NOUN × 4 + 12 MODIFIER × 2 = 18 + 8 + 24 = 50.
    assert sum(counts.values()) == 50
    assert counts["subj.seat_0"] == 3
    assert counts["noun.chips"] == 4
    assert counts["mod.cmp.eq.5"] == 2


def test_default_main_deck_supports_4_player_initial_deal() -> None:
    # 4 players × HAND_SIZE (7) = 28 cards needed for the opening deal.
    decks = build_default_deck()
    assert len(decks.main) >= 28


def test_build_default_deck_filters_to_passed_cards() -> None:
    cards = load_cards()
    nouns_only = tuple(c for c in cards if c.type is CardType.NOUN)
    # Filtering to NOUN-only must raise because the yaml deck section
    # references SUBJECT/MODIFIER ids that aren't in the filtered pool.
    with pytest.raises(ValueError, match="unknown card id"):
        build_default_deck(nouns_only)


# --- Custom-path loading + schema validation ---------------------------------


_VALID_FIXTURE = """
condition_cards:
  - id: cond.if
    name: IF
    kind: IF
    slots:
      - { name: SUBJECT, type: SUBJECT }
      - { name: QUANT, type: MODIFIER }
      - { name: NOUN, type: NOUN }
subject_cards:
  - { id: subj.x, name: X }
noun_cards:
  - { id: noun.x, name: X }
modifier_cards:
  - { id: mod.x, name: "GE:1" }
deck:
  - { id: subj.x, copies: 1 }
"""


def test_load_cards_accepts_custom_path(tmp_path: Path) -> None:
    target = tmp_path / "cards.yaml"
    target.write_text(_VALID_FIXTURE)
    cards = load_cards(target)
    assert {c.id for c in cards} == {"subj.x", "noun.x", "mod.x"}


def test_missing_required_section_raises_value_error(tmp_path: Path) -> None:
    target = tmp_path / "broken.yaml"
    # Missing `deck:` field — schema requires it.
    target.write_text(
        yaml.safe_dump(
            {
                "condition_cards": [],
                "subject_cards": [],
                "noun_cards": [],
                "modifier_cards": [],
            }
        )
    )
    with pytest.raises(ValueError, match="schema validation failed"):
        load_cards(target)


def test_unknown_card_type_in_slot_raises(tmp_path: Path) -> None:
    target = tmp_path / "bad_type.yaml"
    bad = yaml.safe_load(_VALID_FIXTURE)
    bad["condition_cards"][0]["slots"][0]["type"] = "NOT_A_TYPE"
    target.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="schema validation failed"):
        load_cards(target)


def test_zero_copies_rejected(tmp_path: Path) -> None:
    target = tmp_path / "zero_copies.yaml"
    bad = yaml.safe_load(_VALID_FIXTURE)
    bad["deck"][0]["copies"] = 0
    target.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="schema validation failed"):
        load_cards(target)


def test_empty_yaml_rejected(tmp_path: Path) -> None:
    target = tmp_path / "empty.yaml"
    target.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_cards(target)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    target = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError, match="not found"):
        load_cards(target)

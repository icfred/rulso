"""Tests for the cards.yaml loader (RUL-17 baseline + RUL-31 M2 extensions)."""

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
    load_effect_cards,
    load_goal_cards,
)
from rulso.state import Card, CardType, GoalCard, RuleKind

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


def test_load_cards_covers_main_deck_card_types() -> None:
    """``load_cards`` returns SUBJECT / NOUN / MODIFIER / JOKER cards.

    EFFECT cards (their own deck) and goal cards (their own type) are loaded
    by ``load_effect_cards`` / ``load_goal_cards`` and not present here.
    """
    cards = load_cards()
    types = {c.type for c in cards}
    assert types == {CardType.SUBJECT, CardType.NOUN, CardType.MODIFIER, CardType.JOKER}
    assert CardType.EFFECT not in types


def test_load_cards_count_matches_yaml_sections() -> None:
    """Per-type counts from cards.yaml — M1.5 baseline + M2 additions.

    SUBJECT: 6 M1.5 (4 seats + leader + wounded) + 2 polymorphic (anyone, each).
    NOUN: 2 M1.5 (chips, vp) + 6 M2 (cards, rules, hits, gifts, rounds, burn).
    MODIFIER: 12 baked-N comparators + 5 OP-only + 5 operators.
    JOKER: 4 (persist_when, persist_while, double, echo).
    """
    cards = load_cards()
    by_type: dict[CardType, list[Card]] = {t: [] for t in CardType}
    for c in cards:
        by_type[c.type].append(c)
    assert len(by_type[CardType.SUBJECT]) == 8
    assert len(by_type[CardType.NOUN]) == 8
    assert len(by_type[CardType.MODIFIER]) == 22
    assert len(by_type[CardType.JOKER]) == 4
    assert len(by_type[CardType.EFFECT]) == 0


def test_subject_names_match_engine_substrate() -> None:
    """SUBJECT card names must match what the engine actually scopes against.

    Literal seats: ``Player.id`` from ``rules.start_game`` (``p0..p3``).
    Labels: keys in ``labels.LABEL_NAMES`` (``"THE LEADER"`` / ``"THE WOUNDED"``)
    per ADR-0001. Polymorphic SUBJECTs follow ADR-0003 (`ANYONE`,
    `EACH_PLAYER`) — disambiguation lives in `name`, not in render text.
    """
    subjects = {c.name for c in load_cards() if c.type is CardType.SUBJECT}
    assert subjects == {
        "p0",
        "p1",
        "p2",
        "p3",
        "THE LEADER",
        "THE WOUNDED",
        "ANYONE",
        "EACH_PLAYER",
    }


def test_subject_scope_modes_per_adr_0003() -> None:
    """Polymorphic SUBJECTs carry the right ``scope_mode`` (ADR-0003)."""
    subjects = {c.name: c for c in load_cards() if c.type is CardType.SUBJECT}
    assert subjects["ANYONE"].scope_mode == "existential"
    assert subjects["EACH_PLAYER"].scope_mode == "iterative"
    # Every other SUBJECT defaults to ``singular``.
    for name, card in subjects.items():
        if name not in {"ANYONE", "EACH_PLAYER"}:
            assert card.scope_mode == "singular", f"SUBJECT {name!r} unexpected scope_mode"


def test_non_subject_cards_default_to_singular_scope_mode() -> None:
    """``scope_mode`` defaults to ``singular`` on all non-SUBJECT cards.

    ADR-0003 places ``scope_mode`` on the SUBJECT axis; the field is shared on
    ``Card`` for shape uniformity but is read only for SUBJECTs.
    """
    for card in load_cards():
        if card.type is not CardType.SUBJECT:
            assert card.scope_mode == "singular"


def test_noun_names_match_resolver_vocabulary() -> None:
    """NOUN names cover M1.5 + M2 reads per design/cards-inventory.md."""
    nouns = {c.name for c in load_cards() if c.type is CardType.NOUN}
    assert nouns == {
        "CHIPS",
        "VP",
        "CARDS",
        "RULES",
        "HITS",
        "GIFTS",
        "ROUNDS",
        "BURN_TOKENS",
    }


def test_modifier_comparators_use_known_ops() -> None:
    """Comparator MODIFIERs follow ``<OP>`` (M2) or ``<OP>:<N>`` (M1.5 baked).

    Operator MODIFIERs are skipped here — they're tested separately.
    """
    valid_ops = {"GE", "GT", "LE", "LT", "EQ"}
    operator_names = {"BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"}
    seen_ops: set[str] = set()
    for m in load_cards():
        if m.type is not CardType.MODIFIER or m.name in operator_names:
            continue
        op, _, n = m.name.partition(":")
        assert op in valid_ops, f"comparator {m.name!r} has unknown OP {op!r}"
        if n:
            assert n.isdigit(), f"comparator {m.name!r} threshold {n!r} not an int"
        seen_ops.add(op)
    assert seen_ops == valid_ops


def test_op_only_comparators_present_per_adr_0002() -> None:
    """Each of the 5 ops has an OP-only variant (dice fills N at play time)."""
    op_only = {c.name for c in load_cards() if c.type is CardType.MODIFIER and ":" not in c.name}
    # Filter to comparators (operators have no `:` either).
    op_only -= {"BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"}
    assert op_only == {"LT", "LE", "GT", "GE", "EQ"}


def test_operator_modifiers_present_per_adr_0004() -> None:
    """Operator MODIFIERs cover the full ADR-0004 catalogue."""
    operators = {c.name for c in load_cards() if c.type is CardType.MODIFIER}
    operators &= {"BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"}
    assert operators == {"BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"}


def test_joker_names_follow_joker_prefix() -> None:
    """JOKER names follow ``JOKER:<VARIANT>`` per design/cards-inventory.md."""
    jokers = {c.name for c in load_cards() if c.type is CardType.JOKER}
    assert jokers == {
        "JOKER:PERSIST_WHEN",
        "JOKER:PERSIST_WHILE",
        "JOKER:DOUBLE",
        "JOKER:ECHO",
    }


# --- Condition templates ------------------------------------------------------


def test_load_condition_templates_covers_if_when_while() -> None:
    """All three lifetime templates land in M2 per design/cards-inventory.md."""
    templates = load_condition_templates()
    assert isinstance(templates, tuple)
    assert all(isinstance(t, ConditionTemplate) for t in templates)
    by_kind = {t.kind: t for t in templates}
    assert set(by_kind) == {RuleKind.IF, RuleKind.WHEN, RuleKind.WHILE}
    assert by_kind[RuleKind.IF].name == "IF"
    assert by_kind[RuleKind.WHEN].name == "WHEN"
    assert by_kind[RuleKind.WHILE].name == "WHILE"


def test_condition_if_remains_first_template() -> None:
    """``rules._draw_condition_template`` reads ``templates[0]``.

    Until the M2 condition deck lands as a real deck, the IF template must
    stay first so M1.5 round flow continues to seed IF rules.
    """
    assert load_condition_templates()[0].kind is RuleKind.IF


def test_condition_slots_match_grammar_render_if_rule_contract() -> None:
    """All three M2 templates share the same ``[SUBJECT, QUANT, NOUN]`` shape."""
    for template in load_condition_templates():
        slot_names = tuple(s.name for s in template.slots)
        slot_types = tuple(s.type for s in template.slots)
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
    condition_ids = {t.id for t in decks.conditions}
    main_ids = {c.id for c in decks.main}
    assert condition_ids.isdisjoint(main_ids)


def test_default_main_deck_excludes_effect_and_goal_cards() -> None:
    """Effect cards and goal cards live in their own decks, never in main."""
    main_ids = {c.id for c in build_default_deck().main}
    effect_ids = {c.id for c in load_effect_cards()}
    goal_ids = {g.id for g in load_goal_cards()}
    assert effect_ids.isdisjoint(main_ids)
    assert goal_ids.isdisjoint(main_ids)


def test_default_main_deck_multiplies_copies() -> None:
    """Main deck composition matches the yaml ``deck:`` section.

    Composition is extended as Phase 3 consumer paths land. RUL-44 adds the
    six M2 polymorphic NOUNs at 2 copies each; RUL-42 (G) adds 5 OP-only
    comparator MODIFIERs at 2 copies each (ADR-0002); RUL-43 (H) adds 5
    operator MODIFIERs at 2 copies each (ADR-0004). Pre-Phase-3 baseline
    was 50 (6 SUBJECT × 3 + 2 NOUN × 4 + 12 MODIFIER × 2).
    """
    decks = build_default_deck()
    counts: dict[str, int] = {}
    for c in decks.main:
        counts[c.id] = counts.get(c.id, 0) + 1
    # 6 SUBJECT × 3 + 8 NOUN (2×4 M1.5 + 6×2 M2 RUL-44) + 12 MODIFIER × 2
    # + 5 OP-only comparators × 2 (RUL-42) + 5 operator MODIFIERs × 2 (RUL-43)
    # = 18 + 20 + 24 + 10 + 10 = 82.
    assert sum(counts.values()) == 82
    assert counts["subj.p0"] == 3
    assert counts["noun.chips"] == 4
    assert counts["noun.cards"] == 2
    assert counts["noun.burn"] == 2
    assert counts["mod.cmp.eq.5"] == 2
    # RUL-42 (G): OP-only comparators present at 2 copies each.
    for op_id in ("mod.cmp.lt", "mod.cmp.le", "mod.cmp.gt", "mod.cmp.ge", "mod.cmp.eq"):
        assert counts[op_id] == 2
    # RUL-43 (H): every operator MODIFIER seeded at 2 copies.
    for op_id in ("mod.op.but", "mod.op.and", "mod.op.or", "mod.op.more_than", "mod.op.at_least"):
        assert counts[op_id] == 2, f"operator {op_id} not at expected copies"


def test_default_main_deck_supports_4_player_initial_deal() -> None:
    decks = build_default_deck()
    assert len(decks.main) >= 28


def test_build_default_deck_filters_to_passed_cards() -> None:
    cards = load_cards()
    nouns_only = tuple(c for c in cards if c.type is CardType.NOUN)
    with pytest.raises(ValueError, match="unknown card id"):
        build_default_deck(nouns_only)


# --- Effect cards (RUL-31) ----------------------------------------------------


def test_load_effect_cards_returns_frozen_tuple_typed_effect() -> None:
    effects = load_effect_cards()
    assert isinstance(effects, tuple)
    assert all(isinstance(c, Card) for c in effects)
    assert all(c.type is CardType.EFFECT for c in effects)
    with pytest.raises(ValidationError):
        effects[0].name = "MUTATED"  # type: ignore[misc]


def test_load_effect_cards_covers_m2_starter_subset() -> None:
    """All 12 M2 starter effect cards from design/effects-inventory.md."""
    ids = {c.id for c in load_effect_cards()}
    assert ids == {
        "eff.chips.gain.5",
        "eff.chips.gain.10",
        "eff.chips.drain.5",
        "eff.vp.gain.1",
        "eff.vp.drain.1",
        "eff.burn.apply.1",
        "eff.mute.apply",
        "eff.blessed.apply",
        "eff.chained.apply",
        "eff.burn.clear.1",
        "eff.draw.2",
        "eff.noop",
    }


def test_effect_cards_have_unique_ids() -> None:
    effect_ids = [c.id for c in load_effect_cards()]
    assert len(effect_ids) == len(set(effect_ids))


def test_blessed_effect_carries_target_modifier_per_inventory() -> None:
    """BLESSED applies to the unmatched cohort — encoded as ``@EXCEPT_MATCHED``."""
    by_id = {c.id: c for c in load_effect_cards()}
    assert by_id["eff.blessed.apply"].name == "APPLY_BLESSED@EXCEPT_MATCHED"


# --- Goal cards (RUL-31) ------------------------------------------------------


def test_load_goal_cards_returns_frozen_tuple_of_goal_cards() -> None:
    goals = load_goal_cards()
    assert isinstance(goals, tuple)
    assert all(isinstance(g, GoalCard) for g in goals)
    with pytest.raises(ValidationError):
        goals[0].name = "MUTATED"  # type: ignore[misc]


def test_load_goal_cards_covers_m2_starter_subset() -> None:
    """All 7 M2 starter goals from design/goals-inventory.md."""
    ids = {g.id for g in load_goal_cards()}
    assert ids == {
        "goal.banker",
        "goal.debtor",
        "goal.builder",
        "goal.philanthropist",
        "goal.survivor",
        "goal.free_agent",
        "goal.hoarder",
    }


def test_goal_cards_kinds_split_single_and_renewable() -> None:
    """6 single-claim + 1 renewable per goals-inventory.md."""
    goals = load_goal_cards()
    kinds = [g.claim_kind for g in goals]
    assert kinds.count("single") == 6
    assert kinds.count("renewable") == 1
    renewable = next(g for g in goals if g.claim_kind == "renewable")
    assert renewable.id == "goal.hoarder"


def test_goal_cards_vp_award_uniform_one() -> None:
    """M2 starter awards 1 VP per claim uniformly (tuning deferred)."""
    for goal in load_goal_cards():
        assert goal.vp_award == 1


def test_goal_cards_have_unique_ids_and_predicate_keys() -> None:
    goals = load_goal_cards()
    ids = [g.id for g in goals]
    predicates = [g.claim_condition for g in goals]
    assert len(ids) == len(set(ids))
    assert len(predicates) == len(set(predicates))


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


_M2_FIXTURE = """
condition_cards:
  - id: cond.if
    name: IF
    kind: IF
    slots:
      - { name: SUBJECT, type: SUBJECT }
      - { name: QUANT, type: MODIFIER }
      - { name: NOUN, type: NOUN }
subject_cards:
  - { id: subj.a, name: A }
  - { id: subj.any, name: ANYONE, scope_mode: existential }
noun_cards:
  - { id: noun.x, name: X }
modifier_cards:
  - { id: mod.x, name: "GE:1" }
operator_modifier_cards:
  - { id: mod.op.but, name: BUT, targets: [SUBJECT] }
joker_cards:
  - { id: jkr.x, name: "JOKER:X" }
effect_cards:
  - { id: eff.x, name: "GAIN_VP:1" }
goal_cards:
  - id: goal.x
    name: THE_X
    claim_condition: chips_at_least_75
    vp_award: 1
    claim_kind: single
deck:
  - { id: subj.a, copies: 1 }
  - { id: subj.any, copies: 1 }
  - { id: jkr.x, copies: 1 }
  - { id: mod.op.but, copies: 1 }
"""


def test_load_cards_accepts_custom_path(tmp_path: Path) -> None:
    target = tmp_path / "cards.yaml"
    target.write_text(_VALID_FIXTURE)
    cards = load_cards(target)
    assert {c.id for c in cards} == {"subj.x", "noun.x", "mod.x"}


def test_minimal_yaml_omits_optional_m2_sections(tmp_path: Path) -> None:
    """M2 sections (operator_modifier_cards / joker_cards / effect_cards /
    goal_cards) default to empty so M1.5-shaped fixtures still validate."""
    target = tmp_path / "minimal.yaml"
    target.write_text(_VALID_FIXTURE)
    assert load_effect_cards(target) == ()
    assert load_goal_cards(target) == ()


def test_full_m2_fixture_loads_every_card_kind(tmp_path: Path) -> None:
    target = tmp_path / "m2.yaml"
    target.write_text(_M2_FIXTURE)
    cards = load_cards(target)
    types = {c.type for c in cards}
    assert types == {CardType.SUBJECT, CardType.NOUN, CardType.MODIFIER, CardType.JOKER}
    effects = load_effect_cards(target)
    assert {c.type for c in effects} == {CardType.EFFECT}
    assert {c.id for c in effects} == {"eff.x"}
    goals = load_goal_cards(target)
    assert {g.id for g in goals} == {"goal.x"}


def test_missing_required_section_raises_value_error(tmp_path: Path) -> None:
    target = tmp_path / "broken.yaml"
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


def test_invalid_scope_mode_rejected(tmp_path: Path) -> None:
    target = tmp_path / "bad_scope.yaml"
    bad = yaml.safe_load(_M2_FIXTURE)
    bad["subject_cards"][1]["scope_mode"] = "not_a_mode"
    target.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="schema validation failed"):
        load_cards(target)


def test_operator_targets_required_non_empty(tmp_path: Path) -> None:
    target = tmp_path / "empty_targets.yaml"
    bad = yaml.safe_load(_M2_FIXTURE)
    bad["operator_modifier_cards"][0]["targets"] = []
    target.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="schema validation failed"):
        load_cards(target)


def test_operator_targets_must_be_known_slot_kind(tmp_path: Path) -> None:
    target = tmp_path / "bad_targets.yaml"
    bad = yaml.safe_load(_M2_FIXTURE)
    bad["operator_modifier_cards"][0]["targets"] = ["JOKER"]
    target.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="schema validation failed"):
        load_cards(target)


def test_invalid_claim_kind_rejected(tmp_path: Path) -> None:
    target = tmp_path / "bad_claim.yaml"
    bad = yaml.safe_load(_M2_FIXTURE)
    bad["goal_cards"][0]["claim_kind"] = "perpetual"
    target.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="schema validation failed"):
        load_goal_cards(target)


def test_empty_yaml_rejected(tmp_path: Path) -> None:
    target = tmp_path / "empty.yaml"
    target.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_cards(target)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    target = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError, match="not found"):
        load_cards(target)

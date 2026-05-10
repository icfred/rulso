"""Tests for operator-MODIFIER fold (RUL-43, ADR-0004).

Covers SUBJECT-targeted (BUT/AND/OR), NOUN-targeted (AND/OR), and
QUANT-targeted (MORE_THAN/AT_LEAST) operators, including:

* Singular path (no operator MODIFIERs) is byte-identical to M1.5 resolver.
* Each operator's documented semantics per the ADR-0004 table.
* Multi-fold left-to-right play order (BUT chains, last-write-wins for QUANT).
* Render-side surfacing of ``Slot.modifiers`` on ``IfRule``.
"""

from __future__ import annotations

import pytest

from rulso.effects import (
    OPERATOR_MODIFIER_NAMES,
    is_operator_modifier,
    resolve_if_rule,
)
from rulso.grammar import render_if_rule
from rulso.state import (
    Card,
    CardType,
    GameState,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- Helpers ------------------------------------------------------------------


def _subject(name: str) -> Card:
    return Card(id=f"sub_{name.lower().replace(' ', '_')}", type=CardType.SUBJECT, name=name)


def _quant(op: str, n: int) -> Card:
    return Card(id=f"q_{op.lower()}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


def _noun(name: str) -> Card:
    return Card(id=f"n_{name.lower()}", type=CardType.NOUN, name=name)


def _op_mod(name: str) -> Card:
    return Card(id=f"mod_op_{name.lower()}", type=CardType.MODIFIER, name=name)


_GAIN_VP_1 = Card(id="eff.vp.gain.1", type=CardType.EFFECT, name="GAIN_VP:1")


def _state(*players: Player) -> GameState:
    return GameState(players=players, revealed_effect=_GAIN_VP_1)


def _player(pid: str, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=int(pid[1:]) if pid[1:].isdigit() else 0, chips=chips, vp=vp)


def _if_rule(
    *,
    subject: Card,
    quant: Card,
    noun: Card,
    subject_mods: tuple[Card, ...] = (),
    quant_mods: tuple[Card, ...] = (),
    noun_mods: tuple[Card, ...] = (),
) -> RuleBuilder:
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(
                name="SUBJECT",
                type=CardType.SUBJECT,
                filled_by=subject,
                modifiers=subject_mods,
            ),
            Slot(
                name="QUANT",
                type=CardType.MODIFIER,
                filled_by=quant,
                modifiers=quant_mods,
            ),
            Slot(
                name="NOUN",
                type=CardType.NOUN,
                filled_by=noun,
                modifiers=noun_mods,
            ),
        ),
    )


# --- Catalogue + predicate ----------------------------------------------------


def test_operator_modifier_names_match_adr_0004() -> None:
    assert OPERATOR_MODIFIER_NAMES == frozenset({"BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"})


def test_is_operator_modifier_recognises_each_kind() -> None:
    for name in ("BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"):
        assert is_operator_modifier(_op_mod(name)) is True


def test_is_operator_modifier_rejects_comparators_and_others() -> None:
    assert is_operator_modifier(_quant("GE", 5)) is False
    assert is_operator_modifier(_subject("p0")) is False
    assert is_operator_modifier(_noun("CHIPS")) is False


# --- Singular path stays byte-identical --------------------------------------


def test_singular_path_no_modifiers_unchanged() -> None:
    """Slots with empty ``modifiers`` round-trip through the M1.5 path."""
    state = _state(_player("p0", chips=20), _player("p1", chips=2))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 10),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0


# --- grammar.render_if_rule surfaces modifier tuples -------------------------


def test_render_if_rule_surfaces_modifier_tuples() -> None:
    sub_op = _op_mod("BUT")
    sub_rhs = _subject("THE WOUNDED")
    q_op = _op_mod("AT_LEAST")
    n_op = _op_mod("OR")
    n_rhs = _noun("VP")
    rule = _if_rule(
        subject=_subject("THE LEADER"),
        subject_mods=(sub_op, sub_rhs),
        quant=_quant("GT", 5),
        quant_mods=(q_op,),
        noun=_noun("CHIPS"),
        noun_mods=(n_op, n_rhs),
    )
    rendered = render_if_rule(rule)
    assert rendered.subject_modifiers == (sub_op, sub_rhs)
    assert rendered.quant_modifiers == (q_op,)
    assert rendered.noun_modifiers == (n_op, n_rhs)


def test_render_if_rule_empty_modifiers_default() -> None:
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    rendered = render_if_rule(rule)
    assert rendered.subject_modifiers == ()
    assert rendered.quant_modifiers == ()
    assert rendered.noun_modifiers == ()


# --- SUBJECT operator: BUT (set difference) ----------------------------------


def test_subject_but_subtracts_rhs_scope() -> None:
    """``LEADER BUT WOUNDED`` excludes WOUNDED holders from the LEADER set.

    ADR-0001: vp ties → all tied players hold LEADER. Here vp is all 0 so
    every player holds LEADER; min-chips holder is p2.
    """
    state = _state(
        _player("p0", chips=15),
        _player("p1", chips=12),
        _player("p2", chips=5),
        _player("p3", chips=8),
    )
    rule = _if_rule(
        subject=_subject("THE LEADER"),
        subject_mods=(_op_mod("BUT"), _subject("THE WOUNDED")),
        quant=_quant("GT", 5),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    # LEADER scope = {p0,p1,p2,p3}; minus WOUNDED {p2} → {p0,p1,p3}; all > 5.
    assert new.players[0].vp == 1
    assert new.players[1].vp == 1
    assert new.players[2].vp == 0  # excluded by BUT
    assert new.players[3].vp == 1


def test_subject_but_chains_left_to_right() -> None:
    """Two ``BUT``s on the same SUBJECT are additive (ADR-0004 chaining)."""
    state = _state(
        _player("p0", chips=10),
        _player("p1", chips=10),
        _player("p2", chips=10),
        _player("p3", chips=10),
    )
    rule = _if_rule(
        subject=_subject("THE LEADER"),
        subject_mods=(
            _op_mod("BUT"),
            _subject("p0"),
            _op_mod("BUT"),
            _subject("p1"),
        ),
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    # LEADER (vp tied: all) ∖ {p0} ∖ {p1} = {p2, p3}.
    assert new.players[0].vp == 0
    assert new.players[1].vp == 0
    assert new.players[2].vp == 1
    assert new.players[3].vp == 1


def test_subject_but_to_empty_is_no_op() -> None:
    """SUBJECT ∖ SUBJECT = ∅ → no scope → no effect (state unchanged)."""
    state = _state(_player("p0"), _player("p1"))
    rule = _if_rule(
        subject=_subject("p0"),
        subject_mods=(_op_mod("BUT"), _subject("p0")),
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    assert new == state


# --- SUBJECT operator: AND / OR (set union) ----------------------------------


def test_subject_and_unions_rhs() -> None:
    state = _state(_player("p0"), _player("p1"), _player("p2"))
    rule = _if_rule(
        subject=_subject("p0"),
        subject_mods=(_op_mod("AND"), _subject("p2")),
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0
    assert new.players[2].vp == 1


def test_subject_or_aliases_and_for_subject() -> None:
    """ADR-0004: ``OR`` on SUBJECT is set union — alias of ``AND``."""
    state = _state(_player("p0"), _player("p1"), _player("p2"))
    rule = _if_rule(
        subject=_subject("p1"),
        subject_mods=(_op_mod("OR"), _subject("p2")),
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 0
    assert new.players[1].vp == 1
    assert new.players[2].vp == 1


# --- NOUN operator: AND (sum) / OR (max) -------------------------------------


def test_noun_and_sums_reads() -> None:
    """``HAS GE 30 CHIPS AND VP`` reads chips + vp per player."""
    state = _state(_player("p0", chips=20, vp=5), _player("p1", chips=20, vp=2))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 25),
        noun=_noun("CHIPS"),
        noun_mods=(_op_mod("AND"), _noun("VP")),
    )
    new = resolve_if_rule(state, rule)
    # p0: 20 + 5 = 25 ≥ 25 → fires.
    assert new.players[0].vp == 6


def test_noun_or_takes_max() -> None:
    """``HAS GT 5 CHIPS OR VP`` checks max(chips, vp)."""
    p0 = _player("p0", chips=4, vp=10)
    state = _state(p0)
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GT", 5),
        noun=_noun("CHIPS"),
        noun_mods=(_op_mod("OR"), _noun("VP")),
    )
    new = resolve_if_rule(state, rule)
    # max(4, 10) = 10 > 5 → fires.
    assert new.players[0].vp == 11


def test_noun_or_max_under_threshold_does_not_fire() -> None:
    state = _state(_player("p0", chips=2, vp=1))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GT", 5),
        noun=_noun("CHIPS"),
        noun_mods=(_op_mod("OR"), _noun("VP")),
    )
    new = resolve_if_rule(state, rule)
    assert new == state


# --- QUANT operator: MORE_THAN / AT_LEAST ------------------------------------


def test_quant_more_than_strips_equality_from_ge() -> None:
    """``GE 10 MORE_THAN`` becomes ``GT 10`` (drops equality)."""
    state = _state(_player("p0", chips=10), _player("p1", chips=11))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 10),
        quant_mods=(_op_mod("MORE_THAN"),),
        noun=_noun("CHIPS"),
    )
    # Without MORE_THAN, p0 (chips=10) would satisfy GE 10. With MORE_THAN it's GT.
    assert resolve_if_rule(state, rule) == state

    rule2 = _if_rule(
        subject=_subject("p1"),
        quant=_quant("GE", 10),
        quant_mods=(_op_mod("MORE_THAN"),),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule2)
    # p1 (chips=11) > 10 → still fires under GT.
    assert new.players[1].vp == 1


def test_quant_at_least_adds_equality_to_gt() -> None:
    """``GT 5 AT_LEAST`` becomes ``GE 5`` (per ADR example 2)."""
    state = _state(_player("p0", chips=5))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GT", 5),
        quant_mods=(_op_mod("AT_LEAST"),),
        noun=_noun("CHIPS"),
    )
    # Without AT_LEAST: chips=5 fails GT 5. With AT_LEAST: GE 5 → satisfied.
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1


def test_quant_more_than_strips_equality_from_le() -> None:
    """``LE 5 MORE_THAN`` strips equality → ``LT 5``."""
    state = _state(_player("p0", chips=5), _player("p1", chips=4))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("LE", 5),
        quant_mods=(_op_mod("MORE_THAN"),),
        noun=_noun("CHIPS"),
    )
    # p0 chips=5 fails LT 5.
    assert resolve_if_rule(state, rule) == state
    rule2 = _if_rule(
        subject=_subject("p1"),
        quant=_quant("LE", 5),
        quant_mods=(_op_mod("MORE_THAN"),),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule2)
    assert new.players[1].vp == 1


def test_quant_at_least_adds_equality_to_lt() -> None:
    """``LT 5 AT_LEAST`` adds equality → ``LE 5``."""
    state = _state(_player("p0", chips=5))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("LT", 5),
        quant_mods=(_op_mod("AT_LEAST"),),
        noun=_noun("CHIPS"),
    )
    # Without AT_LEAST: chips=5 fails LT 5. With AT_LEAST: LE 5 → satisfied.
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1


def test_quant_modifiers_last_write_wins() -> None:
    """``GE 5 AT_LEAST MORE_THAN`` ends as ``GT 5`` (ADR example 4)."""
    state = _state(_player("p0", chips=5), _player("p1", chips=6))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 5),
        quant_mods=(_op_mod("AT_LEAST"), _op_mod("MORE_THAN")),
        noun=_noun("CHIPS"),
    )
    # Net op = GT. p0 chips=5 fails.
    assert resolve_if_rule(state, rule) == state
    rule2 = _if_rule(
        subject=_subject("p1"),
        quant=_quant("GE", 5),
        quant_mods=(_op_mod("AT_LEAST"), _op_mod("MORE_THAN")),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule2)
    assert new.players[1].vp == 1


def test_quant_modifiers_eq_unaffected() -> None:
    """``EQ`` has no strict/non-strict axis — both ops leave it alone."""
    state = _state(_player("p0", chips=7))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("EQ", 7),
        quant_mods=(_op_mod("MORE_THAN"), _op_mod("AT_LEAST")),
        noun=_noun("CHIPS"),
    )
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1


# --- Validation ---------------------------------------------------------------


def test_subject_operator_missing_rhs_raises() -> None:
    state = _state(_player("p0"))
    rule = _if_rule(
        subject=_subject("p0"),
        subject_mods=(_op_mod("BUT"),),  # RHS missing
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    with pytest.raises(ValueError, match="missing RHS"):
        resolve_if_rule(state, rule)


def test_unknown_subject_operator_raises() -> None:
    state = _state(_player("p0"))
    rule = _if_rule(
        subject=_subject("p0"),
        subject_mods=(_op_mod("MORE_THAN"), _subject("p0")),  # QUANT op on SUBJECT
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
    )
    with pytest.raises(ValueError, match="unexpected SUBJECT operator"):
        resolve_if_rule(state, rule)


def test_unknown_noun_operator_raises() -> None:
    state = _state(_player("p0"))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 0),
        noun=_noun("CHIPS"),
        noun_mods=(_op_mod("BUT"), _noun("VP")),  # SUBJECT op on NOUN
    )
    with pytest.raises(ValueError, match="unexpected NOUN operator"):
        resolve_if_rule(state, rule)


def test_unknown_quant_operator_raises() -> None:
    state = _state(_player("p0"))
    rule = _if_rule(
        subject=_subject("p0"),
        quant=_quant("GE", 0),
        quant_mods=(_op_mod("AND"),),  # SUBJECT op on QUANT
        noun=_noun("CHIPS"),
    )
    with pytest.raises(ValueError, match="unexpected QUANT operator"):
        resolve_if_rule(state, rule)

"""RUL-44: M2 polymorphic NOUN reads — `effects._evaluate_has` extension.

Per ``design/cards-inventory.md``'s M2 NOUN table the resolver evaluates a
``HAS [QUANT] [NOUN]`` rule by reading from these sources:

* ``CARDS``       → ``len(player.hand)``
* ``RULES``       → ``state.persistent_rules`` count where ``created_by == player.id``
* ``HITS``        → ``player.history.hits_taken_this_game`` (RUL-26 substrate)
* ``GIFTS``       → ``player.history.cards_given_this_game``
* ``ROUNDS``      → ``state.round_number`` (player-agnostic broadcast)
* ``BURN_TOKENS`` → ``player.status.burn``

These tests exercise each NOUN in isolation (correct field read), against
each comparator OP (truthy/falsy paths), at the inventory edges (empty hand,
no persistent rules, round 1), and through the full integration path
(``resolve_if_rule`` builds + scope-fires the IF rule).
"""

from __future__ import annotations

from rulso.effects import resolve_if_rule
from rulso.state import (
    Card,
    CardType,
    GameState,
    PersistentRule,
    Player,
    PlayerHistory,
    PlayerStatus,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- Helpers -----------------------------------------------------------------


def _subject(name: str) -> Card:
    return Card(id=f"sub_{name.lower().replace(' ', '_')}", type=CardType.SUBJECT, name=name)


def _quant(op: str, n: int) -> Card:
    return Card(id=f"q_{op}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


def _noun(name: str) -> Card:
    return Card(id=f"n_{name.lower()}", type=CardType.NOUN, name=name)


def _hand_card(idx: int) -> Card:
    return Card(id=f"h_{idx}", type=CardType.NOUN, name="CHIPS")


def _if_rule(subject: Card, quant: Card, noun: Card) -> RuleBuilder:
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=subject),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=quant),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=noun),
        ),
    )


def _persistent_if(created_by: str) -> PersistentRule:
    """A PersistentRule attributed to ``created_by``. Shape only — content
    irrelevant for ``noun.rules`` counting (``created_by`` is the read key).
    """
    return PersistentRule(
        kind=RuleKind.WHEN,
        rule=_if_rule(_subject("p0"), _quant("GE", 0), _noun("CHIPS")),
        created_round=1,
        created_by=created_by,
    )


# --- CARDS — len(player.hand) ------------------------------------------------


def test_noun_cards_reads_hand_length() -> None:
    p0 = Player(id="p0", seat=0, hand=(_hand_card(0), _hand_card(1), _hand_card(2)))
    state = GameState(players=(p0,))
    rule = _if_rule(_subject("p0"), _quant("EQ", 3), _noun("CARDS"))
    assert resolve_if_rule(state, rule).players[0].vp == 1


def test_noun_cards_empty_hand_reads_zero() -> None:
    """Empty hand → CARDS=0; comparator boundary at 0 must fire on EQ:0."""
    p0 = Player(id="p0", seat=0, hand=())
    state = GameState(players=(p0,))
    eq_zero = _if_rule(_subject("p0"), _quant("EQ", 0), _noun("CARDS"))
    assert resolve_if_rule(state, eq_zero).players[0].vp == 1
    gt_zero = _if_rule(_subject("p0"), _quant("GT", 0), _noun("CARDS"))
    assert resolve_if_rule(state, gt_zero) == state


def test_noun_cards_comparators_truthy_and_falsy() -> None:
    p0 = Player(id="p0", seat=0, hand=(_hand_card(0), _hand_card(1)))
    state = GameState(players=(p0,))
    # 2 cards: GE:2 fires; LT:2 doesn't; LT:5 does.
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("GE", 2), _noun("CARDS")))
        .players[0]
        .vp
        == 1
    )
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("LT", 2), _noun("CARDS"))) == state
    )
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("LT", 5), _noun("CARDS")))
        .players[0]
        .vp
        == 1
    )


# --- RULES — persistent rules created_by player ------------------------------


def test_noun_rules_counts_created_by_player() -> None:
    p0 = Player(id="p0", seat=0)
    p1 = Player(id="p1", seat=1)
    state = GameState(
        players=(p0, p1),
        persistent_rules=(
            _persistent_if("p0"),
            _persistent_if("p0"),
            _persistent_if("p1"),
        ),
    )
    # p0 has 2 persistent rules.
    rule_p0 = _if_rule(_subject("p0"), _quant("EQ", 2), _noun("RULES"))
    assert resolve_if_rule(state, rule_p0).players[0].vp == 1
    # p1 has 1 persistent rule.
    rule_p1 = _if_rule(_subject("p1"), _quant("EQ", 1), _noun("RULES"))
    assert resolve_if_rule(state, rule_p1).players[1].vp == 1


def test_noun_rules_no_persistent_rules_reads_zero() -> None:
    p0 = Player(id="p0", seat=0)
    state = GameState(players=(p0,), persistent_rules=())
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 0), _noun("RULES")))
        .players[0]
        .vp
        == 1
    )
    # Sanity: GT:0 fails — no rules.
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("GT", 0), _noun("RULES"))) == state
    )


# --- HITS — PlayerHistory.hits_taken_this_game -------------------------------


def test_noun_hits_reads_history_field() -> None:
    """``HITS`` resolves to ``hits_taken_this_game`` per RUL-26 substrate.

    The cards-inventory text uses a placeholder ``hits_this_round``; the
    actual state field is ``hits_taken_this_game`` (added by RUL-26 for
    exactly this NOUN). ``_noun_value`` reads the latter.
    """
    p0 = Player(
        id="p0",
        seat=0,
        history=PlayerHistory(hits_taken_this_game=4),
    )
    state = GameState(players=(p0,))
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 4), _noun("HITS")))
        .players[0]
        .vp
        == 1
    )
    assert resolve_if_rule(state, _if_rule(_subject("p0"), _quant("GE", 5), _noun("HITS"))) == state


def test_noun_hits_default_zero() -> None:
    p0 = Player(id="p0", seat=0)
    state = GameState(players=(p0,))
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 0), _noun("HITS")))
        .players[0]
        .vp
        == 1
    )


# --- GIFTS — PlayerHistory.cards_given_this_game -----------------------------


def test_noun_gifts_reads_history_field() -> None:
    p0 = Player(
        id="p0",
        seat=0,
        history=PlayerHistory(cards_given_this_game=3),
    )
    state = GameState(players=(p0,))
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("GE", 3), _noun("GIFTS")))
        .players[0]
        .vp
        == 1
    )
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("LT", 3), _noun("GIFTS"))) == state
    )


def test_noun_gifts_default_zero() -> None:
    p0 = Player(id="p0", seat=0)
    state = GameState(players=(p0,))
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 0), _noun("GIFTS")))
        .players[0]
        .vp
        == 1
    )


# --- ROUNDS — state.round_number (player-agnostic) ---------------------------


def test_noun_rounds_reads_state_round_number() -> None:
    p0 = Player(id="p0", seat=0)
    state = GameState(players=(p0,), round_number=7)
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 7), _noun("ROUNDS")))
        .players[0]
        .vp
        == 1
    )
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("LT", 5), _noun("ROUNDS"))) == state
    )


def test_noun_rounds_round_one_edge() -> None:
    """Inventory edge: round 1 reads as 1 (not 0)."""
    p0 = Player(id="p0", seat=0)
    state = GameState(players=(p0,), round_number=1)
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 1), _noun("ROUNDS")))
        .players[0]
        .vp
        == 1
    )


def test_noun_rounds_is_player_agnostic() -> None:
    """Every player sees the same round number — confirms broadcast read."""
    p0 = Player(id="p0", seat=0, vp=0)
    p1 = Player(id="p1", seat=1, vp=0)
    state = GameState(players=(p0, p1), round_number=5)
    rule_p0 = _if_rule(_subject("p0"), _quant("EQ", 5), _noun("ROUNDS"))
    rule_p1 = _if_rule(_subject("p1"), _quant("EQ", 5), _noun("ROUNDS"))
    assert resolve_if_rule(state, rule_p0).players[0].vp == 1
    assert resolve_if_rule(state, rule_p1).players[1].vp == 1


# --- BURN_TOKENS — PlayerStatus.burn -----------------------------------------


def test_noun_burn_tokens_reads_status_burn() -> None:
    p0 = Player(id="p0", seat=0, status=PlayerStatus(burn=2))
    state = GameState(players=(p0,))
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("GE", 2), _noun("BURN_TOKENS")))
        .players[0]
        .vp
        == 1
    )
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("LT", 2), _noun("BURN_TOKENS")))
        == state
    )


def test_noun_burn_tokens_default_zero() -> None:
    p0 = Player(id="p0", seat=0)
    state = GameState(players=(p0,))
    assert (
        resolve_if_rule(state, _if_rule(_subject("p0"), _quant("EQ", 0), _noun("BURN_TOKENS")))
        .players[0]
        .vp
        == 1
    )


# --- Cross-NOUN sanity: each NOUN dispatches to the right field --------------


def test_each_m2_noun_reads_distinct_fields() -> None:
    """All M2 NOUNs evaluate independently against the same player.

    Single player set up so each NOUN has a different value (3 cards, 1 rule,
    4 hits, 2 gifts, 7 rounds, 5 burn). Each rule that targets the matching
    EQ:N fires; the others must not.
    """
    p0 = Player(
        id="p0",
        seat=0,
        hand=(_hand_card(0), _hand_card(1), _hand_card(2)),
        status=PlayerStatus(burn=5),
        history=PlayerHistory(hits_taken_this_game=4, cards_given_this_game=2),
    )
    state = GameState(
        players=(p0,),
        round_number=7,
        persistent_rules=(_persistent_if("p0"),),
    )
    expectations = {
        "CARDS": 3,
        "RULES": 1,
        "HITS": 4,
        "GIFTS": 2,
        "ROUNDS": 7,
        "BURN_TOKENS": 5,
    }
    for noun_name, expected in expectations.items():
        rule_match = _if_rule(_subject("p0"), _quant("EQ", expected), _noun(noun_name))
        assert resolve_if_rule(state, rule_match).players[0].vp == 1, (
            f"NOUN {noun_name} should read as {expected}"
        )
        # The same rule with EQ on a non-matching value must not fire.
        rule_miss = _if_rule(_subject("p0"), _quant("EQ", expected + 1), _noun(noun_name))
        assert resolve_if_rule(state, rule_miss) == state, (
            f"NOUN {noun_name} EQ:{expected + 1} must not fire when value={expected}"
        )

"""MARKED-narrowing consumer for the EACH_PLAYER scope (RUL-60).

Per ``design/status-tokens.md`` "MARKED + non-MARKED + EACH PLAYER rule":

* ≥1 player holds MARKED at scope time → an iterative SUBJECT (EACH_PLAYER)
  narrows its candidate set to the MARKED holders only.
* 0 MARKED holders → the rule fires on the full candidate set (no narrowing).
* Non-iterative SUBJECTs (singular literal/label, existential ANYONE) ignore
  MARKED — MARKED is an EACH_PLAYER-only diversion.

The MARKED apply / decay path is already wired (RUL-40 + ``status.tick_resolve_end``);
this file pins the consumer-side narrowing in ``effects.resolve_if_rule``.
"""

from __future__ import annotations

from rulso.effects import resolve_if_rule
from rulso.state import (
    Card,
    CardType,
    GameState,
    Player,
    PlayerStatus,
    RuleBuilder,
    RuleKind,
    ScopeMode,
    Slot,
)

_GAIN_VP_1 = Card(id="eff.vp.gain.1", type=CardType.EFFECT, name="GAIN_VP:1")


def _subject(name: str, scope_mode: ScopeMode = "singular") -> Card:
    return Card(
        id=f"sub_{name.lower().replace(' ', '_')}",
        type=CardType.SUBJECT,
        name=name,
        scope_mode=scope_mode,
    )


def _quant(op: str, n: int) -> Card:
    return Card(id=f"q_{op}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}")


def _noun(name: str) -> Card:
    return Card(id=f"n_{name.lower()}", type=CardType.NOUN, name=name)


def _if_rule(subject: Card, quant: Card, noun: Card) -> RuleBuilder:
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=subject),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=quant),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=noun),
        ),
    )


def _player(pid: str, seat: int, *, chips: int = 50, vp: int = 0, marked: bool = False) -> Player:
    return Player(
        id=pid,
        seat=seat,
        chips=chips,
        vp=vp,
        status=PlayerStatus(marked=marked),
    )


def _seated_state(players: tuple[Player, ...], *, active_seat: int = 0) -> GameState:
    return GameState(players=players, active_seat=active_seat, revealed_effect=_GAIN_VP_1)


# --- iterative: ≥1 MARKED holder narrows scope --------------------------------


def test_iterative_narrows_to_marked_holders_when_any_marked() -> None:
    """All four players satisfy ``HAS GE 0 VP``; only p1 and p3 hold MARKED.
    EACH_PLAYER must fire only on the MARKED subset (+1 VP each); non-MARKED
    matchers are skipped entirely."""
    players = (
        _player("p0", 0, vp=0, marked=False),
        _player("p1", 1, vp=0, marked=True),
        _player("p2", 2, vp=0, marked=False),
        _player("p3", 3, vp=0, marked=True),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 0
    assert new.players[1].vp == 1
    assert new.players[2].vp == 0
    assert new.players[3].vp == 1


def test_iterative_narrows_to_single_marked_holder() -> None:
    """One MARKED holder → exactly one fire even when all players satisfy
    the HAS clause."""
    players = (
        _player("p0", 0, vp=0, marked=False),
        _player("p1", 1, vp=0, marked=False),
        _player("p2", 2, vp=0, marked=True),
        _player("p3", 3, vp=0, marked=False),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    assert (
        new.players[0].vp,
        new.players[1].vp,
        new.players[2].vp,
        new.players[3].vp,
    ) == (0, 0, 1, 0)


def test_iterative_marked_holder_failing_has_clause_does_not_fire() -> None:
    """MARKED only narrows the candidate set — the HAS clause still gates each
    fire. p1 is MARKED but does not satisfy ``HAS GE 10 CHIPS`` → no fire."""
    players = (
        _player("p0", 0, chips=20, marked=False),
        _player("p1", 1, chips=5, marked=True),
        _player("p2", 2, chips=20, marked=False),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    # Without narrowing, p0 and p2 would each gain +1 VP. With MARKED narrowing,
    # the candidate set is {p1}; p1 fails HAS so no fire — net state unchanged.
    assert new == state


# --- iterative: 0 MARKED holders falls back to full candidate set -------------


def test_iterative_no_marked_falls_back_to_all_players() -> None:
    """No MARKED holder → EACH_PLAYER behaves as the pre-RUL-60 path; every
    matching player fires."""
    players = (
        _player("p0", 0, chips=20),
        _player("p1", 1, chips=5),
        _player("p2", 2, chips=20),
        _player("p3", 3, chips=20),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("EACH_PLAYER", "iterative"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0
    assert new.players[2].vp == 1
    assert new.players[3].vp == 1


# --- non-iterative SUBJECTs ignore MARKED -------------------------------------


def test_existential_ignores_marked() -> None:
    """ANYONE (existential) fires once with the full satisfying subset.
    MARKED on p1 must not narrow the subset — p0, p1, p2 all qualify and all
    receive +1 VP."""
    players = (
        _player("p0", 0, chips=20, marked=False),
        _player("p1", 1, chips=20, marked=True),
        _player("p2", 2, chips=20, marked=False),
        _player("p3", 3, chips=5, marked=False),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("ANYONE", "existential"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 1
    assert new.players[2].vp == 1
    assert new.players[3].vp == 0


def test_singular_literal_ignores_marked() -> None:
    """Singular SUBJECT (literal player id) targets exactly that player.
    Another player being MARKED must not divert the fire."""
    players = (
        _player("p0", 0, chips=20, marked=False),
        _player("p1", 1, chips=20, marked=True),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("p0"), _quant("GE", 10), _noun("CHIPS"))
    new = resolve_if_rule(state, rule)
    assert new.players[0].vp == 1
    assert new.players[1].vp == 0


def test_singular_label_ignores_marked() -> None:
    """Singular SUBJECT (label lookup, here THE LEADER on p1 by VP) targets
    the label holder. A different player holding MARKED must not divert."""
    players = (
        _player("p0", 0, vp=0, marked=True),
        _player("p1", 1, vp=3, marked=False),
        _player("p2", 2, vp=1, marked=False),
    )
    state = _seated_state(players, active_seat=0)
    rule = _if_rule(_subject("THE LEADER"), _quant("GE", 0), _noun("VP"))
    new = resolve_if_rule(state, rule)
    # LEADER = p1 (highest VP); the GAIN_VP:1 effect lands on p1 only,
    # independent of p0's MARKED.
    assert new.players[0].vp == 0
    assert new.players[1].vp == 4
    assert new.players[2].vp == 1

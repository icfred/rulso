"""Effect dispatcher (RUL-39).

Covers the M2 effect-card dispatcher that replaces the M1.5 ``+1 VP`` stub:

* ``<KIND>[:<MAG>][@<TARGET_MOD>]`` parser for ``revealed_effect.name``.
* Built-in handlers — ``GAIN_CHIPS / LOSE_CHIPS / GAIN_VP / LOSE_VP / DRAW / NOOP``.
* ``register_effect_kind`` extension hook (last-wins).
* ``target_modifier`` rewrite rules (all four).
* Status-applying kinds raise ``NotImplementedError`` until RUL-40 lands.
* ``resolve_if_rule`` integrates the dispatcher end-to-end.
"""

from __future__ import annotations

import pytest

from rulso import effects
from rulso.effects import dispatch_effect, register_effect_kind, resolve_if_rule
from rulso.state import (
    Card,
    CardType,
    GameState,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- Helpers -----------------------------------------------------------------


def _player(pid: str, seat: int = 0, chips: int = 50, vp: int = 0) -> Player:
    return Player(id=pid, seat=seat, chips=chips, vp=vp)


def _effect(name: str) -> Card:
    return Card(id=f"eff.test.{name}", type=CardType.EFFECT, name=name)


def _state(*players: Player, revealed: Card | None = None) -> GameState:
    return GameState(players=players, revealed_effect=revealed)


def _if_rule(subject: str, op: str, n: int, noun: str) -> RuleBuilder:
    return RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(
                name="SUBJECT",
                type=CardType.SUBJECT,
                filled_by=Card(id=f"sub_{subject}", type=CardType.SUBJECT, name=subject),
            ),
            Slot(
                name="QUANT",
                type=CardType.MODIFIER,
                filled_by=Card(id=f"q_{op}_{n}", type=CardType.MODIFIER, name=f"{op}:{n}"),
            ),
            Slot(
                name="NOUN",
                type=CardType.NOUN,
                filled_by=Card(id=f"n_{noun}", type=CardType.NOUN, name=noun),
            ),
        ),
    )


@pytest.fixture(autouse=True)
def _restore_registry() -> None:
    """Snapshot/restore the module-level effect registry for each test.

    Tests that call :func:`register_effect_kind` to install custom handlers
    are isolated from siblings (and from the built-ins they may override).
    """
    snapshot = dict(effects._EFFECT_HANDLERS)
    yield
    effects._EFFECT_HANDLERS.clear()
    effects._EFFECT_HANDLERS.update(snapshot)


# --- Parser ------------------------------------------------------------------


def test_parser_kind_only_defaults_magnitude_one() -> None:
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].chips == 51


def test_parser_kind_with_magnitude() -> None:
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS:7"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].chips == 57


def test_parser_kind_with_target_modifier_only() -> None:
    """KIND@MOD sans :MAG defaults magnitude to 1 with the modifier wired."""
    state = _state(
        _player("p0"), _player("p1", seat=1), revealed=_effect("GAIN_CHIPS@EXCEPT_MATCHED")
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    # @EXCEPT_MATCHED rewrites scope: p0 (matched) is excluded; p1 receives.
    assert out.players[0].chips == 50
    assert out.players[1].chips == 51


def test_parser_kind_magnitude_and_modifier() -> None:
    state = _state(
        _player("p0"),
        _player("p1", seat=1),
        revealed=_effect("GAIN_CHIPS:5@EXCEPT_MATCHED"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].chips == 50
    assert out.players[1].chips == 55


def test_parser_rejects_empty_kind() -> None:
    state = _state(_player("p0"), revealed=_effect(":5"))
    with pytest.raises(ValueError, match="empty KIND"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


def test_parser_rejects_empty_magnitude() -> None:
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS:"))
    with pytest.raises(ValueError, match="no magnitude"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


def test_parser_rejects_non_integer_magnitude() -> None:
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS:abc"))
    with pytest.raises(ValueError, match="non-integer magnitude"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


def test_parser_rejects_negative_magnitude() -> None:
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS:-1"))
    with pytest.raises(ValueError, match="negative magnitude"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


def test_parser_rejects_unknown_target_token() -> None:
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS@UNHEARD"))
    with pytest.raises(ValueError, match="unknown target token"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


# --- dispatch_effect — early-return paths -----------------------------------


def test_dispatch_returns_state_when_revealed_effect_is_none() -> None:
    state = _state(_player("p0"))
    out = dispatch_effect(state, None, frozenset({"p0"}))
    assert out is state


def test_dispatch_returns_state_when_targets_resolve_empty() -> None:
    """``EXCEPT_MATCHED`` with every player matched → empty target set → no-op."""
    state = _state(_player("p0"), revealed=_effect("GAIN_CHIPS:5@EXCEPT_MATCHED"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out == state


def test_dispatch_unknown_kind_raises() -> None:
    state = _state(_player("p0"), revealed=_effect("UNKNOWN_KIND"))
    with pytest.raises(ValueError, match="unknown effect kind"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


# --- Built-in handlers -------------------------------------------------------


def test_gain_chips_adds_magnitude_to_each_target() -> None:
    state = _state(
        _player("p0", chips=10), _player("p1", seat=1, chips=10), revealed=_effect("GAIN_CHIPS:3")
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0", "p1"}))
    assert out.players[0].chips == 13
    assert out.players[1].chips == 13


def test_lose_chips_subtracts_magnitude_floored_at_zero() -> None:
    state = _state(_player("p0", chips=2), revealed=_effect("LOSE_CHIPS:5"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].chips == 0  # floor


def test_gain_vp_adds_magnitude_to_each_target() -> None:
    state = _state(_player("p0", vp=1), revealed=_effect("GAIN_VP:2"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].vp == 3


def test_lose_vp_subtracts_magnitude_floored_at_zero() -> None:
    state = _state(_player("p0", vp=1), revealed=_effect("LOSE_VP:5"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].vp == 0  # floor


def test_noop_returns_state_unchanged() -> None:
    state = _state(_player("p0"), revealed=_effect("NOOP"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out == state


def test_draw_appends_cards_from_deck_top() -> None:
    deck = (
        Card(id="c1", type=CardType.NOUN, name="CHIPS"),
        Card(id="c2", type=CardType.NOUN, name="VP"),
        Card(id="c3", type=CardType.NOUN, name="CHIPS"),
    )
    state = GameState(
        players=(_player("p0"),),
        deck=deck,
        revealed_effect=_effect("DRAW:2"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    # Top of deck = end of tuple (mirrors rules._refill_hands' deck.pop()).
    assert tuple(c.id for c in out.players[0].hand) == ("c3", "c2")
    assert tuple(c.id for c in out.deck) == ("c1",)


def test_draw_handles_deck_empty_short_draw() -> None:
    """DRAW:5 against a deck of 1 yields a short draw, never raises."""
    deck = (Card(id="c1", type=CardType.NOUN, name="CHIPS"),)
    state = GameState(players=(_player("p0"),), deck=deck, revealed_effect=_effect("DRAW:5"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert len(out.players[0].hand) == 1
    assert out.deck == ()


def test_draw_zero_magnitude_is_noop() -> None:
    state = GameState(players=(_player("p0"),), revealed_effect=_effect("DRAW:0"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out is state


# --- target_modifier resolution ---------------------------------------------


def test_target_mod_all_matched_default() -> None:
    state = _state(_player("p0"), _player("p1", seat=1), revealed=_effect("GAIN_VP:1"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].vp == 1
    assert out.players[1].vp == 0


def test_target_mod_except_matched_inverts_scope() -> None:
    state = _state(
        _player("p0"),
        _player("p1", seat=1),
        _player("p2", seat=2),
        revealed=_effect("GAIN_VP:1@EXCEPT_MATCHED"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].vp == 0
    assert out.players[1].vp == 1
    assert out.players[2].vp == 1


def test_target_mod_active_seat_only_overrides_match_set() -> None:
    state = GameState(
        players=(_player("p0"), _player("p1", seat=1)),
        active_seat=1,
        revealed_effect=_effect("GAIN_VP:1@ACTIVE_SEAT"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].vp == 0
    assert out.players[1].vp == 1


def test_target_mod_dealer_only_overrides_match_set() -> None:
    state = GameState(
        players=(_player("p0"), _player("p1", seat=1)),
        dealer_seat=1,
        revealed_effect=_effect("GAIN_VP:1@DEALER"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].vp == 0
    assert out.players[1].vp == 1


# --- Status / clear unregistered kinds --------------------------------------
# RUL-40 registered handlers for the M2 starter status kinds (APPLY_BURN,
# CLEAR_BURN, APPLY_MUTE, APPLY_BLESSED, APPLY_MARKED, APPLY_CHAINED,
# CLEAR_CHAINED) — those are exercised in test_status.py. The kinds without
# starter cards (per design/status-tokens.md "M2 starter subset") still hit
# the dispatcher's pending-stub raise below.


@pytest.mark.parametrize("name", ["CLEAR_MUTE", "CLEAR_BLESSED", "CLEAR_MARKED"])
def test_unregistered_status_clear_kinds_raise(name: str) -> None:
    state = _state(_player("p0"), revealed=_effect(name))
    with pytest.raises(NotImplementedError, match="M2 Phase 3 E"):
        dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))


# --- register_effect_kind ----------------------------------------------------


def test_register_effect_kind_installs_handler() -> None:
    captured: dict[str, object] = {}

    def fake(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
        captured["targets"] = targets
        captured["magnitude"] = magnitude
        return state.model_copy(update={"round_number": 99})

    register_effect_kind("APPLY_BURN", fake)
    state = _state(_player("p0"), revealed=_effect("APPLY_BURN:3"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.round_number == 99
    assert captured == {"targets": frozenset({"p0"}), "magnitude": 3}


def test_register_effect_kind_last_write_wins() -> None:
    register_effect_kind(
        "GAIN_VP",
        lambda s, t, m: s.model_copy(update={"round_number": 1}),
    )
    register_effect_kind(
        "GAIN_VP",
        lambda s, t, m: s.model_copy(update={"round_number": 2}),
    )
    state = _state(_player("p0"), revealed=_effect("GAIN_VP:1"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.round_number == 2


# --- resolve_if_rule integration --------------------------------------------


def test_resolve_if_rule_dispatches_revealed_effect() -> None:
    """End-to-end: rule matches → dispatcher applies the round's effect."""
    state = _state(_player("p0", chips=10), revealed=_effect("GAIN_CHIPS:5"))
    rule = _if_rule("p0", "GE", 0, "CHIPS")
    out = resolve_if_rule(state, rule)
    assert out.players[0].chips == 15
    assert out.players[0].vp == 0  # GAIN_CHIPS, not GAIN_VP


def test_resolve_if_rule_no_match_skips_dispatch() -> None:
    state = _state(_player("p0", chips=10), revealed=_effect("GAIN_CHIPS:5"))
    rule = _if_rule("p0", "GE", 100, "CHIPS")
    out = resolve_if_rule(state, rule)
    assert out == state  # HAS-false → no dispatch


def test_resolve_if_rule_with_no_revealed_effect_is_noop_on_match() -> None:
    """``revealed_effect=None`` (no card drawn) → dispatcher returns state unchanged."""
    state = GameState(players=(_player("p0", chips=10),))
    rule = _if_rule("p0", "GE", 0, "CHIPS")
    out = resolve_if_rule(state, rule)
    assert out is state

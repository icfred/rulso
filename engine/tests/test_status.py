"""Status apply / clear / decay primitives (RUL-40).

Covers:

* Per-token apply / clear primitives (counter for BURN, idempotent toggles
  for MUTE / BLESSED / MARKED / CHAINED).
* ``tick_round_start`` — BURN drains chips, MUTE clears, BURN tokens persist.
* ``tick_resolve_end`` — MARKED clears, other tokens unchanged.
* ``consume_blessed_or_else`` — BLESSED cancels the next chip-loss and clears.
* Effect-handler integration through ``effects.dispatch_effect`` for the 7
  M2 starter kinds (RUL-30 ``status-tokens.md`` "M2 starter subset" table).
* Round-flow integration: ``rules.enter_round_start`` step 2 ticks BURN/MUTE
  via ``status.tick_round_start``; ``rules.enter_resolve`` step 10 clears
  MARKED via ``status.tick_resolve_end``.
"""

from __future__ import annotations

from rulso import status
from rulso.effects import dispatch_effect
from rulso.state import (
    BURN_TICK,
    Card,
    CardType,
    GameState,
    Player,
    PlayerStatus,
)

# --- Helpers -----------------------------------------------------------------


def _player(
    pid: str = "p0",
    seat: int = 0,
    chips: int = 50,
    *,
    burn: int = 0,
    mute: bool = False,
    blessed: bool = False,
    marked: bool = False,
    chained: bool = False,
) -> Player:
    return Player(
        id=pid,
        seat=seat,
        chips=chips,
        status=PlayerStatus(burn=burn, mute=mute, blessed=blessed, marked=marked, chained=chained),
    )


def _effect(name: str) -> Card:
    return Card(id=f"eff.test.{name.lower()}", type=CardType.EFFECT, name=name)


def _state_with(*players: Player, revealed: Card | None = None) -> GameState:
    return GameState(players=players, revealed_effect=revealed)


# --- apply_burn (counter) ---------------------------------------------------


def test_apply_burn_increments_counter() -> None:
    p = status.apply_burn(_player(burn=2), 3)
    assert p.status.burn == 5


def test_apply_burn_default_magnitude_is_one() -> None:
    p = status.apply_burn(_player(burn=0))
    assert p.status.burn == 1


def test_apply_burn_does_not_mutate_other_status_fields() -> None:
    p = status.apply_burn(_player(burn=1, mute=True, marked=True), 1)
    assert p.status.burn == 2
    assert p.status.mute is True
    assert p.status.marked is True


# --- apply toggles (idempotent) ---------------------------------------------


def test_apply_mute_sets_flag() -> None:
    p = status.apply_mute(_player(mute=False))
    assert p.status.mute is True


def test_apply_mute_idempotent_when_held() -> None:
    initial = _player(mute=True)
    p = status.apply_mute(initial)
    assert p is initial


def test_apply_blessed_sets_flag() -> None:
    p = status.apply_blessed(_player())
    assert p.status.blessed is True


def test_apply_blessed_idempotent_when_held() -> None:
    initial = _player(blessed=True)
    assert status.apply_blessed(initial) is initial


def test_apply_marked_sets_flag() -> None:
    p = status.apply_marked(_player())
    assert p.status.marked is True


def test_apply_marked_idempotent_when_held() -> None:
    initial = _player(marked=True)
    assert status.apply_marked(initial) is initial


def test_apply_chained_sets_flag() -> None:
    p = status.apply_chained(_player())
    assert p.status.chained is True


def test_apply_chained_idempotent_when_held() -> None:
    initial = _player(chained=True)
    assert status.apply_chained(initial) is initial


# --- clear primitives -------------------------------------------------------


def test_clear_burn_zeroes_counter() -> None:
    p = status.clear_burn(_player(burn=3))
    assert p.status.burn == 0


def test_clear_burn_noop_when_zero() -> None:
    initial = _player(burn=0)
    assert status.clear_burn(initial) is initial


def test_clear_chained_resets_flag() -> None:
    p = status.clear_chained(_player(chained=True))
    assert p.status.chained is False


def test_clear_chained_noop_when_clear() -> None:
    initial = _player(chained=False)
    assert status.clear_chained(initial) is initial


# --- tick_round_start (BURN drain + MUTE clear) -----------------------------


def test_tick_round_start_drains_chips_per_burn_token() -> None:
    p = status.tick_round_start(_player(chips=50, burn=2))
    assert p.chips == 50 - BURN_TICK * 2


def test_tick_round_start_floors_chips_at_zero() -> None:
    p = status.tick_round_start(_player(chips=3, burn=2))
    assert p.chips == 0


def test_tick_round_start_persists_burn_tokens() -> None:
    p = status.tick_round_start(_player(chips=50, burn=2))
    assert p.status.burn == 2  # tokens persist; only chips tick


def test_tick_round_start_clears_mute() -> None:
    p = status.tick_round_start(_player(mute=True))
    assert p.status.mute is False


def test_tick_round_start_does_not_touch_other_tokens() -> None:
    p = status.tick_round_start(_player(blessed=True, marked=True, chained=True))
    assert p.status.blessed is True
    assert p.status.marked is True
    assert p.status.chained is True


# --- tick_resolve_end (MARKED clear) ----------------------------------------


def test_tick_resolve_end_clears_marked() -> None:
    p = status.tick_resolve_end(_player(marked=True))
    assert p.status.marked is False


def test_tick_resolve_end_noop_when_unmarked() -> None:
    initial = _player(marked=False)
    assert status.tick_resolve_end(initial) is initial


def test_tick_resolve_end_does_not_touch_other_tokens() -> None:
    p = status.tick_resolve_end(_player(burn=2, mute=True, blessed=True, chained=True, marked=True))
    assert p.status.burn == 2
    assert p.status.mute is True
    assert p.status.blessed is True
    assert p.status.chained is True
    assert p.status.marked is False


# --- consume_blessed_or_else ------------------------------------------------


def test_consume_blessed_cancels_loss_and_clears_token() -> None:
    p = status.consume_blessed_or_else(_player(chips=50, blessed=True), 7)
    assert p.chips == 50  # loss cancelled
    assert p.status.blessed is False


def test_consume_blessed_or_else_applies_loss_when_unblessed() -> None:
    p = status.consume_blessed_or_else(_player(chips=50, blessed=False), 7)
    assert p.chips == 43


def test_consume_blessed_or_else_floors_loss_at_zero() -> None:
    p = status.consume_blessed_or_else(_player(chips=3, blessed=False), 7)
    assert p.chips == 0


# --- Effect-handler integration via dispatcher ------------------------------


def test_dispatch_apply_burn_routes_to_status_handler() -> None:
    """Per the hand-over: dispatch eff.burn.apply.1 via D, verify burn=1 on target."""
    state = _state_with(_player("p0"), _player("p1", seat=1), revealed=_effect("APPLY_BURN:1"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.burn == 1
    assert out.players[1].status.burn == 0


def test_dispatch_apply_burn_stacks_with_existing_count() -> None:
    state = _state_with(_player("p0", burn=2), revealed=_effect("APPLY_BURN:3"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.burn == 5


def test_dispatch_clear_burn_zeroes_counter() -> None:
    state = _state_with(_player("p0", burn=4), revealed=_effect("CLEAR_BURN:1"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.burn == 0


def test_dispatch_apply_mute_sets_toggle() -> None:
    state = _state_with(_player("p0"), revealed=_effect("APPLY_MUTE"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.mute is True


def test_dispatch_apply_blessed_sets_toggle() -> None:
    state = _state_with(_player("p0"), revealed=_effect("APPLY_BLESSED"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.blessed is True


def test_dispatch_apply_marked_sets_toggle() -> None:
    state = _state_with(_player("p0"), revealed=_effect("APPLY_MARKED"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.marked is True


def test_dispatch_apply_chained_sets_toggle() -> None:
    state = _state_with(_player("p0"), revealed=_effect("APPLY_CHAINED"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.chained is True


def test_dispatch_clear_chained_resets_toggle() -> None:
    state = _state_with(_player("p0", chained=True), revealed=_effect("CLEAR_CHAINED"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.chained is False


def test_dispatch_yaml_loaded_marked_apply_card_end_to_end() -> None:
    """The yaml-loaded ``eff.marked.apply`` card dispatches MARKED on its target.

    Pulls the card from :func:`rulso.cards.load_effect_cards` rather than
    hand-building it, proving the cards.yaml → dispatcher round-trip works
    for the RUL-61 additions.
    """
    from rulso.cards import load_effect_cards

    by_id = {c.id: c for c in load_effect_cards()}
    revealed = by_id["eff.marked.apply"]
    state = _state_with(_player("p0"), _player("p1", seat=1), revealed=revealed)
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.marked is True
    assert out.players[1].status.marked is False


def test_dispatch_yaml_loaded_chained_clear_card_end_to_end() -> None:
    """The yaml-loaded ``eff.chained.clear`` card dispatches CHAINED removal."""
    from rulso.cards import load_effect_cards

    by_id = {c.id: c for c in load_effect_cards()}
    revealed = by_id["eff.chained.clear"]
    state = _state_with(_player("p0", chained=True), revealed=revealed)
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.chained is False


def test_dispatch_apply_burn_with_target_modifier_inverts_scope() -> None:
    """``@EXCEPT_MATCHED`` rewrites the target set before the handler runs."""
    state = _state_with(
        _player("p0"),
        _player("p1", seat=1),
        revealed=_effect("APPLY_BURN:1@EXCEPT_MATCHED"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].status.burn == 0
    assert out.players[1].status.burn == 1


def test_dispatch_apply_marked_to_multiple_targets() -> None:
    """MARKED is the only M2 starter applier with payload-defined multi-target."""
    state = _state_with(
        _player("p0"),
        _player("p1", seat=1),
        _player("p2", seat=2),
        revealed=_effect("APPLY_MARKED"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0", "p1"}))
    assert out.players[0].status.marked is True
    assert out.players[1].status.marked is True
    assert out.players[2].status.marked is False


# --- Round-flow integration -------------------------------------------------


def test_enter_round_start_ticks_burn_and_mute_via_status_module() -> None:
    """``rules.enter_round_start`` step 2 routes through ``status.tick_round_start``."""
    from rulso.rules import advance_phase, start_game

    state = start_game()
    burned = state.players[0].model_copy(
        update={
            "chips": 30,
            # blessed deliberately False — RUL-49 routes the BURN tick through
            # ``consume_blessed_or_else``, so blessed=True would be consumed
            # here. Cover that path in ``test_tick_round_start_blessed_*``.
            "status": PlayerStatus(burn=2, mute=True, blessed=False, marked=True, chained=True),
        }
    )
    state = state.model_copy(update={"players": (burned,) + state.players[1:]})
    state = advance_phase(state)
    p0 = state.players[0]
    assert p0.chips == 30 - BURN_TICK * 2
    assert p0.status.burn == 2  # persists
    assert p0.status.mute is False  # one-round clear
    # tick_round_start leaves marked / chained alone at this site.
    assert p0.status.marked is True
    assert p0.status.chained is True


def test_enter_resolve_clears_marked_via_status_module() -> None:
    """``rules.enter_resolve`` step 10 routes through ``status.tick_resolve_end``."""
    import random

    from rulso.rules import enter_resolve, start_game
    from rulso.state import (
        Phase,
        Play,
        RuleBuilder,
        RuleKind,
        Slot,
    )

    state = start_game()
    sub = Card(id="sub_p0", type=CardType.SUBJECT, name="p0")
    quant = Card(id="q_ge_0", type=CardType.MODIFIER, name="GE:0")
    noun = Card(id="n_chips", type=CardType.NOUN, name="CHIPS")
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(name="SUBJECT", type=CardType.SUBJECT, filled_by=sub),
            Slot(name="QUANT", type=CardType.MODIFIER, filled_by=quant),
            Slot(name="NOUN", type=CardType.NOUN, filled_by=noun),
        ),
        plays=(Play(player_id="p0", card=sub, slot="SUBJECT"),),
    )
    marked_p0 = state.players[0].model_copy(
        update={
            "status": PlayerStatus(burn=1, mute=True, blessed=True, marked=True, chained=True),
        }
    )
    state = state.model_copy(
        update={
            "players": (marked_p0,) + state.players[1:],
            "phase": Phase.RESOLVE,
            "active_rule": rule,
            # NOOP keeps the resolver pure for this test (we only care about
            # the step-10 tick here).
            "revealed_effect": Card(id="eff.noop", type=CardType.EFFECT, name="NOOP"),
        }
    )
    state = enter_resolve(state, rng=random.Random(0))
    p0 = state.players[0]
    # MARKED cleared at step 10. Other tokens untouched at this step.
    assert p0.status.marked is False
    assert p0.status.burn == 1
    assert p0.status.mute is True
    assert p0.status.blessed is True
    assert p0.status.chained is True


# --- RUL-49: BLESSED + chip-loss wiring -------------------------------------


def test_dispatch_lose_chips_cancelled_by_blessed_then_applies_after_clear() -> None:
    """BLESSED cancels the first LOSE_CHIPS, clears, second LOSE_CHIPS lands."""
    state = _state_with(_player("p0", chips=50, blessed=True), revealed=_effect("LOSE_CHIPS:5"))
    state = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert state.players[0].chips == 50  # first loss cancelled
    assert state.players[0].status.blessed is False  # token consumed
    state = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert state.players[0].chips == 45  # second loss lands
    assert state.players[0].status.blessed is False


def test_dispatch_lose_chips_blessed_consumed_independently_per_target() -> None:
    """Multi-target LOSE_CHIPS: only blessed targets cancel; others lose chips."""
    state = _state_with(
        _player("p0", chips=50, blessed=True),
        _player("p1", seat=1, chips=50, blessed=False),
        revealed=_effect("LOSE_CHIPS:5"),
    )
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0", "p1"}))
    assert out.players[0].chips == 50  # blessed cancelled
    assert out.players[0].status.blessed is False
    assert out.players[1].chips == 45  # unblessed lost chips
    assert out.players[1].status.blessed is False


def test_dispatch_lose_chips_zero_magnitude_does_not_consume_blessed() -> None:
    """``LOSE_CHIPS:0`` is a no-op — must not silently consume a held BLESSED."""
    state = _state_with(_player("p0", chips=50, blessed=True), revealed=_effect("LOSE_CHIPS:0"))
    out = dispatch_effect(state, state.revealed_effect, frozenset({"p0"}))
    assert out.players[0].chips == 50
    assert out.players[0].status.blessed is True


def test_tick_round_start_blessed_cancels_burn_drain_and_clears() -> None:
    """Round 1: BLESSED cancels the BURN tick chip-drain; BURN tokens persist."""
    p = status.tick_round_start(_player(chips=50, burn=2, blessed=True))
    assert p.chips == 50  # drain cancelled
    assert p.status.blessed is False  # token consumed
    assert p.status.burn == 2  # BURN tokens persist


def test_tick_round_start_blessed_then_unblessed_drains_next_round() -> None:
    """Round 1's drain is cancelled by BLESSED; round 2's drain applies."""
    p = _player(chips=50, burn=2, blessed=True)
    p = status.tick_round_start(p)
    assert p.chips == 50
    assert p.status.blessed is False
    p = status.tick_round_start(p)
    assert p.chips == 50 - BURN_TICK * 2  # round 2 drains normally
    assert p.status.burn == 2


def test_tick_round_start_blessed_with_zero_burn_keeps_blessed() -> None:
    """No BURN → no drain → BLESSED is not a 'chip-loss event' here. Token stays."""
    p = status.tick_round_start(_player(chips=50, burn=0, blessed=True))
    assert p.chips == 50
    assert p.status.blessed is True  # untouched (no chip-loss to cancel)


def test_tick_round_start_blessed_clears_mute_alongside_drain_cancellation() -> None:
    """BLESSED cancels the BURN drain; MUTE clear still fires (separate decay)."""
    p = status.tick_round_start(_player(chips=50, burn=1, blessed=True, mute=True))
    assert p.chips == 50
    assert p.status.blessed is False
    assert p.status.mute is False  # MUTE decays regardless of BLESSED


def test_tick_round_start_multi_player_blessed_consumed_independently() -> None:
    """ANYONE/EACH-style fan-out: each player's BLESSED is consumed independently."""
    players = (
        _player("p0", chips=50, burn=2, blessed=True),  # cancelled, blessed clears
        _player("p1", seat=1, chips=50, burn=0, blessed=True),  # no drain, blessed stays
        _player("p2", seat=2, chips=50, burn=2, blessed=False),  # drain applies
        _player("p3", seat=3, chips=50, burn=0, blessed=False),  # no-op
    )
    ticked = tuple(status.tick_round_start(p) for p in players)
    assert (
        ticked[0].chips == 50 and ticked[0].status.blessed is False and ticked[0].status.burn == 2
    )
    assert ticked[1].chips == 50 and ticked[1].status.blessed is True
    assert ticked[2].chips == 50 - BURN_TICK * 2 and ticked[2].status.blessed is False
    assert ticked[3].chips == 50 and ticked[3].status.blessed is False

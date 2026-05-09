"""Round-flow phase machine.

Pure-function transitions over ``GameState``. Implements the round flow defined
in ``design/state.md`` for the M1 milestone. Shop, persistent-rule WHILE tick,
joker attachment and effect application are stubbed — see
``docs/engine/round-flow.md``.

All functions return a new ``GameState``; the input state is never mutated.
"""

from __future__ import annotations

from rulso import labels
from rulso.state import (
    BURN_TICK,
    PLAYER_COUNT,
    VP_TO_WIN,
    Card,
    CardType,
    GameState,
    Phase,
    Play,
    Player,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- M1 stub rule shape -----------------------------------------------------
# Real card content lands with cards.yaml; until then the round flow uses a
# fixed 4-slot template. Slot 0 is filled by the dealer in round_start; slots
# 1-3 are filled during build by the other three players. The dealer's own
# build turn (the 4th tick) is therefore a no-op pass under the M1 stub.
_M1_RULE_SLOT_DEFS: tuple[tuple[str, CardType], ...] = (
    ("subject", CardType.SUBJECT),
    ("noun", CardType.NOUN),
    ("modifier", CardType.MODIFIER),
    ("noun_2", CardType.NOUN),
)
_M1_DEALER_FRAGMENT: Card = Card(
    id="m1_stub_dealer_subject",
    type=CardType.SUBJECT,
    name="ANYONE",
)
_M1_EFFECT_CARD: Card = Card(
    id="m1_stub_effect",
    type=CardType.MODIFIER,
    name="EFFECT",
)


# --- Public entry points ----------------------------------------------------


def start_game(seed: int = 0) -> GameState:
    """Initialize a fresh 4-player game.

    Returns a state at ``phase=ROUND_START`` with ``round_number=0`` and
    ``dealer_seat=0``. Hands and decks are empty (M1 stub: deck and card
    distribution land in a later ticket). ``seed`` is accepted for API stability
    but unused in M1 because there is no shuffling yet.
    """
    del seed  # M1: nothing to shuffle yet.
    players = tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT))
    return GameState(
        phase=Phase.ROUND_START,
        round_number=0,
        dealer_seat=0,
        active_seat=0,
        players=players,
    )


def advance_phase(state: GameState) -> GameState:
    """Advance one logical step based on the current phase.

    ``BUILD`` ticks model a forced-pass turn (no card played). To play a card
    during build, call :func:`play_card` directly.
    """
    phase = state.phase
    if phase is Phase.LOBBY:
        return enter_round_start(state)
    if phase is Phase.ROUND_START:
        return enter_round_start(state)
    if phase is Phase.BUILD:
        return _build_tick(state)
    if phase is Phase.RESOLVE:
        return enter_resolve(state)
    if phase is Phase.SHOP:
        raise NotImplementedError("M2: shop phase")
    if phase is Phase.END:
        return state
    raise ValueError(f"unknown phase {phase!r}")


def enter_round_start(state: GameState) -> GameState:
    """Run round_start steps 1-8 from ``design/state.md`` atomically.

    Ends in ``phase=BUILD`` with the dealer's first slot pre-filled.
    """
    new_round = state.round_number + 1
    # Step 2: BURN tick + MUTE expiry.
    players = tuple(_apply_burn_tick(p) for p in state.players)
    # Step 3: recompute floating labels (ADR-0001 — computed-not-stored).
    # M1 consumers: none directly here (no WHILE rules yet, and the M1
    # resolver isn't wired into enter_resolve). The recompute is preserved
    # as the canonical design step 3 hook. The resolver itself takes labels
    # as a transient parameter via effects.resolve_if_rule(state, rule,
    # labels=...); see docs/engine/labels.md.
    labels.recompute_labels(state.model_copy(update={"players": players}))
    # Step 4: WHILE-rule tick — M1 has no persistent rules; guard the path.
    if state.persistent_rules:
        raise NotImplementedError("M2: persistent rule WHILE tick")
    # Step 5: shop check — bypassed in M1. See docs/engine/round-flow.md.
    # Step 6: reveal effect card.
    revealed_effect = _M1_EFFECT_CARD
    # Step 7: dealer plays the condition template + slot 0.
    dealer = players[state.dealer_seat]
    slots = tuple(
        Slot(
            name=name,
            type=type_,
            filled_by=_M1_DEALER_FRAGMENT if i == 0 else None,
        )
        for i, (name, type_) in enumerate(_M1_RULE_SLOT_DEFS)
    )
    first_play = Play(
        player_id=dealer.id,
        card=_M1_DEALER_FRAGMENT,
        slot=slots[0].name,
    )
    active_rule = RuleBuilder(
        template=RuleKind.IF,
        slots=slots,
        plays=(first_play,),
    )
    primed = state.model_copy(
        update={
            "round_number": new_round,
            "players": players,
            "phase": Phase.ROUND_START,
            "revealed_effect": revealed_effect,
            "active_rule": active_rule,
            "build_turns_taken": 0,
        }
    )
    # Step 8: transition to BUILD.
    return enter_build(primed)


def enter_build(state: GameState) -> GameState:
    """Transition to BUILD with ``active_seat = (dealer + 1) % PLAYER_COUNT``."""
    return state.model_copy(
        update={
            "phase": Phase.BUILD,
            "active_seat": (state.dealer_seat + 1) % PLAYER_COUNT,
            "build_turns_taken": 0,
        }
    )


def enter_resolve(state: GameState) -> GameState:
    """Run resolve steps 1-13 atomically. Ends in ROUND_START or END."""
    if state.phase is not Phase.RESOLVE:
        raise ValueError(f"enter_resolve requires phase=RESOLVE, got {state.phase}")
    if state.active_rule is None:
        raise ValueError("enter_resolve called with no active_rule")
    if state.active_rule.joker_attached is not None:
        raise NotImplementedError("M2: joker attachment")
    # Steps 1-7 (render, scope, evaluate, apply effects, joker, persistent
    # trigger, goal claim) are M1 stubs — no state changes.
    # Step 8: label recompute — labels.py stub.
    # Step 9: win check.
    winner = _check_winner(state.players)
    if winner is not None:
        return state.model_copy(
            update={
                "phase": Phase.END,
                "winner": winner,
                "active_rule": None,
            }
        )
    # Step 10: cleanup — discard played fragments.
    discarded = tuple(s.filled_by for s in state.active_rule.slots if s.filled_by is not None)
    # Step 11: rotate dealer.
    new_dealer = (state.dealer_seat + 1) % PLAYER_COUNT
    # Step 12: refill hands — M1 stub no-op (no deck).
    # Step 13: transition to ROUND_START.
    return state.model_copy(
        update={
            "phase": Phase.ROUND_START,
            "active_rule": None,
            "discard": state.discard + discarded,
            "dealer_seat": new_dealer,
            "build_turns_taken": 0,
            "revealed_effect": None,
        }
    )


def play_card(state: GameState, card: Card, slot_name: str) -> GameState:
    """Active player plays ``card`` into ``slot_name``; advances the build turn.

    Validates phase=BUILD, slot exists, slot is unfilled, card type matches
    slot type. Hand membership is not checked in M1 (hands are empty stubs).
    """
    if state.phase is not Phase.BUILD:
        raise ValueError(f"play_card requires phase=BUILD, got {state.phase}")
    if state.active_rule is None:
        raise ValueError("play_card called with no active_rule")

    rule = state.active_rule
    target_idx = next(
        (i for i, s in enumerate(rule.slots) if s.name == slot_name),
        None,
    )
    if target_idx is None:
        raise ValueError(f"unknown slot {slot_name!r}")
    target = rule.slots[target_idx]
    if target.filled_by is not None:
        raise ValueError(f"slot {slot_name!r} already filled")
    if target.type is not card.type:
        raise ValueError(f"card type {card.type} does not match slot type {target.type}")

    new_slot = target.model_copy(update={"filled_by": card})
    new_slots = rule.slots[:target_idx] + (new_slot,) + rule.slots[target_idx + 1 :]
    active_player_id = state.players[state.active_seat].id
    new_play = Play(player_id=active_player_id, card=card, slot=slot_name)
    new_rule = rule.model_copy(
        update={
            "slots": new_slots,
            "plays": rule.plays + (new_play,),
        }
    )
    return _build_tick(state.model_copy(update={"active_rule": new_rule}))


def pass_turn(state: GameState) -> GameState:
    """Active player passes (forced pass / no legal play). Advances the turn."""
    if state.phase is not Phase.BUILD:
        raise ValueError(f"pass_turn requires phase=BUILD, got {state.phase}")
    return _build_tick(state)


# --- Internals --------------------------------------------------------------


def _build_tick(state: GameState) -> GameState:
    """Advance one build turn. May transition to RESOLVE or fail back to ROUND_START."""
    new_taken = state.build_turns_taken + 1
    if new_taken < PLAYER_COUNT:
        return state.model_copy(
            update={
                "build_turns_taken": new_taken,
                "active_seat": (state.active_seat + 1) % PLAYER_COUNT,
            }
        )
    # Full revolution complete — evaluate fill state.
    rule = state.active_rule
    if rule is None:
        raise ValueError("build revolution ended with no active_rule")
    all_filled = all(s.filled_by is not None for s in rule.slots)
    if all_filled:
        return state.model_copy(
            update={
                "build_turns_taken": new_taken,
                "phase": Phase.RESOLVE,
            }
        )
    return _fail_rule_and_rotate(state)


def _fail_rule_and_rotate(state: GameState) -> GameState:
    """Rule failed: discard fragments, rotate dealer, return to ROUND_START."""
    rule = state.active_rule
    discarded = (
        tuple(s.filled_by for s in rule.slots if s.filled_by is not None)
        if rule is not None
        else ()
    )
    new_dealer = (state.dealer_seat + 1) % PLAYER_COUNT
    return state.model_copy(
        update={
            "phase": Phase.ROUND_START,
            "active_rule": None,
            "discard": state.discard + discarded,
            "dealer_seat": new_dealer,
            "build_turns_taken": 0,
            "revealed_effect": None,
        }
    )


def _apply_burn_tick(player: Player) -> Player:
    """Step 2: lose ``BURN_TICK × burn_count`` chips and clear MUTE."""
    burn = player.status.burn
    new_chips = max(0, player.chips - BURN_TICK * burn)
    new_status = player.status.model_copy(update={"mute": False})
    return player.model_copy(update={"chips": new_chips, "status": new_status})


def _check_winner(players: tuple[Player, ...]) -> Player | None:
    """Step 9: first player at or above ``VP_TO_WIN`` wins. Tie-break deferred."""
    for p in players:
        if p.vp >= VP_TO_WIN:
            return p
    return None

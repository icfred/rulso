"""Round flow phase machine.

Pure functions; each transition returns a new GameState. M1 implements the IF
path; shop and persistent-rule paths raise NotImplementedError("M2") so the M1
flow stays inside round_start -> build -> resolve -> round_start.

Shop guard: the shop check inside enter_round_start raises NotImplementedError
when round_number % shop_interval == 0. M1 callers either keep round_number
below shop_interval or override config.shop_interval to a sentinel value (e.g.
10**9). Tests use the latter to exercise multi-round flow.
"""

from __future__ import annotations

import random

from . import labels
from .state import (
    Card,
    Config,
    GameState,
    Play,
    Player,
    RuleBuilder,
    Slot,
)


def start_game(seed: int = 0, config: Config | None = None) -> GameState:
    """Initialize a fresh game. Result has phase="round_start", round_number=0."""
    cfg = config or Config()
    rng = random.Random(seed)
    deck = _make_placeholder_deck(rng)
    effect_deck = tuple(
        Card(id=f"effect_{i}", type="JOKER", text="effect placeholder") for i in range(20)
    )
    goal_deck = tuple(Card(id=f"goal_{i}", type="NOUN", text="goal placeholder") for i in range(20))

    players: list[Player] = []
    for seat in range(cfg.player_count):
        hand = deck[seat * cfg.hand_size : (seat + 1) * cfg.hand_size]
        players.append(
            Player(
                id=f"p{seat}",
                seat=seat,
                chips=cfg.starting_chips,
                vp=0,
                hand=hand,
            )
        )
    remaining_deck = deck[cfg.player_count * cfg.hand_size :]
    active_goals = goal_deck[: cfg.active_goals]
    goal_remainder = goal_deck[cfg.active_goals :]

    return GameState(
        config=cfg,
        phase="round_start",
        round_number=0,
        dealer_seat=0,
        active_seat=0,
        players=tuple(players),
        deck=remaining_deck,
        effect_deck=effect_deck,
        goal_deck=goal_remainder,
        active_goals=active_goals,
        seed=seed,
    )


def advance_phase(state: GameState) -> GameState:
    """Run the transition out of state.phase. One phase boundary per call."""
    if state.phase == "lobby":
        return enter_round_start(state.model_copy(update={"phase": "round_start"}))
    if state.phase == "round_start":
        return enter_round_start(state)
    if state.phase == "build":
        return _finish_build(state)
    if state.phase == "resolve":
        return enter_resolve(state)
    if state.phase == "shop":
        raise NotImplementedError("M2 — shop phase")
    if state.phase == "end":
        return state
    raise ValueError(f"unknown phase: {state.phase!r}")


def enter_round_start(state: GameState) -> GameState:
    """Run round_start steps 1-7, emerge in build phase."""
    cfg = state.config
    new_round = state.round_number + 1

    new_players = _burn_tick(state.players, cfg)

    labels.recompute(state)

    if state.persistent_rules:
        raise NotImplementedError("M2 — WHILE rule tick")

    if cfg.shop_interval > 0 and new_round % cfg.shop_interval == 0:
        raise NotImplementedError("M2 — shop phase")

    revealed_effect, effect_deck = _draw_one(state.effect_deck)

    rule = _make_m1_rule(new_round, state.dealer_seat)

    next_state = state.model_copy(
        update={
            "round_number": new_round,
            "players": new_players,
            "revealed_effect": revealed_effect,
            "effect_deck": effect_deck,
            "active_rule": rule,
        }
    )
    return enter_build(next_state)


def enter_build(state: GameState) -> GameState:
    """Set active_seat to dealer+1, reset build counter, transition to build."""
    cfg = state.config
    return state.model_copy(
        update={
            "phase": "build",
            "active_seat": (state.dealer_seat + 1) % cfg.player_count,
            "build_turns_taken": 0,
        }
    )


def play_card(state: GameState, card: Card, slot_name: str) -> GameState:
    """Active player plays card into named slot. M1: no legality validation."""
    if state.phase != "build":
        raise ValueError("play_card requires build phase")
    if state.active_rule is None:
        raise ValueError("no active rule")

    rule = state.active_rule
    target_idx = next(
        (i for i, s in enumerate(rule.slots) if s.name == slot_name and s.filled_by is None),
        None,
    )
    if target_idx is None:
        raise ValueError(f"slot {slot_name!r} not open or unknown")
    new_slots = tuple(
        s.model_copy(update={"filled_by": card}) if i == target_idx else s
        for i, s in enumerate(rule.slots)
    )
    new_plays = rule.plays + (Play(seat=state.active_seat, card=card, slot_name=slot_name),)
    new_rule = rule.model_copy(update={"slots": new_slots, "plays": new_plays})
    return _advance_active_seat(state.model_copy(update={"active_rule": new_rule}))


def force_pass(state: GameState) -> GameState:
    """Active player passes (no legal card, or M1 test-driven pass)."""
    if state.phase != "build":
        raise ValueError("force_pass requires build phase")
    if state.active_rule is None:
        raise ValueError("no active rule")
    rule = state.active_rule
    new_plays = rule.plays + (Play(seat=state.active_seat, card=None, slot_name=None),)
    new_rule = rule.model_copy(update={"plays": new_plays})
    return _advance_active_seat(state.model_copy(update={"active_rule": new_rule}))


def enter_resolve(state: GameState) -> GameState:
    """M1: discard fragments, win check, rotate dealer, refill hands, return to round_start.

    Effect application, JOKER persistence, persistent-rule trigger, and goal
    claim evaluation are deferred to M2.
    """
    cfg = state.config
    rule = state.active_rule
    if rule is None:
        raise ValueError("no active rule to resolve")

    if rule.joker_attached is not None:
        raise NotImplementedError("M2 — JOKER persistence")
    if state.persistent_rules:
        raise NotImplementedError("M2 — persistent rule trigger check")

    discard = state.discard + tuple(s.filled_by for s in rule.slots if s.filled_by is not None)

    winner_seat = next((p.seat for p in state.players if p.vp >= cfg.vp_to_win), None)
    if winner_seat is not None:
        return state.model_copy(
            update={
                "phase": "end",
                "winner_seat": winner_seat,
                "active_rule": None,
                "discard": discard,
            }
        )

    new_dealer = (state.dealer_seat + 1) % cfg.player_count
    refilled_players, new_deck, new_discard = _refill_hands(
        state.players, state.deck, discard, cfg.hand_size
    )

    return state.model_copy(
        update={
            "phase": "round_start",
            "dealer_seat": new_dealer,
            "active_seat": new_dealer,
            "active_rule": None,
            "build_turns_taken": 0,
            "players": refilled_players,
            "deck": new_deck,
            "discard": new_discard,
        }
    )


def _finish_build(state: GameState) -> GameState:
    cfg = state.config
    if state.build_turns_taken < cfg.player_count:
        raise ValueError(f"build incomplete: {state.build_turns_taken}/{cfg.player_count} turns")
    rule = state.active_rule
    if rule is None:
        raise ValueError("no active rule")
    all_required_filled = all(s.filled_by is not None for s in rule.slots if s.required)
    if all_required_filled:
        return enter_resolve(state)
    return _fail_rule(state)


def _fail_rule(state: GameState) -> GameState:
    """Rule failed: discard fragments, rotate dealer, refill, return to round_start."""
    cfg = state.config
    rule = state.active_rule
    assert rule is not None
    discard = state.discard + tuple(s.filled_by for s in rule.slots if s.filled_by is not None)
    new_dealer = (state.dealer_seat + 1) % cfg.player_count
    refilled_players, new_deck, new_discard = _refill_hands(
        state.players, state.deck, discard, cfg.hand_size
    )
    return state.model_copy(
        update={
            "phase": "round_start",
            "dealer_seat": new_dealer,
            "active_seat": new_dealer,
            "active_rule": None,
            "build_turns_taken": 0,
            "players": refilled_players,
            "deck": new_deck,
            "discard": new_discard,
        }
    )


def _advance_active_seat(state: GameState) -> GameState:
    cfg = state.config
    return state.model_copy(
        update={
            "active_seat": (state.active_seat + 1) % cfg.player_count,
            "build_turns_taken": state.build_turns_taken + 1,
        }
    )


def _burn_tick(players: tuple[Player, ...], cfg: Config) -> tuple[Player, ...]:
    return tuple(
        p.model_copy(
            update={
                "chips": max(0, p.chips - cfg.burn_tick * p.status.burn),
                "status": p.status.model_copy(update={"mute": False}),
            }
        )
        for p in players
    )


def _refill_hands(
    players: tuple[Player, ...],
    deck: tuple[Card, ...],
    discard: tuple[Card, ...],
    hand_size: int,
) -> tuple[tuple[Player, ...], tuple[Card, ...], tuple[Card, ...]]:
    """Top up each player's hand from the deck. Reshuffles discard when deck empties."""
    new_players: list[Player] = []
    cur_deck = deck
    cur_discard = discard
    for p in players:
        need = hand_size - len(p.hand)
        if need <= 0:
            new_players.append(p)
            continue
        if len(cur_deck) < need:
            cur_deck = cur_deck + cur_discard
            cur_discard = ()
        drawn = cur_deck[:need]
        cur_deck = cur_deck[need:]
        new_players.append(p.model_copy(update={"hand": p.hand + drawn}))
    return tuple(new_players), cur_deck, cur_discard


def _draw_one(deck: tuple[Card, ...]) -> tuple[Card | None, tuple[Card, ...]]:
    if not deck:
        return None, deck
    return deck[0], deck[1:]


def _make_m1_rule(round_number: int, dealer_seat: int) -> RuleBuilder:
    """M1 placeholder rule: 3 slots, dealer pre-fills slot 0.

    Real shape derives from the dealer's condition card in M2.
    """
    template = Card(
        id=f"cond_if_r{round_number}",
        type="CONDITION",
        text="IF",
        rule_kind="IF",
    )
    first_card = Card(
        id=f"frag_subject_r{round_number}",
        type="SUBJECT",
        text="placeholder subject",
    )
    slots = (
        Slot(name="subject", kind="SUBJECT", filled_by=first_card),
        Slot(name="noun", kind="NOUN"),
        Slot(name="modifier", kind="MODIFIER"),
    )
    plays = (Play(seat=dealer_seat, card=first_card, slot_name="subject"),)
    return RuleBuilder(template=template, slots=slots, plays=plays)


def _make_placeholder_deck(rng: random.Random) -> tuple[Card, ...]:
    cards: list[Card] = []
    for i in range(80):
        t = ("SUBJECT", "NOUN", "MODIFIER")[i % 3]
        cards.append(Card(id=f"deck_{t}_{i}", type=t, text=f"placeholder {t}"))
    rng.shuffle(cards)
    return tuple(cards)

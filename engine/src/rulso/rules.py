"""Round-flow phase machine.

Pure-function transitions over ``GameState``. Implements the round flow defined
in ``design/state.md``. Shop, persistent-rule WHILE tick, joker attachment and
real effect-card application are stubbed — see ``docs/engine/round-flow.md``.

All functions return a new ``GameState``; the input state is never mutated.

RNG contract (RUL-18):

* ``start_game(seed)`` performs the initial deck shuffle and 4×HAND_SIZE deal
  using ``random.Random(seed)``. The rng is consumed and discarded — same seed
  in, same opening state out.
* ``enter_resolve(state, *, rng=None)`` shuffles ``state.discard`` back into
  ``state.deck`` when refilling depletes the deck. Pass an explicit
  ``random.Random(...)`` for deterministic mid-game refills (cli.py does).
  ``rng=None`` falls back to a fresh non-deterministic ``random.Random()``.
* ``advance_phase(state, *, rng=None)`` forwards ``rng`` to ``enter_resolve``;
  other phase boundaries don't shuffle.

The seed is intentionally NOT carried on ``GameState`` (substrate is
additive-only and frozen; threading the RNG through public entry points keeps
``GameState`` purely declarative).
"""

from __future__ import annotations

import random

from rulso import cards as cards_module
from rulso import effects, labels, legality, persistence
from rulso.cards import ConditionTemplate
from rulso.state import (
    BURN_TICK,
    HAND_SIZE,
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

# --- Round-flow placeholder effect card -------------------------------------
# Round-flow draws an effect card from ``state.effect_deck`` at round_start
# step 6 in a follow-up Phase 3 ticket. Until then the round reveals this
# NOOP placeholder so ``revealed_effect`` is non-None during BUILD/RESOLVE
# (narration code reads it) and the dispatcher returns state unchanged when
# the round resolves.
_M1_EFFECT_CARD: Card = Card(
    id="m1_stub_effect",
    type=CardType.EFFECT,
    name="NOOP",
)


# --- Public entry points ----------------------------------------------------


def start_game(seed: int = 0) -> GameState:
    """Initialize a fresh 4-player game with shuffled deck and dealt hands.

    Builds the main deck via :func:`cards.build_default_deck`, shuffles it with
    ``random.Random(seed)``, deals ``HAND_SIZE`` cards to each of the
    ``PLAYER_COUNT`` players, and parks the remainder in ``state.deck``.

    Returns a state at ``phase=ROUND_START`` with ``round_number=0`` and
    ``dealer_seat=0``. Same ``seed`` ⇒ same opening hands (RUL-18 determinism
    contract).
    """
    rng = random.Random(seed)
    decks = cards_module.build_default_deck()
    deck_list = list(decks.main)
    rng.shuffle(deck_list)

    cursor = 0
    players: list[Player] = []
    for i in range(PLAYER_COUNT):
        hand = tuple(deck_list[cursor : cursor + HAND_SIZE])
        cursor += HAND_SIZE
        players.append(Player(id=f"p{i}", seat=i, hand=hand))
    remaining_deck = tuple(deck_list[cursor:])

    # RUL-39: seed effect_deck from cards.yaml. Round-flow draw lands later.
    effect_deck = cards_module.load_effect_cards()

    return GameState(
        phase=Phase.ROUND_START,
        round_number=0,
        dealer_seat=0,
        active_seat=0,
        players=tuple(players),
        deck=remaining_deck,
        effect_deck=effect_deck,
    )


def advance_phase(state: GameState, *, rng: random.Random | None = None) -> GameState:
    """Advance one logical step based on the current phase.

    ``BUILD`` ticks model a forced-pass turn (no card played). To play a card
    during build, call :func:`play_card` directly. ``rng`` is forwarded to
    :func:`enter_resolve` for the deck-refill shuffle.
    """
    phase = state.phase
    if phase is Phase.LOBBY:
        return enter_round_start(state)
    if phase is Phase.ROUND_START:
        return enter_round_start(state)
    if phase is Phase.BUILD:
        return _build_tick(state)
    if phase is Phase.RESOLVE:
        return enter_resolve(state, rng=rng)
    if phase is Phase.SHOP:
        raise NotImplementedError("M2: shop phase")
    if phase is Phase.END:
        return state
    raise ValueError(f"unknown phase {phase!r}")


def enter_round_start(state: GameState) -> GameState:
    """Run round_start steps 1-8 from ``design/state.md`` atomically.

    Ends in ``phase=BUILD`` with the dealer's first slot pre-filled — unless
    the dealer holds no card matching slot 0's type, in which case the rule
    fails immediately and the dealer rotates (rule never enters BUILD).
    """
    new_round = state.round_number + 1
    # Step 2: BURN tick + MUTE expiry.
    players = tuple(_apply_burn_tick(p) for p in state.players)
    # Step 3: recompute floating labels (ADR-0001 — computed-not-stored).
    # The recompute is preserved as the canonical design step 3 hook; the
    # resolver receives labels as a transient parameter from enter_resolve.
    labels.recompute_labels(state.model_copy(update={"players": players}))
    # Step 4: WHILE-rule tick — no-op when no persistent rules (M1.5 path).
    if state.persistent_rules:
        tick_state = state.model_copy(update={"players": players, "round_number": new_round})
        tick_labels = labels.recompute_labels(tick_state)
        tick_state = persistence.tick_while_rules(tick_state, tick_labels)
        players = tick_state.players
    # Step 5: shop check — bypassed in M1. See docs/engine/round-flow.md.
    # Step 6: reveal effect card. Real effect-deck draw lands with M2; the
    # stub keeps revealed_effect non-None during BUILD/RESOLVE.
    revealed_effect = _M1_EFFECT_CARD
    # Step 7: dealer plays the condition template + slot 0.
    condition = _draw_condition_template()
    slots = tuple(Slot(name=cs.name, type=cs.type) for cs in condition.slots)
    if not slots:
        raise ValueError(f"condition template {condition.id!r} has no slots")
    dealer = players[state.dealer_seat]
    first_slot = slots[0]
    chosen = legality.first_card_of_type(dealer.hand, first_slot.type)
    if chosen is None:
        # No legal seed-card in the dealer's hand → rule fails immediately.
        # Round is consumed (round_number ticked) and dealer rotates.
        new_dealer_seat = (state.dealer_seat + 1) % PLAYER_COUNT
        return state.model_copy(
            update={
                "round_number": new_round,
                "players": players,
                "phase": Phase.ROUND_START,
                "active_rule": None,
                "dealer_seat": new_dealer_seat,
                "build_turns_taken": 0,
                "revealed_effect": None,
            }
        )

    new_dealer_hand = _remove_first(dealer.hand, chosen)
    new_dealer = dealer.model_copy(update={"hand": new_dealer_hand})
    players = players[: state.dealer_seat] + (new_dealer,) + players[state.dealer_seat + 1 :]

    filled_first = first_slot.model_copy(update={"filled_by": chosen})
    final_slots = (filled_first,) + slots[1:]
    first_play = Play(player_id=dealer.id, card=chosen, slot=first_slot.name)
    active_rule = RuleBuilder(
        template=condition.kind,
        slots=final_slots,
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


def enter_resolve(state: GameState, *, rng: random.Random | None = None) -> GameState:
    """Run resolve steps 1-13 atomically. Ends in ROUND_START or END.

    ``rng`` is consumed by the deck-refill shuffle (step 12) when ``state.deck``
    runs short. Pass ``random.Random(seed)`` for deterministic refills; ``None``
    falls back to a fresh non-deterministic ``random.Random()``.
    """
    if state.phase is not Phase.RESOLVE:
        raise ValueError(f"enter_resolve requires phase=RESOLVE, got {state.phase}")
    if state.active_rule is None:
        raise ValueError("enter_resolve called with no active_rule")
    if state.active_rule.joker_attached is not None:
        raise NotImplementedError("M2: joker attachment")
    # Steps 1-4: render + scope + evaluate + apply effects via the resolver.
    # ADR-0001 labels are computed-not-stored, so the resolver recomputes
    # them from ``state`` when called without an explicit labels mapping.
    # IF-only in M1.5; WHEN/WHILE land with persistent rules (M2) so we
    # guard the call here to keep the path future-safe.
    if state.active_rule.template is RuleKind.IF:
        state = effects.resolve_if_rule(state, state.active_rule)
    # Step 6: persistent rule trigger check (no-op when none active).
    if state.persistent_rules:
        state = persistence.check_when_triggers(state, labels.recompute_labels(state))
    # Steps 5 & 7: joker (guarded above) + goal claim — M2 stubs (no-op M1.5).
    # Step 8: label recompute — implicit (computed-not-stored).
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
    # Step 12: refill hands.
    refill_rng = rng if rng is not None else random.Random()
    state_post_discard = state.model_copy(
        update={
            "discard": state.discard + discarded,
        }
    )
    refilled = _refill_hands(state_post_discard, refill_rng)
    # Step 13: transition to ROUND_START.
    return refilled.model_copy(
        update={
            "phase": Phase.ROUND_START,
            "active_rule": None,
            "dealer_seat": new_dealer,
            "build_turns_taken": 0,
            "revealed_effect": None,
        }
    )


def play_card(state: GameState, card: Card, slot_name: str) -> GameState:
    """Active player plays ``card`` into ``slot_name``; advances the build turn.

    Validates phase=BUILD, slot exists, slot is unfilled, card type matches
    slot type. Removes ``card`` from the active player's hand by id+identity
    (the first matching instance, in case of duplicates).
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
    active_player = state.players[state.active_seat]
    new_play = Play(player_id=active_player.id, card=card, slot=slot_name)
    new_rule = rule.model_copy(
        update={
            "slots": new_slots,
            "plays": rule.plays + (new_play,),
        }
    )
    new_hand = _remove_first(active_player.hand, card)
    new_player = active_player.model_copy(update={"hand": new_hand})
    new_players = (
        state.players[: state.active_seat] + (new_player,) + state.players[state.active_seat + 1 :]
    )
    return _build_tick(
        state.model_copy(
            update={
                "active_rule": new_rule,
                "players": new_players,
            }
        )
    )


def pass_turn(state: GameState) -> GameState:
    """Active player passes (forced pass / no legal play). Advances the turn."""
    if state.phase is not Phase.BUILD:
        raise ValueError(f"pass_turn requires phase=BUILD, got {state.phase}")
    return _build_tick(state)


# --- Internals --------------------------------------------------------------


def _draw_condition_template() -> ConditionTemplate:
    """Return one CONDITION template per round.

    M1.5 ships a single condition (``cond.if``); the deck has one card. When
    multiple conditions land, this draws the first deterministically — RUL-21
    or later can promote it to an rng-shuffled condition deck. Loading per
    round is cheap (yaml is small); avoids a new ``GameState`` field for the
    condition deck while substrate stays additive-only.
    """
    templates = cards_module.load_condition_templates()
    if not templates:
        raise RuntimeError("cards.yaml exposes no condition templates")
    return templates[0]


def _refill_hands(state: GameState, rng: random.Random) -> GameState:
    """Step 12: refill each player's hand to ``HAND_SIZE``.

    When ``state.deck`` empties mid-refill, shuffles ``state.discard`` back into
    the deck via ``rng`` and continues. If both deck and discard are empty,
    stops drawing for that player (hand stays under ``HAND_SIZE`` until cards
    return to the discard pile next round).
    """
    deck = list(state.deck)
    discard = list(state.discard)
    new_players: list[Player] = []
    for player in state.players:
        needed = HAND_SIZE - len(player.hand)
        drawn: list[Card] = []
        while needed > 0:
            if not deck:
                if not discard:
                    break
                deck = discard
                rng.shuffle(deck)
                discard = []
            drawn.append(deck.pop())
            needed -= 1
        if drawn:
            new_players.append(player.model_copy(update={"hand": player.hand + tuple(drawn)}))
        else:
            new_players.append(player)
    return state.model_copy(
        update={
            "players": tuple(new_players),
            "deck": tuple(deck),
            "discard": tuple(discard),
        }
    )


def _remove_first(hand: tuple[Card, ...], card: Card) -> tuple[Card, ...]:
    """Remove the first occurrence of ``card`` (by identity, then id) from ``hand``."""
    for i, c in enumerate(hand):
        if c is card or c.id == card.id:
            return hand[:i] + hand[i + 1 :]
    raise ValueError(f"card {card.id!r} not in hand")


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

"""Round-flow phase machine.

Pure-function transitions over ``GameState``. Implements the round flow defined
in ``design/state.md``. Shop and persistent-rule WHILE tick are stubbed — see
``docs/engine/round-flow.md``.

All functions return a new ``GameState``; the input state is never mutated.

RNG contract (RUL-18, extended by RUL-47, hardened by RUL-54):

* ``start_game(seed)`` performs the initial deck shuffle and 4×HAND_SIZE deal
  using ``random.Random(seed)``. The rng is consumed and discarded — same seed
  in, same opening state out.
* ``enter_round_start(state, *, rng=None)`` requires an rng to reshuffle
  ``state.effect_discard`` back into ``state.effect_deck`` when step 6's draw
  finds an empty deck (RUL-47). ``rng=None`` is tolerated only when the
  recycle path does not trigger; reaching it without an rng raises
  ``ValueError`` rather than silently falling back to a non-deterministic
  ``random.Random()`` (RUL-54 — the silent fallback diverged seeded games at
  round ~13 once the 12-card effect deck exhausted).
* ``enter_resolve(state, *, rng=None)`` shuffles ``state.discard`` back into
  ``state.deck`` when refilling depletes the main deck. Same contract as
  ``enter_round_start``: ``rng=None`` is fine when the deck has enough cards,
  but reaching the reshuffle without one raises ``ValueError``.
* ``advance_phase(state, *, rng=None)`` forwards ``rng`` to both
  ``enter_round_start`` and ``enter_resolve``; other phase boundaries don't
  shuffle.

The seed is intentionally NOT carried on ``GameState`` (substrate is
additive-only and frozen; threading the RNG through public entry points keeps
``GameState`` purely declarative).
"""

from __future__ import annotations

import random

from rulso import cards as cards_module
from rulso import effects, goals, labels, legality, persistence, status
from rulso.cards import ConditionTemplate
from rulso.state import (
    ACTIVE_GOALS,
    DISCARD_COST,
    HAND_SIZE,
    PLAYER_COUNT,
    SHOP_INTERVAL,
    VP_TO_WIN,
    Card,
    CardType,
    GameState,
    GoalCard,
    LastRoll,
    Phase,
    Play,
    Player,
    RuleBuilder,
    RuleKind,
    ShopOffer,
    Slot,
)

# RUL-42 (G): OP-only comparator names (ADR-0002). Mirrors the set in
# effects.py — kept local to avoid a back-import; the two are co-evolved.
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})

# RUL-45 (J): JOKER variant names per design/cards-inventory.md. Persistence
# variants promote the rule into ``persistent_rules`` (and skip slot
# discard); DOUBLE handles its post-dispatch wrapper inside
# ``effects.resolve_if_rule``; ECHO re-fires next round via WHEN promotion.
_JOKER_PERSIST_WHEN: str = "JOKER:PERSIST_WHEN"
_JOKER_PERSIST_WHILE: str = "JOKER:PERSIST_WHILE"
_JOKER_DOUBLE: str = "JOKER:DOUBLE"
_JOKER_ECHO: str = "JOKER:ECHO"
_JOKER_PERSISTENT_VARIANTS: frozenset[str] = frozenset(
    {_JOKER_PERSIST_WHEN, _JOKER_PERSIST_WHILE, _JOKER_ECHO}
)
_JOKER_VARIANTS: frozenset[str] = frozenset(
    {_JOKER_PERSIST_WHEN, _JOKER_PERSIST_WHILE, _JOKER_DOUBLE, _JOKER_ECHO}
)


# RUL-70: label-refresh discipline. Every public entry point that may touch a
# label-driving attribute (vp / chips / burn / cards_given) recomputes
# ``state.labels`` on its way out so clients can read the wire field directly
# instead of mirroring the engine's computation (ADR-0001).
def _with_recomputed_labels(state: GameState) -> GameState:
    """Return ``state`` with ``state.labels`` refreshed from the canonical compute."""
    return state.model_copy(update={"labels": labels.to_wire(labels.recompute_labels(state))})


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

    # --- RUL-46: goal-deck seed (own block) ---
    # Same `rng` continues — keeps `start_game(seed)` deterministic (RUL-18).
    # `state.md` Game Start step 3 reveals 3 face-up goals; if the catalogue
    # has fewer than ACTIVE_GOALS, leftover slots stay None per the spike's
    # "deck exhaustion" handling.
    goal_pool = list(cards_module.load_goal_cards())
    rng.shuffle(goal_pool)
    initial_goals: list[GoalCard | None] = []
    for _ in range(ACTIVE_GOALS):
        initial_goals.append(goal_pool.pop() if goal_pool else None)
    initial_active_goals: tuple[GoalCard | None, ...] = tuple(initial_goals)
    initial_goal_deck: tuple[GoalCard, ...] = tuple(goal_pool)
    # --- end RUL-46 block ---

    # --- RUL-51: shop-pool seed (own block) ---
    # Same `rng` continues — keeps `start_game(seed)` deterministic (RUL-18).
    # ``cards.yaml`` ships an empty ``shop_cards:`` section for M2; the SHOP
    # cadence + ordering substrate runs over an empty pool and short-circuits
    # in :func:`enter_round_start` so M1.5 / M2 smoke output is unaffected.
    shop_pool_list = list(cards_module.load_shop_offers())
    rng.shuffle(shop_pool_list)
    initial_shop_pool: tuple[ShopOffer, ...] = tuple(shop_pool_list)
    # --- end RUL-51 block ---

    return _with_recomputed_labels(
        GameState(
            phase=Phase.ROUND_START,
            round_number=0,
            dealer_seat=0,
            active_seat=0,
            players=tuple(players),
            deck=remaining_deck,
            effect_deck=effect_deck,
            goal_deck=initial_goal_deck,
            active_goals=initial_active_goals,
            shop_pool=initial_shop_pool,
        )
    )


def advance_phase(state: GameState, *, rng: random.Random | None = None) -> GameState:
    """Advance one logical step based on the current phase.

    ``BUILD`` ticks model a forced-pass turn (no card played). To play a card
    during build, call :func:`play_card` directly. ``rng`` is forwarded to
    :func:`enter_resolve` for the deck-refill shuffle.
    """
    phase = state.phase
    if phase is Phase.LOBBY:
        return enter_round_start(state, rng=rng)
    if phase is Phase.ROUND_START:
        return enter_round_start(state, rng=rng)
    if phase is Phase.BUILD:
        return _build_tick(state)
    if phase is Phase.RESOLVE:
        return enter_resolve(state, rng=rng)
    if phase is Phase.SHOP:
        # RUL-51: SHOP completes after the driver has applied each purchase
        # (via :func:`apply_shop_purchase` / :func:`skip_shop_purchase`).
        # ``complete_shop`` discards remaining offers and resumes round_start
        # steps 6-8 (effect draw + dealer seed + transition to BUILD).
        return complete_shop(state, rng=rng)
    if phase is Phase.END:
        return state
    raise ValueError(f"unknown phase {phase!r}")


def enter_round_start(state: GameState, *, rng: random.Random | None = None) -> GameState:
    """Run round_start steps 1-8 from ``design/state.md``.

    Ends in one of three states:

    * ``phase=BUILD`` — happy path; the dealer's first slot is pre-filled.
    * ``phase=ROUND_START`` — dealer held no card matching slot 0's type, so
      the rule failed immediately and the dealer rotated.
    * ``phase=SHOP`` — round_number hits the ``SHOP_INTERVAL`` cadence AND at
      least one offer is available; pauses for the driver to apply purchases
      via :func:`apply_shop_purchase`, then resume with
      :func:`advance_phase` (which calls :func:`complete_shop` and runs
      steps 6-8). Per ``design/state.md`` SHOP step 5: SHOP does NOT consume
      the round counter — round_start resumes from step 6 after SHOP.

    ``rng`` is consumed by the step-6 effect-deck draw (RUL-47) and the
    step-5 ``shop_discard``→``shop_pool`` recycle (RUL-51). ``rng=None`` is
    tolerated only when neither recycle path triggers; reaching either
    without an rng raises ``ValueError`` (RUL-54 — see module docstring).
    """
    new_round = state.round_number + 1
    # Step 2: status tick — BURN drains chips, MUTE clears (RUL-40, RUL-30).
    players = tuple(status.tick_round_start(p) for p in state.players)
    # Step 3 (ADR-0001 / RUL-70): floating-label recompute is published on
    # ``state.labels`` by ``_with_recomputed_labels`` at every public-entry
    # return; resolver still receives labels as a transient parameter from
    # ``enter_resolve`` for in-flight effect application.
    # Step 4: WHILE-rule tick — no-op when no persistent rules (M1.5 path).
    if state.persistent_rules:
        tick_state = state.model_copy(update={"players": players, "round_number": new_round})
        tick_labels = labels.recompute_labels(tick_state)
        tick_state = persistence.tick_while_rules(tick_state, tick_labels)
        players = tick_state.players
    # Step 5: SHOP check (RUL-51). Cadence: ``round_number % SHOP_INTERVAL == 0``
    # (every 3 rounds — fires on 3, 6, 9, …). SHOP enters only when offers
    # are available; an empty ``shop_pool`` + ``shop_discard`` short-circuits
    # the phase entirely so callers without SHOP content see no visible SHOP
    # transition (preserves CLI / smoke output byte-for-byte until shop_cards
    # land in cards.yaml).
    post_step_4 = state.model_copy(update={"players": players, "round_number": new_round})
    if new_round % SHOP_INTERVAL == 0:
        offers, new_pool, new_discard = _draw_shop_offers(
            post_step_4.shop_pool, post_step_4.shop_discard, rng
        )
        if offers:
            return _with_recomputed_labels(
                post_step_4.model_copy(
                    update={
                        "phase": Phase.SHOP,
                        "shop_offer": offers,
                        "shop_pool": new_pool,
                        "shop_discard": new_discard,
                    }
                )
            )
    # No SHOP this round — proceed directly to steps 6-8.
    return _with_recomputed_labels(_round_start_post_shop(post_step_4, rng=rng))


def complete_shop(state: GameState, *, rng: random.Random | None = None) -> GameState:
    """Finalize the SHOP phase: discard remaining offers, resume round_start.

    Per ``design/state.md`` SHOP steps 4-5: unsold offers move to
    ``shop_discard``, then round_start resumes from step 6 (effect draw +
    dealer seed). SHOP does NOT consume the round counter — ``round_number``
    was already advanced when SHOP was entered. ``rng`` is forwarded to the
    step-6 effect-deck draw.
    """
    if state.phase is not Phase.SHOP:
        raise ValueError(f"complete_shop requires phase=SHOP, got {state.phase}")
    cleared = state.model_copy(
        update={
            "phase": Phase.ROUND_START,
            "shop_offer": (),
            "shop_discard": state.shop_discard + state.shop_offer,
        }
    )
    return _round_start_post_shop(cleared, rng=rng)


def apply_shop_purchase(state: GameState, player_id: str, offer_index: int) -> GameState:
    """Apply one SHOP purchase: deduct chips, append wrapped card to hand.

    Drives one buyer's choice during the SHOP phase. The driver determines
    the iteration order via :func:`shop_purchase_order` and calls this once
    per buying player. Skipping a turn requires no engine call — just omit
    the player from the iteration.

    Per ``design/state.md`` SHOP step 3, the purchased card "goes to hand
    (counts against HAND_SIZE; player must discard if over)". This function
    appends without enforcing the over-cap discard — that's deferred to the
    BUILD-phase discard surface, mirroring how RESOLVE step 12 refills past
    HAND_SIZE never down-caps live hands either.

    Raises ``ValueError`` on bad phase, unknown player, out-of-range
    ``offer_index``, or insufficient chips.
    """
    if state.phase is not Phase.SHOP:
        raise ValueError(f"apply_shop_purchase requires phase=SHOP, got {state.phase}")
    player_idx = next((i for i, p in enumerate(state.players) if p.id == player_id), None)
    if player_idx is None:
        raise ValueError(f"unknown player {player_id!r}")
    if not (0 <= offer_index < len(state.shop_offer)):
        raise ValueError(
            f"offer_index {offer_index} out of range (have {len(state.shop_offer)} offers)"
        )
    offer = state.shop_offer[offer_index]
    player = state.players[player_idx]
    if player.chips < offer.price:
        raise ValueError(
            f"player {player_id!r} cannot afford offer (chips={player.chips}, price={offer.price})"
        )
    new_player = player.model_copy(
        update={
            "chips": player.chips - offer.price,
            "hand": player.hand + (offer.card,),
        }
    )
    new_players = state.players[:player_idx] + (new_player,) + state.players[player_idx + 1 :]
    new_offer = state.shop_offer[:offer_index] + state.shop_offer[offer_index + 1 :]
    return _with_recomputed_labels(
        state.model_copy(update={"players": new_players, "shop_offer": new_offer})
    )


def shop_purchase_order(state: GameState) -> tuple[str, ...]:
    """Return ``Player.id`` tuple in SHOP purchase order.

    Per ``design/state.md`` SHOP step 2: ascending VP, ties broken by lowest
    chips, ties broken by seat. Pure function — no side effects, no rng.
    """
    return tuple(p.id for p in sorted(state.players, key=lambda p: (p.vp, p.chips, p.seat)))


def _round_start_post_shop(state: GameState, *, rng: random.Random | None) -> GameState:
    """Run round_start steps 6-8 from ``design/state.md``.

    Reached from two paths: directly from :func:`enter_round_start` when the
    SHOP cadence doesn't fire (or no offers available), and indirectly from
    :func:`complete_shop` once the driver has applied purchases. ``state``
    must already have ``round_number`` advanced and post-WHILE-tick players.
    """
    # Step 6: reveal effect card from effect_deck (RUL-47). Recycle
    # effect_discard if the deck is empty per design/effects-inventory.md
    # "Deck-empty reshuffle". ``revealed_effect`` stays None when both piles
    # are empty (no cards to draw — same path the NOOP card exercises).
    revealed_effect, effect_deck, effect_discard = _draw_effect_card(
        state.effect_deck, state.effect_discard, rng
    )
    # Step 7: dealer plays the condition template + slot 0.
    condition = _draw_condition_template()
    slots = tuple(Slot(name=cs.name, type=cs.type) for cs in condition.slots)
    if not slots:
        raise ValueError(f"condition template {condition.id!r} has no slots")
    dealer = state.players[state.dealer_seat]
    first_slot = slots[0]
    chosen = legality.first_card_of_type(dealer.hand, first_slot.type)
    if chosen is None:
        # No legal seed-card in the dealer's hand → rule fails immediately.
        # Round is consumed (round_number ticked) and dealer rotates. The
        # just-drawn revealed_effect goes to effect_discard rather than being
        # lost (design/effects-inventory.md "Rule-failure interaction").
        new_dealer_seat = (state.dealer_seat + 1) % PLAYER_COUNT
        failed_effect_discard = (
            effect_discard + (revealed_effect,) if revealed_effect is not None else effect_discard
        )
        return state.model_copy(
            update={
                "phase": Phase.ROUND_START,
                "active_rule": None,
                "dealer_seat": new_dealer_seat,
                "build_turns_taken": 0,
                "revealed_effect": None,
                "effect_deck": effect_deck,
                "effect_discard": failed_effect_discard,
            }
        )
    new_dealer_hand = _remove_first(dealer.hand, chosen)
    new_dealer = dealer.model_copy(update={"hand": new_dealer_hand})
    players = (
        state.players[: state.dealer_seat] + (new_dealer,) + state.players[state.dealer_seat + 1 :]
    )
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
            "players": players,
            "phase": Phase.ROUND_START,
            "revealed_effect": revealed_effect,
            "effect_deck": effect_deck,
            "effect_discard": effect_discard,
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
    runs short. Pass ``random.Random(seed)`` for deterministic refills.
    ``rng=None`` is tolerated only when the reshuffle does not trigger;
    reaching it without an rng raises ``ValueError`` (RUL-54 — see module
    docstring).
    """
    if state.phase is not Phase.RESOLVE:
        raise ValueError(f"enter_resolve requires phase=RESOLVE, got {state.phase}")
    if state.active_rule is None:
        raise ValueError("enter_resolve called with no active_rule")
    active_rule = state.active_rule
    joker = active_rule.joker_attached
    joker_name = joker.name if joker is not None else None
    if joker_name is not None and joker_name not in _JOKER_VARIANTS:
        raise ValueError(f"unknown JOKER variant {joker_name!r} on active_rule")
    # Steps 1-4: render + scope + evaluate + apply effects via the resolver.
    # ADR-0001 labels are computed-not-stored, so the resolver recomputes
    # them from ``state`` when called without an explicit labels mapping.
    # IF-only in M1.5; WHEN/WHILE land with persistent rules (M2) so we
    # guard the call here to keep the path future-safe.
    # JOKER:DOUBLE is honoured inside ``effects.resolve_if_rule`` (it reads
    # ``rule.joker_attached`` after dispatch and re-applies the same effect).
    if active_rule.template is RuleKind.IF:
        state = effects.resolve_if_rule(state, active_rule)
    # Step 6: persistent rule trigger check (no-op when none active). Runs
    # BEFORE step 5 so a freshly-added ECHO/PERSIST rule does not satisfy its
    # own WHEN trigger in the same resolve — that would collapse "echoes next
    # round" into "fires twice this round". The state.md ordering is preserved
    # in spirit: only previously-active WHENs see this round's mutations.
    if state.persistent_rules:
        state = persistence.check_when_triggers(state, labels.recompute_labels(state))
    # Step 5: JOKER attachment (RUL-45). PERSIST_WHEN/PERSIST_WHILE/ECHO
    # promote the rule into ``persistent_rules`` (per design/state.md step 5)
    # and lock its fragments out of the round-end discard pile. DOUBLE leaves
    # no persistent residue — its effect-doubling fired inside resolve_if_rule.
    persisted_via_joker = False
    if joker_name in _JOKER_PERSISTENT_VARIANTS:
        if joker_name == _JOKER_PERSIST_WHEN:
            kind = RuleKind.WHEN
        elif joker_name == _JOKER_PERSIST_WHILE:
            kind = RuleKind.WHILE
        else:  # _JOKER_ECHO — re-fire next round via the WHEN trigger path.
            kind = RuleKind.WHEN
        promoted = active_rule.model_copy(
            update={"template": kind, "joker_attached": None},
        )
        state = persistence.add_persistent_rule(state, promoted, kind)
        persisted_via_joker = True
    # Step 7: goal claim check (RUL-46) — awards VP per `design/goals-inventory.md`.
    state = goals.check_claims(state)
    # Step 8: label recompute — implicit (computed-not-stored).
    # Step 9: win check.
    winner = _check_winner(state.players)
    if winner is not None:
        return _with_recomputed_labels(
            state.model_copy(
                update={
                    "phase": Phase.END,
                    "winner": winner,
                    "active_rule": None,
                }
            )
        )
    # Step 10: cleanup — discard played fragments and expire MARKED tokens
    # (one-round lifetime per RUL-30 / design/state.md). Persisted rules keep
    # their fragments locked into ``persistent_rules`` (state.md step 10
    # "except those locked into persistent_rules"); the joker card itself
    # also stays with the rule, not the discard pile.
    if persisted_via_joker:
        discarded = ()
    else:
        discarded = tuple(s.filled_by for s in active_rule.slots if s.filled_by is not None)
        if joker is not None:
            discarded = discarded + (joker,)
    cleaned_players = tuple(status.tick_resolve_end(p) for p in state.players)
    # Step 10 (effect cleanup, RUL-47): the round's revealed_effect was
    # consumed by step 4's dispatch. Append it to effect_discard so the
    # effect deck is recyclable; mirrors the fragment-discard hook above.
    consumed_effect = state.revealed_effect
    new_effect_discard = (
        state.effect_discard + (consumed_effect,)
        if consumed_effect is not None
        else state.effect_discard
    )
    # Step 11: rotate dealer.
    new_dealer = (state.dealer_seat + 1) % PLAYER_COUNT
    # Step 12: refill hands.
    refill_rng = rng
    state_post_discard = state.model_copy(
        update={
            "players": cleaned_players,
            "discard": state.discard + discarded,
            "effect_discard": new_effect_discard,
        }
    )
    refilled = _refill_hands(state_post_discard, refill_rng)
    # Step 13: transition to ROUND_START.
    return _with_recomputed_labels(
        refilled.model_copy(
            update={
                "phase": Phase.ROUND_START,
                "active_rule": None,
                "dealer_seat": new_dealer,
                "build_turns_taken": 0,
                "revealed_effect": None,
            }
        )
    )


def play_card(
    state: GameState,
    card: Card,
    slot_name: str,
    *,
    dice_mode: int | None = None,
    dice_roll: int | None = None,
) -> GameState:
    """Active player plays ``card`` into ``slot_name``; advances the build turn.

    Validates phase=BUILD, slot exists, slot is unfilled, card type matches
    slot type. Removes ``card`` from the active player's hand by id+identity
    (the first matching instance, in case of duplicates).

    RUL-42 (G) — comparator dice (ADR-0002): when ``card`` is an OP-only
    comparator MODIFIER (``card.name`` in ``{LT, LE, GT, GE, EQ}``),
    ``dice_mode`` (1 for 1d6, 2 for 2d6) and ``dice_roll`` (the drawn N) are
    required. Both are recorded on ``state.last_roll`` so the resolver can
    bake N into the QUANT slot. Both are ignored for non-OP-only cards.
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
    updates: dict[str, object] = {
        "active_rule": new_rule,
        "players": new_players,
    }
    # RUL-42 (G): record the dice roll for OP-only comparators per ADR-0002.
    if card.name in _OP_ONLY_COMPARATOR_NAMES:
        if dice_mode is None or dice_roll is None:
            raise ValueError(f"OP-only comparator {card.name!r} requires dice_mode and dice_roll")
        if dice_mode not in (1, 2):
            raise ValueError(f"dice_mode must be 1 or 2, got {dice_mode!r}")
        updates["last_roll"] = LastRoll(
            player_id=active_player.id,
            value=dice_roll,
            dice_count=dice_mode,
        )
    return _build_tick(state.model_copy(update=updates))


def pass_turn(state: GameState) -> GameState:
    """Active player passes (forced pass / no legal play). Advances the turn."""
    if state.phase is not Phase.BUILD:
        raise ValueError(f"pass_turn requires phase=BUILD, got {state.phase}")
    return _with_recomputed_labels(_build_tick(state))


def discard_redraw(
    state: GameState,
    player_id: str,
    card_ids: tuple[str, ...],
    *,
    refill_rng: random.Random | None = None,
) -> GameState:
    """Active player spends chips to discard ``card_ids`` and redraw N replacements.

    Per ``design/state.md`` BUILD phase: a player may discard 1..3 cards at the
    cost of :data:`DISCARD_COST` chips each, then immediately draw the same
    number of replacements from ``state.deck``. The discard pile receives the
    spent cards; when the deck exhausts mid-draw, ``state.discard`` is
    reshuffled back into the deck via ``refill_rng`` — same shape as
    :func:`_refill_hands` (RUL-54 conditional-substrate rule).

    Mutations:

    * Remove ``card_ids`` (in order) from the active player's hand.
    * Append the removed cards to ``state.discard``.
    * Deduct ``len(card_ids) * DISCARD_COST`` chips from the active player.
    * Draw ``len(card_ids)`` cards from ``state.deck`` (recycle when empty)
      and append them to the hand.
    * Advance the build turn via :func:`_build_tick`.

    Raises ``ValueError`` on: non-BUILD phase, out-of-turn caller, empty
    ``card_ids``, unknown card (by id) in the active player's hand, or
    insufficient chips. ``refill_rng=None`` is tolerated only when the deck
    has enough cards to satisfy the draw without recycling.
    """
    if state.phase is not Phase.BUILD:
        raise ValueError(f"discard_redraw requires phase=BUILD, got {state.phase}")
    active_player = state.players[state.active_seat]
    if active_player.id != player_id:
        raise ValueError(
            f"discard_redraw out-of-turn: active player is {active_player.id!r}, not {player_id!r}"
        )
    if not card_ids:
        raise ValueError("discard_redraw requires at least one card_id")
    cost = len(card_ids) * DISCARD_COST
    if active_player.chips < cost:
        raise ValueError(
            f"player {player_id!r} cannot afford discard (chips={active_player.chips}, cost={cost})"
        )
    hand = active_player.hand
    discarded: list[Card] = []
    for cid in card_ids:
        idx = next((i for i, c in enumerate(hand) if c.id == cid), None)
        if idx is None:
            raise ValueError(f"card {cid!r} not in {player_id!r} hand")
        discarded.append(hand[idx])
        hand = hand[:idx] + hand[idx + 1 :]
    new_discard = state.discard + tuple(discarded)
    drawn, new_deck, new_discard = _draw_n(state.deck, new_discard, len(card_ids), refill_rng)
    new_player = active_player.model_copy(
        update={
            "chips": active_player.chips - cost,
            "hand": hand + drawn,
        }
    )
    new_players = (
        state.players[: state.active_seat] + (new_player,) + state.players[state.active_seat + 1 :]
    )
    return _with_recomputed_labels(
        _build_tick(
            state.model_copy(
                update={
                    "players": new_players,
                    "deck": new_deck,
                    "discard": new_discard,
                }
            )
        )
    )


def play_joker(state: GameState, card: Card) -> GameState:
    """Active player attaches ``card`` (a JOKER) to the active rule (RUL-45).

    JOKERs do not fill a slot — they bind to the rule as a whole via
    ``RuleBuilder.joker_attached`` (see ``design/cards-inventory.md`` "JOKER").
    Validates phase=BUILD, an active rule exists, no joker is already attached
    (one joker per rule per design/state.md), and ``card.type is JOKER``. The
    card is removed from the active player's hand by id+identity. Advances the
    build turn like any other play.

    Resolution semantics (consumed by :func:`enter_resolve` / DOUBLE wrapper
    in :func:`effects.resolve_if_rule`):

    * ``JOKER:PERSIST_WHEN`` — promote rule to WHEN and lodge in
      ``persistent_rules`` after this round's effect fires.
    * ``JOKER:PERSIST_WHILE`` — same, with WHILE.
    * ``JOKER:DOUBLE`` — dispatched effect runs twice on the matching scope.
    * ``JOKER:ECHO`` — promote to a one-shot WHEN so the rule re-evaluates at
      the next resolve's WHEN-trigger check.
    """
    if state.phase is not Phase.BUILD:
        raise ValueError(f"play_joker requires phase=BUILD, got {state.phase}")
    if state.active_rule is None:
        raise ValueError("play_joker called with no active_rule")
    if card.type is not CardType.JOKER:
        raise ValueError(f"play_joker requires a JOKER card, got type={card.type}")
    rule = state.active_rule
    if rule.joker_attached is not None:
        raise ValueError("active_rule already has a JOKER attached")
    if card.name not in _JOKER_VARIANTS:
        raise ValueError(f"unknown JOKER variant {card.name!r}")

    new_rule = rule.model_copy(update={"joker_attached": card})
    active_player = state.players[state.active_seat]
    new_play = Play(player_id=active_player.id, card=card, slot="JOKER")
    new_rule = new_rule.model_copy(update={"plays": rule.plays + (new_play,)})
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


def _draw_effect_card(
    effect_deck: tuple[Card, ...],
    effect_discard: tuple[Card, ...],
    rng: random.Random | None,
) -> tuple[Card | None, tuple[Card, ...], tuple[Card, ...]]:
    """Pop the top card from ``effect_deck``; recycle ``effect_discard`` if empty.

    Returns ``(drawn_card_or_None, new_effect_deck, new_effect_discard)``. When
    both piles are empty, the drawn card is ``None`` and both piles stay empty
    (per design/effects-inventory.md "Deck-empty reshuffle"). The recycle
    shuffles ``effect_discard`` into ``effect_deck`` via ``rng`` and resets the
    discard to empty before popping — mirrors :func:`_refill_hands`'s deck
    refill so seeded games stay reproducible. ``rng=None`` is tolerated when
    the recycle does not trigger; reaching it without one raises ``ValueError``
    (RUL-54).
    """
    deck = list(effect_deck)
    discard = list(effect_discard)
    if not deck:
        if not discard:
            return None, (), ()
        if rng is None:
            raise ValueError("seeded rng required to recycle effect_discard into effect_deck")
        deck = discard
        rng.shuffle(deck)
        discard = []
    drawn = deck.pop()
    return drawn, tuple(deck), tuple(discard)


# RUL-51: number of SHOP offers drawn face-up per shop round per
# `design/state.md` Phase: shop step 1 ("Draw 4 special cards…").
_SHOP_OFFER_SIZE: int = 4


def _draw_shop_offers(
    pool: tuple[ShopOffer, ...],
    discard: tuple[ShopOffer, ...],
    rng: random.Random | None,
    k: int = _SHOP_OFFER_SIZE,
) -> tuple[tuple[ShopOffer, ...], tuple[ShopOffer, ...], tuple[ShopOffer, ...]]:
    """Pop up to ``k`` offers from ``pool``; recycle ``discard`` if empty.

    Returns ``(drawn_offers, new_pool, new_discard)``. When both piles are
    empty, returns ``((), (), ())``. The recycle shuffles ``discard`` into
    the pool via ``rng`` and resets the discard before continuing — mirrors
    :func:`_draw_effect_card` so seeded games stay reproducible. ``rng=None``
    is tolerated when the recycle does not trigger; reaching it without one
    raises ``ValueError`` (RUL-54 conditional-substrate rule).
    """
    pool_list = list(pool)
    discard_list = list(discard)
    drawn: list[ShopOffer] = []
    while len(drawn) < k:
        if not pool_list:
            if not discard_list:
                break
            if rng is None:
                raise ValueError("seeded rng required to recycle shop_discard into shop_pool")
            pool_list = discard_list
            rng.shuffle(pool_list)
            discard_list = []
        drawn.append(pool_list.pop())
    return tuple(drawn), tuple(pool_list), tuple(discard_list)


def _draw_n(
    deck: tuple[Card, ...],
    discard: tuple[Card, ...],
    n: int,
    rng: random.Random | None,
) -> tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]]:
    """Draw ``n`` cards from ``deck``; recycle ``discard`` when the deck empties.

    Returns ``(drawn, new_deck, new_discard)``. When both piles are empty mid-
    draw, returns fewer than ``n`` cards rather than raising. The recycle
    shuffles ``discard`` into the deck via ``rng`` and resets the discard —
    mirrors :func:`_refill_hands`'s recycle so seeded games stay reproducible.
    ``rng=None`` is tolerated when the recycle does not trigger; reaching it
    without one raises ``ValueError`` (RUL-54 conditional-substrate rule).
    """
    deck_list = list(deck)
    discard_list = list(discard)
    drawn: list[Card] = []
    while len(drawn) < n:
        if not deck_list:
            if not discard_list:
                break
            if rng is None:
                raise ValueError("seeded rng required to recycle discard into deck")
            deck_list = discard_list
            rng.shuffle(deck_list)
            discard_list = []
        drawn.append(deck_list.pop())
    return tuple(drawn), tuple(deck_list), tuple(discard_list)


def _refill_hands(state: GameState, rng: random.Random | None) -> GameState:
    """Step 12: refill each player's hand to ``HAND_SIZE``.

    When ``state.deck`` empties mid-refill, shuffles ``state.discard`` back into
    the deck via ``rng`` and continues. If both deck and discard are empty,
    stops drawing for that player (hand stays under ``HAND_SIZE`` until cards
    return to the discard pile next round). ``rng=None`` is tolerated when the
    reshuffle does not trigger; reaching it without one raises ``ValueError``
    (RUL-54).
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
                if rng is None:
                    raise ValueError("seeded rng required to recycle discard into deck")
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
    """Rule failed: discard fragments, rotate dealer, return to ROUND_START.

    The round's revealed_effect (drawn at the prior round_start step 6) is
    pushed to effect_discard alongside the fragments — design/effects-
    inventory.md "Rule-failure interaction (decided: discard)".
    """
    rule = state.active_rule
    discarded = (
        tuple(s.filled_by for s in rule.slots if s.filled_by is not None)
        if rule is not None
        else ()
    )
    consumed_effect = state.revealed_effect
    new_effect_discard = (
        state.effect_discard + (consumed_effect,)
        if consumed_effect is not None
        else state.effect_discard
    )
    new_dealer = (state.dealer_seat + 1) % PLAYER_COUNT
    return state.model_copy(
        update={
            "phase": Phase.ROUND_START,
            "active_rule": None,
            "discard": state.discard + discarded,
            "effect_discard": new_effect_discard,
            "dealer_seat": new_dealer,
            "build_turns_taken": 0,
            "revealed_effect": None,
        }
    )


def _check_winner(players: tuple[Player, ...]) -> Player | None:
    """Step 9: first player at or above ``VP_TO_WIN`` wins. Tie-break deferred."""
    for p in players:
        if p.vp >= VP_TO_WIN:
            return p
    return None

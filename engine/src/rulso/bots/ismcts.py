"""ISMCTS spike — minimal smart bot for the M4 design-signal pivot.

Information Set Monte Carlo Tree Search at its leanest. Per BUILD-phase
turn, for every action returned by :func:`legality.enumerate_legal_actions`:

  1. Sample one opponent-hand assignment (uniform over cards-not-known-to-
     be-elsewhere — see :func:`_sample_opponent_hands`).
  2. Apply the candidate action against the sampled state.
  3. Roll out via :mod:`rulso.bots.random` to game end or
     ``max_rollout_rounds`` cap, whichever comes first.
  4. Score the rollout +1 if the active player wins, 0 otherwise.

Repeat steps 1-4 :data:`DEFAULT_ROLLOUTS` times per action; pick max-mean-
score action; tie-break by lowest action index (deterministic given the
same input rng). Pass-through to :mod:`rulso.bots.random` for SHOP / dice /
non-BUILD turns — the spike's question is "does smart BUILD play beat
random?", everything else is iteration-ticket scope.

Substrate-gap caveat (RUL-43): :func:`legality._enumerate_plays` skips
operator MODIFIERs (``BUT`` / ``AND`` / ``OR`` / ``MORE_THAN`` /
``AT_LEAST``) because no ``play_operator`` action shape exists. ISMCTS
inherits this skip — until the substrate gap closes, operator MODIFIERs
remain dead weight in the deck regardless of bot strength. Tracked as a
substrate follow-up in the RUL-76 hand-back.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from rulso.bots import random as random_bot
from rulso.legality import (
    Action,
    DiscardRedraw,
    Pass,
    PlayCard,
    PlayJoker,
    enumerate_legal_actions,
)
from rulso.rules import (
    advance_phase,
    apply_shop_purchase,
    discard_redraw,
    pass_turn,
    play_card,
    play_joker,
    shop_purchase_order,
)
from rulso.state import GameState, Phase, Player

DEFAULT_ROLLOUTS: int = 25
"""Per-action rollout count.

The RUL-76 hand-over specified 50 as the working baseline; the spike's
first smoke (2 games, 50 rollouts, bots.random opponents) clocked
~190s/game — ~200× over the gate's 0.9s/game budget. Stop-condition (b)
authorises dropping the default to 25 without re-handing-back, halving
runtime while keeping the ±10pp standard error on per-action win-rate
estimates inside the noise the strength-assertion (≥55%) already tolerates.

Speed is still the dominant follow-up — see hand-back. Rollout-count
tuning sweep is in the spike's out-of-scope list; the iteration ticket
post-spike chooses the production constant from a 10/25/50/100/200 sweep
informed by strength-vs-cost tradeoff data."""

DEFAULT_MAX_ROLLOUT_ROUNDS: int = 200
"""Hard cap on rollout rounds. Matches the simulate-harness default; protects
against pathological JOKER:ECHO chains or never-terminating WHILE loops."""

# Mirror the catalogue in :mod:`rulso.simulate` — operator-only comparators
# need a dice roll baked at play time. Pulled local to avoid importing
# ``rulso.simulate`` (which would create a heavyweight dependency on the
# observer machinery just to read one frozenset).
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})


def choose_action(
    state: GameState,
    player_id: str,
    rng: random.Random,
    *,
    rollouts: int = DEFAULT_ROLLOUTS,
    max_rollout_rounds: int = DEFAULT_MAX_ROLLOUT_ROUNDS,
) -> Action:
    """Return the action with the highest sampled win-rate for ``player_id``.

    Deterministic: same ``rng`` state in → same action out. Sub-rngs for
    each rollout are derived from ``rng`` via :func:`random.Random.randint`,
    so rollouts are independent yet replayable.

    Non-BUILD phases fall through to :func:`rulso.bots.random.choose_action`
    (the spike's scope is BUILD-phase action selection only — SHOP and dice
    decisions are iteration-ticket territory).
    """
    if state.phase is not Phase.BUILD:
        return random_bot.choose_action(state, player_id, rng)
    player = _find_player(state, player_id)
    legal = enumerate_legal_actions(state, player)
    if not legal:
        return Pass()
    # No need to roll out when there's nothing to choose between — common in
    # forced situations (e.g. one playable card matching the only open slot,
    # chips below DISCARD_COST). Cheap optimisation; nontrivial fraction of
    # turns hit this in practice.
    if len(legal) == 1:
        return legal[0]

    best_idx = 0
    best_wins = -1
    for i, action in enumerate(legal):
        wins = 0
        for _ in range(rollouts):
            seed = rng.randint(0, 2**31 - 1)
            sub_rng = random.Random(seed)
            sampled = _sample_opponent_hands(state, player_id, sub_rng)
            try:
                applied = _apply_build_action(sampled, action, sub_rng)
            except ValueError:
                # An action that's legal in the original state but invalid
                # against the sampled state (e.g. duplicate card_id in the
                # reshuffled hand): skip the rollout. Treated as a non-win.
                continue
            winner = _rollout(applied, sub_rng, max_rollout_rounds)
            if winner == player_id:
                wins += 1
        if wins > best_wins:
            best_wins = wins
            best_idx = i
    return legal[best_idx]


def _find_player(state: GameState, player_id: str) -> Player:
    for p in state.players:
        if p.id == player_id:
            return p
    raise ValueError(f"unknown player {player_id!r}")


def _sample_opponent_hands(
    state: GameState, active_player_id: str, rng: random.Random
) -> GameState:
    """Re-deal opponent hands uniformly from the pool of unseen cards.

    The active player's hand is preserved; every other player's hand plus
    the current ``state.deck`` are pooled, shuffled, and re-dealt to the
    same hand-size shape. The leftover goes back to ``state.deck``.

    This is the standard ISMCTS information-set sampling step: from the
    active player's perspective, any opponent could be holding any card
    not in the active hand and not visible elsewhere. Discard, slots, and
    persistent rules are already accounted for — they aren't part of the
    pool because they're already excluded from ``state.deck`` and from
    opponent hands by the engine's normal play flow.
    """
    pool: list = list(state.deck)
    for p in state.players:
        if p.id != active_player_id:
            pool.extend(p.hand)
    rng.shuffle(pool)
    cursor = 0
    new_players: list[Player] = []
    for p in state.players:
        if p.id == active_player_id:
            new_players.append(p)
            continue
        n = len(p.hand)
        new_hand = tuple(pool[cursor : cursor + n])
        cursor += n
        new_players.append(p.model_copy(update={"hand": new_hand}))
    new_deck = tuple(pool[cursor:])
    return state.model_copy(update={"players": tuple(new_players), "deck": new_deck})


def _apply_build_action(state: GameState, action: Action, rng: random.Random) -> GameState:
    """Apply ``action`` to a BUILD-phase ``state``; mirror ``simulate._drive_build_turn``.

    Resolves OP-only comparator dice rolls at play time per ADR-0002 (the
    legality enumeration picks the dice mode; the actual rolled N is drawn
    here against the same ``rng`` driving the rollout).
    """
    active = state.players[state.active_seat]
    if isinstance(action, PlayCard):
        card = _find_hand_card(active, action.card_id)
        dice_mode: int | None = None
        dice_roll: int | None = None
        if card.name in _OP_ONLY_COMPARATOR_NAMES and action.dice in (1, 2):
            dice_mode = action.dice
            dice_roll = sum(rng.randint(1, 6) for _ in range(dice_mode))
        return play_card(state, card, action.slot, dice_mode=dice_mode, dice_roll=dice_roll)
    if isinstance(action, PlayJoker):
        card = _find_hand_card(active, action.card_id)
        return play_joker(state, card)
    if isinstance(action, DiscardRedraw):
        return discard_redraw(state, active.id, action.card_ids, refill_rng=rng)
    if isinstance(action, Pass):
        return pass_turn(state)
    raise ValueError(f"unhandled action {type(action).__name__}")


def _find_hand_card(player: Player, card_id: str):
    for card in player.hand:
        if card.id == card_id:
            return card
    raise ValueError(f"card {card_id!r} not in {player.id!r} hand")


def _rollout(state: GameState, rng: random.Random, max_rounds: int) -> str | None:
    """Drive ``state`` to END with random-bot play; return winner id or ``None``.

    Same phase-dispatch shape as :func:`rulso.simulate._play_one_game` minus
    observers and metrics. A single ``rng`` services every random draw — the
    rollout is variance, not the canonical record, so the disjoint-rng
    discipline isn't load-bearing inside this loop.
    """
    rounds = 0
    while state.phase is not Phase.END:
        if state.phase is Phase.ROUND_START:
            if rounds >= max_rounds:
                return None
            rounds += 1
            state = advance_phase(state, rng=rng)
        elif state.phase is Phase.BUILD:
            active = state.players[state.active_seat]
            action = random_bot.choose_action(state, active.id, rng)
            state = _apply_build_action(state, action, rng)
        elif state.phase is Phase.RESOLVE:
            state = advance_phase(state, rng=rng)
        elif state.phase is Phase.SHOP:
            for pid in shop_purchase_order(state):
                idx = random_bot.select_purchase(state, pid, rng)
                if idx is None:
                    continue
                state = apply_shop_purchase(state, pid, idx)
            state = advance_phase(state, rng=rng)
        else:
            return None
    return state.winner.id if state.winner is not None else None


# SHOP bot delegate — pass-through to bots.random per the spike's scope.
# The driver in :mod:`rulso.simulate` looks up the per-bot SHOP function
# via this name, mirroring the ``choose_action`` lookup.
select_purchase: Callable[[GameState, str, random.Random], int | None] = random_bot.select_purchase

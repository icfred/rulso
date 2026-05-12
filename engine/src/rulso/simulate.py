"""Bot-vs-bot simulation harness — quantitative design signal.

Runs N self-play games with the random-legal bot (``rulso.bots.random``),
collects metrics by wrapping engine entry points as non-mutating observers,
and emits a structured JSON dump + terminal summary. No engine state is
mutated; wrappers forward arguments unchanged and restore originals on
teardown (same pattern as ``tests/test_m2_watchable.py``).

Public surface:

* :func:`simulate` — run N games, return :class:`SimResults`.
* :func:`format_summary` — render :class:`SimResults` as a terminal summary.
* :func:`run` — CLI entry: parse args, call :func:`simulate`, dump JSON and/or
  print summary. Wired in :mod:`rulso.cli` as the ``simulate`` subcommand.

Determinism (RUL-54 disjoint-rng pattern):
    Per seed ``s`` the four rngs are
    ``random.Random(s) / s ^ 0x5EED / s ^ 0xD1CE / s ^ 0xEFFC``. Same
    ``seed_base`` + same ``games`` ⇒ byte-identical JSON output.

Observation points (all wrapped, all restored):

* ``effects.dispatch_effect`` → effect fire histogram (per ``Card.id``)
* ``effects.resolve_if_rule`` → rule-effect VP attribution (delta of total VP)
* ``goals._resolve_one_goal`` → goal-claim histogram + goal VP attribution
* ``status.apply_burn`` / ``apply_mute`` / ``apply_blessed`` / ``apply_marked`` /
  ``apply_chained`` → apply counters per token
* ``status.clear_burn`` / ``clear_chained`` → explicit-clear counters
* ``status.consume_blessed_or_else`` → BLESSED clear counter (consumed)
* ``status.tick_round_start`` / ``tick_resolve_end`` → decay counters
  (BURN tick, MUTE/MARKED natural lifetime clears)

JSON schema lives in ``docs/engine/simulate.md``.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TextIO

from rulso import cards as cards_module
from rulso import effects, goals, status
from rulso.bots.random import choose_action, select_purchase
from rulso.legality import DiscardRedraw, Pass, PlayCard, PlayJoker
from rulso.rules import (
    advance_phase,
    apply_shop_purchase,
    discard_redraw,
    pass_turn,
    play_card,
    play_joker,
    shop_purchase_order,
    start_game,
)
from rulso.state import PLAYER_COUNT, Card, GameState, Phase, Player

_DEFAULT_GAMES: int = 1000
_DEFAULT_SEED_BASE: int = 0
_DEFAULT_ROUNDS: int = 200
_DEFAULT_DUMP_PATH: str = "simulate.json"

# Mirror cli._OP_ONLY_COMPARATOR_NAMES — kept local to avoid importing cli
# (which would pull in argparse for every simulate invocation that imports
# this module from a test).
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})

_STATUS_TOKENS: tuple[str, ...] = ("BURN", "MUTE", "BLESSED", "MARKED", "CHAINED")
_JOKER_VARIANTS: tuple[str, ...] = (
    "JOKER:PERSIST_WHEN",
    "JOKER:PERSIST_WHILE",
    "JOKER:DOUBLE",
    "JOKER:ECHO",
)

# Anomaly thresholds — tunable as design matures. Documented in
# ``docs/engine/simulate.md`` so playtesters know what each flag means.
#
# Cap-hit threshold sits above the current M2 baseline (~36% under random
# bots; the M2 smoke pins 6/10 winners = 40% cap-hit at N=10). Tightens
# as ISMCTS (M4) replaces random bots and the steady-state cap-hit rate
# drops. Below 50% is healthy at the bots.random tier; above means the
# deck/cap stalled rather than landed.
_WINNER_SKEW_FACTOR: float = 2.0
_CAP_HIT_WARN_FRACTION: float = 0.50


# --- Data classes -----------------------------------------------------------


@dataclass
class _GameResult:
    """Per-game stats — one row per simulated game."""

    seed: int
    winner_seat: int | None
    rounds_started: int
    cap_hit: bool
    final_chips: tuple[int, ...]
    card_plays: Counter[str] = field(default_factory=Counter)
    joker_plays: Counter[str] = field(default_factory=Counter)
    effect_draws: Counter[str] = field(default_factory=Counter)
    effect_fires: Counter[str] = field(default_factory=Counter)
    goal_claims: Counter[str] = field(default_factory=Counter)
    rule_vp: int = 0
    goal_vp: int = 0
    status_apply: Counter[str] = field(default_factory=Counter)
    status_clear: Counter[str] = field(default_factory=Counter)
    status_decay: Counter[str] = field(default_factory=Counter)


@dataclass
class SimResults:
    """Aggregated simulation output. Serialised by :func:`to_json_dict`."""

    config: dict[str, int]
    catalogue: dict[str, tuple[str, ...]]
    per_game: tuple[_GameResult, ...]


# --- Observer ---------------------------------------------------------------


class _Observer:
    """Mutable counter sink shared with patched engine functions.

    Each game resets the ``current`` slot to a fresh :class:`_GameResult`
    before play; patched wrappers write into ``current`` directly. After the
    game completes the caller pulls ``current`` out and stashes it in the
    per-game list.
    """

    def __init__(self) -> None:
        self.current: _GameResult | None = None

    def _gr(self) -> _GameResult:
        gr = self.current
        if gr is None:
            raise AssertionError("observer called outside a game")
        return gr


def _patch_engine(obs: _Observer) -> dict[str, Any]:
    """Install observer wrappers. Returns the originals for :func:`_unpatch_engine`."""
    originals: dict[str, Any] = {
        "dispatch_effect": effects.dispatch_effect,
        "resolve_if_rule": effects.resolve_if_rule,
        "resolve_one_goal": goals._resolve_one_goal,
        "apply_burn": status.apply_burn,
        "apply_mute": status.apply_mute,
        "apply_blessed": status.apply_blessed,
        "apply_marked": status.apply_marked,
        "apply_chained": status.apply_chained,
        "clear_burn": status.clear_burn,
        "clear_chained": status.clear_chained,
        "consume_blessed_or_else": status.consume_blessed_or_else,
        "tick_round_start": status.tick_round_start,
        "tick_resolve_end": status.tick_resolve_end,
    }

    orig_dispatch = originals["dispatch_effect"]
    orig_resolve_if = originals["resolve_if_rule"]
    orig_resolve_one_goal = originals["resolve_one_goal"]
    orig_apply_burn = originals["apply_burn"]
    orig_apply_mute = originals["apply_mute"]
    orig_apply_blessed = originals["apply_blessed"]
    orig_apply_marked = originals["apply_marked"]
    orig_apply_chained = originals["apply_chained"]
    orig_clear_burn = originals["clear_burn"]
    orig_clear_chained = originals["clear_chained"]
    orig_consume = originals["consume_blessed_or_else"]
    orig_tick_round_start = originals["tick_round_start"]
    orig_tick_resolve_end = originals["tick_resolve_end"]

    def wrapped_dispatch(
        state: GameState, revealed_effect: Card | None, scope: frozenset[str]
    ) -> GameState:
        out = orig_dispatch(state, revealed_effect, scope)
        if revealed_effect is not None and out is not state:
            obs._gr().effect_fires[revealed_effect.id] += 1
        return out

    def wrapped_resolve_if(
        state: GameState,
        rule: Any,
        labels_map: dict[str, frozenset[str]] | None = None,
    ) -> GameState:
        before = sum(p.vp for p in state.players)
        out = orig_resolve_if(state, rule, labels_map)
        delta = sum(p.vp for p in out.players) - before
        if delta:
            obs._gr().rule_vp += delta
        return out

    def wrapped_resolve_one_goal(state: GameState, index: int, goal: Any) -> GameState:
        before = sum(p.vp for p in state.players)
        out = orig_resolve_one_goal(state, index, goal)
        delta = sum(p.vp for p in out.players) - before
        if delta > 0:
            obs._gr().goal_claims[goal.id] += 1
            obs._gr().goal_vp += delta
        return out

    def wrapped_apply_burn(player: Player, magnitude: int = 1) -> Player:
        obs._gr().status_apply["BURN"] += magnitude
        return orig_apply_burn(player, magnitude)

    def wrapped_apply_mute(player: Player) -> Player:
        if not player.status.mute:
            obs._gr().status_apply["MUTE"] += 1
        return orig_apply_mute(player)

    def wrapped_apply_blessed(player: Player) -> Player:
        if not player.status.blessed:
            obs._gr().status_apply["BLESSED"] += 1
        return orig_apply_blessed(player)

    def wrapped_apply_marked(player: Player) -> Player:
        if not player.status.marked:
            obs._gr().status_apply["MARKED"] += 1
        return orig_apply_marked(player)

    def wrapped_apply_chained(player: Player) -> Player:
        if not player.status.chained:
            obs._gr().status_apply["CHAINED"] += 1
        return orig_apply_chained(player)

    def wrapped_clear_burn(player: Player) -> Player:
        if player.status.burn > 0:
            obs._gr().status_clear["BURN"] += 1
        return orig_clear_burn(player)

    def wrapped_clear_chained(player: Player) -> Player:
        if player.status.chained:
            obs._gr().status_clear["CHAINED"] += 1
        return orig_clear_chained(player)

    def wrapped_consume(player: Player, loss: int) -> Player:
        if player.status.blessed:
            obs._gr().status_clear["BLESSED"] += 1
        return orig_consume(player, loss)

    def wrapped_tick_round_start(player: Player) -> Player:
        if player.status.burn > 0:
            obs._gr().status_decay["BURN"] += player.status.burn
        if player.status.mute:
            obs._gr().status_decay["MUTE"] += 1
        return orig_tick_round_start(player)

    def wrapped_tick_resolve_end(player: Player) -> Player:
        if player.status.marked:
            obs._gr().status_decay["MARKED"] += 1
        return orig_tick_resolve_end(player)

    effects.dispatch_effect = wrapped_dispatch
    effects.resolve_if_rule = wrapped_resolve_if
    goals._resolve_one_goal = wrapped_resolve_one_goal
    status.apply_burn = wrapped_apply_burn
    status.apply_mute = wrapped_apply_mute
    status.apply_blessed = wrapped_apply_blessed
    status.apply_marked = wrapped_apply_marked
    status.apply_chained = wrapped_apply_chained
    status.clear_burn = wrapped_clear_burn
    status.clear_chained = wrapped_clear_chained
    status.consume_blessed_or_else = wrapped_consume
    status.tick_round_start = wrapped_tick_round_start
    status.tick_resolve_end = wrapped_tick_resolve_end
    return originals


def _unpatch_engine(originals: dict[str, Any]) -> None:
    effects.dispatch_effect = originals["dispatch_effect"]
    effects.resolve_if_rule = originals["resolve_if_rule"]
    goals._resolve_one_goal = originals["resolve_one_goal"]
    status.apply_burn = originals["apply_burn"]
    status.apply_mute = originals["apply_mute"]
    status.apply_blessed = originals["apply_blessed"]
    status.apply_marked = originals["apply_marked"]
    status.apply_chained = originals["apply_chained"]
    status.clear_burn = originals["clear_burn"]
    status.clear_chained = originals["clear_chained"]
    status.consume_blessed_or_else = originals["consume_blessed_or_else"]
    status.tick_round_start = originals["tick_round_start"]
    status.tick_resolve_end = originals["tick_resolve_end"]


def _patch_cards_cache() -> dict[str, Any]:
    """Cache ``cards.load_*`` outputs for the duration of one sim run.

    Profile baseline (RUL-74): ``cards._read`` was called 889 times per
    10 games (87% of runtime spent re-parsing ``design/cards.yaml`` from
    ``rules._draw_condition_template``). The catalogue is immutable
    across a sim run, so wrap each loader in a closure returning the
    once-computed value and restore the originals on teardown. Same
    observer-pattern shape as :func:`_patch_engine` — no permanent
    module-level state.

    The cache lives only inside this function's scope; the returned
    ``originals`` dict is the only handle to it. ``_unpatch_cards_cache``
    restores the real loaders, dropping the cache as the closure
    references go out of scope.
    """
    cached_conditions = cards_module.load_condition_templates()
    cached_effects = cards_module.load_effect_cards()
    cached_goals = cards_module.load_goal_cards()
    cached_shop = cards_module.load_shop_offers()
    cached_main = cards_module.load_cards()
    cached_decks = cards_module.build_default_deck()

    originals: dict[str, Any] = {
        "load_condition_templates": cards_module.load_condition_templates,
        "load_effect_cards": cards_module.load_effect_cards,
        "load_goal_cards": cards_module.load_goal_cards,
        "load_shop_offers": cards_module.load_shop_offers,
        "load_cards": cards_module.load_cards,
        "build_default_deck": cards_module.build_default_deck,
    }
    cards_module.load_condition_templates = lambda path=None: cached_conditions
    cards_module.load_effect_cards = lambda path=None: cached_effects
    cards_module.load_goal_cards = lambda path=None: cached_goals
    cards_module.load_shop_offers = lambda path=None: cached_shop
    cards_module.load_cards = lambda path=None: cached_main
    cards_module.build_default_deck = lambda cards=None, *, path=None: cached_decks
    return originals


def _unpatch_cards_cache(originals: dict[str, Any]) -> None:
    cards_module.load_condition_templates = originals["load_condition_templates"]
    cards_module.load_effect_cards = originals["load_effect_cards"]
    cards_module.load_goal_cards = originals["load_goal_cards"]
    cards_module.load_shop_offers = originals["load_shop_offers"]
    cards_module.load_cards = originals["load_cards"]
    cards_module.build_default_deck = originals["build_default_deck"]


# --- Game runner ------------------------------------------------------------


def _play_one_game(seed: int, max_rounds: int, obs: _Observer) -> _GameResult:
    """Run one bot-vs-bot game; return per-game stats.

    Mirrors :func:`rulso.cli.run_game` minus the line-oriented narration —
    same engine entry points, same disjoint-rng disposition (RUL-54). The
    observer accumulates engine-level metrics via the wrappers installed by
    :func:`_patch_engine`; the loop here is responsible for the metrics that
    only the driver sees (card plays, joker plays, effect draws, winner seat,
    rounds started).
    """
    rng = random.Random(seed)
    refill_rng = random.Random(seed ^ 0x5EED)
    dice_rng = random.Random(seed ^ 0xD1CE)
    effect_rng = random.Random(seed ^ 0xEFFC)
    state = start_game(seed)

    gr = _GameResult(
        seed=seed,
        winner_seat=None,
        rounds_started=0,
        cap_hit=False,
        final_chips=(),
    )
    obs.current = gr

    rounds_started = 0
    seen_revealed_effect_ids: set[int] = set()  # python ids of Card instances counted

    while state.phase is not Phase.END:
        if state.phase is Phase.ROUND_START:
            if rounds_started >= max_rounds:
                gr.cap_hit = True
                break
            rounds_started += 1
            state = advance_phase(state, rng=effect_rng)
        elif state.phase is Phase.BUILD:
            _maybe_count_effect_draw(state, gr, seen_revealed_effect_ids)
            state = _drive_build_turn(state, rng, dice_rng, refill_rng, gr)
        elif state.phase is Phase.RESOLVE:
            state = advance_phase(state, rng=refill_rng)
        elif state.phase is Phase.SHOP:
            state = _drive_shop(state, rng)
            state = advance_phase(state, rng=effect_rng)
        else:
            raise AssertionError(f"unexpected phase {state.phase!r}")

    gr.rounds_started = rounds_started
    gr.final_chips = tuple(p.chips for p in state.players)
    winner = state.winner
    gr.winner_seat = winner.seat if winner is not None else None
    obs.current = None
    return gr


def _maybe_count_effect_draw(state: GameState, gr: _GameResult, seen_ids: set[int]) -> None:
    eff = state.revealed_effect
    if eff is None:
        return
    key = id(eff)
    if key in seen_ids:
        return
    seen_ids.add(key)
    gr.effect_draws[eff.id] += 1


def _drive_build_turn(
    state: GameState,
    rng: random.Random,
    dice_rng: random.Random,
    refill_rng: random.Random,
    gr: _GameResult,
) -> GameState:
    active_player = state.players[state.active_seat]
    action = choose_action(state, active_player.id, rng)
    if isinstance(action, PlayCard):
        card = _find_hand_card(active_player, action.card_id)
        gr.card_plays[card.id] += 1
        dice_mode: int | None = None
        dice_roll: int | None = None
        if card.name in _OP_ONLY_COMPARATOR_NAMES and action.dice in (1, 2):
            dice_mode = action.dice
            dice_roll = sum(dice_rng.randint(1, 6) for _ in range(dice_mode))
        return play_card(state, card, action.slot, dice_mode=dice_mode, dice_roll=dice_roll)
    if isinstance(action, DiscardRedraw):
        return discard_redraw(state, active_player.id, action.card_ids, refill_rng=refill_rng)
    if isinstance(action, Pass):
        return pass_turn(state)
    if isinstance(action, PlayJoker):
        card = _find_hand_card(active_player, action.card_id)
        gr.card_plays[card.id] += 1
        gr.joker_plays[card.name] += 1
        return play_joker(state, card)
    raise AssertionError(f"unhandled action variant {type(action).__name__}")


def _drive_shop(state: GameState, rng: random.Random) -> GameState:
    order = shop_purchase_order(state)
    for player_id in order:
        offer_index = select_purchase(state, player_id, rng)
        if offer_index is None:
            continue
        state = apply_shop_purchase(state, player_id, offer_index)
    return state


def _find_hand_card(player: Player, card_id: str) -> Card:
    for card in player.hand:
        if card.id == card_id:
            return card
    raise ValueError(f"card {card_id!r} not in {player.id} hand")


# --- Public entry -----------------------------------------------------------


def simulate(
    *,
    games: int = _DEFAULT_GAMES,
    seed_base: int = _DEFAULT_SEED_BASE,
    max_rounds: int = _DEFAULT_ROUNDS,
) -> SimResults:
    """Run ``games`` self-play games and return aggregated stats.

    Deterministic: same ``games`` + ``seed_base`` + ``max_rounds`` produce
    byte-identical output (per the disjoint-rng pattern). Patches engine
    entry points for observation and restores them in a ``finally`` block;
    raises propagate after restoration so a partial run does not leave the
    engine wedged.
    """
    if games <= 0:
        raise ValueError(f"games must be > 0, got {games}")
    if max_rounds <= 0:
        raise ValueError(f"max_rounds must be > 0, got {max_rounds}")

    catalogue = _load_catalogue()
    obs = _Observer()
    engine_originals = _patch_engine(obs)
    cards_originals = _patch_cards_cache()
    per_game: list[_GameResult] = []
    try:
        for i in range(games):
            seed = seed_base + i
            per_game.append(_play_one_game(seed, max_rounds, obs))
    finally:
        _unpatch_cards_cache(cards_originals)
        _unpatch_engine(engine_originals)

    return SimResults(
        config={
            "games": games,
            "seed_base": seed_base,
            "max_rounds": max_rounds,
        },
        catalogue=catalogue,
        per_game=tuple(per_game),
    )


def _load_catalogue() -> dict[str, tuple[str, ...]]:
    """Load the card / effect / goal id catalogue for zero-occurrence flagging."""
    cards = cards_module.load_cards()
    effects_cards = cards_module.load_effect_cards()
    goal_cards = cards_module.load_goal_cards()
    return {
        "cards": tuple(sorted({c.id for c in cards})),
        "effects": tuple(sorted({c.id for c in effects_cards})),
        "goals": tuple(sorted(g.id for g in goal_cards)),
    }


# --- Aggregation + JSON -----------------------------------------------------


def to_json_dict(results: SimResults) -> dict[str, Any]:
    """Serialise :class:`SimResults` to a JSON-friendly nested dict.

    Schema is documented in ``docs/engine/simulate.md``. Counter values are
    flattened to ``dict[str, int]`` with id-sorted keys so the JSON is
    deterministic.
    """
    per_game = results.per_game
    cfg = results.config
    catalogue = results.catalogue
    n_games = len(per_game)

    winner_seats = [g.winner_seat for g in per_game if g.winner_seat is not None]
    cap_hits = sum(1 for g in per_game if g.cap_hit)
    by_seat: dict[str, int] = {}
    for seat in winner_seats:
        by_seat[str(seat)] = by_seat.get(str(seat), 0) + 1
    winners = len(winner_seats)

    lengths = [g.rounds_started for g in per_game]

    card_usage = _merge_counters(g.card_plays for g in per_game)
    effect_fires = _merge_counters(g.effect_fires for g in per_game)
    effect_draws = _merge_counters(g.effect_draws for g in per_game)
    goal_claims = _merge_counters(g.goal_claims for g in per_game)
    joker_plays = _merge_counters(g.joker_plays for g in per_game)

    status_apply = _merge_counters(g.status_apply for g in per_game)
    status_clear = _merge_counters(g.status_clear for g in per_game)
    status_decay = _merge_counters(g.status_decay for g in per_game)

    chip_pool: list[int] = []
    for g in per_game:
        chip_pool.extend(g.final_chips)

    rule_vp_all = sum(g.rule_vp for g in per_game)
    goal_vp_all = sum(g.goal_vp for g in per_game)
    rule_vp_won = sum(g.rule_vp for g in per_game if g.winner_seat is not None)
    goal_vp_won = sum(g.goal_vp for g in per_game if g.winner_seat is not None)

    effect_rate: dict[str, dict[str, int | float]] = {}
    for eff_id in catalogue["effects"]:
        drawn = effect_draws.get(eff_id, 0)
        fired = effect_fires.get(eff_id, 0)
        effect_rate[eff_id] = {
            "drawn": drawn,
            "fired": fired,
            "fire_rate": (fired / drawn) if drawn else 0.0,
        }

    joker_rate: dict[str, int] = {
        variant: joker_plays.get(variant, 0) for variant in _JOKER_VARIANTS
    }

    status_block: dict[str, dict[str, int]] = {}
    for tok in _STATUS_TOKENS:
        status_block[tok] = {
            "apply": status_apply.get(tok, 0),
            "clear": status_clear.get(tok, 0),
            "decay": status_decay.get(tok, 0),
        }

    out: dict[str, Any] = {
        "config": dict(cfg),
        "winner_distribution": {
            "winners": winners,
            "cap_hits": cap_hits,
            "by_seat": dict(sorted(by_seat.items(), key=lambda kv: int(kv[0]))),
        },
        "game_length": _length_stats(lengths, cap_hits, n_games),
        "card_usage": _padded_counter(card_usage, catalogue["cards"]),
        "effect_cards": effect_rate,
        "goal_claims": _padded_counter(goal_claims, catalogue["goals"]),
        "joker_attachments": joker_rate,
        "vp_attribution": {
            "all_games": {"rule_vp": rule_vp_all, "goal_vp": goal_vp_all},
            "winning_games": {"rule_vp": rule_vp_won, "goal_vp": goal_vp_won},
        },
        "status_tokens": status_block,
        "chip_economy": _chip_stats(chip_pool),
    }
    out["anomalies"] = _detect_anomalies(out, n_games)
    return out


def _merge_counters(per_game: Any) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for c in per_game:
        merged.update(c)
    return dict(sorted(merged.items()))


def _padded_counter(values: dict[str, int], catalogue: tuple[str, ...]) -> dict[str, int]:
    """Return values keyed by every catalogue id (zeros included), id-sorted."""
    out: dict[str, int] = {key: values.get(key, 0) for key in catalogue}
    for k, v in values.items():
        if k not in out:
            out[k] = v
    return dict(sorted(out.items()))


def _length_stats(lengths: Sequence[int], cap_hits: int, n_games: int) -> dict[str, float | int]:
    if not lengths:
        return {
            "min": 0,
            "max": 0,
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
            "cap_hit_rate": 0.0,
        }
    return {
        "min": min(lengths),
        "max": max(lengths),
        "mean": statistics.fmean(lengths),
        "median": statistics.median(lengths),
        "std": statistics.pstdev(lengths) if len(lengths) > 1 else 0.0,
        "cap_hit_rate": cap_hits / n_games if n_games else 0.0,
    }


def _chip_stats(chips: Sequence[int]) -> dict[str, float | int]:
    if not chips:
        return {"min": 0, "max": 0, "mean": 0.0, "median": 0.0, "std": 0.0}
    return {
        "min": min(chips),
        "max": max(chips),
        "mean": statistics.fmean(chips),
        "median": statistics.median(chips),
        "std": statistics.pstdev(chips) if len(chips) > 1 else 0.0,
    }


# --- Anomaly detection ------------------------------------------------------


def _detect_anomalies(payload: dict[str, Any], n_games: int) -> list[str]:
    """Inspect the rendered payload and return human-readable WARN strings.

    Reads the same nested dict that gets dumped to JSON so flags exactly
    track the published numbers. Thresholds are module-level constants
    (``_WINNER_SKEW_FACTOR``, ``_CAP_HIT_WARN_FRACTION``) — adjust there if
    they false-positive on healthy runs.
    """
    flags: list[str] = []

    for card_id, count in payload["card_usage"].items():
        if count == 0:
            flags.append(f"WARN: card {card_id!r} never played")
    for eff_id, row in payload["effect_cards"].items():
        if row["drawn"] == 0:
            flags.append(f"WARN: effect {eff_id!r} never drawn")
        elif row["fired"] == 0:
            flags.append(f"WARN: effect {eff_id!r} drawn {row['drawn']}x but never fired")
    for goal_id, count in payload["goal_claims"].items():
        if count == 0:
            flags.append(f"WARN: goal {goal_id!r} never claimed")

    by_seat = payload["winner_distribution"]["by_seat"]
    if by_seat:
        # Flat expectation = total winners / PLAYER_COUNT (4 seats); compare
        # against ALL seats, not just populated ones, so a 9-0-0-1 split
        # still flags as skewed (avg = 2.5, top = 9 > 5.0).
        total_winners = sum(by_seat.values())
        flat = total_winners / PLAYER_COUNT
        top_seat, top_count = max(by_seat.items(), key=lambda kv: kv[1])
        if flat > 0 and top_count > _WINNER_SKEW_FACTOR * flat:
            flags.append(
                f"WARN: winner distribution skewed — seat {top_seat} won {top_count}x "
                f"(>{_WINNER_SKEW_FACTOR:.1f}× flat expectation of {flat:.1f})"
            )

    cap_rate = payload["game_length"].get("cap_hit_rate", 0.0)
    if cap_rate > _CAP_HIT_WARN_FRACTION:
        flags.append(f"WARN: cap-hit rate {cap_rate:.0%} exceeds {_CAP_HIT_WARN_FRACTION:.0%}")

    return flags


# --- Terminal summary -------------------------------------------------------


_SUMMARY_LINE_BUDGET: int = 50
_SUMMARY_TOP_CARDS: int = 5
_SUMMARY_MAX_ANOMALIES: int = 12


def format_summary(payload: dict[str, Any]) -> str:
    """Render a ≤50-line terminal summary of the JSON payload.

    Compresses jokers and status onto single lines, caps card_usage to the
    top-N played cards plus one zero-play roll-up, and truncates the
    anomaly list with a "+N more" suffix when it overflows. The full data
    lives in the JSON dump — the summary is the at-a-glance view.
    """
    cfg = payload["config"]
    wd = payload["winner_distribution"]
    gl = payload["game_length"]
    vp = payload["vp_attribution"]
    ce = payload["chip_economy"]
    lines: list[str] = []
    lines.append(
        f"simulate: games={cfg['games']} seed_base={cfg['seed_base']} "
        f"max_rounds={cfg['max_rounds']}"
    )
    lines.append(
        f"winners: {wd['winners']}/{cfg['games']}  cap_hits={wd['cap_hits']}  "
        f"by_seat={wd['by_seat']}"
    )
    lines.append(
        f"length: min={gl['min']} median={gl['median']:.0f} mean={gl['mean']:.1f} "
        f"max={gl['max']} std={gl['std']:.1f} cap_hit_rate={gl['cap_hit_rate']:.1%}"
    )
    lines.append(
        f"vp_source: all=rule:{vp['all_games']['rule_vp']}/goal:{vp['all_games']['goal_vp']}  "
        f"won=rule:{vp['winning_games']['rule_vp']}/goal:{vp['winning_games']['goal_vp']}"
    )
    lines.append(
        f"chips_final: min={ce['min']} median={ce['median']:.0f} mean={ce['mean']:.1f} "
        f"max={ce['max']} std={ce['std']:.1f}"
    )
    jokers = payload["joker_attachments"]
    lines.append("jokers: " + "  ".join(f"{k.split(':', 1)[-1]}={v}" for k, v in jokers.items()))
    status_block = payload["status_tokens"]
    lines.append(
        "status (a/c/d): "
        + "  ".join(
            f"{tok}={row['apply']}/{row['clear']}/{row['decay']}"
            for tok, row in status_block.items()
        )
    )

    sorted_cards = sorted(payload["card_usage"].items(), key=lambda kv: (-kv[1], kv[0]))
    top = [kv for kv in sorted_cards if kv[1] > 0][:_SUMMARY_TOP_CARDS]
    zero_cards = [cid for cid, c in sorted_cards if c == 0]
    lines.append(f"card_usage (top {len(top)} / zero-play={len(zero_cards)}):")
    for cid, count in top:
        lines.append(f"  {cid}: {count}")
    if zero_cards:
        lines.append(f"  zero-play ids: {', '.join(zero_cards)}")

    lines.append("effect_cards (drawn → fired):")
    for eid, row in sorted(payload["effect_cards"].items()):
        lines.append(
            f"  {eid}: drawn={row['drawn']} fired={row['fired']} rate={row['fire_rate']:.2f}"
        )

    lines.append("goal_claims:")
    for gid, count in sorted(payload["goal_claims"].items()):
        lines.append(f"  {gid}: {count}")

    anomalies = payload.get("anomalies", [])
    if anomalies:
        shown = anomalies[:_SUMMARY_MAX_ANOMALIES]
        suffix = (
            f"  ... (+{len(anomalies) - _SUMMARY_MAX_ANOMALIES} more)"
            if len(anomalies) > _SUMMARY_MAX_ANOMALIES
            else None
        )
        lines.append(f"anomalies ({len(anomalies)}):")
        for flag in shown:
            lines.append(f"  {flag}")
        if suffix is not None:
            lines.append(suffix)
    else:
        lines.append("anomalies: none")

    if len(lines) > _SUMMARY_LINE_BUDGET:
        # Hard ceiling — should not be reached unless effect_cards / goals
        # have exploded. Keep the head and add a marker so the truncation
        # is visible rather than silent.
        kept = lines[: _SUMMARY_LINE_BUDGET - 1]
        kept.append(f"  ... (+{len(lines) - len(kept)} lines truncated)")
        lines = kept
    return "\n".join(lines)


# --- CLI -------------------------------------------------------------------


def run(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """Parse args, run the sim, write JSON + summary. Wired in :mod:`rulso.cli`."""
    if out is None:
        out = sys.stdout
    args = _parse_args(argv)
    results = simulate(
        games=args.games,
        seed_base=args.seed_base,
        max_rounds=args.rounds,
    )
    payload = to_json_dict(results)
    if args.analyse:
        with open(args.analyse, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=False)
            f.write("\n")
    if args.summary or not args.analyse:
        out.write(format_summary(payload))
        out.write("\n")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rulso simulate",
        description=("Run a bot-vs-bot simulation sweep and dump quantitative design signal."),
    )
    parser.add_argument(
        "--games",
        type=int,
        default=_DEFAULT_GAMES,
        help=f"games to play (default: {_DEFAULT_GAMES})",
    )
    parser.add_argument(
        "--seed-base",
        type=int,
        default=_DEFAULT_SEED_BASE,
        help=(f"seed for game 0 (game i uses seed_base + i; default: {_DEFAULT_SEED_BASE})"),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=_DEFAULT_ROUNDS,
        help=f"per-game round cap (default: {_DEFAULT_ROUNDS})",
    )
    parser.add_argument(
        "--analyse",
        type=str,
        default=None,
        const=_DEFAULT_DUMP_PATH,
        nargs="?",
        help=(
            "write JSON dump to PATH. Pass --analyse with no value to use "
            f"{_DEFAULT_DUMP_PATH!r}; omit the flag to skip the dump."
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help=(
            "print a terminal summary in addition to the JSON dump. "
            "Implicit when --analyse is omitted."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run())

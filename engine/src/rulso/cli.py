"""CLI runner — plays a 4-bot game and narrates each round.

Drives the M1 round-flow phase machine (``rulso.rules``) with the random-legal
bot (``rulso.bots.random``). One game per invocation; exits 0 on a winner,
non-zero on round-cap exhaustion.

Output is line-oriented ``key=value`` event records (snake_case keys, no ANSI),
greppable by event type. See ``docs/engine/cli.md`` for the schema.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Sequence
from typing import TextIO

from rulso.bots.random import DiscardRedraw, Pass, PlayCard, PlayJoker, choose_action
from rulso.rules import advance_phase, pass_turn, play_card, play_joker
from rulso.rules import start_game as _start_game
from rulso.state import (
    PLAYER_COUNT,
    Card,
    GameState,
    Phase,
    Player,
    RuleBuilder,
)

_DEFAULT_ROUNDS: int = 50
_DEFAULT_SEED: int = 0

# RUL-42 (G): OP-only comparator names per ADR-0002. CLI is the seat with the
# rng for the dice roll; rules.play_card stamps last_roll using the value we
# pass in so rules.py stays pure.
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Parses args, runs one game, returns the exit code."""
    args = _parse_args(argv)
    return run_game(seed=args.seed, max_rounds=args.rounds, out=sys.stdout)


def run_game(*, seed: int, max_rounds: int, out: TextIO) -> int:
    """Play one game; emit per-event lines to ``out``. Return 0 on win, 1 on cap-hit."""
    rng = random.Random(seed)
    refill_rng = random.Random(seed ^ 0x5EED)  # disjoint stream from bot decisions
    # RUL-42 (G): comparator dice rng — disjoint from bot decisions and refills
    # so reordering bot picks doesn't reshuffle dice rolls.
    dice_rng = random.Random(seed ^ 0xD1CE)
    state = _start_game(seed)
    _emit(out, "game_start", seed=seed, max_rounds=max_rounds, players=PLAYER_COUNT)

    rounds_started = 0
    while state.phase is not Phase.END:
        if state.phase is Phase.ROUND_START:
            if rounds_started >= max_rounds:
                _emit_standings(out, state)
                _emit(out, "cap_hit", rounds_started=rounds_started, winner="none")
                return 1
            rounds_started += 1
            prior_dealer = state.dealer_seat
            state = advance_phase(
                state
            )  # ROUND_START → BUILD or back to ROUND_START on dealer-no-seed
            if state.phase is Phase.ROUND_START:
                _narrate_dealer_seed_failure(out, state, prior_dealer)
                continue
            _narrate_round_start(out, state)
        elif state.phase is Phase.BUILD:
            prior_rule = state.active_rule
            state = _drive_build_turn(state, rng, dice_rng, out)
            if state.phase is Phase.ROUND_START:
                # Build revolution finished with unfilled slots → rule failed.
                _narrate_rule_failed(out, prior_rule, state)
        elif state.phase is Phase.RESOLVE:
            _narrate_resolve(out, state)
            state = advance_phase(state, rng=refill_rng)  # RESOLVE → ROUND_START or END
        else:
            _emit(out, "unhandled_phase", phase=state.phase.value)
            return 1

    _emit_standings(out, state)
    winner = state.winner
    _emit(
        out,
        "game_end",
        winner=winner.id if winner is not None else "none",
        winner_seat=winner.seat if winner is not None else -1,
        rounds_started=rounds_started,
    )
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rulso",
        description="Play a 4-bot Rulso game and narrate each round.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_SEED,
        help=f"RNG seed for bot decisions (default: {_DEFAULT_SEED})",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=_DEFAULT_ROUNDS,
        help=f"Round cap; non-zero exit if reached without a winner (default: {_DEFAULT_ROUNDS})",
    )
    return parser.parse_args(argv)


def _drive_build_turn(
    state: GameState,
    rng: random.Random,
    dice_rng: random.Random,
    out: TextIO,
) -> GameState:
    """Pull one bot action for the active player and apply it. Returns new state."""
    active_player = state.players[state.active_seat]
    action = choose_action(state, active_player.id, rng)
    if isinstance(action, PlayCard):
        card = _find_hand_card(active_player, action.card_id)
        # RUL-42 (G): if the played card is an OP-only comparator (ADR-0002),
        # roll the dice mode the bot picked and pass the drawn N to play_card.
        dice_mode: int | None = None
        dice_roll: int | None = None
        if card.name in _OP_ONLY_COMPARATOR_NAMES and action.dice in (1, 2):
            dice_mode = action.dice
            dice_roll = sum(dice_rng.randint(1, 6) for _ in range(dice_mode))
        _emit(
            out,
            "turn",
            round=state.round_number,
            seat=state.active_seat,
            player=active_player.id,
            action="play_card",
            card=action.card_id,
            slot=action.slot,
            dice=action.dice if action.dice is not None else "none",
            roll=dice_roll if dice_roll is not None else "none",
        )
        return play_card(
            state,
            card,
            action.slot,
            dice_mode=dice_mode,
            dice_roll=dice_roll,
        )
    if isinstance(action, DiscardRedraw):
        # Discard isn't wired into rules.py yet; treat as a pass and flag.
        # Reachable post-RUL-18 when a player's hand has no slot-compatible
        # card; full discard wiring lands later.
        _emit(
            out,
            "turn",
            round=state.round_number,
            seat=state.active_seat,
            player=active_player.id,
            action="discard_redraw_unimplemented",
            cards=",".join(action.card_ids),
        )
        return pass_turn(state)
    if isinstance(action, Pass):
        _emit(
            out,
            "turn",
            round=state.round_number,
            seat=state.active_seat,
            player=active_player.id,
            action="pass",
        )
        return pass_turn(state)
    if isinstance(action, PlayJoker):
        # RUL-45 (J): JOKER attachment — narrate then dispatch via play_joker.
        card = _find_hand_card(active_player, action.card_id)
        _emit(
            out,
            "turn",
            round=state.round_number,
            seat=state.active_seat,
            player=active_player.id,
            action="play_joker",
            card=action.card_id,
        )
        return play_joker(state, card)
    raise AssertionError(f"unhandled action variant {type(action).__name__}")


def _narrate_round_start(out: TextIO, state: GameState) -> None:
    """Emit the round-start, dealer-fragment, and effect-card events."""
    rule = state.active_rule
    template = rule.template.value if rule is not None else "unknown"
    effect = state.revealed_effect
    _emit(
        out,
        "round_start",
        round=state.round_number,
        dealer=state.dealer_seat,
        template=template,
        effect_card=effect.id if effect is not None else "none",
    )
    if rule is not None:
        slot_summary = ",".join(f"{s.name}:{s.type.value}" for s in rule.slots)
        _emit(
            out,
            "rule_template",
            round=state.round_number,
            slots=slot_summary,
        )
        for play in rule.plays:
            _emit(
                out,
                "dealer_fragment",
                round=state.round_number,
                player=play.player_id,
                slot=play.slot,
                card=play.card.id,
            )


def _narrate_dealer_seed_failure(out: TextIO, state: GameState, prior_dealer: int) -> None:
    """Emit round_start + rule_failed events when the dealer cannot seed slot 0.

    enter_round_start consumes the round (round_number ticks, dealer rotates)
    but never enters BUILD. Mirrors the build-time path so log-grepping sees
    one ``round_start`` and one ``rule_failed`` per consumed round regardless
    of fail mode.
    """
    _emit(
        out,
        "round_start",
        round=state.round_number,
        dealer=prior_dealer,
        template="unknown",
        effect_card="none",
    )
    _emit(
        out,
        "rule_failed",
        round=state.round_number,
        reason="dealer_no_seed_card",
        next_dealer=state.dealer_seat,
    )
    _emit_standings(out, state)


def _narrate_rule_failed(out: TextIO, prior_rule: RuleBuilder | None, state: GameState) -> None:
    """Emit a rule_failed event with the slots that ended up unfilled.

    ``prior_rule`` is the rule snapshot from before the final build tick;
    rules.py clears ``active_rule`` on fail-and-rotate. The new dealer for the
    next round is the rotated value already in ``state``.
    """
    if prior_rule is None:
        _emit(out, "rule_failed", round=state.round_number, reason="no_rule")
        return
    unfilled = [s.name for s in prior_rule.slots if s.filled_by is None]
    filled = [s.name for s in prior_rule.slots if s.filled_by is not None]
    _emit(
        out,
        "rule_failed",
        round=state.round_number,
        unfilled_slots=",".join(unfilled) if unfilled else "none",
        filled_slots=",".join(filled) if filled else "none",
        next_dealer=state.dealer_seat,
    )
    _emit_standings(out, state)


def _narrate_resolve(out: TextIO, state: GameState) -> None:
    """Emit a resolve summary. M1: rules.enter_resolve is a stub, so the effect
    summary is structural (rendered slots + filled-by ids); real effect
    application lands when grammar.py / effects.py are wired into the round
    flow (see handback for the substrate ticket)."""
    rule = state.active_rule
    if rule is None:
        _emit(out, "resolve", round=state.round_number, status="no_rule")
        return
    rendered = _render_rule_text(rule)
    filled = ",".join(_filled_slot_summaries(rule))
    _emit(
        out,
        "resolve",
        round=state.round_number,
        status="resolved",
        template=rule.template.value,
        rendered=rendered,
        slots=filled,
    )
    _emit_standings(out, state)


def _render_rule_text(rule: RuleBuilder) -> str:
    """Cheap structural rendering — joins slot card names in slot order.

    Slot defs come from the CONDITION card (RUL-18); for an IF rule that's
    SUBJECT / QUANT / NOUN, which matches ``grammar.render_if_rule``.
    """
    parts: list[str] = [rule.template.value]
    for slot in rule.slots:
        token = slot.filled_by.name if slot.filled_by is not None else f"<{slot.name}?>"
        parts.append(token)
    return " ".join(parts)


def _filled_slot_summaries(rule: RuleBuilder) -> list[str]:
    out: list[str] = []
    for slot in rule.slots:
        if slot.filled_by is None:
            out.append(f"{slot.name}=unfilled")
        else:
            out.append(f"{slot.name}={slot.filled_by.id}")
    return out


def _emit_standings(out: TextIO, state: GameState) -> None:
    parts = [
        f"{p.id}=chips:{p.chips},vp:{p.vp}" for p in sorted(state.players, key=lambda pl: pl.seat)
    ]
    _emit(out, "standings", round=state.round_number, players=" ".join(parts))


def _emit(out: TextIO, event: str, **fields: object) -> None:
    pieces = [f"event={event}"]
    pieces.extend(f"{k}={v}" for k, v in fields.items())
    out.write(" ".join(pieces))
    out.write("\n")


def _find_hand_card(player: Player, card_id: str) -> Card:
    for card in player.hand:
        if card.id == card_id:
            return card
    raise ValueError(f"card {card_id!r} not in {player.id} hand")


if __name__ == "__main__":
    raise SystemExit(main())

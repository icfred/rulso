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

from rulso.bots.random import DiscardRedraw, Pass, PlayCard, choose_action
from rulso.rules import advance_phase, pass_turn, play_card
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


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Parses args, runs one game, returns the exit code."""
    args = _parse_args(argv)
    return run_game(seed=args.seed, max_rounds=args.rounds, out=sys.stdout)


def run_game(*, seed: int, max_rounds: int, out: TextIO) -> int:
    """Play one game; emit per-event lines to ``out``. Return 0 on win, 1 on cap-hit."""
    rng = random.Random(seed)
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
            state = advance_phase(state)  # ROUND_START → BUILD
            _narrate_round_start(out, state)
        elif state.phase is Phase.BUILD:
            prior_rule = state.active_rule
            state = _drive_build_turn(state, rng, out)
            if state.phase is Phase.ROUND_START:
                # Build revolution finished with unfilled slots → rule failed.
                _narrate_rule_failed(out, prior_rule, state)
        elif state.phase is Phase.RESOLVE:
            _narrate_resolve(out, state)
            state = advance_phase(state)  # RESOLVE → ROUND_START or END
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


def _drive_build_turn(state: GameState, rng: random.Random, out: TextIO) -> GameState:
    """Pull one bot action for the active player and apply it. Returns new state."""
    active_player = state.players[state.active_seat]
    action = choose_action(state, active_player.id, rng)
    if isinstance(action, PlayCard):
        card = _find_hand_card(active_player, action.card_id)
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
        )
        return play_card(state, card, action.slot)
    if isinstance(action, DiscardRedraw):
        # Discard isn't wired into rules.py yet; treat as a pass and flag.
        # M1 hands are empty so this branch is unreachable in practice; kept
        # for forward-compat once hands are populated.
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

    Real grammar (``grammar.render_if_rule``) requires SUBJECT/QUANT/NOUN slot
    names, but the M1 stub rule in rules.py uses subject/noun/modifier/noun_2.
    Until that mismatch is reconciled, the CLI prints whatever's filled — the
    rule won't actually fire in M1 anyway (empty hands → all passes → fail).
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

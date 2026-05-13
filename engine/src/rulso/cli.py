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

from rulso.bots import human as human_bot
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
)
from rulso.rules import start_game as _start_game
from rulso.state import (
    DISCARD_COST,
    PLAYER_COUNT,
    Card,
    GameState,
    Phase,
    Player,
    RuleBuilder,
)

_DEFAULT_ROUNDS: int = 50
_DEFAULT_SEED: int = 0
_DEFAULT_WS_HOST: str = "127.0.0.1"
_DEFAULT_WS_PORT: int = 8765

# RUL-42 (G): OP-only comparator names per ADR-0002. CLI is the seat with the
# rng for the dice roll; rules.play_card stamps last_roll using the value we
# pass in so rules.py stays pure.
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Parses args, runs one game, returns the exit code.

    With ``--ws`` the CLI does NOT run a game in-process — it connects to a
    running ``rulso-server`` and drives the human seat via TTY. See
    :mod:`rulso.cli_ws`. The other flags (``--seed``, ``--rounds``,
    ``--human-seat``) are ignored in WS mode; the server owns those concerns.

    With ``simulate`` as the first positional argument the CLI dispatches to
    :func:`rulso.simulate.run` — see ``docs/engine/simulate.md`` for the
    sim-harness contract. The remaining positional/flag args are forwarded.
    """
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "simulate":
        from rulso.simulate import run as run_simulate

        return run_simulate(argv_list[1:], out=sys.stdout)
    args = _parse_args(argv_list)
    if args.ws:
        from rulso.cli_ws import main_ws

        return main_ws(host=args.ws_host, port=args.ws_port)
    return run_game(
        seed=args.seed,
        max_rounds=args.rounds,
        out=sys.stdout,
        human_seat=args.human_seat,
        human_stdin=sys.stdin if args.human_seat is not None else None,
    )


def run_game(
    *,
    seed: int,
    max_rounds: int,
    out: TextIO,
    human_seat: int | None = None,
    human_stdin: TextIO | None = None,
) -> int:
    """Play one game; emit per-event lines to ``out``. Return 0 on win, 1 on cap-hit.

    When ``human_seat`` is set, the seat at that index is driven by
    :func:`rulso.bots.human.select_action` reading from ``human_stdin``; the
    other seats keep using the random-legal bot. ``human_seat=None`` (default)
    preserves the four-bot baseline byte-for-byte.
    """
    rng = random.Random(seed)
    refill_rng = random.Random(seed ^ 0x5EED)  # disjoint stream from bot decisions
    # RUL-42 (G): comparator dice rng — disjoint from bot decisions and refills
    # so reordering bot picks doesn't reshuffle dice rolls.
    dice_rng = random.Random(seed ^ 0xD1CE)
    # RUL-54: effect-deck recycle rng — disjoint from bot/refill/dice streams.
    # The 12-card effect deck recycles around round ~13; before RUL-54 the CLI
    # never threaded this through and enter_round_start fell back to an unseeded
    # random.Random(), diverging seeded games past the first recycle.
    effect_rng = random.Random(seed ^ 0xEFFC)
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
            state = advance_phase(state, rng=effect_rng)  # ROUND_START → BUILD or SHOP
            if state.phase is Phase.SHOP:
                # RUL-51: defer round_start narration until SHOP completes and
                # the dealer reveals the template. The SHOP branch below picks
                # up the same state on the next loop iteration.
                continue
            _narrate_round_start(out, state)
        elif state.phase is Phase.BUILD:
            prior_rule = state.active_rule
            state = _drive_build_turn(
                state,
                rng,
                dice_rng,
                refill_rng,
                out,
                human_seat=human_seat,
                human_stdin=human_stdin,
            )
            if state.phase is Phase.ROUND_START:
                # Build revolution finished with unfilled slots → rule failed.
                _narrate_rule_failed(out, prior_rule, state)
        elif state.phase is Phase.RESOLVE:
            _narrate_resolve(out, state)
            state = advance_phase(state, rng=refill_rng)  # RESOLVE → ROUND_START or END
        elif state.phase is Phase.SHOP:
            # RUL-51: SHOP fires when ``round_number % SHOP_INTERVAL == 0`` and
            # at least one offer is available. Drive purchases in canonical
            # order (VP asc, chips asc, seat asc) and finalise via advance_phase.
            state = _drive_shop(out, state, rng)
            state = advance_phase(state, rng=effect_rng)  # SHOP → BUILD
            _narrate_round_start(out, state)
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
    parser.add_argument(
        "--human-seat",
        type=int,
        default=None,
        choices=range(PLAYER_COUNT),
        metavar=f"{{0..{PLAYER_COUNT - 1}}}",
        help=(
            "Drive the given seat from the terminal; other seats remain random "
            "bots. Omit to play a four-bot game (default)."
        ),
    )
    parser.add_argument(
        "--ws",
        action="store_true",
        help=(
            "Connect to a running rulso-server over WebSocket and drive the "
            "human seat via TTY instead of running a game in-process. The "
            "server owns --seed / --human-seat in this mode."
        ),
    )
    parser.add_argument(
        "--ws-host",
        default=_DEFAULT_WS_HOST,
        help=f"Server host when --ws is set (default: {_DEFAULT_WS_HOST})",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=_DEFAULT_WS_PORT,
        help=f"Server port when --ws is set (default: {_DEFAULT_WS_PORT})",
    )
    return parser.parse_args(argv)


def _drive_build_turn(
    state: GameState,
    rng: random.Random,
    dice_rng: random.Random,
    refill_rng: random.Random,
    out: TextIO,
    *,
    human_seat: int | None = None,
    human_stdin: TextIO | None = None,
) -> GameState:
    """Pull one action for the active player and apply it. Returns new state.

    Routes the active seat through the human-seat driver when
    ``human_seat == state.active_seat`` and ``human_stdin`` is set; otherwise
    the random-legal bot picks. Action shapes are identical between the two
    drivers — downstream emit/dispatch is unchanged.
    """
    active_player = state.players[state.active_seat]
    if human_seat is not None and state.active_seat == human_seat and human_stdin is not None:
        action = human_bot.select_action(state, active_player, stdin=human_stdin, stdout=out)
    else:
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
        # RUL-68: real discard substrate. Spends DISCARD_COST per card and
        # draws replacements; ``refill_rng`` shares the disjoint stream that
        # also feeds round-end hand refills (``enter_resolve`` step 12).
        _emit(
            out,
            "turn",
            round=state.round_number,
            seat=state.active_seat,
            player=active_player.id,
            action="discard_redraw",
            cards=",".join(action.card_ids),
            cost=len(action.card_ids) * DISCARD_COST,
        )
        return discard_redraw(
            state,
            active_player.id,
            action.card_ids,
            refill_rng=refill_rng,
        )
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


def _drive_shop(out: TextIO, state: GameState, rng: random.Random) -> GameState:
    """Drive one SHOP phase to completion (RUL-51).

    Emits ``shop_open`` once, then for each player in
    :func:`rulso.rules.shop_purchase_order` either a ``shop_purchase`` (when
    the bot picks an affordable offer) or a ``shop_skip`` (when no offer is
    affordable). Closes with ``shop_close`` reporting the unsold offer count.
    The caller is responsible for the post-SHOP :func:`advance_phase` that
    resumes round_start steps 6-8.
    """
    _emit(
        out,
        "shop_open",
        round=state.round_number,
        offer_count=len(state.shop_offer),
    )
    order = shop_purchase_order(state)
    for player_id in order:
        offer_index = select_purchase(state, player_id, rng)
        if offer_index is None:
            _emit(out, "shop_skip", round=state.round_number, player=player_id)
            continue
        offer = state.shop_offer[offer_index]
        _emit(
            out,
            "shop_purchase",
            round=state.round_number,
            player=player_id,
            offer=offer.card.id,
            price=offer.price,
        )
        state = apply_shop_purchase(state, player_id, offer_index)
    _emit(out, "shop_close", round=state.round_number, unsold=len(state.shop_offer))
    return state


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

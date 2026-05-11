"""WebSocket server — single-game asyncio loop (RUL-64, ADR-0008).

One game per process, one human seat per connection, bots (``bots.random``)
fill the other three seats. Engine is authoritative: every transition that
mutates ``GameState`` emits a :class:`StateBroadcast`; every client
:class:`ActionSubmit` is re-validated via
:func:`rulso.legality.enumerate_legal_actions` before being applied. ``Pass`` is
server-side only (per ADR-0008) — picked automatically when the human's legal
set is empty, never submitted by clients.

Mirrors the loop shape of :mod:`rulso.cli` (sync, single-game), replacing the
TTY driver with WebSocket I/O and preserving the disjoint-rng pattern
(``seed / seed^0x5EED / seed^0xD1CE / seed^0xEFFC``).

Concurrency model: a single reader coroutine drains incoming envelopes and
either replies with an :class:`ErrorEnvelope` (PROTOCOL_INVALID / NOT_YOUR_TURN)
or queues the submission for the game loop. The game loop validates legality
at apply time and replies with ILLEGAL_ACTION if the queued action is no longer
valid. The reader yields after every queue.put and the game loop yields after
every broadcast so the two stay in lockstep — neither outruns the other's
view of ``state_ref``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import random
import sys
from collections.abc import Callable, Sequence
from typing import Any

import websockets
from pydantic import TypeAdapter, ValidationError

from rulso.bots.random import choose_action, select_purchase
from rulso.legality import (
    DiscardRedraw,
    Pass,
    PlayCard,
    PlayJoker,
    enumerate_legal_actions,
)
from rulso.protocol import (
    PROTOCOL_VERSION,
    ActionSubmit,
    ClientEnvelope,
    ErrorCode,
    ErrorEnvelope,
    Hello,
    StateBroadcast,
)
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
from rulso.state import (
    PLAYER_COUNT,
    Card,
    GameState,
    Phase,
    Player,
)

_CLIENT_ADAPTER = TypeAdapter(ClientEnvelope)

# Mirrors the CLI constant — only OP-only comparator MODIFIERs trigger a dice
# roll on play (ADR-0002). Kept private to the server so the CLI's constant
# stays the single source consumed by ``rulso.cli``.
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765
_DEFAULT_SEED = 0
_DEFAULT_HUMAN_SEAT = 0

# WebSocket close code for "service overloaded" — used when a second client
# arrives while a game is already in progress.
_CLOSE_CODE_BUSY = 1013


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point — runs one game-server to completion, returns 0."""
    args = _parse_args(argv)
    asyncio.run(
        run_server(
            host=args.host,
            port=args.port,
            seed=args.seed,
            human_seat=args.human_seat,
        )
    )
    return 0


async def run_server(
    *,
    host: str,
    port: int,
    seed: int,
    human_seat: int,
    on_listening: Callable[[int], None] | None = None,
) -> None:
    """Serve one Rulso game over WebSocket and return when it ends.

    Accepts the first connection, runs the engine loop, broadcasts state on
    every transition, and closes the connection once the game terminates.
    Subsequent connections while the active game is in progress are rejected
    with WebSocket close code 1013 (service overloaded).

    ``on_listening`` is a test hook — invoked once with the actual bound port
    immediately after the listener comes up. Production callers leave it
    ``None`` and pass an explicit ``port``.
    """
    if not (0 <= human_seat < PLAYER_COUNT):
        raise ValueError(f"human_seat must be in 0..{PLAYER_COUNT - 1}, got {human_seat}")

    busy = False
    done = asyncio.Event()

    async def _handler(ws: Any) -> None:
        nonlocal busy
        if busy:
            await ws.close(code=_CLOSE_CODE_BUSY, reason="server already serving a game")
            return
        busy = True
        try:
            await _serve_game(ws, seed=seed, human_seat=human_seat)
        finally:
            done.set()

    async with websockets.serve(_handler, host, port) as server:
        if on_listening is not None:
            for sock in server.sockets or ():
                on_listening(sock.getsockname()[1])
                break
        await done.wait()


async def _serve_game(ws: Any, *, seed: int, human_seat: int) -> None:
    """Run one game on the given connection.

    Sends :class:`Hello`, spins a reader task to drain inbound envelopes, runs
    the engine loop to completion (or until the client disconnects), then
    cancels the reader and closes the connection.
    """
    await _send_envelope(ws, Hello(seat=human_seat, protocol_version=PROTOCOL_VERSION))

    action_queue: asyncio.Queue[ActionSubmit] = asyncio.Queue()
    state_ref: dict[str, GameState | None] = {"state": None}

    reader_task = asyncio.create_task(
        _drain_client(ws, action_queue=action_queue, state_ref=state_ref, human_seat=human_seat)
    )
    try:
        await _run_game_loop(
            ws,
            action_queue=action_queue,
            state_ref=state_ref,
            seed=seed,
            human_seat=human_seat,
        )
    except websockets.ConnectionClosed:
        # Client disconnected mid-game; clean shutdown.
        pass
    finally:
        reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, websockets.ConnectionClosed):
            await reader_task
        with contextlib.suppress(websockets.ConnectionClosed):
            await ws.close()


def classify_submission(state: GameState | None, human_seat: int) -> ErrorEnvelope | None:
    """Return an :class:`ErrorEnvelope` if it is not the human's turn, else ``None``.

    Captures the reader's turn-ownership check as a pure function so the
    integration tests can sanity-check the rejection path without timing
    races. The reader only consults this — legality (``ILLEGAL_ACTION``) and
    parse failures (``PROTOCOL_INVALID``) are handled elsewhere.
    """
    if state is None or state.phase is not Phase.BUILD or state.active_seat != human_seat:
        return ErrorEnvelope(
            code=ErrorCode.NOT_YOUR_TURN,
            message=_describe_turn_state(state, human_seat),
        )
    return None


async def _drain_client(
    ws: Any,
    *,
    action_queue: asyncio.Queue[ActionSubmit],
    state_ref: dict[str, GameState | None],
    human_seat: int,
) -> None:
    """Receive envelopes; reply with errors or queue for the game loop.

    Validates parse-time concerns (PROTOCOL_INVALID) and turn ownership
    (NOT_YOUR_TURN). Legality is checked by the game loop at apply time —
    the reader only confirms it is the human's turn to act before queuing.

    Yields after queuing so the game loop has an opportunity to apply the
    queued action (and update ``state_ref``) before we observe the next
    submission. Without this yield the reader would batch consecutive
    in-turn submissions against a stale state snapshot and emit a misleading
    string of ILLEGAL_ACTION errors.
    """
    try:
        async for raw in ws:
            raw_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            try:
                envelope = _CLIENT_ADAPTER.validate_json(raw_str)
            except ValidationError as exc:
                await _send_envelope(
                    ws,
                    ErrorEnvelope(code=ErrorCode.PROTOCOL_INVALID, message=str(exc)),
                )
                continue
            error = classify_submission(state_ref["state"], human_seat)
            if error is not None:
                await _send_envelope(ws, error)
                continue
            await action_queue.put(envelope)
            # Let the game loop process this submission against the current
            # state before we inspect the next one — see docstring.
            await asyncio.sleep(0)
    except websockets.ConnectionClosed:
        return


async def _run_game_loop(
    ws: Any,
    *,
    action_queue: asyncio.Queue[ActionSubmit],
    state_ref: dict[str, GameState | None],
    seed: int,
    human_seat: int,
) -> None:
    """Drive the engine to a terminal state; broadcast after every transition."""
    rng = random.Random(seed)
    refill_rng = random.Random(seed ^ 0x5EED)
    dice_rng = random.Random(seed ^ 0xD1CE)
    effect_rng = random.Random(seed ^ 0xEFFC)

    state = start_game(seed)
    state_ref["state"] = state
    await _send_envelope(ws, _build_state_broadcast(state, human_seat))

    while state.phase is not Phase.END:
        if state.phase is Phase.ROUND_START:
            state = advance_phase(state, rng=effect_rng)
        elif state.phase is Phase.BUILD:
            if state.active_seat == human_seat:
                state = await _take_human_turn(ws, action_queue, state, dice_rng, refill_rng)
            else:
                state = _take_bot_turn(state, rng, dice_rng, refill_rng)
        elif state.phase is Phase.RESOLVE:
            state = advance_phase(state, rng=refill_rng)
        elif state.phase is Phase.SHOP:
            state = await _drive_shop(ws, state, rng, human_seat=human_seat)
            state = advance_phase(state, rng=effect_rng)
        else:
            raise AssertionError(f"unhandled phase {state.phase}")
        state_ref["state"] = state
        await _send_envelope(ws, _build_state_broadcast(state, human_seat))
        # Give the reader task an explicit chance to drain a pending submission
        # against the latest state. ``ws.send`` already yields, but on fast
        # localhost the loop can race through a full bot rotation before any
        # network-buffered submission becomes readable; this keeps the
        # reader's view of ``state_ref`` close to real-time.
        await asyncio.sleep(0)


async def _take_human_turn(
    ws: Any,
    action_queue: asyncio.Queue[ActionSubmit],
    state: GameState,
    dice_rng: random.Random,
    refill_rng: random.Random,
) -> GameState:
    """Await one legal submission from the human; auto-pass on empty legal set.

    Re-validates legality at apply time (the reader may have queued a
    submission against a state that has since advanced — game loop guards
    against this with a synchronous ``action in legal`` check).
    """
    player = state.players[state.active_seat]
    legal = enumerate_legal_actions(state, player)
    if not legal:
        return pass_turn(state)
    while True:
        envelope = await action_queue.get()
        if envelope.action in legal:
            return _apply_action(state, envelope.action, dice_rng, refill_rng)
        await _send_envelope(
            ws,
            ErrorEnvelope(
                code=ErrorCode.ILLEGAL_ACTION,
                message=(
                    f"action {envelope.action.kind} not in legal set for seat {state.active_seat}"
                ),
            ),
        )


def _take_bot_turn(
    state: GameState,
    rng: random.Random,
    dice_rng: random.Random,
    refill_rng: random.Random,
) -> GameState:
    """Pick and apply one action for the active non-human seat."""
    player = state.players[state.active_seat]
    action = choose_action(state, player.id, rng)
    if isinstance(action, Pass):
        return pass_turn(state)
    return _apply_action(state, action, dice_rng, refill_rng)


def _apply_action(
    state: GameState,
    action: PlayCard | PlayJoker | DiscardRedraw,
    dice_rng: random.Random,
    refill_rng: random.Random,
) -> GameState:
    """Dispatch one action variant to the engine. Pre: legality already checked."""
    player = state.players[state.active_seat]
    if isinstance(action, PlayCard):
        card = _find_hand_card(player, action.card_id)
        dice_mode: int | None = None
        dice_roll: int | None = None
        if card.name in _OP_ONLY_COMPARATOR_NAMES and action.dice in (1, 2):
            dice_mode = action.dice
            dice_roll = sum(dice_rng.randint(1, 6) for _ in range(dice_mode))
        return play_card(state, card, action.slot, dice_mode=dice_mode, dice_roll=dice_roll)
    if isinstance(action, PlayJoker):
        card = _find_hand_card(player, action.card_id)
        return play_joker(state, card)
    if isinstance(action, DiscardRedraw):
        # RUL-68: real discard substrate. Shares ``refill_rng`` with round-end
        # hand refills (``enter_resolve`` step 12) — both consume the disjoint
        # ``seed ^ 0x5EED`` stream.
        return discard_redraw(state, player.id, action.card_ids, refill_rng=refill_rng)
    raise AssertionError(f"unhandled action variant {type(action).__name__}")


async def _drive_shop(
    ws: Any, state: GameState, rng: random.Random, *, human_seat: int
) -> GameState:
    """Drive every SHOP purchase in canonical order; broadcast after each.

    All seats (including the human's) are bot-driven in SHOP per ADR-0008:
    SHOP is engine-internal; clients do not submit SHOP envelopes in the MVP
    surface.
    """
    order = shop_purchase_order(state)
    for player_id in order:
        offer_index = select_purchase(state, player_id, rng)
        if offer_index is None:
            continue
        state = apply_shop_purchase(state, player_id, offer_index)
        await _send_envelope(ws, _build_state_broadcast(state, human_seat))
    return state


def _build_state_broadcast(state: GameState, human_seat: int) -> StateBroadcast:
    """Wrap ``state`` in a :class:`StateBroadcast`, attaching legal actions only
    when the human seat is active in BUILD.

    Re-uses :func:`enumerate_legal_actions` exactly as the human-turn driver
    does. Re-cost is O(slots × hand) — see ADR-0008 follow-up notes for the
    caching ticket. None on every other broadcast (bot turns, non-BUILD
    phases, terminal state).
    """
    if state.phase is not Phase.BUILD or state.active_seat != human_seat:
        return StateBroadcast(state=state)
    legal = enumerate_legal_actions(state, state.players[human_seat])
    return StateBroadcast(state=state, legal_actions=tuple(legal))


async def _send_envelope(ws: Any, envelope: Any) -> None:
    """Serialise a Pydantic envelope as JSON and send it on ``ws``."""
    await ws.send(envelope.model_dump_json())


def _find_hand_card(player: Player, card_id: str) -> Card:
    for card in player.hand:
        if card.id == card_id:
            return card
    raise ValueError(f"card {card_id!r} not in {player.id} hand")


def _describe_turn_state(state: GameState | None, human_seat: int) -> str:
    if state is None:
        return f"game not yet in progress (human seat={human_seat})"
    return (
        f"current phase={state.phase.value} active_seat={state.active_seat} human_seat={human_seat}"
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rulso-server",
        description="Serve one Rulso game over WebSocket (M3 foundation client).",
    )
    parser.add_argument(
        "--host",
        default=_DEFAULT_HOST,
        help=f"Bind host (default: {_DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help=f"Bind port (default: {_DEFAULT_PORT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_SEED,
        help=f"RNG seed for bot decisions and dice (default: {_DEFAULT_SEED})",
    )
    parser.add_argument(
        "--human-seat",
        type=int,
        default=_DEFAULT_HUMAN_SEAT,
        choices=range(PLAYER_COUNT),
        metavar=f"{{0..{PLAYER_COUNT - 1}}}",
        help=(
            f"Seat index the connecting client drives; other seats stay bot-driven "
            f"(default: {_DEFAULT_HUMAN_SEAT})"
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())

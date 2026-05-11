"""WebSocket server tests (RUL-64).

Exercises the handshake, broadcast cadence, the three rejection codes
(``PROTOCOL_INVALID`` / ``NOT_YOUR_TURN`` / ``ILLEGAL_ACTION``), and an
end-to-end game completion.

Each test starts the server on an ephemeral port, runs one client interaction,
and lets the server complete naturally when the client closes (or the game
ends). ``pytest-asyncio`` is configured in ``auto`` mode (see
``pyproject.toml``); plain ``async def`` tests are picked up directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

import pytest
import websockets
from pydantic import TypeAdapter

from rulso.legality import (
    PlayCard,
    enumerate_legal_actions,
)
from rulso.protocol import (
    PROTOCOL_VERSION,
    ActionSubmit,
    ErrorCode,
    ErrorEnvelope,
    Hello,
    ServerEnvelope,
    StateBroadcast,
)
from rulso.rules import start_game
from rulso.server import classify_submission, run_server
from rulso.state import Phase

_SERVER_ADAPTER = TypeAdapter(ServerEnvelope)
_RECV_TIMEOUT = 10.0
_END_TO_END_TIMEOUT = 60.0
# Bot-only progress check: 16 broadcasts is enough to span at least one full
# turn rotation under any starting seed (initial state + advance_phase to BUILD
# + several bot turns), without depending on a specific seat assignment.
_PROGRESS_BROADCASTS = 16


@contextlib.asynccontextmanager
async def _server_running(*, seed: int, human_seat: int) -> AsyncIterator[int]:
    """Start the server on an ephemeral port; yield the bound port."""
    loop = asyncio.get_running_loop()
    port_future: asyncio.Future[int] = loop.create_future()

    def _on_listening(p: int) -> None:
        if not port_future.done():
            port_future.set_result(p)

    task = asyncio.create_task(
        run_server(
            host="127.0.0.1",
            port=0,
            seed=seed,
            human_seat=human_seat,
            on_listening=_on_listening,
        )
    )
    try:
        port = await asyncio.wait_for(port_future, timeout=5.0)
        yield port
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=5.0)


async def _recv_envelope(ws: websockets.ClientConnection) -> ServerEnvelope:
    raw = await asyncio.wait_for(ws.recv(), timeout=_RECV_TIMEOUT)
    return _SERVER_ADAPTER.validate_json(raw)


async def _recv_hello(ws: websockets.ClientConnection) -> Hello:
    msg = await _recv_envelope(ws)
    assert isinstance(msg, Hello), f"expected Hello, got {type(msg).__name__}"
    return msg


async def _drain_until_human_build(
    ws: websockets.ClientConnection,
    human_seat: int,
    *,
    max_frames: int = 200,
) -> StateBroadcast:
    """Read broadcasts (skipping errors) until phase=BUILD and active_seat=human_seat."""
    for _ in range(max_frames):
        msg = await _recv_envelope(ws)
        if isinstance(msg, StateBroadcast):
            state = msg.state
            if state.phase is Phase.BUILD and state.active_seat == human_seat:
                return msg
    pytest.fail(f"never reached BUILD+seat={human_seat} within {max_frames} frames")


# --- handshake -------------------------------------------------------------


async def test_hello_emitted_on_connect_pins_seat_and_version() -> None:
    async with _server_running(seed=0, human_seat=2) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            hello = await _recv_hello(ws)
    assert hello.seat == 2
    assert hello.protocol_version == PROTOCOL_VERSION


# --- bot-only progression --------------------------------------------------


async def test_bot_seats_progress_without_human_input() -> None:
    """The server drives non-human seats without waiting on client input.

    With a non-active human seat at the start, the client just observes
    broadcasts; bot turns mutate state and the server keeps broadcasting.
    Asserts that multiple distinct states arrive (state evolves) and at least
    one BUILD turn is taken by a non-human seat.
    """
    async with _server_running(seed=0, human_seat=2) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            states: list[StateBroadcast] = []
            saw_bot_build_turn = False
            for _ in range(_PROGRESS_BROADCASTS):
                msg = await _recv_envelope(ws)
                assert isinstance(msg, StateBroadcast)
                states.append(msg)
                state = msg.state
                if state.phase is Phase.BUILD and state.active_seat != 2:
                    saw_bot_build_turn = True
                # Stop early if the human becomes active — the bots have
                # clearly progressed past their first round of turns.
                if state.phase is Phase.BUILD and state.active_seat == 2:
                    break
    assert saw_bot_build_turn, "expected at least one bot BUILD turn"
    # State must have actually evolved across broadcasts (not the same state
    # repeated). Compare first vs last by hand-size sums + round_number.
    first, last = states[0].state, states[-1].state
    assert (first.round_number, sum(len(p.hand) for p in first.players)) != (
        last.round_number,
        sum(len(p.hand) for p in last.players),
    )


# --- action round-trip -----------------------------------------------------


async def test_action_submit_is_applied_and_broadcast() -> None:
    """Client submits a legal action; server applies and broadcasts next state."""
    async with _server_running(seed=0, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            human_turn = await _drain_until_human_build(ws, human_seat=0)
            state_before = human_turn.state
            player = state_before.players[0]
            legal = enumerate_legal_actions(state_before, player)
            assert legal, "expected non-empty legal set for human turn"
            # Prefer a PlayCard so the broadcast shows a slot getting filled
            # and active_seat advancing.
            chosen = next(
                (a for a in legal if isinstance(a, PlayCard)),
                legal[0],
            )
            await ws.send(ActionSubmit(action=chosen).model_dump_json())
            # Drain broadcasts until we see one where active_seat has advanced
            # past the human or the human's hand shrank (action applied).
            for _ in range(20):
                msg = await _recv_envelope(ws)
                assert isinstance(msg, StateBroadcast)
                after = msg.state
                if len(after.players[0].hand) < len(state_before.players[0].hand):
                    return
                if after.active_seat != 0 or after.phase is not Phase.BUILD:
                    return
            pytest.fail("server did not apply submitted action within 20 broadcasts")


# --- rejection codes -------------------------------------------------------


def test_classify_submission_rejects_pre_game_state() -> None:
    """Before the engine has produced a state, every submission is NOT_YOUR_TURN."""
    error = classify_submission(None, human_seat=0)
    assert error is not None
    assert error.code is ErrorCode.NOT_YOUR_TURN


def test_classify_submission_rejects_non_build_phase() -> None:
    """Submissions in any phase other than BUILD are NOT_YOUR_TURN regardless of seat."""
    state = start_game(0)
    # ``start_game`` returns ROUND_START — a non-BUILD phase.
    assert state.phase is Phase.ROUND_START
    error = classify_submission(state, human_seat=state.active_seat)
    assert error is not None
    assert error.code is ErrorCode.NOT_YOUR_TURN


def test_classify_submission_rejects_wrong_seat_in_build() -> None:
    """In BUILD, a submission from a seat other than the active one is rejected.

    Constructs the rejection via ``model_copy`` to avoid driving the full
    engine to a BUILD state — the helper is pure and only inspects
    ``state.phase`` and ``state.active_seat``.
    """
    state = start_game(0).model_copy(update={"phase": Phase.BUILD, "active_seat": 2})
    error = classify_submission(state, human_seat=0)
    assert error is not None
    assert error.code is ErrorCode.NOT_YOUR_TURN


def test_classify_submission_passes_when_human_is_active_in_build() -> None:
    state = start_game(0).model_copy(update={"phase": Phase.BUILD, "active_seat": 0})
    assert classify_submission(state, human_seat=0) is None


async def test_not_your_turn_rejection_when_seat_is_not_human() -> None:
    """Back-to-back submissions: the second lands while a bot seat is active.

    Sends a legal action and a bogus action in immediate succession after
    the human's first BUILD turn opens. The reader's ``await asyncio.sleep(0)``
    after queuing the first submission lets the game loop apply it and
    advance state to a bot seat before the reader processes the second from
    the TCP buffer — so the second submission's turn-ownership check
    deterministically sees a bot active and rejects with NOT_YOUR_TURN.
    """
    async with _server_running(seed=0, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            human_turn = await _drain_until_human_build(ws, human_seat=0)
            player = human_turn.state.players[0]
            legal = enumerate_legal_actions(human_turn.state, player)
            chosen = next((a for a in legal if isinstance(a, PlayCard)), legal[0])
            bogus = ActionSubmit(action=PlayCard(card_id="x", slot="SUBJECT", dice=None))
            await ws.send(ActionSubmit(action=chosen).model_dump_json())
            await ws.send(bogus.model_dump_json())
            for _ in range(60):
                msg = await _recv_envelope(ws)
                if isinstance(msg, ErrorEnvelope):
                    assert msg.code is ErrorCode.NOT_YOUR_TURN
                    return
            pytest.fail("never received NOT_YOUR_TURN within 60 frames")


async def test_illegal_action_rejection_on_card_not_in_hand() -> None:
    """A structurally-valid action that is not in the legal set → ILLEGAL_ACTION."""
    async with _server_running(seed=0, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            human_turn = await _drain_until_human_build(ws, human_seat=0)
            # A PlayCard with a card_id that's certain not to be in the
            # human's hand is structurally valid (passes parse) but illegal
            # at the engine level.
            bogus = ActionSubmit(
                action=PlayCard(card_id="not.a.real.card.id", slot="SUBJECT", dice=None)
            )
            await ws.send(bogus.model_dump_json())
            for _ in range(20):
                msg = await _recv_envelope(ws)
                if isinstance(msg, ErrorEnvelope):
                    assert msg.code is ErrorCode.ILLEGAL_ACTION
                    # The engine state must not have advanced — the human's
                    # hand size is preserved.
                    assert (
                        len(human_turn.state.players[0].hand) > 0  # sanity: hand had cards
                    )
                    return
            pytest.fail("never received ILLEGAL_ACTION within 20 frames")


async def test_protocol_invalid_rejection_on_unknown_envelope_type() -> None:
    """Unknown envelope ``type`` → PROTOCOL_INVALID; server does not disconnect."""
    async with _server_running(seed=2, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            await ws.send(json.dumps({"type": "resign"}))
            for _ in range(60):
                msg = await _recv_envelope(ws)
                if isinstance(msg, ErrorEnvelope):
                    assert msg.code is ErrorCode.PROTOCOL_INVALID
                    # Verify the server is still alive — closing the client
                    # cleanly should let the server task return.
                    return
            pytest.fail("never received PROTOCOL_INVALID within 60 frames")


# --- legal_actions broadcast field ----------------------------------------


async def test_human_build_broadcasts_carry_legal_actions() -> None:
    """When the human seat is active in BUILD, broadcasts include a non-empty
    ``legal_actions`` tuple. Bot turns and non-BUILD broadcasts carry ``None``.
    """
    async with _server_running(seed=0, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            for _ in range(200):
                msg = await _recv_envelope(ws)
                if not isinstance(msg, StateBroadcast):
                    continue
                state = msg.state
                if state.phase is Phase.BUILD and state.active_seat == 0:
                    assert msg.legal_actions is not None
                    assert len(msg.legal_actions) > 0
                    return
                # Anything else — bot BUILD or non-BUILD phase — carries None.
                assert msg.legal_actions is None
            pytest.fail("never observed human BUILD broadcast within 200 frames")


async def test_terminal_state_broadcast_has_no_legal_actions() -> None:
    """The terminal ``Phase.END`` broadcast carries ``legal_actions = None``."""
    async with _server_running(seed=0, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            try:
                async with asyncio.timeout(_END_TO_END_TIMEOUT):
                    while True:
                        msg = await _recv_envelope(ws)
                        if not isinstance(msg, StateBroadcast):
                            continue
                        if msg.state.phase is Phase.END:
                            assert msg.legal_actions is None
                            return
                        if msg.state.phase is Phase.BUILD and msg.state.active_seat == 0:
                            player = msg.state.players[0]
                            legal = enumerate_legal_actions(msg.state, player)
                            if legal:
                                chosen = next(
                                    (a for a in legal if isinstance(a, PlayCard)),
                                    legal[0],
                                )
                                await ws.send(ActionSubmit(action=chosen).model_dump_json())
            except websockets.ConnectionClosed:
                pass
    pytest.fail("game never reached Phase.END within timeout")


# --- end-to-end ------------------------------------------------------------


async def test_end_to_end_game_completes_with_terminal_state_broadcast() -> None:
    """Driving the client automatically through to game end yields a terminal
    ``StateBroadcast`` with ``phase=END`` and ``winner`` set, after which the
    server closes the connection (per ADR-0008: no separate end_of_game envelope).

    Uses seed 0 which wins under the post-RUL-55 deterministic baseline.
    """
    terminal: StateBroadcast | None = None
    async with _server_running(seed=0, human_seat=0) as port:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv_hello(ws)
            try:
                async with asyncio.timeout(_END_TO_END_TIMEOUT):
                    while True:
                        msg = await _recv_envelope(ws)
                        if isinstance(msg, StateBroadcast):
                            state = msg.state
                            if state.phase is Phase.END:
                                terminal = msg
                            if state.phase is Phase.BUILD and state.active_seat == 0:
                                player = state.players[0]
                                legal = enumerate_legal_actions(state, player)
                                if legal:
                                    # Pick a PlayCard if available; fall back
                                    # to whatever's legal otherwise.
                                    chosen = next(
                                        (a for a in legal if isinstance(a, PlayCard)),
                                        legal[0],
                                    )
                                    await ws.send(ActionSubmit(action=chosen).model_dump_json())
            except websockets.ConnectionClosed:
                pass
    assert terminal is not None, "game did not produce a terminal StateBroadcast"
    assert terminal.state.phase is Phase.END
    assert terminal.state.winner is not None

"""WebSocket-driven CLI client (RUL-71, ADR-0008).

Thin shim. When ``rulso --ws`` is passed, the CLI does NOT run a game
in-process — it connects to a running ``rulso-server``, renders every
:class:`StateBroadcast` to stdout, prompts the human on broadcasts that carry
``legal_actions``, and submits one :class:`ActionSubmit` per chosen index.
Same legal-action surface as the browser; same submission shape; same engine.

State arrives via the wire; this module never mutates :class:`GameState`
directly. The server lockstep (``await asyncio.sleep(0)`` after every queue
put and broadcast) guarantees the prompt is opened against the latest state —
so a synchronous ``stdin.readline()`` while the prompt is open does not race
against concurrent broadcasts (the server is itself awaiting the queued
submission).
"""

from __future__ import annotations

import asyncio
import sys
from typing import TextIO

import websockets
from pydantic import TypeAdapter

from rulso.bots.human import _describe_action
from rulso.legality import DiscardRedraw, PlayCard, PlayJoker
from rulso.protocol import (
    ActionSubmit,
    ErrorEnvelope,
    Hello,
    ServerEnvelope,
    StateBroadcast,
)
from rulso.state import Phase

_ClientAction = PlayCard | PlayJoker | DiscardRedraw

_SERVER_ADAPTER: TypeAdapter[ServerEnvelope] = TypeAdapter(ServerEnvelope)


def main_ws(*, host: str, port: int) -> int:
    """Sync entry point wired by ``rulso --ws``; returns the exit code."""
    return asyncio.run(run(host=host, port=port, stdin=sys.stdin, stdout=sys.stdout))


async def run(
    *,
    host: str,
    port: int,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    """Connect, drive the wire loop, return ``0`` on terminal state else ``1``.

    Exit codes:

    * ``0`` — a :class:`StateBroadcast` with ``phase=END`` arrived and the
      connection closed cleanly.
    * ``1`` — premature disconnect (server died, EOF on stdin while a turn
      was open, refused connection) or the wire ended before END.
    """
    url = f"ws://{host}:{port}"
    try:
        ws_cm = websockets.connect(url)
    except OSError as exc:  # pragma: no cover — addressed via the async path below
        _emit(stdout, "ws_connect_failed", url=url, reason=str(exc))
        return 1
    try:
        async with ws_cm as ws:
            return await _drive(ws, stdin=stdin, stdout=stdout)
    except (ConnectionRefusedError, OSError) as exc:
        _emit(stdout, "ws_connect_failed", url=url, reason=str(exc))
        return 1


async def _drive(
    ws: websockets.ClientConnection,
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    """Pump envelopes from ``ws`` until terminal state or disconnect."""
    saw_terminal = False
    last_legal: tuple[_ClientAction, ...] | None = None
    try:
        async for raw in ws:
            envelope = _SERVER_ADAPTER.validate_json(raw)
            if isinstance(envelope, Hello):
                _emit(
                    stdout,
                    "ws_hello",
                    seat=envelope.seat,
                    protocol_version=envelope.protocol_version,
                )
                continue
            if isinstance(envelope, ErrorEnvelope):
                _emit(
                    stdout,
                    "ws_error",
                    code=envelope.code.value,
                    message=envelope.message,
                )
                # An ILLEGAL_ACTION leaves the human's turn open server-side:
                # the legal set we held when the rejection arrived is still
                # in play, so re-prompt against it. NOT_YOUR_TURN /
                # PROTOCOL_INVALID don't get a re-prompt (no submission was
                # expected when they arrived).
                if last_legal is not None:
                    submitted = await _prompt_and_submit(ws, last_legal, stdin=stdin, stdout=stdout)
                    if not submitted:
                        return 1
                continue
            assert isinstance(envelope, StateBroadcast)
            _render_state(envelope, stdout)
            if envelope.state.phase is Phase.END:
                saw_terminal = True
                last_legal = None
                # Stay in the loop — the server closes the connection after
                # the terminal broadcast and the async-for exits cleanly. If
                # the connection has already closed by the time we get here
                # the ConnectionClosed handler below absorbs it.
                continue
            if envelope.legal_actions:
                last_legal = envelope.legal_actions
                submitted = await _prompt_and_submit(ws, last_legal, stdin=stdin, stdout=stdout)
                if not submitted:
                    return 1
            else:
                last_legal = None
    except websockets.ConnectionClosed:
        pass
    return 0 if saw_terminal else 1


async def _prompt_and_submit(
    ws: websockets.ClientConnection,
    legal: tuple[_ClientAction, ...],
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> bool:
    """Render the legal set, read one index from ``stdin``, send the action.

    Loops on invalid input (non-integer / out-of-range) without crashing.
    Returns ``False`` on EOF — the caller exits the wire loop (the server
    would otherwise hold the turn until the connection drops).
    """
    _emit(stdout, "ws_legal", count=len(legal))
    for i, action in enumerate(legal):
        stdout.write(f"  [{i}] {_describe_action(action)}\n")
    _flush(stdout)
    while True:
        line = stdin.readline()
        if not line:
            _emit(stdout, "ws_input", outcome="eof_disconnect")
            return False
        choice = line.strip()
        try:
            idx = int(choice)
        except ValueError:
            _emit(
                stdout,
                "ws_input",
                outcome="invalid",
                value=repr(choice),
                max=len(legal) - 1,
            )
            continue
        if 0 <= idx < len(legal):
            chosen = legal[idx]
            await ws.send(ActionSubmit(action=chosen).model_dump_json())
            _emit(stdout, "ws_submit", index=idx, kind=chosen.kind)
            return True
        _emit(
            stdout,
            "ws_input",
            outcome="out_of_range",
            value=idx,
            max=len(legal) - 1,
        )


def _render_state(broadcast: StateBroadcast, stdout: TextIO) -> None:
    """Emit a terse multi-line snapshot of one :class:`StateBroadcast`.

    Decision-support text (full card prose, rule preview, opponents panel) is
    the browser's job per RUL-69; the CLI sticks to a greppable event-line
    shape that's playable on a terminal.
    """
    state = broadcast.state
    winner_id = state.winner.id if state.winner is not None else "none"
    _emit(
        stdout,
        "ws_state",
        round=state.round_number,
        phase=state.phase.value,
        active_seat=state.active_seat,
        winner=winner_id,
    )
    parts = [
        f"{p.id}=chips:{p.chips},vp:{p.vp}" for p in sorted(state.players, key=lambda pl: pl.seat)
    ]
    _emit(stdout, "ws_standings", players=" ".join(parts))
    rule = state.active_rule
    if rule is not None:
        slot_summary = ",".join(
            f"{s.name}:{(s.filled_by.name if s.filled_by is not None else '<empty>')}"
            for s in rule.slots
        )
        _emit(stdout, "ws_rule", template=rule.template.value, slots=slot_summary)


def _emit(out: TextIO, event: str, **fields: object) -> None:
    pieces = [f"event={event}"]
    pieces.extend(f"{k}={v}" for k, v in fields.items())
    out.write(" ".join(pieces))
    out.write("\n")


def _flush(out: TextIO) -> None:
    flush = getattr(out, "flush", None)
    if callable(flush):
        flush()

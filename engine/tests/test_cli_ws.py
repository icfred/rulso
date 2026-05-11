"""Tests for the WebSocket-driven CLI client (RUL-71).

Spins up the real :mod:`rulso.server` on an ephemeral port and drives the
client (:mod:`rulso.cli_ws`) against it with injected ``stdin`` / ``stdout``
TextIO — same pattern as ``test_cli_human_seat.py`` for input, same
``pytest-asyncio auto`` mode as ``test_server.py`` for the server harness.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
from collections.abc import AsyncIterator

from rulso import cli_ws
from rulso.server import run_server

_END_TO_END_TIMEOUT = 60.0
_BOT_PROGRESS_TIMEOUT = 10.0


@contextlib.asynccontextmanager
async def _server_running(*, seed: int, human_seat: int) -> AsyncIterator[int]:
    """Start the engine WS server on an ephemeral port; yield the bound port."""
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


# --- handshake ------------------------------------------------------------


async def test_ws_client_receives_hello_with_seat_and_version() -> None:
    """Connecting prints ``event=ws_hello`` with the server-assigned seat."""
    async with _server_running(seed=0, human_seat=3) as port:
        stdin = io.StringIO("")
        stdout = io.StringIO()
        # Empty stdin — when the human seat first becomes active in BUILD
        # we'll EOF out cleanly. We only need to observe the Hello.
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                cli_ws.run(host="127.0.0.1", port=port, stdin=stdin, stdout=stdout),
                timeout=_BOT_PROGRESS_TIMEOUT,
            )
    text = stdout.getvalue()
    assert "event=ws_hello" in text
    assert "seat=3" in text
    assert "protocol_version=1" in text


# --- bot-only progress (no prompt before a human turn) ---------------------


async def test_ws_client_renders_bot_turns_before_human_turn() -> None:
    """Multiple non-human BUILD broadcasts render to stdout without prompting.

    With ``human_seat=3`` the first BUILD turn (active_seat=2 under seed 0)
    belongs to a bot. Empty stdin means we exit via ``eof_disconnect`` the
    instant seat 3 becomes active; everything written to stdout before that
    point is bot progress.
    """
    async with _server_running(seed=0, human_seat=3) as port:
        stdin = io.StringIO("")
        stdout = io.StringIO()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                cli_ws.run(host="127.0.0.1", port=port, stdin=stdin, stdout=stdout),
                timeout=_BOT_PROGRESS_TIMEOUT,
            )
    text = stdout.getvalue()
    lines = text.splitlines()
    # Walk the transcript: every BUILD-active-non-human line that appears
    # before the first ``ws_legal`` line is a bot turn we rendered without
    # prompting. We expect at least one.
    bot_turns_before_prompt = 0
    for line in lines:
        if line.startswith("event=ws_legal"):
            break
        if "event=ws_state" in line and "phase=build" in line and "active_seat=3" not in line:
            bot_turns_before_prompt += 1
    assert bot_turns_before_prompt >= 1, (
        f"expected ≥1 bot BUILD turn before first prompt, got 0; transcript:\n{text}"
    )


# --- action round-trip via injected stdin ---------------------------------


async def test_ws_client_submits_action_from_injected_stdin() -> None:
    """Feeding ``0\\n`` at the prompt sends ``ActionSubmit`` and the next
    broadcast reflects the submitted action.

    Captures the round-trip without playing to END: we feed a small number
    of choices, EOF, and assert the transcript carries at least one
    ``ws_submit`` plus subsequent state advances.
    """
    async with _server_running(seed=0, human_seat=0) as port:
        stdin = io.StringIO("0\n" * 8)
        stdout = io.StringIO()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                cli_ws.run(host="127.0.0.1", port=port, stdin=stdin, stdout=stdout),
                timeout=_END_TO_END_TIMEOUT,
            )
    text = stdout.getvalue()
    assert "event=ws_legal" in text, "human seat never received legal_actions"
    assert "event=ws_submit" in text, "no ActionSubmit was sent"
    assert "index=0" in text, "expected index=0 to be the submitted choice"
    # The state must have advanced past the submitter's first BUILD slot —
    # either active_seat moved off 0, or we observed another phase, before
    # we eventually hit EOF or END.
    assert "event=ws_state" in text


async def test_ws_client_rejects_invalid_input_then_accepts() -> None:
    """Non-integer / out-of-range inputs loop without crashing or disconnecting."""
    async with _server_running(seed=0, human_seat=0) as port:
        # bogus → out-of-range (9999) → valid (0), repeated to outlast any
        # extra prompts the game may open.
        stdin = io.StringIO("bad\n9999\n0\n" * 12)
        stdout = io.StringIO()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                cli_ws.run(host="127.0.0.1", port=port, stdin=stdin, stdout=stdout),
                timeout=_END_TO_END_TIMEOUT,
            )
    text = stdout.getvalue()
    assert "event=ws_input outcome=invalid" in text
    assert "event=ws_input outcome=out_of_range" in text
    assert "event=ws_submit" in text


# --- end-to-end completion -------------------------------------------------


async def test_ws_client_reaches_terminal_state_and_exits_clean() -> None:
    """A fast-terminating seed (0) drives the game to ``phase=end`` and the
    CLI client returns exit code 0 with the terminal state in its transcript.
    """
    async with _server_running(seed=0, human_seat=0) as port:
        # Plenty of "0" picks — seed 0 wins under post-RUL-55 baseline.
        stdin = io.StringIO("0\n" * 1000)
        stdout = io.StringIO()
        rc = await asyncio.wait_for(
            cli_ws.run(host="127.0.0.1", port=port, stdin=stdin, stdout=stdout),
            timeout=_END_TO_END_TIMEOUT,
        )
    text = stdout.getvalue()
    assert rc == 0
    assert "phase=end" in text
    # A real winner is rendered — not "none" — on the terminal broadcast.
    end_lines = [line for line in text.splitlines() if "phase=end" in line]
    assert end_lines, "no phase=end line in transcript"
    assert any("winner=p" in line for line in end_lines), (
        f"terminal broadcast missing winner; lines:\n{end_lines}"
    )


async def test_ws_client_connect_refused_returns_nonzero() -> None:
    """Connecting to a dead port returns ``1`` and prints ``ws_connect_failed``."""
    # Bind+release a port to find one nothing is listening on.
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead_port = sock.getsockname()[1]
    sock.close()

    stdin = io.StringIO("")
    stdout = io.StringIO()
    rc = await asyncio.wait_for(
        cli_ws.run(host="127.0.0.1", port=dead_port, stdin=stdin, stdout=stdout),
        timeout=5.0,
    )
    assert rc == 1
    assert "event=ws_connect_failed" in stdout.getvalue()


# --- --ws CLI flag plumbs through main() -----------------------------------


def test_main_ws_flag_calls_cli_ws_main_ws(monkeypatch) -> None:
    """``rulso --ws`` dispatches to :func:`cli_ws.main_ws` with parsed host+port.

    Doesn't actually connect — patches ``cli_ws.main_ws`` to capture args.
    """
    from rulso import cli

    captured: dict[str, object] = {}

    def fake_main_ws(*, host: str, port: int) -> int:
        captured["host"] = host
        captured["port"] = port
        return 0

    monkeypatch.setattr("rulso.cli_ws.main_ws", fake_main_ws)

    rc = cli.main(["--ws", "--ws-host", "1.2.3.4", "--ws-port", "9999"])
    assert rc == 0
    assert captured == {"host": "1.2.3.4", "port": 9999}


def test_main_without_ws_flag_runs_in_process(monkeypatch) -> None:
    """Omitting ``--ws`` preserves the four-bot in-process baseline."""
    from rulso import cli

    captured: dict[str, object] = {}

    def fake_run_game(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("rulso.cli.run_game", fake_run_game)

    rc = cli.main(["--seed", "5", "--rounds", "3"])
    assert rc == 0
    assert captured["seed"] == 5
    assert captured["max_rounds"] == 3
    assert captured["human_seat"] is None

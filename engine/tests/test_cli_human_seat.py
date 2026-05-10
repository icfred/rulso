"""Smoke tests for the CLI ``--human-seat`` driver (RUL-52).

A scripted ``stdin`` pipes index choices in, the engine drives a full game,
and we assert the human-prompt path is exercised, invalid input is rejected
without crashing, EOF falls back to ``Pass``, and omitting the flag preserves
the four-bot baseline (no human prompts).
"""

from __future__ import annotations

import io

import pytest

from rulso.cli import main, run_game

_SEED = 0
_ROUNDS = 10


def _run_with_stdin(stdin_text: str, *, human_seat: int = 0) -> tuple[int, str]:
    out = io.StringIO()
    rc = run_game(
        seed=_SEED,
        max_rounds=_ROUNDS,
        out=out,
        human_seat=human_seat,
        human_stdin=io.StringIO(stdin_text),
    )
    return rc, out.getvalue()


def test_human_seat_picks_first_action_terminates() -> None:
    """``0\\n`` for every prompt drives the game to a terminal event."""
    rc, text = _run_with_stdin("0\n" * 500)
    assert rc in (0, 1)
    assert "event=human_prompt" in text
    assert "seat=0" in text
    assert "event=game_end" in text or "event=cap_hit" in text


def test_human_seat_rejects_invalid_then_accepts() -> None:
    """Non-integer and out-of-range inputs loop without crashing."""
    rc, text = _run_with_stdin("bad\n9999\n0\n" * 300)
    assert rc in (0, 1)
    assert "event=human_input outcome=invalid" in text
    assert "event=human_input outcome=out_of_range" in text
    assert "event=game_end" in text or "event=cap_hit" in text


def test_human_seat_eof_falls_back_to_pass() -> None:
    """Empty stdin → every human turn is a Pass; cap-hit is the expected end."""
    rc, text = _run_with_stdin("")
    assert rc in (0, 1)
    assert "event=human_input outcome=eof_pass" in text
    assert "event=game_end" in text or "event=cap_hit" in text


def test_no_human_seat_default_emits_no_human_events() -> None:
    """Omitting ``human_seat`` preserves the four-bot baseline output."""
    out = io.StringIO()
    rc = run_game(seed=_SEED, max_rounds=_ROUNDS, out=out)
    text = out.getvalue()
    assert rc in (0, 1)
    assert "event=human_prompt" not in text
    assert "event=human_input" not in text


def test_main_human_seat_flag_parses_and_runs(monkeypatch, capsys) -> None:
    """``--human-seat`` plumbs through ``main``; uses ``sys.stdin`` for input."""
    monkeypatch.setattr("sys.stdin", io.StringIO("0\n" * 500))
    rc = main(["--seed", str(_SEED), "--rounds", str(_ROUNDS), "--human-seat", "0"])
    captured = capsys.readouterr()
    assert rc in (0, 1)
    assert "event=human_prompt" in captured.out


@pytest.mark.parametrize("seat", [0, 1, 2, 3])
def test_human_seat_each_seat_index_works(seat: int) -> None:
    """All four seat indices route through the human driver without error."""
    rc, text = _run_with_stdin("0\n" * 500, human_seat=seat)
    assert rc in (0, 1)
    assert f"seat={seat}" in text
    assert "event=human_prompt" in text


def test_main_rejects_human_seat_out_of_range(capsys) -> None:
    """argparse ``choices`` rejects seat indices outside ``[0, PLAYER_COUNT)``."""
    with pytest.raises(SystemExit):
        main(["--human-seat", "9"])
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err

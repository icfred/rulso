"""Smoke test for the CLI runner.

Asserts the in-process entry point terminates without exceptions and produces
non-empty greppable output. Full game-completion semantics belong to RUL-12.
"""

from __future__ import annotations

import io

from rulso.cli import main, run_game


def test_main_runs_to_cap_without_exceptions(capsys) -> None:
    rc = main(["--seed", "0", "--rounds", "20"])
    captured = capsys.readouterr()
    assert rc in (0, 1)
    assert captured.out, "CLI produced no stdout"
    assert "event=game_start" in captured.out
    # Round-cap or winner — one of these terminal events must fire.
    assert ("event=cap_hit" in captured.out) or ("event=game_end" in captured.out)


def test_run_game_emits_round_start_events() -> None:
    buf = io.StringIO()
    rc = run_game(seed=0, max_rounds=5, out=buf)
    assert rc in (0, 1)
    text = buf.getvalue()
    assert "event=round_start round=1" in text
    # Round-cap path should print standings before cap_hit.
    if "event=cap_hit" in text:
        assert "event=standings" in text


def test_main_default_seed_and_rounds_run_succeeds(capsys) -> None:
    # Exercise argparse defaults; round cap small enough to keep the test fast
    # is set via explicit flag in the smoke test above. This run uses defaults
    # only for --seed.
    rc = main(["--rounds", "5"])
    captured = capsys.readouterr()
    assert rc in (0, 1)
    assert "event=game_start seed=0" in captured.out

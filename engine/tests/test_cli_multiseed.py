"""Multi-seed CLI smoke (RUL-12).

Sweeps 20 seeds through ``cli.main`` to prove M1's documented behaviour holds
regardless of RNG state: the round cap is always exhausted (no winner) and the
narration always emits the substrate events.

Why every run cap-hits: M1 hands are empty, so the random-legal bot Passes on
every build turn → no slot ever fills → every rule fails on the unfilled-slot
path → the round counter ticks until the cap. Asserting a winner is RUL-21.
"""

from __future__ import annotations

import io

import pytest

from rulso.cli import run_game

_SEEDS = tuple(range(20))
_ROUNDS = 20


@pytest.mark.parametrize("seed", _SEEDS)
def test_each_seed_terminates_without_exception_and_hits_cap(seed: int) -> None:
    buf = io.StringIO()
    rc = run_game(seed=seed, max_rounds=_ROUNDS, out=buf)
    assert rc == 1, f"seed={seed} expected cap-hit (rc=1), got rc={rc}"
    text = buf.getvalue()
    assert text, f"seed={seed}: empty stdout"
    assert "event=game_start" in text, f"seed={seed}: missing game_start"
    assert "event=round_start" in text, f"seed={seed}: missing round_start"
    assert "event=rule_failed" in text, f"seed={seed}: missing rule_failed"
    assert "event=cap_hit" in text, f"seed={seed}: missing cap_hit"


def test_all_seeds_emit_one_round_start_per_round() -> None:
    """Every cap-hit run starts exactly ``_ROUNDS`` rounds (one per cap budget)."""
    for seed in _SEEDS:
        buf = io.StringIO()
        run_game(seed=seed, max_rounds=_ROUNDS, out=buf)
        text = buf.getvalue()
        round_starts = text.count("event=round_start ")
        assert round_starts == _ROUNDS, f"seed={seed}: {round_starts} round_starts, want {_ROUNDS}"


def test_no_winner_emitted_across_seeds() -> None:
    """M1 reality check: no run produces ``event=game_end``. Lift this assertion in RUL-21."""
    for seed in _SEEDS:
        buf = io.StringIO()
        run_game(seed=seed, max_rounds=_ROUNDS, out=buf)
        assert "event=game_end" not in buf.getvalue(), f"seed={seed}: unexpected winner in M1"

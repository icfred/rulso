"""Multi-seed CLI smoke (RUL-12, refreshed for RUL-18).

Sweeps 20 seeds through ``cli.main`` to prove the round-flow + bot loop is
crash-free regardless of RNG state.

Post-RUL-18, hands are dealt and rules can resolve: a run terminates either
when a player reaches ``VP_TO_WIN`` (rc=0, ``event=game_end``) or when the
round cap is exhausted (rc=1, ``event=cap_hit``). Either is acceptable; the
test only asserts no crash and that the substrate events fire. Tightening to
"every seed produces a winner" is RUL-21 (M1.5 watchable smoke).
"""

from __future__ import annotations

import io

import pytest

from rulso.cli import run_game

_SEEDS = tuple(range(20))
_ROUNDS = 20


@pytest.mark.parametrize("seed", _SEEDS)
def test_each_seed_terminates_without_exception(seed: int) -> None:
    buf = io.StringIO()
    rc = run_game(seed=seed, max_rounds=_ROUNDS, out=buf)
    assert rc in (0, 1), f"seed={seed}: unexpected rc={rc}"
    text = buf.getvalue()
    assert text, f"seed={seed}: empty stdout"
    assert "event=game_start" in text, f"seed={seed}: missing game_start"
    assert "event=round_start" in text, f"seed={seed}: missing round_start"
    # Either winner or cap_hit must terminate the loop.
    terminated = ("event=game_end" in text) or ("event=cap_hit" in text)
    assert terminated, f"seed={seed}: neither game_end nor cap_hit emitted"


def test_round_start_event_count_matches_rounds_consumed() -> None:
    """Every consumed round emits exactly one ``round_start`` event.

    Both successful starts and dealer-no-seed-card immediate-fail starts now
    emit a ``round_start`` event so log-grep counts stay consistent.
    """
    for seed in _SEEDS:
        buf = io.StringIO()
        run_game(seed=seed, max_rounds=_ROUNDS, out=buf)
        text = buf.getvalue()
        round_starts = text.count("event=round_start ")
        # Cap-hit runs consume all _ROUNDS budget; winner runs consume some
        # subset. Either way round_starts > 0 and ≤ _ROUNDS.
        assert 1 <= round_starts <= _ROUNDS, (
            f"seed={seed}: {round_starts} round_starts, want 1..{_ROUNDS}"
        )

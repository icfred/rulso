"""M1.5 watchable smoke (RUL-21).

End-to-end bar that promises a recognisable game: bots play real cards from
real hands, IF rules resolve, +1 VP fires, and a winner emerges in a
non-trivial fraction of the sweep. RUL-22's ``docs/engine/m1-smoke.md``
explicitly defers the "real game produces a winner" assertion to this file.

Empirical baseline at ``rounds=100`` (RUL-21 worker probe with the
post-RUL-27 play-bias bot): 6/10 seeds win, 10/10 runs see at least one
``event=resolve``, 63 total resolves across the sweep. Floors below sit well
under those values to absorb future bot/rules drift without going green on
genuinely-broken pipelines.

Stalls on a subset of seeds (e.g. 0, 1, 8, 9) are
``rule_failed reason=dealer_no_seed_card`` runs: per RUL-18 the dealer must
seed slot 0 from hand or the rule fails immediately and the dealer rotates.
That is correct behaviour, not a bug; see ``docs/engine/m1-5-smoke.md``.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from rulso.cli import main

_SEEDS: tuple[int, ...] = tuple(range(10))
_ROUNDS = 100

# Floors well below observed values (winners=6, runs_with_resolve=10,
# total_resolves=63). Tightening them later is fine; loosening them needs a
# matching note in docs/engine/m1-5-smoke.md.
_MIN_WINNERS = 1
_MIN_RUNS_WITH_RESOLVE = 5
_MIN_TOTAL_RESOLVES = 30


@pytest.fixture(scope="module")
def sweep() -> dict[int, str]:
    """Run ``cli.main`` once per seed and return seed → captured stdout."""
    results: dict[int, str] = {}
    for seed in _SEEDS:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--seed", str(seed), "--rounds", str(_ROUNDS)])
        text = buf.getvalue()
        # Record rc into the captured text on a side-channel line so per-test
        # assertions can recover it without re-running the game.
        results[seed] = f"__rc__={rc}\n{text}"
    return results


def _rc(captured: str) -> int:
    first, _, _ = captured.partition("\n")
    assert first.startswith("__rc__=")
    return int(first.removeprefix("__rc__="))


def _is_winner(captured: str) -> bool:
    return _rc(captured) == 0 and "event=game_end" in captured


@pytest.mark.parametrize("seed", _SEEDS)
def test_each_seed_terminates_without_exception(seed: int, sweep: dict[int, str]) -> None:
    captured = sweep[seed]
    rc = _rc(captured)
    assert rc in (0, 1), f"seed={seed}: unexpected rc={rc}"
    assert f"event=game_start seed={seed}" in captured, f"seed={seed}: missing game_start"
    assert "event=round_start" in captured, f"seed={seed}: build loop never started a round"
    terminated = ("event=game_end" in captured) or ("event=cap_hit" in captured)
    assert terminated, f"seed={seed}: neither game_end nor cap_hit emitted"


def test_at_least_one_seed_produces_a_winner(sweep: dict[int, str]) -> None:
    """The watchable bar — a real game must end with a winner across the sweep."""
    winners = sum(1 for seed in _SEEDS if _is_winner(sweep[seed]))
    assert winners >= _MIN_WINNERS, (
        f"no seed produced a winner across {len(_SEEDS)} runs at rounds={_ROUNDS}; "
        f"rules pipeline or +1 VP effect may be broken"
    )


def test_rules_resolve_across_the_sweep(sweep: dict[int, str]) -> None:
    """Every IF rule that fully fills emits ``event=resolve``.

    A near-zero total means rules never fill — usually a bot regression
    (always discarding) or a slot-typing change that stops legal plays.
    """
    total_resolves = sum(sweep[seed].count("event=resolve ") for seed in _SEEDS)
    assert total_resolves >= _MIN_TOTAL_RESOLVES, (
        f"only {total_resolves} rules resolved across all {len(_SEEDS)} seeds "
        f"(floor={_MIN_TOTAL_RESOLVES}); resolver path may not be firing"
    )


def test_resolves_are_not_one_lucky_seed(sweep: dict[int, str]) -> None:
    """Resolves should be spread across most seeds, not concentrated in one."""
    runs_with_resolve = sum(1 for seed in _SEEDS if sweep[seed].count("event=resolve ") > 0)
    assert runs_with_resolve >= _MIN_RUNS_WITH_RESOLVE, (
        f"only {runs_with_resolve}/{len(_SEEDS)} runs saw any resolve "
        f"(floor={_MIN_RUNS_WITH_RESOLVE}); rule fills may be too sparse"
    )

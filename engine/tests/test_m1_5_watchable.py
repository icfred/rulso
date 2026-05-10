"""M1.5 watchable smoke (RUL-21, re-contracted RUL-34 for M2 Phase 3).

## Contract during M2 Phase 3

This is now a **regression backstop**, not the watchable bar. It asserts the
engine still terminates and rules still fire — not that winners emerge. The
"someone wins" promise moves to RUL-35's M2 watchable smoke, which lands as
the Phase 3 tail and re-asserts the watchable contract on the fully-wired M2
deck.

Why the demotion: each Phase 3 ticket extends ``cards.yaml deck:`` for its
consumer. Even silently-safe additions (ANYONE/EACH no-op via empty scope;
JOKERs sit in-hand) dilute the rule-fire pool — winners drop from 6/10 to
1-2/10 without the engine being broken (RUL-31 + RUL-34 worker probes). If
the smoke kept ``_MIN_WINNERS = 1``, the first Phase 3 PR to extend ``deck:``
would land it red on a correct change. Instead we let the winner count
degrade gracefully through Phase 3 and tighten back up in RUL-35.

## What this still catches

- The CLI runs to termination across the seed sweep without exception.
- Each seed emits ``game_start`` + ``round_start`` and reaches either
  ``game_end`` or ``cap_hit``.
- Rules resolve in volume across the sweep — a near-zero ``total_resolves``
  or a sweep where most seeds see no resolve at all means the resolver path
  is broken (bot regression, slot-typing change, grammar fault).

## Empirical baselines

Seeds 0..9 at ``rounds=100``:

| Probe                                     | winners | runs_with_resolve | total_resolves |
|-------------------------------------------|---------|-------------------|----------------|
| baseline (post-RUL-27, current ``deck:``) | 6       | 10                | 63             |
| RUL-34 worst-case (silently-safe adds)    | 1       | 10                | 49             |

Worst-case is the min across three 10-seed windows (0..9 / 10..19 / 20..29)
with subj.anyone, subj.each, jkr.persist_when, jkr.persist_while, jkr.double,
jkr.echo each at +2 copies on top of the M1.5 baseline. Floors below sit at
worst-case × 0.7 — tight enough to fail loudly on a real regression, loose
enough to absorb Phase 3 deck dilution.

Stalls on a subset of seeds (e.g. 0, 1, 8, 9 in the baseline) are
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

# RUL-34: winner floor dropped to 0 — winner-emergence is asserted by RUL-35's
# M2 watchable smoke once the Phase 3 fan completes. Resolve floors derived
# from the worst-case probe (winners=1, runs_with_resolve=10, total_resolves=49)
# at 0.7 margin: floor(10 * 0.7) = 7, floor(49 * 0.7) = 34. Tightening is fine;
# loosening needs a matching note in docs/engine/m1-5-smoke.md.
_MIN_WINNERS = 0
_MIN_RUNS_WITH_RESOLVE = 7
_MIN_TOTAL_RESOLVES = 34


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


@pytest.mark.parametrize("seed", _SEEDS)
def test_each_seed_terminates_without_exception(seed: int, sweep: dict[int, str]) -> None:
    captured = sweep[seed]
    rc = _rc(captured)
    assert rc in (0, 1), f"seed={seed}: unexpected rc={rc}"
    assert f"event=game_start seed={seed}" in captured, f"seed={seed}: missing game_start"
    assert "event=round_start" in captured, f"seed={seed}: build loop never started a round"
    terminated = ("event=game_end" in captured) or ("event=cap_hit" in captured)
    assert terminated, f"seed={seed}: neither game_end nor cap_hit emitted"


def test_rules_resolve_across_the_sweep(sweep: dict[int, str]) -> None:
    """Every IF rule that fully fills emits ``event=resolve``.

    A near-zero total means rules never fill — usually a bot regression
    (always discarding) or a slot-typing change that stops legal plays.
    Phase 3 deck dilution shifts the count downward; floor accommodates that
    while still catching genuine breakage.
    """
    total_resolves = sum(sweep[seed].count("event=resolve ") for seed in _SEEDS)
    assert total_resolves >= _MIN_TOTAL_RESOLVES, (
        f"only {total_resolves} rules resolved across all {len(_SEEDS)} seeds "
        f"(floor={_MIN_TOTAL_RESOLVES}); resolver path may not be firing"
    )


def test_resolves_are_not_one_lucky_seed(sweep: dict[int, str]) -> None:
    """Resolves should be spread across most seeds, not concentrated in one.

    Phase 3 worst-case probe still sees 10/10 seeds resolve at least once;
    the floor leaves margin for further dilution as more variants land.
    """
    runs_with_resolve = sum(1 for seed in _SEEDS if sweep[seed].count("event=resolve ") > 0)
    assert runs_with_resolve >= _MIN_RUNS_WITH_RESOLVE, (
        f"only {runs_with_resolve}/{len(_SEEDS)} runs saw any resolve "
        f"(floor={_MIN_RUNS_WITH_RESOLVE}); rule fills may be too sparse"
    )

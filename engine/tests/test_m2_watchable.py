"""M2 watchable smoke (RUL-35) — Wave 3 gate.

Reclaims the "someone wins" bar that ``test_m1_5_watchable.py`` deferred for
Phase 3 (RUL-34 re-contracted it as a regression backstop while ``deck:`` was
being filled). With the full M2 vocabulary wired and RUL-54's determinism
substrate in place, this smoke asserts the engine produces winners across a
seed sweep and that all three rule lifetimes (IF / WHEN / WHILE) plus the
goal-claim and chip-effect paths are exercised end-to-end.

## Shape

10 seeds × ``rounds=200`` via ``cli.main``. Stdout drives the termination /
winner / resolve assertions exactly as M1.5 does. To assert lifecycle
coverage that the CLI does not surface — WHEN/WHILE persistent rules, goal
claims, chip-affecting effects — the fixture wraps four engine entry points
(``effects.resolve_if_rule``, ``persistence.check_when_triggers``,
``persistence.tick_while_rules``, ``goals.check_claims``) with non-mutating
counters and restores the originals on teardown. The wrappers do not alter
any state passing through; they only observe.

This pattern is testing-only and reversible. No production module is
modified by this ticket (RUL-35 hard constraint).

## Empirical baseline (deterministic main post-RUL-55)

Seeds 0..9 at ``rounds=200``:

| Metric                                        | Observed | Floor |
|-----------------------------------------------|----------|-------|
| winners                                       | 7/10     | 7     |
| runs with ≥1 ``event=resolve``                | 10/10    | 8     |
| persistent WHEN rules observed (sweep total)  | ≥1       | 1     |
| persistent WHILE rules observed (sweep total) | ≥1       | 1     |
| goal-claim VP awarded (sweep total)           | ≥1       | 1     |
| effect chip-delta (sweep total)               | ≥1       | 1     |

Winners under the RUL-55 PLAY_BIAS=0.75 heuristic: seeds 0/1/3/4/5/7/9.
Cap-hit: seeds 2/6/8. Bimodal split is stable across ``rounds=200`` and
``rounds=300`` — a substrate property of the current bots, not flake.
Below 7/10 fires the next polish ticket; ≤6/10 with random bots is the
"the bots are bad" signal that M3 ISMCTS addresses.

Lifecycle-coverage floors are pinned at 1 (sweep-aggregate) by design — the
DoD asks for "at least one … across sweep". The observed counts are orders
of magnitude above the floor; a regression that drops any of them to zero
means the corresponding code path stopped firing, which is exactly what we
want to catch.

See ``docs/engine/m2-smoke.md`` for the per-assertion rationale.
"""

from __future__ import annotations

import contextlib
import io
import re
from typing import Any

import pytest

from rulso import effects, goals, persistence
from rulso.cli import main
from rulso.state import RuleKind

_SEEDS: tuple[int, ...] = tuple(range(10))
_ROUNDS = 200

# RUL-55 (Phase 3.5 polish) raised the floor from 5 → 7 after PLAY_BIAS
# 0.85 → 0.75 in ``bots.random``. Deterministic baseline is 7/10 winners
# at rounds=200 across seeds 0..9, stable at rounds=300. Set at the
# observed count with no slack — below 7 is the next polish trigger.
_MIN_WINNERS = 7
# Observed 10/10 in the baseline probe; 0.8 margin absorbs minor variance.
_MIN_RUNS_WITH_RESOLVE = 8
# Lifecycle floors — DoD asks "at least one … across sweep". Observed counts
# are 100×–1000× the floor; a regression to zero means the path stopped firing.
_MIN_PERSISTENT_WHEN_TOTAL = 1
_MIN_PERSISTENT_WHILE_TOTAL = 1
_MIN_GOAL_VP_AWARDED = 1
_MIN_EFFECT_CHIP_DELTA = 1


def _chip_total(state: Any) -> int:
    return sum(p.chips for p in state.players)


def _vp_total(state: Any) -> int:
    return sum(p.vp for p in state.players)


@pytest.fixture(scope="module")
def sweep() -> dict[int, dict[str, Any]]:
    """Run the CLI once per seed; capture stdout + lifecycle counts.

    Wraps four engine entry points to count lifecycle events the CLI does
    not narrate (WHEN/WHILE persistence, goal claims, chip-effect deltas).
    Wrappers are pure observers — they forward arguments unchanged and
    return the original output. Originals are restored on teardown so other
    test modules in the same pytest session are unaffected.
    """
    results: dict[int, dict[str, Any]] = {}

    orig_resolve = effects.resolve_if_rule
    orig_check_when = persistence.check_when_triggers
    orig_tick_while = persistence.tick_while_rules
    orig_check_claims = goals.check_claims

    current: dict[str, Any] = {}

    def wrapped_resolve(state, rule, *args, **kw):
        before_chips = _chip_total(state)
        out = orig_resolve(state, rule, *args, **kw)
        current["effect_chip_delta"] += abs(_chip_total(out) - before_chips)
        return out

    def wrapped_check_when(state, lab):
        out = orig_check_when(state, lab)
        if out != state:
            current["when_triggers_changed_state"] += 1
        return out

    def wrapped_tick_while(state, lab):
        out = orig_tick_while(state, lab)
        for pr in out.persistent_rules:
            if pr.kind is RuleKind.WHEN:
                current["persistent_when_total"] += 1
            elif pr.kind is RuleKind.WHILE:
                current["persistent_while_total"] += 1
        return out

    def wrapped_check_claims(state):
        before_vp = _vp_total(state)
        out = orig_check_claims(state)
        current["goal_vp_awarded"] += _vp_total(out) - before_vp
        return out

    effects.resolve_if_rule = wrapped_resolve
    persistence.check_when_triggers = wrapped_check_when
    persistence.tick_while_rules = wrapped_tick_while
    goals.check_claims = wrapped_check_claims
    try:
        for seed in _SEEDS:
            current.clear()
            current.update(
                effect_chip_delta=0,
                when_triggers_changed_state=0,
                persistent_when_total=0,
                persistent_while_total=0,
                goal_vp_awarded=0,
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["--seed", str(seed), "--rounds", str(_ROUNDS)])
            results[seed] = {
                "rc": rc,
                "stdout": buf.getvalue(),
                **dict(current),
            }
    finally:
        effects.resolve_if_rule = orig_resolve
        persistence.check_when_triggers = orig_check_when
        persistence.tick_while_rules = orig_tick_while
        goals.check_claims = orig_check_claims

    return results


def _is_winner(captured: str) -> bool:
    if "event=game_end" not in captured:
        return False
    return re.search(r"event=game_end winner=p\d", captured) is not None


@pytest.mark.parametrize("seed", _SEEDS)
def test_each_seed_terminates_without_exception(seed: int, sweep) -> None:
    record = sweep[seed]
    rc = record["rc"]
    text = record["stdout"]
    assert rc in (0, 1), f"seed={seed}: unexpected rc={rc}"
    assert f"event=game_start seed={seed}" in text, f"seed={seed}: missing game_start"
    assert "event=round_start" in text, f"seed={seed}: build loop never started a round"
    terminated = ("event=game_end" in text) or ("event=cap_hit" in text)
    assert terminated, f"seed={seed}: neither game_end nor cap_hit emitted"


@pytest.mark.parametrize("seed", _SEEDS)
def test_each_seed_reaches_resolve(seed: int, sweep) -> None:
    """Every seed must enter ``Phase.RESOLVE`` at least once.

    Per the RUL-35 hand-over hard asserts: independent of winner emergence,
    a working substrate must produce at least one resolved rule per game.
    """
    text = sweep[seed]["stdout"]
    assert "event=resolve " in text, f"seed={seed}: no resolve event emitted"


def test_winners_emerge_across_the_sweep(sweep) -> None:
    """Reclaim the M1.5 watchable bar deferred by RUL-34 during Phase 3.

    Pinned at 7/10 — the deterministic post-RUL-55 baseline (PLAY_BIAS=0.75).
    Below 7 means the bot heuristic regressed; ≤6/10 means random bots can't
    carry the deck and M3 ISMCTS is the next move (RUL-55 Stop condition).
    """
    winners = sum(1 for seed in _SEEDS if _is_winner(sweep[seed]["stdout"]))
    assert winners >= _MIN_WINNERS, (
        f"only {winners}/{len(_SEEDS)} seeds produced a winner "
        f"(floor={_MIN_WINNERS}); deck/bot heuristic regressed below the Wave 3 gate"
    )


def test_resolves_spread_across_most_seeds(sweep) -> None:
    """Resolves should fire on most seeds, not concentrate in one or two."""
    runs_with_resolve = sum(
        1 for seed in _SEEDS if sweep[seed]["stdout"].count("event=resolve ") > 0
    )
    assert runs_with_resolve >= _MIN_RUNS_WITH_RESOLVE, (
        f"only {runs_with_resolve}/{len(_SEEDS)} seeds saw any resolve "
        f"(floor={_MIN_RUNS_WITH_RESOLVE}); rule fills may be too sparse"
    )


def test_persistent_when_lifecycle_exercised(sweep) -> None:
    """JOKER:PERSIST_WHEN / JOKER:ECHO promotes IF rules to WHEN persistence.

    Counts how many WHEN-kinded rules are observed in ``persistent_rules``
    across all ``tick_while_rules`` invocations in the sweep. A non-zero
    total proves the WHEN promotion + tick path is wired end-to-end.
    """
    total = sum(sweep[seed]["persistent_when_total"] for seed in _SEEDS)
    assert total >= _MIN_PERSISTENT_WHEN_TOTAL, (
        f"persistent WHEN rules never observed across {len(_SEEDS)} seeds; "
        "JOKER PERSIST_WHEN / ECHO promotion path is not firing"
    )


def test_persistent_while_lifecycle_exercised(sweep) -> None:
    """JOKER:PERSIST_WHILE promotes IF rules to WHILE persistence.

    Counts how many WHILE-kinded rules are observed in ``persistent_rules``
    across all ``tick_while_rules`` invocations in the sweep.
    """
    total = sum(sweep[seed]["persistent_while_total"] for seed in _SEEDS)
    assert total >= _MIN_PERSISTENT_WHILE_TOTAL, (
        f"persistent WHILE rules never observed across {len(_SEEDS)} seeds; "
        "JOKER PERSIST_WHILE promotion path is not firing"
    )


def test_goal_claims_award_vp(sweep) -> None:
    """At least one goal claim across the sweep awards VP.

    ``goals.check_claims`` runs at every resolve. The sweep-aggregate VP
    delta proves the claim predicates evaluate against state and the award
    side-effect lands on players. Zero across all 10 seeds means goal
    claiming is broken.
    """
    total = sum(sweep[seed]["goal_vp_awarded"] for seed in _SEEDS)
    assert total >= _MIN_GOAL_VP_AWARDED, (
        f"no goal claims awarded VP across {len(_SEEDS)} seeds; "
        "goal predicate evaluation or VP award path is broken"
    )


def test_effect_application_moves_chips(sweep) -> None:
    """At least one effect application produces a chip delta across the sweep.

    The aggregate ``abs(chip_total_before - chip_total_after)`` across every
    ``effects.resolve_if_rule`` call. Zero means no resolved rule landed a
    chip-affecting effect — either every resolve had empty scope or the
    effect dispatcher silently dropped the application.
    """
    total = sum(sweep[seed]["effect_chip_delta"] for seed in _SEEDS)
    assert total >= _MIN_EFFECT_CHIP_DELTA, (
        f"no chip-affecting effects landed across {len(_SEEDS)} seeds; "
        "effect dispatcher or resolver scope path is broken"
    )

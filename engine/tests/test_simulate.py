"""Sim harness tests (RUL-74).

Asserts the four contracts the sim harness ships under:

1. **Determinism**: same args ⇒ byte-identical JSON dump (per the RUL-54
   disjoint-rng pattern). Run twice; compare ``to_json_dict`` output.
2. **Coverage**: each metric category produces ≥1 positive count over a
   100-game sweep. Zero across a category implies the wiring broke, not bot
   variance — the M2 watchable smoke (RUL-35) pins the same lifecycle floors
   at much smaller seed counts.
3. **Anomaly flags**: synthetic payloads trigger the documented flags
   (zero-occurrence card / effect / goal, winner-distribution skew, cap-hit
   threshold).
4. **No engine leakage**: after :func:`simulate` returns, the patched engine
   entry points are restored (other tests in the same session must not see
   wrapped functions).

The 100-game sweep runs once via a module-scoped fixture. Per-category
assertions are individual tests so a regression names the broken metric.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from rulso import effects, goals, status
from rulso.simulate import (
    _detect_anomalies,
    format_summary,
    simulate,
    to_json_dict,
)

_GAMES = 100
_SEED_BASE = 0
_MAX_ROUNDS = 200


@pytest.fixture(scope="module")
def sweep() -> dict[str, Any]:
    """Run the 100-game sweep once and yield the JSON payload."""
    results = simulate(games=_GAMES, seed_base=_SEED_BASE, max_rounds=_MAX_ROUNDS)
    return to_json_dict(results)


def test_simulate_is_deterministic() -> None:
    """Same args ⇒ byte-identical JSON dump.

    Uses 50 games to keep the test fast (~15s on a dev machine); RUL-54's
    disjoint-rng pattern guarantees per-seed reproducibility, so 50 games
    is sufficient to surface any non-determinism that would show up at
    larger N.
    """
    a = to_json_dict(simulate(games=50, seed_base=0, max_rounds=_MAX_ROUNDS))
    b = to_json_dict(simulate(games=50, seed_base=0, max_rounds=_MAX_ROUNDS))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_winner_distribution_populated(sweep: dict[str, Any]) -> None:
    wd = sweep["winner_distribution"]
    assert wd["winners"] > 0, "no winners emerged over 100 games — bot/engine regressed"
    assert wd["winners"] + wd["cap_hits"] == _GAMES


def test_game_length_distribution_populated(sweep: dict[str, Any]) -> None:
    gl = sweep["game_length"]
    assert gl["min"] >= 1
    assert gl["max"] >= gl["min"]
    assert gl["mean"] > 0
    assert 0.0 <= gl["cap_hit_rate"] <= 1.0


def test_card_usage_populated(sweep: dict[str, Any]) -> None:
    total = sum(sweep["card_usage"].values())
    assert total > 0, "no cards played across 100 games"


def test_effect_cards_populated(sweep: dict[str, Any]) -> None:
    drawn_total = sum(row["drawn"] for row in sweep["effect_cards"].values())
    fired_total = sum(row["fired"] for row in sweep["effect_cards"].values())
    assert drawn_total > 0, "no effect cards drawn"
    assert fired_total > 0, "effect cards drawn but never fired"


def test_goal_claims_populated(sweep: dict[str, Any]) -> None:
    total = sum(sweep["goal_claims"].values())
    assert total > 0, "no goal claims awarded VP across 100 games"


def test_joker_attachments_populated(sweep: dict[str, Any]) -> None:
    total = sum(sweep["joker_attachments"].values())
    assert total > 0, "no JOKER attachments across 100 games"


def test_vp_attribution_populated(sweep: dict[str, Any]) -> None:
    vp = sweep["vp_attribution"]
    assert vp["all_games"]["rule_vp"] + vp["all_games"]["goal_vp"] > 0


def test_status_tokens_populated(sweep: dict[str, Any]) -> None:
    """At least one status-token application + at least one decay tick fire."""
    tokens = sweep["status_tokens"]
    apply_total = sum(row["apply"] for row in tokens.values())
    decay_total = sum(row["decay"] for row in tokens.values())
    assert apply_total > 0, "no status tokens applied across 100 games"
    assert decay_total > 0, "no status-token decays observed"


def test_chip_economy_populated(sweep: dict[str, Any]) -> None:
    ce = sweep["chip_economy"]
    assert ce["min"] >= 0
    assert ce["max"] >= ce["min"]


def test_anomaly_flags_zero_play_card() -> None:
    """Synthetic payload with a zero-play card raises the WARN flag."""
    payload = _baseline_payload()
    payload["card_usage"] = {"subj.dead_card": 0, "noun.live": 5}
    flags = _detect_anomalies(payload, n_games=10)
    assert any("'subj.dead_card'" in f and "never played" in f for f in flags)


def test_anomaly_flags_winner_skew() -> None:
    """Synthetic payload with seat-0 hogging winners raises the skew flag."""
    payload = _baseline_payload()
    payload["winner_distribution"] = {
        "winners": 10,
        "cap_hits": 0,
        "by_seat": {"0": 9, "1": 1},
    }
    flags = _detect_anomalies(payload, n_games=10)
    assert any("skewed" in f for f in flags)


def test_anomaly_flags_cap_hit_rate() -> None:
    """Synthetic payload with cap-hit rate above threshold raises the flag."""
    payload = _baseline_payload()
    payload["game_length"]["cap_hit_rate"] = 0.75
    flags = _detect_anomalies(payload, n_games=10)
    assert any("cap-hit rate" in f for f in flags)


def test_anomaly_flags_dead_effect() -> None:
    """Effect drawn but never fired raises a distinct WARN."""
    payload = _baseline_payload()
    payload["effect_cards"] = {
        "eff.dead": {"drawn": 4, "fired": 0, "fire_rate": 0.0},
    }
    flags = _detect_anomalies(payload, n_games=10)
    assert any("'eff.dead'" in f and "never fired" in f for f in flags)


def test_anomaly_flags_dead_goal() -> None:
    payload = _baseline_payload()
    payload["goal_claims"] = {"goal.dead": 0, "goal.live": 3}
    flags = _detect_anomalies(payload, n_games=10)
    assert any("'goal.dead'" in f and "never claimed" in f for f in flags)


def test_simulate_restores_engine_after_run() -> None:
    """Calling simulate() must leave the engine entry points unwrapped."""
    pre_dispatch = effects.dispatch_effect
    pre_resolve_if = effects.resolve_if_rule
    pre_resolve_one_goal = goals._resolve_one_goal
    pre_apply_burn = status.apply_burn
    pre_tick_round_start = status.tick_round_start
    simulate(games=2, seed_base=0, max_rounds=50)
    assert effects.dispatch_effect is pre_dispatch
    assert effects.resolve_if_rule is pre_resolve_if
    assert goals._resolve_one_goal is pre_resolve_one_goal
    assert status.apply_burn is pre_apply_burn
    assert status.tick_round_start is pre_tick_round_start


def test_format_summary_is_compact(sweep: dict[str, Any]) -> None:
    """Terminal summary stays under 50 lines per DoD."""
    text = format_summary(sweep)
    lines = text.splitlines()
    assert len(lines) <= 50, f"summary exceeded 50 lines (got {len(lines)})"
    # spot-check the required sections are present
    assert any("simulate:" in line for line in lines)
    assert any("winners:" in line for line in lines)
    assert any("vp_source" in line for line in lines)
    assert any("status" in line for line in lines)


def _baseline_payload() -> dict[str, Any]:
    """A minimal anomaly-free payload that individual tests mutate."""
    return {
        "config": {"games": 10, "seed_base": 0, "max_rounds": 200},
        "winner_distribution": {
            "winners": 10,
            "cap_hits": 0,
            "by_seat": {"0": 3, "1": 2, "2": 3, "3": 2},
        },
        "game_length": {
            "min": 5,
            "max": 50,
            "mean": 20.0,
            "median": 18,
            "std": 5.0,
            "cap_hit_rate": 0.0,
        },
        "card_usage": {"noun.chips": 10},
        "effect_cards": {"eff.live": {"drawn": 3, "fired": 3, "fire_rate": 1.0}},
        "goal_claims": {"goal.live": 4},
        "joker_attachments": {"JOKER:DOUBLE": 2},
        "vp_attribution": {
            "all_games": {"rule_vp": 5, "goal_vp": 3},
            "winning_games": {"rule_vp": 5, "goal_vp": 3},
        },
        "status_tokens": {"BURN": {"apply": 2, "clear": 1, "decay": 4}},
        "chip_economy": {"min": 30, "max": 80, "mean": 50.0, "median": 50, "std": 10.0},
    }

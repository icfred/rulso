_Last edited: 2026-05-12 by RUL-74_

# simulate.py — sim harness

Bot-vs-bot simulation runner. Same engine, same `bots.random`, no I/O during
play — just metrics. Surfaces quantitative design signal (dead cards, dead
goals, positional bias, cap-hit-prone configurations) that line-oriented CLI
playtest output cannot.

Same harness will host ISMCTS rollouts (M4 sub-issue) once the bot lands.

## Module: `rulso.simulate`

| Symbol | Purpose |
|---|---|
| `simulate(*, games, seed_base, max_rounds) -> SimResults` | Run N self-play games and aggregate stats. Patches engine entry points for observation; restores them in `finally`. |
| `to_json_dict(results) -> dict` | Serialise `SimResults` to a JSON-friendly nested dict (deterministic key order). |
| `format_summary(payload) -> str` | Render a ≤50-line terminal summary of the JSON payload. |
| `run(argv, out)` | CLI entry; parses args, calls `simulate`, dumps JSON and/or prints summary. Dispatched from `rulso.cli.main` when the first positional arg is `simulate`. |

## CLI

```
rulso simulate [--games N] [--seed-base S] [--rounds R]
               [--analyse [PATH]] [--summary]
```

| Flag | Default | Meaning |
|---|---|---|
| `--games` | 1000 | Number of self-play games. Game `i` uses seed `seed_base + i`. |
| `--seed-base` | 0 | Seed for game 0; downstream seeds are offset from this base. |
| `--rounds` | 200 | Per-game round cap. Cap-hits count as a non-winner game. |
| `--analyse` | _omitted_ | Write JSON dump. Bare `--analyse` ⇒ `simulate.json`; `--analyse path.json` chooses the path. |
| `--summary` | _off_ | Print the terminal summary. Implicit when `--analyse` is omitted. |

Examples:

```bash
uv run rulso simulate --games 1000 --summary
uv run rulso simulate --games 5000 --analyse run.json
uv run rulso simulate --games 1000 --analyse --summary
```

## Determinism

Inherits the RUL-54 disjoint-rng pattern: per seed `s` the four rngs are
`random.Random(s) / s ^ 0x5EED / s ^ 0xD1CE / s ^ 0xEFFC`. Same
`games + seed_base + rounds` ⇒ byte-identical JSON output.
`test_simulate.py::test_simulate_is_deterministic` pins the contract.

## Observation pattern (no engine mutation)

Per the RUL-74 hand-over constraint, no engine production module is modified.
The sim patches engine module-level attributes at the start of `simulate()`
and restores them in a `finally` block (same shape as `tests/test_m2_watchable.py`):

| Wrapped | Counter |
|---|---|
| `effects.dispatch_effect` | effect fire histogram (per `Card.id`) |
| `effects.resolve_if_rule` | rule-effect VP attribution (Δ of `Σ player.vp`) |
| `goals._resolve_one_goal` | goal-claim histogram + goal VP attribution |
| `status.apply_burn` / `apply_mute` / `apply_blessed` / `apply_marked` / `apply_chained` | apply counters per token |
| `status.clear_burn` / `clear_chained` | explicit-clear counters |
| `status.consume_blessed_or_else` | BLESSED clear-on-consume counter |
| `status.tick_round_start` / `tick_resolve_end` | decay counters (BURN tick magnitude, MUTE/MARKED natural lifetime) |

The sim runner additionally tracks driver-side metrics (card plays, joker
plays, effect draws, winner seat, rounds started) by direct observation inside
its own loop without patching `cli.run_game`.

## Performance — `cards.*` cache

Profiling at RUL-74 surfaced that `cards._read` is called once per round
(via `rules._draw_condition_template`) — for a 10-game sweep that was 889
yaml parses and 87% of runtime. The sim wraps `cards.load_condition_templates`
and siblings with closures returning a pre-computed value for the duration of
one `simulate()` call; originals are restored on teardown. Same observer
shape as the engine wrappers — no permanent module-level state.

Throughput after the cache:

| Workload | Time | Rate |
|---|---|---|
| `simulate(games=100, max_rounds=200)` | ~1.0s | ~100 games/sec |
| `rulso simulate --games 1000` | ~7.7s | ~130 games/sec |

`test_simulate.py` runs the full 17-test suite in ~2 seconds.

The cache lives only inside `simulate()`. The CLI path
(`cli.run_game`, `rulso-server`) continues to hit the yaml on every round —
engine-side caching is a follow-on ticket if other call sites want it.

## JSON schema

```jsonc
{
  "config": {
    "games": 1000,
    "seed_base": 0,
    "max_rounds": 200
  },
  "winner_distribution": {
    "winners": 681,           // games that produced a winner
    "cap_hits": 319,          // games that hit max_rounds without a winner
    "by_seat": {"0": 190, "1": 175, "2": 152, "3": 164}
  },
  "game_length": {
    "min": 4, "max": 200,
    "mean": 84.6, "median": 49, "std": 78.2,
    "cap_hit_rate": 0.319
  },
  "card_usage": {              // by Card.id; zero-play ids included
    "subj.anyone": 0,
    "noun.chips": 5217,
    "...": 0
  },
  "effect_cards": {            // per effect_cards: entry in cards.yaml
    "eff.chips.gain.5": {
      "drawn": 528,            // times the card was revealed (1 per round)
      "fired": 660,            // dispatch_effect non-trivial calls (may
                               // exceed drawn under EACH_PLAYER scope)
      "fire_rate": 1.25        // fired / drawn
    }
  },
  "goal_claims": {             // by GoalCard.id; zero-claim ids included
    "goal.hoarder": 2197,
    "goal.builder": 0
  },
  "joker_attachments": {
    "JOKER:PERSIST_WHEN": 1871,
    "JOKER:PERSIST_WHILE": 1264,
    "JOKER:DOUBLE": 2371,
    "JOKER:ECHO": 1909
  },
  "vp_attribution": {
    "all_games":    {"rule_vp": 421, "goal_vp": 5012},
    "winning_games": {"rule_vp": 308, "goal_vp": 4623}
  },
  "status_tokens": {            // apply / clear / decay
    "BURN":    {"apply": 1256, "clear": 120, "decay": 106712},
    "MUTE":    {"apply": 1112, "clear": 0,   "decay": 1012},
    "BLESSED": {"apply": 1403, "clear": 525, "decay": 0},
    "MARKED":  {"apply": 798,  "clear": 0,   "decay": 752},
    "CHAINED": {"apply": 1105, "clear": 247, "decay": 0}
  },
  "chip_economy": {            // final-state per-player chip distribution
    "min": 0, "max": 124,
    "mean": 23.4, "median": 18, "std": 19.7
  },
  "anomalies": [
    "WARN: card 'subj.anyone' never played",
    "WARN: effect 'eff.noop' drawn 926x but never fired",
    "WARN: goal 'goal.builder' never claimed"
  ]
}
```

### Field semantics

* **`drawn` vs `fired`** — `drawn` counts effect-card reveals (1 per round
  that reached BUILD with an effect on the table). `fired` counts
  `dispatch_effect` calls that produced a state change. Under iterative
  SUBJECT scope (`EACH_PLAYER`, ADR-0003) the dispatcher fires once per
  matching player, so `fire_rate` can exceed 1.0 — that is signal, not a
  bug. Zero `fired` with non-zero `drawn` means the effect's predicate
  never matched OR the effect itself is a no-op (`eff.noop`).
* **`rule_vp` vs `goal_vp`** — `rule_vp` is the Σ-VP delta around every
  `effects.resolve_if_rule` call (covers IF rules AND WHEN/WHILE
  persistence — both route through the resolver per `persistence.py`).
  `goal_vp` is the Σ-VP delta around every successful goal claim.
  Discrepancy with total VP awarded would indicate a third VP source —
  none exists in M2, so the two sum to the total.
* **`status_tokens.*.decay`** — BURN decay tracks chip-drain magnitude
  (`burn × BURN_TICK`); MUTE/MARKED decay is a clear count.
* **`chip_economy`** — taken from final-state `Player.chips` across every
  player in every game (4 × `games` data points).

## Anomaly flags

Auto-emitted during `to_json_dict` based on the rendered payload (so the
flags exactly track the published numbers):

| Flag | Trigger |
|---|---|
| `WARN: card '<id>' never played` | `card_usage[id] == 0` |
| `WARN: effect '<id>' never drawn` | `effect_cards[id].drawn == 0` |
| `WARN: effect '<id>' drawn Nx but never fired` | `drawn > 0 AND fired == 0` |
| `WARN: goal '<id>' never claimed` | `goal_claims[id] == 0` |
| `WARN: winner distribution skewed — seat S won Nx` | `max(by_seat) > 2 × (winners / PLAYER_COUNT)` |
| `WARN: cap-hit rate X% exceeds 50%` | `cap_hit_rate > 0.5` |

Thresholds are module-level constants (`_WINNER_SKEW_FACTOR`,
`_CAP_HIT_WARN_FRACTION`); adjust as design matures. The cap-hit threshold
deliberately sits above the M2 random-bot baseline (~36% in 1000-game runs;
40% at the M2 smoke's N=10) so healthy runs don't flag — see the
constant's comment block.

## Test surface

`engine/tests/test_simulate.py` — 17 tests, runs in ~2 seconds.

| Concern | Test |
|---|---|
| Same args ⇒ byte-identical JSON | `test_simulate_is_deterministic` |
| Each metric category has positive counts over 100-game sweep | `test_*_populated` (7 tests) |
| Anomaly flags fire on synthetic payloads | `test_anomaly_flags_*` (5 tests) |
| Patched engine restored after `simulate()` returns | `test_simulate_restores_engine_after_run` |
| Terminal summary stays ≤50 lines | `test_format_summary_is_compact` |
| Coverage floors hold (winners > 0, status apply > 0, status decay > 0, …) | covered by `test_*_populated` |

## Out of scope (RUL-74)

The hand-over scoped out:

* ISMCTS bot integration (next M4 sub-issue)
* Bot-vs-bot strategy comparison (`--bot-a random --bot-b ismcts`)
* Plotting / web dashboard
* Real-time streaming output (single-shot batch run)
* Engine-state changes (observation-only)
* `bots.random` heuristic tuning

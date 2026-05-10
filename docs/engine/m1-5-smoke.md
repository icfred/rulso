_Last edited: 2026-05-10 by RUL-21_

# M1.5 watchable smoke

Closes the M1.5 watchable bar promised by `m1-smoke.md`: with hands dealt,
rules resolving, and `+1 VP` firing, a real game must produce a winner in a
non-trivial fraction of seeds — not every seed, but enough that the
substrate is observably healthy.

## Files

| Test | Surface | Asserts |
|---|---|---|
| `engine/tests/test_m1_5_watchable.py` | `rulso.cli.main` over seeds 0..9 at `rounds=100` | every seed terminates without exception (rc ∈ {0, 1}, `game_start` + `round_start` + (`game_end` ‖ `cap_hit`) emitted); ≥ 1 seed wins; ≥ 30 rules resolve in total; ≥ 5/10 seeds see at least one resolve |

The sweep runs once per session via a module-scoped fixture; per-seed
crash detection is parametrised, aggregate floors are single tests.

## Empirical baseline (post-RUL-27)

Probed against the play-biased random bot (`bots.random.PLAY_BIAS = 0.85`)
at seeds 0..9, `rounds=100`:

| Metric | Observed | Floor in test |
|---|---|---|
| seeds with a winner | 6/10 | ≥ 1 |
| seeds with ≥ 1 resolve | 10/10 | ≥ 5 |
| total resolves across sweep | 63 | ≥ 30 |
| sweep wall-time | ~2.1 s | (no assertion) |

Floors sit roughly at half the observed values — tight enough to fail
loudly on a bot or rules regression, loose enough to absorb noise.
Tightening is fine; loosening needs an explanatory note here.

`rounds=100` is sufficient: winning seeds finish well before the cap, and
lifting the budget to 200/300/500 produces identical results (probed).

## Why some seeds cap-hit

Seeds 0, 1, 8, 9 hit the round cap rather than producing a winner. The
common stall is `event=rule_failed reason=dealer_no_seed_card`: per
RUL-18, the dealer must seed slot 0 from hand, and if no `SUBJECT` card is
in hand the rule fails immediately and the dealer rotates. With four
players and finite hands this is not rare. **This is correct behaviour,
not a bug.**

A future "dealer discards then retries before failing" optimisation would
shrink the cap-hit fraction, but is out of scope for M1.5 — file a
follow-up rather than touching `rules.py` here.

## How this differs from `test_cli_multiseed`

`test_cli_multiseed` asserts the substrate is crash-free across 20 seeds
at `rounds=20` — winners are not required there. This file lifts the bar:
**someone wins**, and rules resolve in volume. When this file goes red,
look at the bot heuristic and the resolver path before the round-flow.

## Stop conditions for future regressions

- `test_at_least_one_seed_produces_a_winner` red → check `effects.resolve_if_rule`
  is still wired into `rules.enter_resolve`, and that the `+1 VP` path
  on a successful goal claim still fires.
- `test_rules_resolve_across_the_sweep` red but winner test green → look at
  whether the bot is filling slots (`bots.random.PLAY_BIAS`,
  `_enumerate_plays` slot-type filter).
- All four parametrised crash tests red → the CLI itself is broken; bisect
  against `cli.run_game` and `rules.advance_phase`.

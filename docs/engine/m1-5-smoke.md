_Last edited: 2026-05-10 by RUL-34_

# M1.5 watchable smoke

End-to-end CLI sweep that asserts the engine still terminates and rules still
fire. **Re-contracted by RUL-34 for M2 Phase 3** — see "Contract change"
below. The "real watchable bar" (someone wins) lives in RUL-35's M2 watchable
smoke.

## Files

| Test | Surface | Asserts |
|---|---|---|
| `engine/tests/test_m1_5_watchable.py` | `rulso.cli.main` over seeds 0..9 at `rounds=100` | every seed terminates without exception (rc ∈ {0, 1}, `game_start` + `round_start` + (`game_end` ‖ `cap_hit`) emitted); ≥ 34 rules resolve in total; ≥ 7/10 seeds see at least one resolve |

The sweep runs once per session via a module-scoped fixture; per-seed
crash detection is parametrised, aggregate floors are single tests.

## Contract change (RUL-34)

Original RUL-21 contract asserted `≥ 1 winner` across the seed sweep. RUL-31
worker probe found that even silently-safe `cards.yaml deck:` extensions
(ANYONE/EACH no-op via empty scope; JOKERs sit in-hand) regress the winner
count from 6/10 to 0–2/10 by diluting the rule-fire pool. Each Phase 3 ticket
extends `deck:` for its consumer, so the smoke would go red on the first
correct Phase 3 PR.

RUL-34 demoted the smoke to a **regression backstop**:

- `_MIN_WINNERS = 0` — winner-emergence is no longer asserted here. RUL-35's
  M2 watchable smoke takes that bar after the Phase 3 fan lands.
- `_MIN_RUNS_WITH_RESOLVE` and `_MIN_TOTAL_RESOLVES` floors **stay**, widened
  to absorb dilution. They catch the genuine breakage we still want
  detected: rules never firing at all means the engine is broken, regardless
  of deck composition.
- `test_at_least_one_seed_produces_a_winner` was **deleted** rather than
  reshaped to a no-op. Termination is already asserted per-seed by
  `test_each_seed_terminates_without_exception`, so a winner test with
  `_MIN_WINNERS = 0` would be tautological.

## Empirical baselines

Seeds 0..9 at `rounds=100`:

| Probe | winners | runs_with_resolve | total_resolves |
|---|---|---|---|
| baseline (post-RUL-27, current `deck:`) | 6 | 10 | 63 |
| RUL-34 worst-case (silently-safe adds) | 1 | 10 | 49 |

Worst-case is the **min** across three 10-seed windows (0..9 / 10..19 /
20..29) with `subj.anyone`, `subj.each`, `jkr.persist_when`,
`jkr.persist_while`, `jkr.double`, `jkr.echo` each at +2 copies on top of
the M1.5 baseline `deck:`. Per-window:

| seeds | winners | runs_with_resolve | total_resolves |
|---|---|---|---|
| 0..9 | 2 | 10 | 62 |
| 10..19 | 2 | 10 | 49 |
| 20..29 | 1 | 10 | 59 |

Why this isolate? Most M2 cards crash the M1.5 engine when drawn (new NOUNs
raise in `_evaluate_has`; OP-only comparators raise in `_parse_quant`;
operator MODIFIERs land in QUANT and raise the same way). The probe must
isolate the **silently-safe** additions — those that statistically dilute
without crashing — to measure the dilution floor for the regression-backstop
contract. Phase 3 tickets that wire crashing variants must extend `deck:`
together with the consumer code, so they don't show up in this measurement.

Floors sit at worst-case × 0.7 (`runs_with_resolve = 7`,
`total_resolves = 34`) — tight enough to fail loudly on a real regression,
loose enough to absorb Phase 3 deck dilution as further variants land.
Tightening is fine; loosening needs an explanatory note here.

`rounds=100` is sufficient: rule-fire counts plateau before the cap, and
lifting the budget to 200/300/500 produces equivalent metrics (RUL-21 probe).

## Why some seeds cap-hit

Seeds that cap-hit rather than producing a winner most often stall on
`event=rule_failed reason=dealer_no_seed_card`: per RUL-18, the dealer must
seed slot 0 from hand, and if no `SUBJECT` card is in hand the rule fails
immediately and the dealer rotates. With four players and finite hands this
is not rare. **This is correct behaviour, not a bug.**

A future "dealer discards then retries before failing" optimisation would
shrink the cap-hit fraction, but is out of scope for M1.5 — file a
follow-up rather than touching `rules.py` here.

## How this differs from `test_cli_multiseed`

`test_cli_multiseed` asserts the substrate is crash-free across 20 seeds
at `rounds=20` — winners are not required there. Both files now share the
"engine terminates and rules fire" contract; `test_m1_5_watchable.py` runs
deeper (rounds=100) and asserts resolve volume, not just survival. When
either file goes red, look at the bot heuristic and the resolver path
before the round-flow.

## Stop conditions for future regressions

- `test_rules_resolve_across_the_sweep` red → look at whether the resolver
  is still wired (`effects.resolve_if_rule` from `rules.enter_resolve`),
  whether the bot is filling slots (`bots.random.PLAY_BIAS`,
  `_enumerate_plays` slot-type filter), or whether a slot-typing change
  stopped legal plays.
- `test_resolves_are_not_one_lucky_seed` red but `_rules_resolve_` green →
  rule fills are too sparse to spread across seeds — check deck composition
  and bot draw/discard balance.
- All ten parametrised crash tests red → the CLI itself is broken; bisect
  against `cli.run_game` and `rules.advance_phase`.
- After Phase 3 lands and the deck has expanded with the full M2
  vocabulary: re-probe and revisit floors. Don't preemptively loosen them.

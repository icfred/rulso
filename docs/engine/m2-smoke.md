_Last edited: 2026-05-10 by RUL-35_

# M2 watchable smoke

Wave 3 gate. Reclaims the "someone wins" bar that ``test_m1_5_watchable.py``
deferred for M2 Phase 3 (RUL-34 re-contracted it as a regression backstop
while ``cards.yaml deck:`` was being filled). With the full M2 vocabulary
wired and RUL-54's determinism substrate in place, this smoke asserts that
all three rule lifetimes (IF / WHEN / WHILE) plus the goal-claim and
chip-effect paths fire end-to-end across a seed sweep.

## Files

| Test | Surface | Asserts |
|---|---|---|
| `engine/tests/test_m2_watchable.py` | `rulso.cli.main` over seeds 0..9 at `rounds=200` | per-seed termination (rc ∈ {0, 1}, `game_start` + `round_start` + (`game_end` ‖ `cap_hit`)); per-seed resolve (`event=resolve` present); aggregate floors on winners, runs-with-resolve, WHEN/WHILE lifecycle, goal-VP, effect chip-delta |

The sweep runs once via a module-scoped fixture; per-seed assertions are
parametrised, aggregate floors are single tests.

## Why test-side instrumentation (not new CLI events)

The CLI narrates one `event=resolve` per `Phase.RESOLVE`. WHEN/WHILE
persistent rules fire silently inside `persistence.check_when_triggers` and
`persistence.tick_while_rules`; goal claims and chip effects happen inside
`goals.check_claims` and `effects.resolve_if_rule` without dedicated events.
RUL-35 is a verification ticket — no production-module edits — so the
sweep fixture wraps four engine entry points as pure observers and
restores the originals on teardown. Wrappers forward arguments unchanged
and return the original output; the only side effect is incrementing a
counter dict. Other test modules in the same pytest session are unaffected
because the wrappers are reverted in `try/finally`.

## Empirical baseline (deterministic main post-RUL-54)

Seeds 0..9 at `rounds=200`:

| Seed | rc | Winner | resolve_if calls | persistent_WHEN | persistent_WHILE | goal_VP | chip_delta |
|---|---|---|---|---|---|---|---|
| 0 | 1 | – | 427 | 384 | 365 | 1 | 15 |
| 1 | 0 | p* | 17 | 2 | 7 | 7 | 0 |
| 2 | 0 | p* | 106 | 34 | 56 | 1 | 80 |
| 3 | 0 | p* | 3 | 0 | 0 | 5 | 0 |
| 4 | 1 | – | 425 | 5 | 397 | 0 | 80 |
| 5 | 0 | p* | 34 | 20 | 5 | 5 | 5 |
| 6 | 1 | – | 411 | 2 | 397 | 0 | 5 |
| 7 | 0 | p* | 13 | 6 | 0 | 6 | 0 |
| 8 | 1 | – | 405 | 4 | 388 | 0 | 5 |
| 9 | 1 | – | 424 | 386 | 377 | 3 | 45 |
| **sum** | | **5/10** | **2265** | **843** | **1992** | **28** | **235** |

Bimodality: seeds 1/2/3/5/7 win regardless of round budget; seeds 0/4/6/8/9
cap-hit even at `rounds=300` (probed). This is a substrate property of the
current bot heuristic and `cards.yaml deck:` composition, not flake. The
RUL-35 hand-over allows the floor down to ≥ 5/10; below 5 fires the Phase
3.5 polish ticket.

`rounds=200` is the budget the hand-over suggests as a start. Lifting to 300
does not move the winner count. Below 200 the cap-hit seeds start emitting
fewer persistent-rule ticks, eroding the lifecycle margins.

## Pinned floors and rationale

| Floor | Value | Observed | Guards against |
|---|---|---|---|
| `_MIN_WINNERS` | 5 | 5 | M2 watchable bar regression — bot heuristic or deck composition pushed below the Wave 3 gate |
| `_MIN_RUNS_WITH_RESOLVE` | 8 | 10 | Resolve path silently stops firing on most seeds (bot regression or slot-typing change) |
| `_MIN_PERSISTENT_WHEN_TOTAL` | 1 | 843 | JOKER:PERSIST_WHEN / JOKER:ECHO promotion or `tick_while_rules` traversal of WHEN rules is broken |
| `_MIN_PERSISTENT_WHILE_TOTAL` | 1 | 1992 | JOKER:PERSIST_WHILE promotion or `tick_while_rules` traversal of WHILE rules is broken |
| `_MIN_GOAL_VP_AWARDED` | 1 | 28 | `goals.check_claims` predicate evaluation or VP award path is broken |
| `_MIN_EFFECT_CHIP_DELTA` | 1 | 235 | `effects.resolve_if_rule` no longer mutates `Player.chips` — dispatcher dropped registration, scope path always empty, or effect handlers got short-circuited |

Lifecycle and goal/effect floors sit at the DoD-mandated minimum (1
sweep-aggregate occurrence). Observed counts are 25×–1000× the floor; the
floors are deliberately trivial — they catch the regression we care about
(path stops firing entirely) without becoming brittle as the bot heuristic
or deck composition evolves.

Winner floor sits at the observed count (5/10). Tightening above 5
requires either bot improvements (M3 ISMCTS) or deck rebalancing; loosening
below 5 needs the Phase 3.5 polish ticket per the RUL-35 Stop condition.

## Why some seeds cap-hit

Same root cause as M1.5 (`rule_failed reason=dealer_no_seed_card`): with
four players and finite hands, the dealer occasionally has no SUBJECT card
to seed slot 0. The rule fails immediately and the dealer rotates. With
the wider M2 deck the dilution is sharper — seeds 0/4/6/8/9 hit
`rule_failed` 175–188× across 200 rounds while still producing 12–25
non-trivial resolves. The persistent_WHILE counts on those seeds (365–397)
show the WHILE rules accumulate and tick every round without firing
chip-affecting effects on the four players (empty SUBJECT scope on most
ticks).

A future "dealer discards then retries before failing" optimisation would
shrink the cap-hit fraction; out of scope for RUL-35.

## How this differs from `test_m1_5_watchable.py`

| Aspect | M1.5 smoke | M2 smoke |
|---|---|---|
| Asserts winner emergence | No (`_MIN_WINNERS = 0`) | Yes (`_MIN_WINNERS = 5`) |
| Lifecycle coverage (WHEN/WHILE/goal/effect) | No | Yes — via wrapper instrumentation |
| Production-edit scope | None | None (testing-only wrappers) |
| Rounds budget | 100 | 200 |

The M1.5 smoke stays untouched and continues to act as a fast (~100-round)
regression detector. The M2 smoke is the slower (~200-round) gate that
asserts the engine is *watchable* — winners emerge, all three rule
lifetimes fire, goals get claimed, chips actually move.

## Stop conditions for future regressions

- `test_winners_emerge_across_the_sweep` red below 5/10 → file the Phase 3.5
  polish ticket; do not lower the floor.
- `test_persistent_when_lifecycle_exercised` or
  `test_persistent_while_lifecycle_exercised` red → JOKER attachment path
  (`rules.enter_resolve` step 5) or `persistence.add_persistent_rule` is
  broken; bisect against `bots.random.choose_action` (JOKER play
  enumeration) and `_JOKER_PERSISTENT_VARIANTS`.
- `test_goal_claims_award_vp` red → `goals.check_claims`, goal predicates
  in `goal_predicates.py`, or the `claim_kind` (single vs renewable)
  bookkeeping in `GameState.active_goals` regressed.
- `test_effect_application_moves_chips` red → `effects.resolve_if_rule`
  dispatcher, `register_effect_kind` registry, or scope evaluation
  regressed; the `_LOSE_CHIPS` / `_GAIN_CHIPS` handlers in particular.
- After bot improvements or deck rebalancing — re-probe and revisit
  floors. Tightening is fine; loosening past the table above needs an
  explanatory note here.

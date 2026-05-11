_Last edited: 2026-05-11 by RUL-56_

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

## Empirical baseline (deterministic main post-RUL-56)

Seeds 0..9 at `rounds=200`:

| Seed | rc | Winner | resolve_if calls | persistent_WHEN | persistent_WHILE | goal_VP | chip_delta |
|---|---|---|---|---|---|---|---|
| 0 | 0 | p* | 16 | 14 | 3 | 6 | 0 |
| 1 | 0 | p* | 4 | 1 | 0 | 5 | 0 |
| 2 | 1 | – | 6 | 195 | 0 | 1 | 0 |
| 3 | 0 | p* | 3 | 0 | 0 | 7 | 0 |
| 4 | 1 | – | 271 | 747 | 216 | 0 | 15 |
| 5 | 0 | p* | 22 | 18 | 3 | 4 | 10 |
| 6 | 1 | – | 412 | 194 | 392 | 0 | 10 |
| 7 | 0 | p* | 14 | 8 | 0 | 7 | 0 |
| 8 | 1 | – | 220 | 379 | 197 | 0 | 0 |
| 9 | 0 | p* | 23 | 20 | 0 | 6 | 10 |
| **sum** | | **6/10** | **991** | **1576** | **811** | **36** | **45** |

Winners: seeds 0/1/3/5/7/9. Cap-hit: seeds 2/4/6/8. Identical winner set to
the pre-SHOP post-RUL-61 baseline — RUL-56's price tuning
(10/12/11/11/11/11/12) keeps the SHOP transparent to winner emergence at
the random-bot tier. With every offer priced 10-12 and BURN/discard drain
running, bots rarely afford the cheapest offer in rounds 3 or 6, so the
SHOP fires and is observed (events emit, the `_drive_shop` path exercises
buyers in ascending-VP order) without diverting enough chips to flip
seeds. Per-seed `resolve_if` and `chip_delta` counts shifted vs the
pre-SHOP baseline because the seeded shop-pool shuffle perturbs the
seed-0 dealing slightly, but aggregate floors hold by orders of magnitude.

The earlier RUL-55 baseline of 7/10 (winners 0/1/3/4/5/7/9) was achieved
with the M2 status vocabulary half-wired — MARKED + CHAINED-clear absent
from production. Once RUL-61 appended `eff.marked.apply` +
`eff.chained.clear` at the head of `cards.yaml effect_cards:`, deck depth
shifted 12 → 14 and seed 4 flipped from winner (~40 rounds) to cap-hit.
Below 6/10 fires the next polish ticket; the gap between random bots and
the full status vocabulary is exactly what M4 ISMCTS (ADR-0006) will
address.

## RUL-56 SHOP content — price-tuning empirical record

Un-tuned ADR-0007 starter prices (5/7/6/6/10/9/12) yielded 5/10 winners
(seeds 1/3/5/7/9, seed 0 flipped to cap-hit vs the pre-SHOP baseline).
Mechanism: `bots.random.select_purchase` is "cheapest affordable, ties by
lowest index". At 5-7 chip offers and 4 buyers per SHOP round, ~12-15
chips per buyer drained across rounds 3 + 6 on top of BURN tick + 5-chip
discards, leaving less runway for discard-redraw, suppressing rule-fire
rate and flipping seed 0.

RUL-56 probed eight configurations within the ADR-0007 5-12 band:

| Config (wounded/leader/gt/eq/double/echo/persist_when) | Winners | Seeds |
|---|---|---|
| 5/7/6/6/10/9/12 (un-tuned ADR-0007) | 5/10 | 1/3/5/7/9 |
| 8/9/8/8/10/11/12 (orchestrator probe-1) | 5/10 | 0/1/3/4/7 |
| 9/10/9/9/11/10/12 | 5/10 | 1/3/4/7/9 |
| 10/11/10/10/12/11/12 | 5/10 | 0/1/3/4/7 |
| 12/12/12/12/12/12/12 (uniform max) | 5/10 | 0/1/3/5/9 |
| 11/12/11/11/12/12/12 (high band) | 4/10 | 1/3/4/7 |
| 11/11/11/11/11/11/12 (uniform 11) | 3/10 | 1/3/9 |
| **10/12/11/11/11/11/12 (locked)** | **6/10** | **0/1/3/5/7/9** |

The locked config preserves ADR-0007's shape (cheap SUBJECT < MODIFIER ≤
JOKER < premium), keeps the 5-12 band (tightened to 10-12), and yields
the only 6/10 config tested. Uniform-low and uniform-high configs both
land at 5/10 with different seed-flip patterns. The locked config's
ascending-VP buy order interacts with the seeded shop-pool shuffle to
leave the seed-0 cap-hit/winner boundary on the winner side.

Per ADR-0007 §"Pricing rationale": "RUL-56 may tune individual prices
against M2 watchable-smoke winner-emergence data; the ADR fixes the
*shape* and the *range*, not per-card specifics." The locked prices
satisfy both constraints — shape and range — while matching the
pre-SHOP baseline.

## RUL-55 polish — Lever A (bot heuristic)

Phase 3.5 push 5/10 → 7/10 via a single-line `bots.random` tweak:
`PLAY_BIAS = 0.85 → 0.75`. Slightly more discards keep SUBJECT cards
cycling through stalled hands, shrinking the cap-hit fraction without
diluting the deck or reshuffling seed-0 deals. No edit to `cards.yaml`,
no test fixture cascade. Probed monotonically (rounds=200, seeds 0..9):
0.70 → 5, 0.72 → 5, **0.75 → 7**, 0.78 → 7, 0.80 → 6, 0.85 → 5 (pre-RUL-55
baseline), 0.95 → 5. Stable across rounds=300 (same 7/10, same seed split).

Why Lever A and not B (deck rebalance): every probed deck rebalance that
hit ≥7/10 (e.g. +1 SUBJECT/+1 NOUN/+1 JOKER per kind → 8/10) reshuffles
seed-0 deals and breaks at least three existing tests
(`test_cards_loader.py` deck-composition mirror; `test_determinism.py`
recycle-path guard relying on seed 0 playing ≥12 rounds;
`test_jokers.py::test_full_game_round_trip_with_persistent_when_joker`
where the goal-pool shuffle shifts THE_HOARDER's claim under
`start_game(seed=0)`). Lever A leaves all those fixtures intact.

## Pinned floors and rationale

| Floor | Value | Observed | Guards against |
|---|---|---|---|
| `_MIN_WINNERS` | 6 | 6 | M2 watchable bar regression — bot heuristic, deck composition, or SHOP price band pushed below the post-RUL-56 gate |
| `_MIN_RUNS_WITH_RESOLVE` | 8 | 10 | Resolve path silently stops firing on most seeds (bot regression or slot-typing change) |
| `_MIN_PERSISTENT_WHEN_TOTAL` | 1 | 1576 | JOKER:PERSIST_WHEN / JOKER:ECHO promotion or `tick_while_rules` traversal of WHEN rules is broken |
| `_MIN_PERSISTENT_WHILE_TOTAL` | 1 | 811 | JOKER:PERSIST_WHILE promotion or `tick_while_rules` traversal of WHILE rules is broken |
| `_MIN_GOAL_VP_AWARDED` | 1 | 36 | `goals.check_claims` predicate evaluation or VP award path is broken |
| `_MIN_EFFECT_CHIP_DELTA` | 1 | 45 | `effects.resolve_if_rule` no longer mutates `Player.chips` — dispatcher dropped registration, scope path always empty, or effect handlers got short-circuited |

Lifecycle and goal/effect floors sit at the DoD-mandated minimum (1
sweep-aggregate occurrence). Observed counts are 25×–800× the floor; the
floors are deliberately trivial — they catch the regression we care about
(path stops firing entirely) without becoming brittle as the bot heuristic
or deck composition evolves.

Winner floor sits at the observed count (6/10) with no slack post-RUL-56.
Tightening above 6 needs another polish lever or M4 ISMCTS (ADR-0006);
loosening below 6 needs a follow-up polish ticket and an explanatory note
here.

## Why some seeds cap-hit

Same root cause as M1.5 (`rule_failed reason=dealer_no_seed_card`): with
four players and finite hands, the dealer occasionally has no SUBJECT card
to seed slot 0. The rule fails immediately and the dealer rotates without
a hand refill, so a 4-dealer streak of zero-SUBJECT hands can loop until
the round cap. With PLAY_BIAS=0.75 (RUL-55) and the post-RUL-61 effect
deck (14 cards), seeds 2/4/6/8 cap-hit. Seed 4 in particular flipped from
winner to cap-hit when the deeper effect deck shifted the recycle
threshold past the round where its prior fast-win path used to land.

A future "dealer discards then retries before failing" optimisation, or
ISMCTS-led smarter discard targeting, would shrink the cap-hit fraction
further. Out of scope for RUL-55.

## How this differs from `test_m1_5_watchable.py`

| Aspect | M1.5 smoke | M2 smoke |
|---|---|---|
| Asserts winner emergence | No (`_MIN_WINNERS = 0`) | Yes (`_MIN_WINNERS = 6`) |
| Lifecycle coverage (WHEN/WHILE/goal/effect) | No | Yes — via wrapper instrumentation |
| Production-edit scope | None | None (testing-only wrappers) |
| Rounds budget | 100 | 200 |

The M1.5 smoke stays untouched and continues to act as a fast (~100-round)
regression detector. The M2 smoke is the slower (~200-round) gate that
asserts the engine is *watchable* — winners emerge, all three rule
lifetimes fire, goals get claimed, chips actually move.

## Stop conditions for future regressions

- `test_winners_emerge_across_the_sweep` red below 6/10 → bisect against
  `bots.random.PLAY_BIAS`, `cards.yaml deck:`/`effect_cards:` composition,
  and any pre-resolve consumer of status tokens (RUL-60 narrowed MARKED's
  EACH_PLAYER consumer; further token consumers shift winner counts);
  do not lower the floor without a follow-up polish ticket and an
  explanatory note here.
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

_Last updated: 2026-05-11 by orchestrator session — **M2.5 CLOSED**: RUL-57 (PR #59), RUL-60 (PR #60), RUL-62 (PR #61), RUL-61 (PR #63), RUL-56 (PR #64) — all 5 shipped. Main at **479 tests passing**, ruff clean, deterministic M2 watchable smoke at **6/10 winners** (seeds 0/1/3/5/7/9) with full M2 status vocabulary + active SHOP content. MARKED applies + narrows EACH_PLAYER scope; CHAINED can be cleared; SHOP fires at 10/12/11/11/11/11/12 price gradient. Next gate: **M3 Foundation/Minimal Client** (RUL-58) — substrate-spike-first per ADR-0006._

# Rulso — orchestrator bootstrap

This is the cold-start payload for a fresh orchestrator chat. Read after `CLAUDE.md` (auto-loaded), then dispatch.

Linear board: https://linear.app/rulso (team `RUL`, projects: Engine / Infra / Bots / Client / Design).

## Active milestones

| ID | Milestone | Goal | State |
|---|---|---|---|
| RUL-5 | M1: Engine core | 4-bot CLI game runs end-to-end, IF rules resolve, state machine sound | **Done** |
| RUL-15 | M1.5: Watchable engine | First moment the game is *real* | **Done** (closed 2026-05-10) |
| RUL-24 | M2: Full card set | Every card type and mechanic from cards.yaml works | **Done** (closed 2026-05-10) — gap-close set tracked as M2.5 below. |
| _(no parent)_ | **M2.5: Mechanic gaps** (pre-M3 sweep) | Close M2 mechanics that ship in code but not in play | **Done** (closed 2026-05-11) — RUL-57/60/62 in batch 1 + RUL-61/56 in batch 2. All 5 shipped; M2.5 follow-ups under RUL-24 cleared. |
| RUL-58 | **M3: Foundation/Minimal Client** | Human can read the board, make a meaningful decision, reach a winner | **Backlog (next gate)** — Substrate-spike-first per ADR-0006. WS protocol shape spike opens M3. |
| RUL-59 | **M4: Smart bot (ISMCTS)** | ISMCTS surfaces real design feedback in solo play | **Backlog** — blocked-by RUL-58; payoff design draws on M3 playtest signal. |
| RUL-23 | Meta — orchestrator-authored cross-cutting commits | Permanent home for orchestrator commits | Permanent In Progress |

## Milestone reorder — ADR-0006 (2026-05-10)

The original `roadmap.md` ordering was M3 ISMCTS → M4 Pixi client → M5 polish. After M2 closed, the user attempted CLI playtesting via `rulso --human-seat 0` (RUL-52) and the prompt was unplayable — card IDs without text, no goal cards visible, no opponent state, 63 discard combos enumerated, no semantic preview of what completing the active rule would do. Bot strength is not the bottleneck; even with perfect ISMCTS opponents the human cannot make a meaningful decision against the current rendering. ADR-0006 reorders the post-M2 milestones:

| Milestone | Old | New |
|---|---|---|
| M3 | ISMCTS bot | **Foundation/Minimal Client** |
| M4 | Pixi client | **Smart bot (ISMCTS)** |
| M5 | Polish | Polish (unchanged) |

Foundation Client DoD bar is "ugly but playable": engine WS protocol + server, client bootstrap (Vite/Pixi/TS), type generation, decision-support rendering (full card text, semantic rule preview, goals visible, opponents' public state), click-to-play input, dice text. Polish (Aegean palette, animations, sound, drag-drop, iconography) all defers to M5.

## In flight

**Nothing in flight. M2.5 is closed.**

### M2.5 ship summary (2026-05-11, PRs #59/#60/#61/#63/#64)

Batch 1 (parallel fan, dispatched and merged in same session):

| Ticket | PR | Notes |
|---|---|---|
| RUL-57 | #59 | `docs/engine/bots.md` PlayCard rules: replaced stale "two entries: dice=1 and dice=2" line with the ADR-0002 split (OP-only → single `dice=2` entry; M1.5 baked-N legacy → dual entries). Doc-only. |
| RUL-60 | #60 | `effects.resolve_if_rule` iterative branch intersects `scoped` with MARKED holders when ≥1 hold MARKED; falls back to unchanged scope at 0. ANYONE / singular SUBJECTs unaffected. 7 new tests in `test_effects_marked_scope.py`. |
| RUL-62 | #61 | ADR-0007 locks **shape 2** (card-buy via existing `_ShopEntry.payload_type` route). 7-offer M2.5 starter table proposed. Every identifier cross-referenced against engine. |

Batch 2 (sequential, ordered to avoid baseline-rebase thrash):

| Ticket | PR | Notes |
|---|---|---|
| RUL-61 | #63 | Status-data completeness: `eff.marked.apply` + `eff.chained.clear` appended at head of `cards.yaml effect_cards:` (preserves seed-0 first-12-pops byte-equality). Floor 7 → 6 ratified — full M2 status vocabulary live; seed 4 flipped to cap-hit (deck depth 12 → 14 shifts recycle timing). `docs/engine/m2-smoke.md` re-baselined to winners 0/1/3/5/7/9. First worker stop-conditioned correctly (workers don't bump smoke floors unilaterally); orchestrator authorised option (a) on re-dispatch. |
| RUL-56 | #64 | SHOP content: 7-offer pool per ADR-0007 with **price-tuned** gradient `10/12/11/11/11/11/12` (within ADR-0007's 5-12 range; tuning explicitly authorised by ADR-0007 §"Pricing rationale"). Un-tuned ADR-0007 prices yielded 4/10 winners; tuning held the 6/10 post-RUL-61 floor with the identical winner set (0/1/3/5/7/9). First worker stop-conditioned correctly when un-tuned prices dropped the floor; orchestrator authorised option (b) — price tune within band, not floor bump. Mechanism: `bots.random.select_purchase` is "cheapest-affordable, ties by lowest index"; tight 10-12 band keeps every offer rarely affordable in rounds 3/6 after BURN + 5-chip discards. |

**Cross-cutting fixes landed via this RUL-23 sweep**:

- `docs/engine/readme.md`: test_shop.py + test_m2_watchable.py rows extended to cite RUL-56/RUL-61 wiring; `_Last edited:` bumped.
- `STATUS.md`: M2.5 marked Done; re-anchored to post-M2.5 state.
- `docs/workflow_lessons.md`: new entry — "ADR's own tuning clause: worker missed the authorisation, orchestrator caught it on the merge sweep" (RUL-56 specifically; template-worthy maybe).

Main: **479 tests passing**, ruff clean. Deterministic M2 watchable smoke at **6/10 winners** (seeds 0/1/3/5/7/9 win; 2/4/6/8 cap-hit) on PLAY_BIAS=0.75 with full M2 status vocabulary + active SHOP content.

## Audit findings — closed by M2.5 (2026-05-10 audit; closed 2026-05-11)

Cross-referenced `engine/src/rulso/{status,effects,goals}.py` against `design/status-tokens.md` and `cards.yaml`. All gaps closed by M2.5:

- **BURN** — apply (`APPLY_BURN`) ✓, clear (`CLEAR_BURN`) ✓, tick (`status.tick_round_start`) ✓, BLESSED interaction ✓, NOUN read (`BURN_TOKENS`) ✓. _Unchanged._
- **MUTE** — apply (`APPLY_MUTE`) ✓, natural decay at `round_start` step 2 ✓, blocks MODIFIER plays in `bots.random._enumerate_plays` ✓. _Unchanged._
- **BLESSED** — apply (`APPLY_BLESSED`) ✓, on-use clear via `consume_blessed_or_else` ✓, integrated at `LOSE_CHIPS` and BURN tick ✓. _Unchanged._
- **MARKED** — apply (`APPLY_MARKED` handler) ✓, natural decay at `resolve` step 10 ✓, **`eff.marked.apply` in `cards.yaml effect_cards:`** ✓ (RUL-61, PR #63), **EACH_PLAYER scope narrowing** ✓ (RUL-60, PR #60). Decorative-only state closed.
- **CHAINED** — apply (`APPLY_CHAINED`) ✓, clear handler (`CLEAR_CHAINED`) ✓, **`eff.chained.clear` in `cards.yaml effect_cards:`** ✓ (RUL-61, PR #63), goal-claim eligibility filter at `goals.py:123` ✓, `THE_FREE_AGENT` predicate read ✓. Permanent-state-once-chained closed.
- **SHOP** substrate ✓ (RUL-51), **content** ✓ (RUL-56, PR #64; 7-offer pool at tuned 10/12/11/11/11/11/12 gradient per ADR-0007). Empty-pool short-circuit closed.
- **All other M2 mechanics** (WHEN/WHILE lifecycle, JOKER variants, polymorphic NOUN reads, comparator dice, operator MODIFIER fold, all 4 floating labels, goal claims) — wired and consumed.

## Wave 4 ship summary (2026-05-10, PRs #54/#55/#56)

### Wave 4 ship summary (2026-05-10, PRs #54/#55/#56)

| ID | PR | Notes |
|---|---|---|
| RUL-53 | #54 | `docs/engine/bots.md` refresh: PlayJoker section + JOKER variant table (PERSIST_WHEN/WHILE/DOUBLE/ECHO), operator-MODIFIER skip rules inline, `enumerate_legal_actions` public-helper section, `bots.human.select_action` section. Doc-only. Out-of-scope drift flagged → RUL-57. |
| RUL-51 | #55 | Real `Phase.SHOP` handler replacing `NotImplementedError`. Additive `ShopOffer` model + `shop_pool` / `shop_offer` / `shop_discard` fields on `GameState`; cadence `round_number % SHOP_INTERVAL == 0`; buy order `(vp asc, chips asc, seat asc)` per `design/state.md` (overrode hand-over's stale "Player.id" tie-break — canonical source wins); recycle-on-empty pool follows the RUL-54 disjoint-rng pattern (`ValueError` if `rng=None` on the recycle path). 13 new tests in `test_shop.py`; one existing test edited (`test_advance_from_shop_raises_not_implemented` → `…with_empty_offer_resumes_round_start`). `cards.yaml shop_cards:` ships empty — SHOP short-circuits in CLI; smoke output byte-for-byte unchanged. Content TBD in RUL-56. |
| RUL-55 | #56 | Lever A only: `PLAY_BIAS = 0.85 → 0.75` in `bots/random.py`. Deterministic baseline lifts 5/10 → 7/10 (seeds 0/1/3/4/5/7/9 win; 2/6/8 cap-hit); stable at rounds=300. `_MIN_WINNERS` raised 5 → 7 (no slack); `docs/engine/m2-smoke.md` baseline + rationale + stop-conditions all re-anchored to 7/10. Lever B (deck rebalance) probed and rejected — every config hitting ≥7/10 reshuffles seed-0 deals and breaks `test_cards_loader`, `test_determinism.test_recycle_path`, `test_jokers.test_full_game_round_trip_with_persistent_when_joker` via the goal-pool shuffle cascade. Rebased onto post-RUL-51 main; full suite (468 tests) re-verified before merge. |

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md`: row added for `test_shop.py`; `cards.py`, `rules.py`, `bots/random.py`, `test_m2_watchable.py` description rows refreshed for Wave 4 wiring (SHOP loader, SHOP phase handler, `select_purchase`, `PLAY_BIAS = 0.75`, 7/10 winner floor). `_Last edited:` bumped to Wave 4.
- `STATUS.md`: re-anchored to post-M2-close state; M2 milestone marked Done; RUL-56/RUL-57 follow-ups registered.
- `docs/workflow_lessons.md`: new entry 2026-05-10 — deck-composition fragility beyond `_drive_to_first_build` (goal-pool shuffle cascade breaks `test_cards_loader` + `test_jokers.test_full_game_round_trip_with_persistent_when_joker` + `test_determinism.test_recycle_path` when the deck reshuffles). Companion to the existing "deck-size fragility in test helpers" lesson from RUL-31 — the fragility is wider than tests-that-use-`_drive_to_first_build`.

**Worker hand-back flags addressed**:
- RUL-51: hand-over said tie-break by `Player.id`; canonical `design/state.md` says VP → chips → seat. Worker correctly followed state.md. **Decision**: keep state.md as the source of truth; the hand-over template was wrong. No ADR needed.
- RUL-51: `shop_cards:` empty in `cards.yaml` — followed the minimal-stub path. Content + payload-type ADR deferred to RUL-56.
- RUL-53: `bots.md` PlayCard rules still claim all comparator MODIFIERs enumerate both dice modes; RUL-42 changed LT/LE/GT/GE/EQ to default 2d6 only. **Filed RUL-57** as a sibling docs follow-up.
- RUL-55: hand-over referenced `engine/data/cards.yaml`; actual path is `design/cards.yaml`. **Memory rule saved** (`feedback_cards_yaml_path.md`) so future hand-overs cite the correct path.

**Outstanding follow-ups**:
- RUL-56: SHOP content (populate `shop_cards:` + payload-type ADR) — **Backlog**, depends on a payload-semantics decision; not blocked but probably waits for M3 playtest signal.
- RUL-57: `bots.md` dice-mode drift — **Backlog**, parallel-safe docs chore.
- RUL-35: M2 watchable smoke — **DONE 2026-05-10 (PR #52)**.
- RUL-51 / RUL-53 / RUL-55: Wave 4 — **DONE 2026-05-10**.

### RUL-35 ship summary (2026-05-10, PR #52, recap)

- **Test-side instrumentation** (no production-module edits): module-scoped fixture wraps `effects.resolve_if_rule`, `persistence.check_when_triggers`, `persistence.tick_while_rules`, `goals.check_claims` as pure observers; restored in `try/finally`. 42/42 green in same pytest session as M1.5 + determinism — no leakage.
- **Empirical baseline pinned**: 5/10 winners → **lifted to 7/10 by RUL-55** (PLAY_BIAS 0.85 → 0.75).
- **Lifecycle floors** at sweep-aggregate ≥1 (observed counts: 843 WHEN, 1992 WHILE, 28 goal-VP, 235 chip-delta).
- **README cwd form preserved**: `uv run --project engine rulso …`.

### RUL-54 substrate fix (2026-05-10, PR #50, recap)

RUL-35's first dispatch correctly stop-condition'd before any code change. Worker probed 5 × 10-seed sweeps and saw winner counts varying 4–6/10 across identical invocations. Root cause: `cli.py:85` called `advance_phase(state)` without rng for `ROUND_START`, and RUL-47's `enter_round_start` fell back to an unseeded `random.Random()` whenever the 12-card effect deck recycled (round ~13). Two latent twins at `enter_resolve` step 12 and `_refill_hands` used the same `rng or random.Random()` fallback shape.

RUL-54 fixed all three sites: shape (b) — `rng=None` tolerated when the reshuffle does not fire; `ValueError` at the reshuffle site otherwise. New disjoint stream `effect_rng = random.Random(seed ^ 0xEFFC)` slots into the CLI alongside `rng` / `refill_rng` (0x5EED) / `dice_rng` (0xD1CE). 4 new tests including `test_determinism.py` byte-identical-stdout invariant.

**Lesson captured** (`docs/workflow_lessons.md` 2026-05-10): a behavioural-substrate cascade at *depth* — RUL-47's fallback only bit at round 13, escaping a PR review that read the diff and confirmed all existing fixtures stayed green. Three substrate axes proposed for the global protocol: code-substrate (file shape), behavioural-substrate (function contract), conditional-substrate (runtime-conditional path). RUL-47 hit all three.

### Wave plan

- **Wave 1 (DONE 2026-05-10)**: RUL-47 (round-flow effect-deck draw — substrate wiring; PR #44) + RUL-48 (cards-inventory.md noun.hits text fix; PR #42) + RUL-50 (sync design/state.md JOKER step-reorder + ECHO conditional; PR #43). RUL-23 sweep: PR #45.
- **Wave 2 (DONE 2026-05-10)**: RUL-49 (BLESSED chip-loss + BURN tick; PR #46) + RUL-52 (CLI human-seat; PR #47). Behavioural-substrate cascade contained in PR #46 (single fixture amended in-PR with explanatory comment; 8 new tests cover the BLESSED+chip-loss matrix). UI/driver work in PR #47 was strictly additive (kw-only `human_seat=None` defaults; existing CLI smoke tests passed unchanged). RUL-23 sweep: this PR.
- **RUL-54 (substrate fix, DONE 2026-05-10)**: PR #50. Thread `effect_rng` through CLI → `enter_round_start`; eliminate `rng or random.Random()` fallbacks at three sites (now raise `ValueError` at the reshuffle path). Disjoint stream `seed ^ 0xEFFC`. New `test_determinism.py` exercises post-round-13 invariants. Unblocked RUL-35.
- **Wave 3 (gate, solo) — DONE 2026-05-10**: RUL-35 — M2 watchable smoke (PR #52). Landed at the hand-over's "acceptable down to" boundary (5/10 deterministic winners). Phase 3.5 polish ticket filed as RUL-55 to push the floor up via bot heuristic and/or deck rebalance.
- **Wave 4 (DONE 2026-05-10)**: parallel fan closes M2 + clears doc debt. PRs #54 (RUL-53), #55 (RUL-51), #56 (RUL-55). Per-ticket detail in the "Wave 4 ship summary" table above.
- **Open after Wave 4**: M3 ISMCTS scoping. Lean is to defer M3 until the user has playtested via RUL-52 (`uv run --project engine rulso --seed 5 --rounds 100 --human-seat 0`) — the playtest data shapes ISMCTS payoff. RUL-56 (SHOP content) is the only non-M3 substrate that can land first; whether it should is a design call.

### Wave 2 — final state (2026-05-10)

| ID | PR | Notes |
|---|---|---|
| RUL-49 | #46 | BLESSED wired into `effects._lose_chips` (LOSE_CHIPS handler) and `status.tick_round_start` (BURN tick). Per-target consumption; zero-magnitude losses do not consume BLESSED; BURN tokens persist when BLESSED cancels the drain. `design/state.md` BLESSED line amended to make the BURN-tick interaction explicit (resolves `design/status-tokens.md` flag 1). 8 new tests in `test_status.py`. Late-import alias renamed (`from rulso import status as _status` → `from rulso import status`) so `_lose_chips` can call into it; circular bootstrap unaffected. |
| RUL-52 | #47 | New `bots/human.py` (TTY action driver). New public helper `bots.random.enumerate_legal_actions(state, player)` — reuses random's predicate set without `PLAY_BIAS` weighting; available to any future driver (replay, ISMCTS rollouts). `cli.run_game` and `cli.main` gain kw-only `human_seat: int|None` and `human_stdin: TextIO|None` (default `None` — baseline preserved byte-for-byte). 7 new tests including parametrised seat-index coverage. `--human-seat 0..3` is the CLI flag. |

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md` index: rows added for `bots/human.py` and `test_cli_human_seat.py`; `bots/random.py` and `status.py` descriptions updated to reflect Wave 2 wiring (`enumerate_legal_actions` public helper + BLESSED chip-loss + zero-magnitude exclusion). `_Last edited:` bumped to Wave 2.

**Worker hand-back flags addressed**:
- RUL-52 worker: `legality.legal_actions(state, player_id)` was named in the hand-over but doesn't exist. Worker correctly used `bots.random.enumerate_legal_actions` instead. **Decision**: keep as-is; the new helper is now the canonical legal-action-enumeration surface. No follow-up filed.
- RUL-52 worker: `docs/engine/bots.md` is stale (predates RUL-43/45 — no `PlayJoker`, no operator-MODIFIER skip rules). Filed **RUL-53** as a Wave 4 docs chore.

**Outstanding follow-ups**:
- RUL-35: M2 watchable smoke — **DONE 2026-05-10 (PR #52)**.
- RUL-51: SHOP round — **Wave 4**, parallel-safe with RUL-53 + RUL-55.
- RUL-53: refresh `docs/engine/bots.md` for Phase 3 + Wave 2 — **Wave 4 docs chore**, parallel-safe.
- RUL-54: rng determinism substrate fix — **DONE 2026-05-10 (PR #50)**.
- RUL-55: Phase 3.5 polish (push winners above 5/10) — **Wave 4**, parallel-safe with RUL-51 + RUL-53.

### Phase 3 fan — final state (2026-05-10)

| ID | Letter | PR | Notes |
|---|---|---|---|
| RUL-39 | D | #37 | Effect dispatcher + `register_effect_kind` registry hook |
| RUL-40 | E | #40 | `status.py` + 7 effect-kind registrations (5 DoD + APPLY_MARKED + CLEAR_CHAINED); BLESSED chip-loss wiring shipped in Wave 2 (RUL-49) |
| RUL-41 | F | #35 | ANYONE / EACH_PLAYER scoping per ADR-0003 (existential = subset-fire-once, iterative = per-player loop) |
| RUL-42 | G | #38 | Comparator dice (ADR-0002) |
| RUL-43 | H | #36 | Operator MODIFIER fold (ADR-0004) |
| RUL-44 | I | #34 | Polymorphic NOUN reads |
| RUL-45 | J | #41 | JOKER attachment (PERSIST_WHEN/WHILE/DOUBLE/ECHO); state.md sync shipped in Wave 1 (RUL-50) |
| RUL-46 | K | #39 | Goal-claim engine; ADR-0005 ratifies retype |

### Wave 1 — final state (2026-05-10)

| ID | PR | Notes |
|---|---|---|
| RUL-47 | #44 | Round-flow effect-deck draw: `enter_round_start` step 6 pops from `effect_deck`; `enter_resolve` step 10 pushes to `effect_discard`; rule-failure paths discard rather than lose; recycle on empty deck via `rng`. `_M1_EFFECT_CARD` removed. 9 new tests in `test_round_flow.py`. |
| RUL-48 | #42 | Single-line `cards-inventory.md` fix: `noun.hits` row now cites `player.history.hits_taken_this_game`. |
| RUL-50 | #43 | `design/state.md` Phase: resolve steps 5/6 swapped (step 5 = WHEN trigger; step 6 = JOKER attachment). ECHO described as one-shot WHEN promotion with conditional re-fire. |

**Lessons captured** (`docs/workflow_lessons.md`):
- 2026-05-10: revealed_effect pin fan-out — every Phase 3 PR needed pin; CLEAN merge mechanics didn't catch
- 2026-05-10: deck-size fragility in test helpers — seed-0 lucky deals invisibly bake into 14+ tests
- 2026-05-10: behavioural-substrate cascade at depth (RUL-47/RUL-54) — `rng=None` fallback didn't bite until round 13, escaping diff-level PR review. Proposes a third "conditional-substrate" axis alongside code-substrate and behavioural-substrate.

M2 Phase 2 SHIPPED (RUL-31 cards/state.py substrate, RUL-32 WHEN+WHILE lifecycle, RUL-33 GENEROUS+CURSED labels). M1.5 smoke re-contract SHIPPED (RUL-34). M2 Phase 3 fan + Wave 1 + Wave 2 + RUL-54 substrate fix SHIPPED (14 PRs in this stretch, all green).

## Open judgment calls

- **Canonical legality module**: `bots.random.enumerate_legal_actions` is the de-facto canonical surface (RUL-52, exercised by `bots/human`). M4 ISMCTS rollouts will consume it; the M3 WS protocol's `action-submit` envelope will likely want a canonical action shape that lives outside `bots/random`. Promote to `legality.py` when M3 starts? Open.
- **Foundation Client substrate spike scope**: M3 substrate-first entry per ADR-0006 is "WebSocket protocol shape spike + ratification ADR". Does the spike output live as one ADR (protocol-envelope shape) or two (envelope shape + state-broadcast cadence)? Defer to the spike worker's hand-back.
- **M2 watchable smoke headroom**: 6/10 floor with one cap-hit of slack (5 winners would breach). Tight but defensible — RUL-55's earlier 7/10 floor was an artifact of half-wired vocabulary (MARKED + CHAINED-clear absent in production; SHOP empty). The post-M2.5 6/10 floor is the honest random-bot ceiling against the full M2 ruleset. Per ADR-0006 the next gate is M3 Foundation Client (human playtest signal) then M4 ISMCTS (smart bot retune). Smoke regression headroom won't grow until M4.
- **Deck-composition fragility extends beyond `_drive_to_first_build`** (RUL-55 Lever B finding, RUL-61 confirmed): the same fragility hit `effect_cards:` — adding 2 cards lifted deck depth 12 → 14, shifted recycle timing past round 13, dropped the watchable floor 7/10 → 6/10 (one seed flipped). Any future ticket that changes `cards.yaml deck:` OR `cards.yaml effect_cards:` composition must rebase + run `test_cards_loader.py`, `test_jokers.test_full_game_round_trip_with_persistent_when_joker`, `test_determinism.test_recycle_path` before merge — and expect a watchable-smoke re-baseline.

## Phase 3 prep — why RUL-34 landed first

RUL-31's worker probe found that even silently-safe deck additions (ANYONE/EACH no-op via empty scope; JOKERs sit in-hand) regress the M1.5 watchable smoke 6/10 → 1-2/10 winners by diluting the rule-fire pool. Each Phase 3 ticket extends `cards.yaml deck:` for its consumer, so the smoke would have gone red on the first Phase 3 PR even when the PR is correct.

**RUL-34** re-contracted the M1.5 smoke as a regression detector during Phase 3: dropped `_MIN_WINNERS` to 0; widened `_MIN_RUNS_WITH_RESOLVE` to 7 and `_MIN_TOTAL_RESOLVES` to 34 (worst-case × 0.7); deleted `test_at_least_one_seed_produces_a_winner`. The "real watchable bar" moves to **RUL-35** (M2 watchable smoke), which lands as the Wave 3 gate and reclaims winner emergence on the fully-wired M2 deck.

## M2 Phase 2 Done summary

3 sub-issues closed:
- **RUL-31** — state.py additive (`CardType.EFFECT`, `Card.scope_mode`, `GoalCard`); cards.yaml extended with full M2 vocabulary; cards.py loader covers new sections + `load_effect_cards` / `load_goal_cards` helpers.
- **RUL-32** — `persistence.tick_while_rules` and `persistence.check_when_triggers`. WHILE persists; WHEN FIFO + discard-on-fire; depth-3 recursion cap; dormant-label handling. Phase 3 effect dispatcher replaced the Phase 2 stub.
- **RUL-33** — GENEROUS = argmax(`history.cards_given_this_game`); CURSED = argmax(`status.burn`). ADR-0001 tie-break: ties → all; zero → empty. MARKED/CHAINED stay empty pending status-apply ticket.

## Done (chronological, this session)

M1 + M1.5 + M2 Phase 1 + M2 Phase 2 + M2 Phase 3 fan + Wave 1 + Wave 2 + Wave 3 (RUL-35) + Wave 4 (RUL-51 + RUL-53 + RUL-55) = ~37 tickets shipped. **M1, M1.5, and M2 all closed.** Next milestone: M3 ISMCTS (RUL-NN to be opened).

## Locked decisions / substrate watchpoints

- `engine/src/rulso/state.py` is the contract. **Additive-only edits.**
- Pydantic v2 + frozen by default; tuples for collections.
- M2 stubs are fully replaced — SHOP entry landed via RUL-51 (PR #55).
- Pre-commit hook resolves `ruff` via `uv run --project engine`.
- **Active ADRs**: ADR-0001 (floating-label definitions), ADR-0002 (comparator dice flow), ADR-0003 (SUBJECT.scope_mode enum), ADR-0004 (operator MODIFIER attachment), ADR-0005 (GoalCard typing).
- Workers do not edit `docs/<area>/readme.md` — orchestrator owns the index, batched into RUL-23 commits per merge sweep.
- Workers branch worktrees from `origin/main` (not local HEAD) — `git fetch origin && git worktree add ... origin/main`.
- All orchestrator-authored cross-cutting commits route through `RUL-23:`.
- Cross-reference identifier names when merging spike/data PRs — grep the engine for downstream consumers.
- Card naming convention (M1.5-ratified, M2-extended): SUBJECT names use `Player.id` literals (`p0..p3`) and `labels.LABEL_NAMES` keys (`"THE LEADER"`); effect-card IDs follow `eff.<status>.<verb>.[N]`.
- **Substrate-and-data tickets** must split DoD into (a) data loadable + (b) data observable in runtime.
- **Behavioural-substrate cascade rule** (2026-05-10): when a PR changes a public-function contract (signature, required-field consumption, exception class), every test that constructs `GameState` for the affected code path is implicitly impacted. Rebase against post-merge main and run affected tests before squash-merge if the PR is part of a parallel fan with a sibling that landed a contract change. CLEAN merge mechanics is necessary but not sufficient.
- **Conditional-substrate rule** (2026-05-10, RUL-54): when a PR adds a code path that fires conditionally on accumulated runtime state (deck exhaustion, retry counter, history growth), spot-check by asking "what's the depth at which this branch first triggers, and does any test reach it?" If no test reaches the branch and it's reachable in production, the path is unreviewed substrate. RUL-47's `rng=None` fallback at the recycle site didn't bite until round 13; RUL-54 lifted it to a `ValueError` so future callers can't silently regress. Disjoint-stream pattern: `rng = seed`, `refill_rng = seed ^ 0x5EED`, `dice_rng = seed ^ 0xD1CE`, `effect_rng = seed ^ 0xEFFC` (RUL-54).
- **Public legal-action surface (Wave 2)**: `bots.random.enumerate_legal_actions(state, player)` is the canonical raw legal-action enumeration — no `PLAY_BIAS` weighting; consumed by `bots.human` and any future driver. `bots.random.choose_action` remains the bot's PLAY_BIAS-weighted picker (`PLAY_BIAS = 0.75` post-RUL-55).
- **SHOP substrate (Wave 4, RUL-51)**: `Phase.SHOP` real handler at `engine/src/rulso/rules.py` (`enter_round_start` step-5 cadence check + `complete_shop` / `apply_shop_purchase` / `shop_purchase_order` helpers). `ShopOffer` model + `shop_pool` / `shop_offer` / `shop_discard` fields on `GameState`. Cadence `round_number % SHOP_INTERVAL == 0` (every 3 rounds); buy order `(vp asc, chips asc, seat asc)` per `design/state.md`. `cards.yaml shop_cards:` ships empty — SHOP short-circuits when no offers; content lands via RUL-56.

## Conventions (also in CLAUDE.md, restated for reflex)

- Linear ticket prefix `RUL-`; team `Rulso`; projects mirror areas.
- Branch: `RUL-<id>-<slug>`. Worktree: `.worktrees/RUL-<id>-<slug>` (gitignored).
- Commit prefix: `RUL-<id>: <imperative subject>`. Orchestrator meta commits use `RUL-23:`.
- Status flow: Backlog → Todo → In Progress → In Review → Done.
- PRs are checkpoints. Squash-merge on clean; rebase-then-squash on conflict. **Spot-check one DoD bullet against the diff before merging.**
- Hand-over template (per global `~/Documents/Projects/CLAUDE.md`): first line `=== TICKET-ID — title ===`; closing `=== END ===`.

## Bootstrap incantation

```
Act as orchestrator for Rulso. Read CLAUDE.md (auto-loaded), STATUS.md, and the
last 5 entries of docs/workflow_lessons.md if present. Then await instructions.
```

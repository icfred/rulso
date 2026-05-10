_Last updated: 2026-05-10 by orchestrator session — Wave 1 SHIPPED (RUL-47 substrate + RUL-48/50 docs); Wave 2 ready (RUL-49 + RUL-52); RUL-35 is the Wave 3 gate; RUL-51 SHOP filed for Wave 4_

# Rulso — orchestrator bootstrap

This is the cold-start payload for a fresh orchestrator chat. Read after `CLAUDE.md` (auto-loaded), then dispatch.

Linear board: https://linear.app/rulso (team `RUL`, projects: Engine / Infra / Bots / Client / Design).

## Active milestones

| ID | Milestone | Goal | State |
|---|---|---|---|
| RUL-5 | M1: Engine core | 4-bot CLI game runs end-to-end, IF rules resolve, state machine sound | **Done** |
| RUL-15 | M1.5: Watchable engine | First moment the game is *real* | **Done** (closed 2026-05-10) |
| RUL-24 | M2: Full card set | Every card type and mechanic from cards.yaml works | Phase 1 + Phase 2 + Phase 3 fan SHIPPED + Wave 1 SHIPPED; Wave 2 (RUL-49 + RUL-52) next; RUL-35 gate is Wave 3; RUL-51 SHOP closes M2 |
| RUL-23 | Meta — orchestrator-authored cross-cutting commits | Permanent home for orchestrator commits | Permanent In Progress |

## In flight

**Nothing in flight.** Wave 1 fully merged. Main: **407 tests passing** (398 + 9 new from RUL-47), ruff clean. Effect deck now draws round-by-round and recycles via discard pile. `_M1_EFFECT_CARD` placeholder removed.

### Wave plan

- **Wave 1 (DONE 2026-05-10)**: RUL-47 (round-flow effect-deck draw — substrate wiring; PR #44) + RUL-48 (cards-inventory.md noun.hits text fix; PR #42) + RUL-50 (sync design/state.md JOKER step-reorder + ECHO conditional; PR #43). Behavioural-substrate (47) fanned with two docs to keep the cascade surface small. No cascade observed — workers' new tests went green on rebase against post-merge main, no RUL-23 fix-forward needed beyond this sweep.
- **Wave 2 (READY)**: RUL-49 (BLESSED chip-loss wiring + BURN tick) + RUL-52 (CLI human-seat). Different files (`status.py`/`effects.py` vs new `bots/human.py` or `cli/human_seat.py`); parallel-safe. Serialised after Wave 1 to avoid stacking two behavioural-substrate changes per the 2026-05-10 cascade lesson.
- **Wave 3 (gate, solo)**: RUL-35 — M2 watchable smoke. Lands on fully-wired M2 (post-49). Reclaims winner-emergence assertion that RUL-34 deferred.
- **Wave 4 (post-gate)**: RUL-51 — SHOP round (every 3 rounds, lowest-VP buys first). Held until Wave 3 baseline pins; SHOP shifts round cadence and we want the smoke floor stable first.
- **Open after Wave 3**: M3 ISMCTS scoping. Lean is to defer M3 until the user has playtested via RUL-52 (CLI human-seat) — playtest data shapes ISMCTS payoff rather than the other way round.

### Phase 3 fan — final state (2026-05-10)

| ID | Letter | PR | Notes |
|---|---|---|---|
| RUL-39 | D | #37 | Effect dispatcher + `register_effect_kind` registry hook |
| RUL-40 | E | #40 | `status.py` + 7 effect-kind registrations (5 DoD + APPLY_MARKED + CLEAR_CHAINED); BLESSED chip-loss wiring deferred to RUL-49 |
| RUL-41 | F | #35 | ANYONE / EACH_PLAYER scoping per ADR-0003 (existential = subset-fire-once, iterative = per-player loop). Reworked once after first PR diverged from ADR. |
| RUL-42 | G | #38 | Comparator dice (ADR-0002) |
| RUL-43 | H | #36 | Operator MODIFIER fold (ADR-0004) |
| RUL-44 | I | #34 | Polymorphic NOUN reads |
| RUL-45 | J | #41 | JOKER attachment (PERSIST_WHEN/WHILE/DOUBLE/ECHO). Step-5/step-6 reorder + ECHO-as-conditional-WHEN flagged for state.md sync (RUL-50, shipped Wave 1). |
| RUL-46 | K | #39 | Goal-claim engine; ADR-0005 ratifies retype |

### Wave 1 — final state (2026-05-10)

| ID | PR | Notes |
|---|---|---|
| RUL-47 | #44 | Round-flow effect-deck draw: `enter_round_start` step 6 pops from `effect_deck`; `enter_resolve` step 10 pushes to `effect_discard`; `_fail_rule_and_rotate` and dealer-no-seed branch also discard (per `design/effects-inventory.md` "Rule-failure interaction"). Recycle on empty deck via `rng`. `_M1_EFFECT_CARD` constant removed. `enter_round_start` gained `*, rng=None` (additive). 9 new tests in `test_round_flow.py`. |
| RUL-48 | #42 | Single-line `cards-inventory.md` fix: `noun.hits` row now cites `player.history.hits_taken_this_game` (was placeholder `hits_this_round`). |
| RUL-50 | #43 | `design/state.md` Phase: resolve steps 5/6 swapped (step 5 = WHEN trigger; step 6 = JOKER attachment, with rationale inline). ECHO described as one-shot WHEN promotion with conditional re-fire (option (a) per ticket). DOUBLE noted as effect-only, no persistent residue. |

**Cross-cutting fixes landed via this RUL-23 sweep**:
- `docs/engine/readme.md` index: brought current for Phase 3 fan + Wave 1 (rows added for `status.py`, `goals.py`, 8 new test files; stale descriptions on `effects.py` and `persistence.py` rewritten).
- `docs/engine/round-flow.md` "M1 stubs that survive" updated: removed JOKER-NotImplementedError bullet (RUL-45 wired it); refreshed effect-application + goal-claim bullets (Phase 3 fan wired them); SHOP bullet now points at RUL-51.
- `design/cards-inventory.md` `jkr.echo` row aligned with state.md ECHO conditional re-fire semantics (RUL-50 worker flag).
- `effects.py:42-46` and `test_effects_nouns.py:171-173`: dropped stale references to the `hits_this_round` placeholder (no longer in any doc post RUL-48).

**Follow-ups outstanding**:
- RUL-49: Wire BLESSED into chip-loss handlers (E shipped `consume_blessed_or_else` primitive; call-site flip deferred) — **Wave 2**
- RUL-51: SHOP round (every 3 rounds, lowest-VP buys first) — **Wave 4**, blocked by RUL-35
- RUL-52: CLI human-seat mode (TTY prompt replaces one bot's `select_action`) — **Wave 2**

**Lessons captured** (`docs/workflow_lessons.md`):
- 2026-05-10: revealed_effect pin fan-out — every Phase 3 PR needed pin; CLEAN merge mechanics didn't catch
- 2026-05-10: deck-size fragility in test helpers — seed-0 lucky deals invisibly bake into 14+ tests

M2 Phase 2 SHIPPED (RUL-31 cards/state.py substrate, RUL-32 WHEN+WHILE lifecycle, RUL-33 GENEROUS+CURSED labels — all merged 2026-05-10). M1.5 smoke re-contract SHIPPED (RUL-34, merged 2026-05-10). M2 Phase 3 fan + Wave 1 SHIPPED (11 PRs total, all green).

## Open judgment calls

- **Wave 2 dispatch**: ready now. RUL-49 + RUL-52 can fan in parallel. Per the 2026-05-10 cascade lesson, RUL-49 is the only behavioural-substrate change in Wave 2; RUL-52 touches `bots/` + new TTY module only. If Wave 2 produces no cascade, dispatch RUL-35 solo.
- **RUL-35 stop condition**: if M2 watchable smoke can't reach ≥7/10 winners on the wired M2 deck, that's a Phase 3.5 polish problem — pause, hand back, file polish ticket. Do not lower the gate floor below 5/10.
- **M3 vs further M2 polish**: defer until Wave 3 result + user CLI-playtest signal (RUL-52).

## Phase 3 prep — why RUL-34 landed first

RUL-31's worker probe found that even silently-safe deck additions (ANYONE/EACH no-op via empty scope; JOKERs sit in-hand) regress the M1.5 watchable smoke 6/10 → 1-2/10 winners by diluting the rule-fire pool. Each Phase 3 ticket extends `cards.yaml deck:` for its consumer, so the smoke would have gone red on the first Phase 3 PR even when the PR is correct.

**RUL-34** re-contracted the M1.5 smoke as a regression detector during Phase 3: dropped `_MIN_WINNERS` to 0; widened `_MIN_RUNS_WITH_RESOLVE` to 7 and `_MIN_TOTAL_RESOLVES` to 34 (worst-case × 0.7); deleted `test_at_least_one_seed_produces_a_winner`. The "real watchable bar" moves to **RUL-35** (M2 watchable smoke), which lands as the Wave 3 gate and reclaims winner emergence on the fully-wired M2 deck.

## M2 Phase 2 Done summary

3 sub-issues closed:
- **RUL-31** — state.py additive (`CardType.EFFECT`, `Card.scope_mode`, `GoalCard`); cards.yaml extended with full M2 vocabulary (CONDITION when/while; SUBJECT ANYONE/EACH; NOUN cards/rules/hits/gifts/rounds/burn; MODIFIER OP-only comparators; operator MODIFIERs with targets; JOKERs; effect_cards section; goal_cards section); cards.py loader covers new sections + `load_effect_cards` / `load_goal_cards` helpers. **Deck composition held byte-identical** — see Phase 3 cross-cutting requirement.
- **RUL-32** — `persistence.tick_while_rules` and `persistence.check_when_triggers` shipped per state.md "Persistent Rules — Lifetimes". WHILE persists; WHEN FIFO + discard-on-fire; depth-3 recursion cap; dormant-label handling. Effect application is a Phase 2 stub (promotes WHEN/WHILE template to IF and reuses `effects.resolve_if_rule` for +1 VP) — Phase 3 effect dispatcher replaced.
- **RUL-33** — GENEROUS = argmax(`history.cards_given_this_game`); CURSED = argmax(`status.burn`). ADR-0001 tie-break: ties → all; zero → empty. MARKED/CHAINED stay empty pending status-apply ticket.

## Done (chronological, this session)

M1 + M1.5 + M2 Phase 1 + M2 Phase 2 + M2 Phase 3 fan + Wave 1 = ~31 tickets shipped.

## Locked decisions / substrate watchpoints

- `engine/src/rulso/state.py` is the contract. **Additive-only edits.**
- Pydantic v2 + frozen by default; tuples for collections.
- M2 stubs raise `NotImplementedError("M2: …")` — most replaced in Phase 3; SHOP entry remains until RUL-51.
- Pre-commit hook resolves `ruff` via `uv run --project engine`.
- **Active ADRs**: ADR-0001 (floating-label definitions), ADR-0002 (comparator dice flow), ADR-0003 (SUBJECT.scope_mode enum), ADR-0004 (operator MODIFIER attachment), ADR-0005 (GoalCard typing).
- Workers do not edit `docs/<area>/readme.md` — orchestrator owns the index, batched into RUL-23 commits per merge sweep.
- Workers branch worktrees from `origin/main` (not local HEAD) — `git fetch origin && git worktree add ... origin/main`.
- All orchestrator-authored cross-cutting commits route through `RUL-23:`.
- Cross-reference identifier names when merging spike/data PRs — grep the engine for downstream consumers.
- Card naming convention (M1.5-ratified, M2-extended): SUBJECT names use `Player.id` literals (`p0..p3`) and `labels.LABEL_NAMES` keys (`"THE LEADER"`); effect-card IDs follow `eff.<status>.<verb>.[N]`.
- **Substrate-and-data tickets** must split DoD into (a) data loadable + (b) data observable in runtime. Holding (a) without (b) is correct when the consumer side isn't ready — RUL-31 lesson, 2026-05-10.
- **Behavioural-substrate cascade rule** (2026-05-10): when a PR changes a public-function contract (signature, required-field consumption, exception class), every test that constructs `GameState` for the affected code path is implicitly impacted. Rebase against post-merge main and run affected tests before squash-merge if the PR is part of a parallel fan with a sibling that landed a contract change. CLEAN merge mechanics is necessary but not sufficient.

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

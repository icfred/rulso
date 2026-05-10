_Last updated: 2026-05-10 by orchestrator session — Wave 2 SHIPPED (RUL-49 BLESSED chip-loss + RUL-52 CLI human-seat); RUL-35 (M2 watchable smoke) is the Wave 3 gate, ready to dispatch; RUL-51 SHOP queued for Wave 4_

# Rulso — orchestrator bootstrap

This is the cold-start payload for a fresh orchestrator chat. Read after `CLAUDE.md` (auto-loaded), then dispatch.

Linear board: https://linear.app/rulso (team `RUL`, projects: Engine / Infra / Bots / Client / Design).

## Active milestones

| ID | Milestone | Goal | State |
|---|---|---|---|
| RUL-5 | M1: Engine core | 4-bot CLI game runs end-to-end, IF rules resolve, state machine sound | **Done** |
| RUL-15 | M1.5: Watchable engine | First moment the game is *real* | **Done** (closed 2026-05-10) |
| RUL-24 | M2: Full card set | Every card type and mechanic from cards.yaml works | Phase 1 + Phase 2 + Phase 3 fan SHIPPED + Wave 1 + Wave 2 SHIPPED. Wave 3 gate (RUL-35) ready. RUL-51 SHOP closes M2 after Wave 3. |
| RUL-23 | Meta — orchestrator-authored cross-cutting commits | Permanent home for orchestrator commits | Permanent In Progress |

## In flight

**Nothing in flight.** Wave 2 fully merged. Main: **425 tests passing**, ruff clean. BLESSED now cancels chip-loss at every site (LOSE_CHIPS effect + BURN tick); `--human-seat` flag on the CLI lets the user play one of the four seats with random bots filling the rest.

### Wave plan

- **Wave 1 (DONE 2026-05-10)**: RUL-47 (round-flow effect-deck draw — substrate wiring; PR #44) + RUL-48 (cards-inventory.md noun.hits text fix; PR #42) + RUL-50 (sync design/state.md JOKER step-reorder + ECHO conditional; PR #43). RUL-23 sweep: PR #45.
- **Wave 2 (DONE 2026-05-10)**: RUL-49 (BLESSED chip-loss + BURN tick; PR #46) + RUL-52 (CLI human-seat; PR #47). Behavioural-substrate cascade contained in PR #46 (single fixture amended in-PR with explanatory comment; 8 new tests cover the BLESSED+chip-loss matrix). UI/driver work in PR #47 was strictly additive (kw-only `human_seat=None` defaults; existing CLI smoke tests passed unchanged). RUL-23 sweep: this PR.
- **Wave 3 (gate, solo) — READY**: RUL-35 — M2 watchable smoke. Lands on fully-wired M2 (post-Wave-2). Reclaims the winner-emergence assertion that RUL-34 deferred during Phase 3.
- **Wave 4 (post-gate)**: RUL-51 — SHOP round (every 3 rounds, lowest-VP buys first). Held until Wave 3 baseline pins; SHOP shifts round cadence.
- **Wave 4 docs chore**: RUL-53 — refresh `docs/engine/bots.md` for RUL-43/45/52 (PlayJoker, operator-MODIFIER skip rules, `enumerate_legal_actions`, `bots/human.py`). Parallel-safe with anything; pick up alongside RUL-51 or whenever a worker has spare cycles.
- **Open after Wave 3**: M3 ISMCTS scoping. Lean is still to defer M3 until the user has playtested via RUL-52 (now landed) — the playtest data shapes ISMCTS payoff.

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
- RUL-35: M2 watchable smoke — **Wave 3 gate, ready**.
- RUL-51: SHOP round — **Wave 4**, blocked by RUL-35.
- RUL-53: refresh `docs/engine/bots.md` for Phase 3 + Wave 2 — **Wave 4 docs chore**.

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

M2 Phase 2 SHIPPED (RUL-31 cards/state.py substrate, RUL-32 WHEN+WHILE lifecycle, RUL-33 GENEROUS+CURSED labels). M1.5 smoke re-contract SHIPPED (RUL-34). M2 Phase 3 fan + Wave 1 + Wave 2 SHIPPED (13 PRs in this stretch, all green).

## Open judgment calls

- **Wave 3 stop condition**: if M2 watchable smoke can't reach ≥7/10 winners on the wired M2 deck, that's a Phase 3.5 polish problem — pause, hand back, file polish ticket. Do not lower the gate floor below 5/10.
- **M3 vs further M2 polish**: defer until Wave 3 result + user CLI-playtest signal (RUL-52 now usable via `uv run rulso --seed 0 --human-seat 0`).
- **Canonical legality module**: RUL-52 worker correctly observed that `legality.legal_actions` doesn't exist — `bots.random.enumerate_legal_actions` is the de-facto canonical surface now. No refactor planned; if a third driver lands (replay, ISMCTS rollouts), reconsider then.

## Phase 3 prep — why RUL-34 landed first

RUL-31's worker probe found that even silently-safe deck additions (ANYONE/EACH no-op via empty scope; JOKERs sit in-hand) regress the M1.5 watchable smoke 6/10 → 1-2/10 winners by diluting the rule-fire pool. Each Phase 3 ticket extends `cards.yaml deck:` for its consumer, so the smoke would have gone red on the first Phase 3 PR even when the PR is correct.

**RUL-34** re-contracted the M1.5 smoke as a regression detector during Phase 3: dropped `_MIN_WINNERS` to 0; widened `_MIN_RUNS_WITH_RESOLVE` to 7 and `_MIN_TOTAL_RESOLVES` to 34 (worst-case × 0.7); deleted `test_at_least_one_seed_produces_a_winner`. The "real watchable bar" moves to **RUL-35** (M2 watchable smoke), which lands as the Wave 3 gate and reclaims winner emergence on the fully-wired M2 deck.

## M2 Phase 2 Done summary

3 sub-issues closed:
- **RUL-31** — state.py additive (`CardType.EFFECT`, `Card.scope_mode`, `GoalCard`); cards.yaml extended with full M2 vocabulary; cards.py loader covers new sections + `load_effect_cards` / `load_goal_cards` helpers.
- **RUL-32** — `persistence.tick_while_rules` and `persistence.check_when_triggers`. WHILE persists; WHEN FIFO + discard-on-fire; depth-3 recursion cap; dormant-label handling. Phase 3 effect dispatcher replaced the Phase 2 stub.
- **RUL-33** — GENEROUS = argmax(`history.cards_given_this_game`); CURSED = argmax(`status.burn`). ADR-0001 tie-break: ties → all; zero → empty. MARKED/CHAINED stay empty pending status-apply ticket.

## Done (chronological, this session)

M1 + M1.5 + M2 Phase 1 + M2 Phase 2 + M2 Phase 3 fan + Wave 1 + Wave 2 = ~33 tickets shipped.

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
- **Substrate-and-data tickets** must split DoD into (a) data loadable + (b) data observable in runtime.
- **Behavioural-substrate cascade rule** (2026-05-10): when a PR changes a public-function contract (signature, required-field consumption, exception class), every test that constructs `GameState` for the affected code path is implicitly impacted. Rebase against post-merge main and run affected tests before squash-merge if the PR is part of a parallel fan with a sibling that landed a contract change. CLEAN merge mechanics is necessary but not sufficient.
- **Public legal-action surface (Wave 2)**: `bots.random.enumerate_legal_actions(state, player)` is the canonical raw legal-action enumeration — no `PLAY_BIAS` weighting; consumed by `bots.human` and any future driver. `bots.random.choose_action` remains the bot's PLAY_BIAS-weighted picker.

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

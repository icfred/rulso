_Last updated: 2026-05-10 by orchestrator session_

# Rulso — orchestrator bootstrap

This is the cold-start payload for a fresh orchestrator chat. Read after `CLAUDE.md` (auto-loaded), then dispatch.

Linear board: https://linear.app/rulso (team `RUL`, projects: Engine / Infra / Bots / Client / Design).

## Active milestones

| ID | Milestone | Goal | State |
|---|---|---|---|
| RUL-5 | M1: Engine core | 4-bot CLI game runs end-to-end, IF rules resolve, state machine sound | **Done** |
| RUL-15 | M1.5: Watchable engine | First moment the game is *real* | **Done** (closed 2026-05-10) |
| RUL-24 | M2: Full card set | Every card type and mechanic from cards.yaml works | Phase 1 head fan all merged; Phase 2 ready to plan |
| RUL-23 | Meta — orchestrator-authored cross-cutting commits | Permanent home for orchestrator commits | Permanent In Progress |

## In flight

None. M1.5 SHIPPED (RUL-21 watchable smoke landed; full pipeline produces winners). M2 Phase 1 SHIPPED (RUL-25 ADRs, RUL-26 substrate, RUL-27 bot heuristic, RUL-28/29/30 inventory spikes all merged). Awaiting user sign-off on Phase 2 ticket shape before dispatch.

## M1.5 Done summary

13 sub-issues closed: RUL-16 (cards-inventory spike), RUL-17 (cards.yaml + loader), RUL-18 (deal real hands + CONDITION cards + naming reconciliation), RUL-19 (LEADER + WOUNDED labels + ADR-0001), RUL-20 (+1 VP effect), RUL-21 (watchable smoke), RUL-22 (label scoping wiring). M1.5 produced a watchable game where bots play real cards, IF rules resolve, labels scope, and winners emerge across 10 seeds at 200 rounds.

## M2 Phase 1 Done summary

7 sub-issues closed:
- **RUL-25** — ADR-0002 (OP-only comparator + dice fills N), ADR-0003 (`SUBJECT.scope_mode: singular | existential | iterative`), ADR-0004 (operator MODIFIERs ratify `RuleBuilder.slots[i].modifiers` with `targets` list).
- **RUL-26** — state.py additive: `Player.history.hits_taken_this_game`, `GameState.shop_deck`, `active_goals` retyped to `tuple[Card | None, ...]`. persistence.py scaffolding live (stub bodies for `tick_while_rules` and `check_when_triggers`; real `add_persistent_rule`).
- **RUL-27** — bot heuristic (PLAY_BIAS = 0.85). Unblocked RUL-21.
- **RUL-28** — `design/goals-inventory.md` (7 starter goals; predicate vocabulary; CHAINED interaction; deck-empty behaviour).
- **RUL-29** — `design/effects-inventory.md` (12 starter effect cards; revealed-effect lifecycle; status-applying effects; magnitude/target_modifier dispatch table).
- **RUL-30** — `design/status-tokens.md` (5 tokens; per-token apply/clear sources; interaction matrix; engine-side dispatch recommendation: new `status.py` module).

## Open judgment calls

None.

## M2 Phase 2 — proposed ticket shape (awaiting sign-off)

3 parallel-safe head-fan tickets:

| Proposed ticket | Scope | Touch surface | Parallel-safe? |
|---|---|---|---|
| **A** — M2 cards content + loader extensions | Extend cards.yaml with M2 SUBJECTs (ANYONE/EACH per ADR-0003 scope_mode), full M2 NOUNs (CARDS/RULES/HITS/GIFTS/ROUNDS/BURN_TOKENS), operator MODIFIERs (per ADR-0004 with targets), JOKERs, full effect-cards section per RUL-29 inventory, goals section per RUL-28. Loader handles new card-type variants. **state.py additive**: `CardType.EFFECT`, `GoalCard` model (per RUL-29 + RUL-28 worker flags), `scope_mode` field on SUBJECT cards (per ADR-0003). | `design/cards.yaml`, `engine/src/rulso/cards.py`, `engine/src/rulso/state.py` (additive), tests, new docs | yes (only ticket touching cards.yaml + state.py) |
| **B** — WHEN + WHILE rule lifecycle | Implement `persistence.tick_while_rules` (round-start tick + on-state-change re-eval) and `persistence.check_when_triggers` (after every state mutation in resolve, depth-cap 3 per state.md). Dormant-label handling. | `engine/src/rulso/persistence.py`, `engine/src/rulso/rules.py` (additive — already wired by RUL-26), tests | yes (only ticket touching persistence.py) |
| **C** — GENEROUS + CURSED labels | Extend `labels.recompute_labels` to compute GENEROUS (argmax player.history.cards_given_this_game) and CURSED (argmax player.status.burn) per ADR-0001's tie-break. M1.5 stubs become live. | `engine/src/rulso/labels.py` (additive), tests | yes (only ticket touching labels.py) |

After A/B/C land, Phase 3 fan opens: effect dispatcher (RUL-29's table), status apply/decay (new status.py per RUL-30), ANYONE/EACH scoping, comparator dice, JOKER conversion (depends on B), operator evaluation, polymorphic rendering, goal cards engine. ~8 wide.

After Phase 3: SHOP round + M2 watchable smoke (single-track tail).

## Done (chronological, this session)

(M1 + M1.5 + M2 Phase 1 = ~25 tickets shipped)

## Locked decisions / substrate watchpoints

- `engine/src/rulso/state.py` is the contract. **Additive-only edits.**
- Pydantic v2 + frozen by default; tuples for collections.
- M2 stubs raise `NotImplementedError("M2: …")` — most will go live in Phase 2-3.
- Pre-commit hook resolves `ruff` via `uv run --project engine`.
- **Active ADRs**: ADR-0001 (floating-label definitions), ADR-0002 (comparator dice flow: OP-only cards, dice fills N), ADR-0003 (SUBJECT.scope_mode enum: singular | existential | iterative), ADR-0004 (operator MODIFIER attachment + targets list).
- Workers do not edit `docs/<area>/readme.md` — orchestrator owns the index, batched into RUL-23 commits per merge sweep.
- Workers branch worktrees from `origin/main` (not local HEAD) — `git fetch origin && git worktree add ... origin/main`.
- All orchestrator-authored cross-cutting commits route through `RUL-23:`.
- Cross-reference identifier names when merging spike/data PRs — grep the engine for downstream consumers.
- Card naming convention (M1.5-ratified, M2-extended): SUBJECT names use `Player.id` literals (`p0..p3`) and `labels.LABEL_NAMES` keys (`"THE LEADER"`); effect-card IDs follow `eff.<status>.<verb>.[N]` (RUL-29's convention; RUL-30 amended to match in PR #29).

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

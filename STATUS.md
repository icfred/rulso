_Last updated: 2026-05-10 by orchestrator session_

# Rulso — orchestrator bootstrap

This is the cold-start payload for a fresh orchestrator chat. Read after `CLAUDE.md` (auto-loaded), then dispatch.

Linear board: https://linear.app/rulso (team `RUL`, projects: Engine / Infra / Bots / Client / Design).

## Active milestones

| ID | Milestone | Goal | State |
|---|---|---|---|
| RUL-5 | M1: Engine core | 4-bot CLI game runs end-to-end, IF rules resolve, state machine sound | **Done** |
| RUL-15 | M1.5: Watchable engine | First moment the game is *real* | **Done** (closed 2026-05-10) |
| RUL-24 | M2: Full card set | Every card type and mechanic from cards.yaml works | Phase 1 + Phase 2 shipped; Phase 3 fan ready to shape |
| RUL-23 | Meta — orchestrator-authored cross-cutting commits | Permanent home for orchestrator commits | Permanent In Progress |

## In flight

**RUL-34** — Re-contract M1.5 watchable smoke for M2 transition (Phase 3 prep). Hand-over emitted; awaiting worker dispatch. Phase 3 fan blocked until this lands (see "Phase 3 prep" below).

M2 Phase 2 SHIPPED (RUL-31 cards/state.py substrate, RUL-32 WHEN+WHILE lifecycle, RUL-33 GENEROUS+CURSED labels — all merged 2026-05-10).

## Phase 3 prep — why RUL-34 must land first

RUL-31's worker probe found that even silently-safe deck additions (ANYONE/EACH no-op via empty scope; JOKERs sit in-hand) regress the M1.5 watchable smoke 6/10 → 0/10 winners by diluting the rule-fire pool. Each Phase 3 ticket extends `cards.yaml deck:` for its consumer, so the smoke would go red on the first Phase 3 PR even when the PR is correct.

**RUL-34** re-contracts the M1.5 smoke as a regression detector during Phase 3 (drops `_MIN_WINNERS` to 0; widens resolve floors to absorb dilution). The "real watchable bar" moves to **RUL-35** (M2 watchable smoke), which lands as the Phase 3 tail.

Sequence: RUL-34 → merge → Phase 3 fan (D–K, parallel) → merge → RUL-35.

## M2 Phase 2 Done summary

3 sub-issues closed:
- **RUL-31** — state.py additive (`CardType.EFFECT`, `Card.scope_mode`, `GoalCard`); cards.yaml extended with full M2 vocabulary (CONDITION when/while; SUBJECT ANYONE/EACH; NOUN cards/rules/hits/gifts/rounds/burn; MODIFIER OP-only comparators; operator MODIFIERs with targets; JOKERs; effect_cards section; goal_cards section); cards.py loader covers new sections + `load_effect_cards` / `load_goal_cards` helpers. **Deck composition held byte-identical** — see Phase 3 cross-cutting requirement.
- **RUL-32** — `persistence.tick_while_rules` and `persistence.check_when_triggers` shipped per state.md "Persistent Rules — Lifetimes". WHILE persists; WHEN FIFO + discard-on-fire; depth-3 recursion cap; dormant-label handling. Effect application is a Phase 2 stub (promotes WHEN/WHILE template to IF and reuses `effects.resolve_if_rule` for +1 VP) — Phase 3 effect dispatcher replaces.
- **RUL-33** — GENEROUS = argmax(`history.cards_given_this_game`); CURSED = argmax(`status.burn`). ADR-0001 tie-break: ties → all; zero → empty. MARKED/CHAINED stay empty pending status-apply ticket.

## Open judgment calls

None.

## M2 Phase 3 — proposed ticket shape (awaiting sign-off)

Phase 2 substrate is in. Phase 3 wires consumers; this is the ~8-wide fan. **All depend on Phase 2 only — none depend on each other within Phase 3 unless flagged.** Substrate-first discipline holds; only one Phase 3 ticket touches `state.py` (status apply/decay introduces `status.py`). Order roughly maps to risk + dependency depth.

| Proposed ticket | Scope | Touch surface | Parallel-safe? |
|---|---|---|---|
| **D — effect dispatcher** | Replace the M1.5 `+1 VP` stub in `effects.resolve_if_rule` with a real `revealed_effect`-driven dispatcher. Parses effect-card name (`<KIND>[:<MAG>][@<TARGET_MOD>]`); applies GAIN_CHIPS / LOSE_CHIPS / GAIN_VP / LOSE_VP / DRAW / NOOP. Status-applying effects (APPLY_BURN / APPLY_MUTE / APPLY_BLESSED / APPLY_CHAINED / CLEAR_BURN) deferred to ticket E (status.py). Wires `rules.start_game` to seed `effect_deck` from `load_effect_cards`. **Extends `deck:`** with effect_cards seeding. | `engine/src/rulso/effects.py`, `engine/src/rulso/rules.py` (start_game seeding only), tests | yes |
| **E — status apply/decay (new `status.py`)** | New module `status.py` per RUL-30 spike. Implements per-token apply/clear/decay matrix from `design/status-tokens.md`. Wires APPLY_BURN / APPLY_MUTE / APPLY_BLESSED / APPLY_CHAINED / CLEAR_BURN effect kinds (consumed by D). Round-start decay tick. **Extends `state.py`** if RUL-30 spike's recommendation needs more `Player.status` fields than already present (additive only). | `engine/src/rulso/status.py` (new), `engine/src/rulso/effects.py` (status-applying dispatcher entries), `engine/src/rulso/rules.py` (round-start decay hook), tests | depends on D for effect-kind dispatch table — sequence after D, or parallel if D's dispatcher exposes a registration hook |
| **F — ANYONE / EACH_PLAYER scoping** | Extend `effects._scope_subject` to honour `Card.scope_mode`: `existential` (ANYONE → first matching player makes the rule fire); `iterative` (EACH_PLAYER → fire effect once per matching player). Singular path unchanged (default). **Extends `deck:`** with subj.anyone + subj.each copies. | `engine/src/rulso/effects.py`, tests | yes |
| **G — comparator dice (OP-only MODIFIERs)** | Extend `effects._parse_quant` (or equivalent) to handle OP-only comparator cards (LT/LE/GT/GE/EQ without baked N). Per ADR-0002: when an OP-only comparator is played, draw N from 1d6 or 2d6 (player choice — bot picks 2d6 by default). **Extends `deck:`** with mod.cmp.{lt,le,gt,ge,eq} copies. | `engine/src/rulso/effects.py` (or `grammar.py`), `engine/src/rulso/bots/random.py` (dice choice), tests | yes |
| **H — operator MODIFIER fold** | Implement ADR-0004 operator attachment: `RuleBuilder.slots[i].modifiers` accepts operator MODIFIERs with `targets`. BUT/AND/OR fold into the SUBJECT or NOUN slot during render + scope; MORE_THAN/AT_LEAST fold into QUANT comparator semantics. **Extends `deck:`** with mod.op.* copies. | `engine/src/rulso/grammar.py`, `engine/src/rulso/effects.py`, `engine/src/rulso/state.py` (additive — ratify RuleBuilder slot.modifiers if not already present), tests | depends on the RuleBuilder slot-modifiers shape — verify additive-only at start; may parallel with D/E/F/G |
| **I — polymorphic NOUN reads** | Extend the NOUN evaluator (`effects._evaluate_has` or equivalent) to handle `CARDS / RULES / HITS / GIFTS / ROUNDS / BURN_TOKENS` per `design/cards-inventory.md` M2 NOUN table. **Extends `deck:`** with noun.{cards,rules,hits,gifts,rounds,burn} copies. | `engine/src/rulso/effects.py`, tests | yes |
| **J — JOKER attachment** | Implement JOKER:PERSIST_WHEN / PERSIST_WHILE / DOUBLE / ECHO. Persist variants promote the rule's CONDITION to WHEN/WHILE via `persistence.add_persistent_rule`. DOUBLE / ECHO modify effect application count. **Extends `deck:`** with jkr.* copies. **Depends on RUL-32** (persistence.add_persistent_rule). | `engine/src/rulso/effects.py`, `engine/src/rulso/legality.py` (JOKERs are legal as a 4th play type), `engine/src/rulso/bots/random.py` (bot picks legal JOKER), tests | yes (RUL-32 done) |
| **K — goal cards engine** | Implement the goal-claim predicate registry per RUL-28's spike: `chips_at_least_75`, `chips_under_10`, `rules_completed_at_least_3`, `gifts_at_least_2`, `burn_at_least_2`, `free_agent`, `full_hand`. Per-round claim check; awards `vp_award`; `single` discards + replenishes from `goal_deck`, `renewable` stays. Wires `rules.start_game` to seed `goal_deck` + `active_goals` from `load_goal_cards`. | new `engine/src/rulso/goals.py`, `engine/src/rulso/rules.py` (start_game seeding + per-round claim hook), tests | yes |

After Phase 3 fan: **RUL-35** (M2 watchable smoke) + SHOP round (single-track tail).

### Phase 3 cross-cutting requirement

Each Phase 3 ticket whose consumer wiring lands new card variants **must extend `cards.yaml` `deck:` with copies for those variants** as part of the same PR. RUL-31 deliberately held the deck identical because no consumer was ready; Phase 3 tickets each unblock a slice of the M2 vocabulary and own the deck extension for their slice. PR-merge spot-check: confirm the deck rows for the variant the ticket wires are present.

## Done (chronological, this session)

(M1 + M1.5 + M2 Phase 1 + M2 Phase 2 = ~28 tickets shipped)

## Locked decisions / substrate watchpoints

- `engine/src/rulso/state.py` is the contract. **Additive-only edits.**
- Pydantic v2 + frozen by default; tuples for collections.
- M2 stubs raise `NotImplementedError("M2: …")` — most replaced in Phase 3.
- Pre-commit hook resolves `ruff` via `uv run --project engine`.
- **Active ADRs**: ADR-0001 (floating-label definitions), ADR-0002 (comparator dice flow: OP-only cards, dice fills N), ADR-0003 (SUBJECT.scope_mode enum: singular | existential | iterative), ADR-0004 (operator MODIFIER attachment + targets list).
- Workers do not edit `docs/<area>/readme.md` — orchestrator owns the index, batched into RUL-23 commits per merge sweep.
- Workers branch worktrees from `origin/main` (not local HEAD) — `git fetch origin && git worktree add ... origin/main`.
- All orchestrator-authored cross-cutting commits route through `RUL-23:`.
- Cross-reference identifier names when merging spike/data PRs — grep the engine for downstream consumers.
- Card naming convention (M1.5-ratified, M2-extended): SUBJECT names use `Player.id` literals (`p0..p3`) and `labels.LABEL_NAMES` keys (`"THE LEADER"`); effect-card IDs follow `eff.<status>.<verb>.[N]` (RUL-29's convention; RUL-30 amended to match in PR #29).
- **Substrate-and-data tickets** must split DoD into (a) data loadable + (b) data observable in runtime. Holding (a) without (b) is correct when the consumer side isn't ready — RUL-31 lesson, 2026-05-10.

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

# Rulso — Project Context

Locked-decisions digest. Source of truth for "what's been decided"; `STATUS.md` is the source of truth for "what's currently in flight"; `design/state.md` is the source of truth for the engine state machine.

Read after `CLAUDE.md` (auto-loads) and before any project work. Promote inline decisions to ADRs in `docs/decisions/` when they're revisited.

**Active ADRs**:
- [ADR-0001](docs/decisions/ADR-0001-floating-label-definitions.md) — Floating-label definitions: LEADER = argmax(vp); WOUNDED = argmin(chips); ties → all tied players hold the label.
- [ADR-0002](docs/decisions/ADR-0002-comparator-dice-flow.md) — OP-only comparator MODIFIERs draw N from 1d6 or 2d6 (player choice).
- [ADR-0003](docs/decisions/ADR-0003-anyone-vs-each-player-scoping.md) — `Card.scope_mode` enum: singular / existential / iterative.
- [ADR-0004](docs/decisions/ADR-0004-operator-modifier-grammar.md) — Operator MODIFIERs (BUT/AND/OR/MORE_THAN/AT_LEAST) fold into `Slot.modifiers` left-to-right; AND/OR on SUBJECT = set union; MORE_THAN/AT_LEAST flip QUANT strictness.
- [ADR-0005](docs/decisions/ADR-0005-goalcard-typing.md) — `GameState.goal_deck` / `goal_discard` / `active_goals` retype from `Card` to `GoalCard` (substrate narrowing; placeholder fields RUL-26 introduced for M2).
- [ADR-0006](docs/decisions/ADR-0006-foundation-client-before-ismcts.md) — Foundation/Minimal Client lands as M3 (was M4); ISMCTS becomes M4 (was M3). CLI human-seat decision-support gap blocks playtest signal regardless of bot strength; rendering primitives needed for the client are duplicated work if built into the CLI.
- [ADR-0007](docs/decisions/ADR-0007-shop-payload-semantics.md) — SHOP payloads are `Card` instances delivered to `Player.hand` via the existing `_ShopEntry.payload_type` route (card-buy semantics). Locks shape 2 from the three RUL-62 candidates; M2.5 starter is 7 offers (2 SUBJECT / 2 MODIFIER / 3 JOKER) on the data-only path.
- [ADR-0008](docs/decisions/ADR-0008-ws-protocol-envelope.md) — WebSocket protocol envelope shape (M3 substrate). Server→client `Hello` / `StateBroadcast` / `ErrorEnvelope` (tagged on `type`); client→server `ActionSubmit` wraps `PlayCard | PlayJoker | DiscardRedraw` imported verbatim from `bots.random` (tagged on `kind`). MVP cadence is full state on every transition (diff is a future additive variant). `Pass` is server-side-only. `PROTOCOL_VERSION=1`.

## Critical context

These shape every decomposition and merge:

- **Digital-first.** No paper prototypes — explicitly ruled out.
- **Smart bots are non-negotiable.** Heuristic bots won't surface design flaws in solo play. ISMCTS at M3.
- **Substrate before content.** Lock fundamentals (state, resources, win condition) before drilling into card content.
- **Balatro is a reference, not a target.** Aesthetic is cool-mainframe Aegean — *don't* clone Balatro's warm arcade vibe.
- **PRs are checkpoints, not reviews.** Orchestrator merges them to keep parallel agents from clobbering each other. PR size doesn't matter; correctness does.

## Game design — locked

- 4 players, hand of 7 mixed cards, 50 starting chips, first to 3 VP wins
- Card types: SUBJECT, NOUN, MODIFIER, JOKER (rare)
- Rule lifetimes: IF (one-shot) / WHEN (persists, fires once) / WHILE (persists, fires repeatedly)
- Numbers via dice (1d6 or 2d6 player choice) when playing comparator MODs
- 3 face-up goal cards (Twilight Imperium-style, replenished on claim)
- Floating labels: THE LEADER / THE WOUNDED / THE GENEROUS / THE CURSED
- Status tokens: BURN / MUTE / BLESSED / MARKED / CHAINED
- SHOP round every 3 rounds; lowest-VP buys first

Full constants table (`PLAYER_COUNT`, `HAND_SIZE`, `STARTING_CHIPS`, `VP_TO_WIN`, etc.), phase semantics, status-token lifetimes, and edge-case index live in `design/state.md` — canonical, not duplicated here.

## Tech stack — locked

- **Engine**: Python 3.12 + Pydantic v2 + asyncio + websockets; ISMCTS bots from M3
- **Client**: TypeScript + Vite + PixiJS v8 (no React)
- **Protocol**: JSON over websocket; client types generated from Pydantic models
- **Lint/format**: Biome for client (TS/JS); Ruff for engine (Python)
- **Aesthetic**: Aegean palette, JetBrains Mono for rule text, Inter for chrome, 16px pixel grid (full spec in `aesthetic.md`)

## Workflow conventions — locked

- Linear ticket prefix `RUL-`; team `Rulso` (https://linear.app/rulso); projects mirror areas (Engine / Infra / Bots / Client / Design)
- Branch naming: `RUL-<id>-<slug>` (kebab-case)
- Commit prefix: `RUL-<id>: <imperative subject>` (`commit-msg` hook enforces)
- Worktrees at `.worktrees/RUL-<id>-<slug>` (gitignored)
- Status flow: Backlog → Todo → In Progress → In Review → Done
- Squash-merge on clean; rebase-then-squash on conflict
- **Spot-check one DoD bullet against the diff before merging** — green mergeability is not enough (see `docs/workflow_lessons.md`)

## Substrate watchpoints

These aren't policy — they're constraints on how new code lands. Workers who break them get rejected at merge.

- **`engine/src/rulso/state.py` is the contract.** Additive-only edits — no renames, retypes, or removals. Latest precedent: RUL-8 added `build_turns_taken` and `revealed_effect` as fields on `GameState`. Workers who rewrite state.py from scratch get re-dispatched.
- **Pydantic v2, frozen by default.** Tuples for collections (deeply immutable; `list.append` bypasses field-locking).
- **M2 stubs raise `NotImplementedError("M2: …")`** in M1/M1.5 modules (`rules.py` shop entry, persistence WHILE-tick, joker attachment). Don't satisfy these unless the ticket explicitly assigns M2 work.
- **Pre-commit hook** resolves `ruff` via `uv run --project engine`; biome via `client/node_modules/.bin/biome`. Contributors need `uv sync` in `engine/` and `npm install` in `client/` — no PATH munging.

## Pointers to canonical sources

| Concern | Source of truth |
|---|---|
| State machine, phases, constants, edge cases | `design/state.md` |
| Card definitions | `design/cards.yaml` (TBD) + `design/cards-inventory.md` (M1.5 spike output, TBD) |
| Aesthetic (palette, type, motion, sound) | `aesthetic.md` |
| Stack, repo layout | `tech.md` |
| Public-facing vision | `README.md` |
| Milestone definitions | `roadmap.md` |
| Orchestrator workflow | `workflows/orchestrator.md` |
| Worker workflow | `workflows/feature-work.md` |
| PR-merge workflow | `workflows/pr-merge.md` |
| Current sprint state (in flight, blocked chain, follow-ups) | `STATUS.md` |
| Captured workflow misses | `docs/workflow_lessons.md` |

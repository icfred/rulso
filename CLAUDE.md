# Rulso — agent bootstrap

Card game where players collaboratively/competitively build IF/WHEN/WHILE rules from typed fragment cards. First to 3 VP wins. Single-player MVP with smart bots.

## Status

Design stage. No code yet. Locked decisions below; details in linked docs.

## Where to find what

| File | Purpose |
|---|---|
| `README.md` | Plain-English vision. **Read first.** (Same content as the public-facing GitHub README.) |
| `roadmap.md` | M1–M5 milestone definitions |
| `tech.md` | Stack, architecture, repo layout |
| `aesthetic.md` | Palette, type, animation, sound |
| `design/state.md` | Round flow, phases, state machine — the contract |
| `design/cards.yaml` | Card definitions (TBD) |
| `workflows/orchestrator.md` | How the orchestrating agent decomposes work and dispatches sub-agents |
| `workflows/feature-work.md` | Per-ticket workflow every sub-agent follows |
| `workflows/pr-merge.md` | How the orchestrator merges sub-agent PRs |
| `docs/` | Agent-curated, AI-optimized feature documentation |

## Critical context

- **Digital-first.** No paper prototypes — explicitly ruled out.
- **Smart bots are non-negotiable.** Heuristic bots won't surface design flaws in solo play. ISMCTS at M3.
- **Substrate before content.** Lock fundamentals (state, resources, win condition) before drilling into card content.
- **Balatro is a reference, not a target.** Aesthetic is cool-mainframe Aegean — *don't* clone Balatro's warm arcade vibe.
- **PRs are checkpoints, not reviews.** The orchestrator merges them to keep parallel agents from clobbering each other. PR size doesn't matter.

## How orchestration works

The user runs **two kinds of Claude Code sessions**:

- **Orchestrator session** — the one currently talking to the user. Decomposes work, writes hand-over prompts, monitors Linear, merges PRs. Does NOT spawn sub-agents via the `Agent` tool. Does NOT write code (except trivial cross-cutting fixes).
- **Worker sessions** — fresh Claude Code chats opened by the user, each fed a hand-over prompt by the orchestrator. Each is a full Opus session. They work independently in worktrees and never report back; their deliverable is a PR + Linear state change.

The user controls parallelization by deciding how many worker chats to open. The orchestrator picks up completed work on the next "anything done?" prompt.

When you (the current session) are asked to start work, decompose, or check status:

1. Read `workflows/orchestrator.md` and follow it.
2. Decompose the request into Linear tickets (Project = area, parent issue = milestone, sub-issues = tasks).
3. Produce hand-over prompts for the user to paste into new chats.
4. When asked "anything done?" / "merge PRs", run the merge sweep per `workflows/pr-merge.md`.

## Core locked decisions

*Game design:*
- 4 players, 50 starting chips, first to 3 VP, hand of 7 mixed cards
- Card types: SUBJECT, NOUN, MODIFIER + rare JOKER
- Rule lifetimes: IF (one-shot) / WHEN (persists, fires once) / WHILE (persists, fires repeatedly)
- Numbers via dice (1d6 or 2d6 player choice) when playing comparator MODs
- 3 face-up goal cards (Twilight Imperium-style, replenished on claim)
- Floating labels: THE LEADER / THE WOUNDED / THE GENEROUS / THE CURSED
- Status tokens: BURN / MUTE / BLESSED / MARKED / CHAINED
- SHOP round every 3 rounds; lowest-VP buys first

*Tech:*
- Engine: Python 3.12 + Pydantic + asyncio + websockets, ISMCTS bots
- Client: TypeScript + Vite + PixiJS v8 (no React)
- Protocol: JSON over websocket; client types generated from Pydantic models
- Lint/format: Biome for client (TS/JS); Ruff for engine (Python)
- Aesthetic: Aegean palette, JetBrains Mono for rule text, Inter for chrome, 16px pixel grid

*Workflow conventions:*
- Linear ticket prefix: `RUL-`
- Branch naming: `RUL-<id>-<short-slug>`
- Commit prefix: `RUL-<id>: ` (enforced by `.githooks/commit-msg`)
- Worktrees live at `.worktrees/RUL-<id>-<slug>` (gitignored)
- Linear projects mirror areas: Engine, Client, Bots, Design, Infra
- Status flow: Backlog → Ready → In Progress → In Review → Done

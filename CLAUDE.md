# Rulso — agent bootstrap

Card game where players collaboratively/competitively build IF/WHEN/WHILE rules from typed fragment cards. First to 3 VP wins. Single-player MVP with smart bots.

## Status

Design stage. No code yet. Locked decisions below; details in linked docs.

## Where to find what

| File | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | **Locked-decisions digest** — game design, stack, workflow conventions, substrate watchpoints. Read this for "what's been decided". |
| `STATUS.md` | **Current sprint state** — in flight, blocked chain, follow-ups. Read this for "what's currently happening". |
| `README.md` | Plain-English vision. (Same content as the public-facing GitHub README.) |
| `roadmap.md` | M1–M5 milestone definitions |
| `tech.md` | Stack, architecture, repo layout |
| `aesthetic.md` | Palette, type, animation, sound |
| `design/state.md` | Round flow, phases, state machine — the canonical engine contract |
| `design/cards.yaml` | Card definitions (TBD) |
| `workflows/orchestrator.md` | How the orchestrating agent decomposes work and dispatches sub-agents |
| `workflows/feature-work.md` | Per-ticket workflow every sub-agent follows |
| `workflows/pr-merge.md` | How the orchestrator merges sub-agent PRs |
| `docs/workflow_lessons.md` | Captured workflow misses |
| `docs/` | Agent-curated, AI-optimized feature documentation |

## Critical context

The project's locked decisions, substrate watchpoints, and pointers to canonical sources live in `PROJECT_CONTEXT.md`. Read it before any work. The current sprint's in-flight tickets, blocked chains, and follow-ups live in `STATUS.md` — read it on every fresh orchestrator chat.

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

## Locked decisions

See `PROJECT_CONTEXT.md`. This file is intentionally a pointer, not a duplicate.

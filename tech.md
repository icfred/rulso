# Rulso — Tech Stack

Engine and client are separate processes communicating over websocket. Engine is authoritative.

## Architecture

```
┌─────────────────┐         websocket          ┌──────────────────┐
│  Python engine  │ ◄──────── JSON ─────────►  │ TypeScript/Pixi  │
│   (engine/)     │                            │     client/      │
│                 │                            │                  │
│ - game state    │                            │ - render (Pixi)  │
│ - round flow    │                            │ - input          │
│ - rule grammar  │                            │ - animations     │
│ - bots (ISMCTS) │                            │ - sound          │
└─────────────────┘                            └──────────────────┘
        │                                                ▲
        └──── shared types (generated from Pydantic) ────┘
```

## Engine — Python

| Concern | Choice |
|---|---|
| Python | 3.12+ |
| Package manager | `uv` |
| State schema | `pydantic` v2 |
| Async | `asyncio` |
| Websocket server | `websockets` library |
| Tests | `pytest` |
| Style | Pure functions where possible; immutable state objects (`pydantic.BaseModel` with `frozen=True`) |

### Engine layout

```
engine/
├── pyproject.toml
├── src/rulso/
│   ├── __init__.py
│   ├── state.py         # GameState, Player, Card, RuleBuilder (pydantic)
│   ├── rules.py         # round flow, phase transitions
│   ├── grammar.py       # polymorphic card rendering
│   ├── effects.py       # effect application
│   ├── labels.py        # label recomputation
│   ├── persistence.py   # WHEN / WHILE rule handling
│   ├── server.py        # websocket entry point
│   ├── protocol.py      # message types (pydantic) for engine↔client
│   └── bots/
│       ├── random.py    # baseline bot for testing
│       └── ismcts.py    # information-set MCTS bot
└── tests/
```

## Client — TypeScript

| Concern | Choice |
|---|---|
| Language | TypeScript |
| Bundler | Vite |
| Renderer | PixiJS v8 |
| Sound | Web Audio API (no library) |
| Framework | None (no React, no Vue) |
| Tests | Vitest (M5+) |

### Client layout

```
client/
├── package.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.ts          # bootstrap
│   ├── net.ts           # websocket client
│   ├── types/           # generated from Python (do not edit by hand)
│   ├── scenes/
│   │   ├── table.ts     # main game scene
│   │   └── menu.ts      # title / menu scene
│   ├── ui/
│   │   ├── card.ts      # card rendering & input
│   │   ├── rule.ts      # active rule renderer
│   │   ├── hand.ts      # player hand
│   │   ├── opponent.ts  # opponent panel
│   │   └── dice.ts      # dice animation
│   ├── audio.ts
│   └── theme.ts         # palette, typography constants
└── public/
    ├── fonts/
    └── sprites/
```

## Protocol

JSON over websocket, snake_case keys. Engine is authoritative — client sends *intent*; engine validates and broadcasts the resulting state.

```jsonc
// Client → engine
{ "type": "play_card", "card_id": "subject_each_player", "slot": "subject" }
{ "type": "discard_redraw", "card_ids": ["xyz"] }
{ "type": "roll_choice", "dice": 2 }

// Engine → client
{ "type": "state", "state": { /* full GameState */ } }
{ "type": "event", "event": "rule_resolved", "details": { /* … */ } }
```

For MVP, full-state on every change is fine (single-player, low frequency). Diff protocol is later optimization.

## Type generation (engine → client)

Engine is the source of truth for shape. Client types are generated from Pydantic models so they cannot drift.

Pipeline (RUL-66): `pydantic-to-typescript` (engine dev-dep, pinned in `engine/pyproject.toml [dependency-groups.dev]`) walks `rulso.protocol` for `BaseModel` subclasses, emits per-model JSON Schema, and pipes through `json-schema-to-typescript` (client dev-dep, resolved via `client/node_modules/.bin/json2ts`) into a single `client/src/types/generated.ts`. Output is committed (not gitignored); re-runs are byte-identical given identical sources.

A hand-curated `client/src/types/envelopes.ts` re-exports the discriminated unions (`ServerEnvelope` / `ClientAction` / `ClientEnvelope`) — pydantic2ts surfaces every `BaseModel` but not the `Annotated[Union[...], Field(discriminator=...)]` aliases (those are `TypeAdapter` aliases, not `BaseModel` subclasses).

```bash
# from repo root
./scripts/regenerate-types.sh
```

Requires `uv` on PATH and `npm install` in `client/`.

## Bot AI

- **Phase 1**: random-legal-play bot (`bots/random.py`) — used as ISMCTS baseline and smoke testing.
- **Phase 2**: ISMCTS (`bots/ismcts.py`) — Information-Set Monte Carlo Tree Search.
  - Sample plausible opponent hands from public info (chip counts, plays seen, history)
  - Simulate K rollouts per candidate move
  - Pick highest expected VP-progress move
  - Configurable thinking budget; default 200ms/turn

ISMCTS-specific notes:
- Need a fast `simulate(state, move)` — pure functions and immutable state make this clean.
- Hidden state: opponents' hands. Use chip counts and rule-build history to bias the sampler.
- Eval function: VP delta + chip delta weighted; possibly tuned via self-play later.

## How to run (target)

```bash
# one-time, at repo root
git config core.hooksPath .githooks   # activate commit hooks (see docs/infra/readme.md)

# in engine/
uv sync
uv run rulso-server          # websocket on :8765

# in client/
npm install
npm run dev                  # vite dev server
```

## Open

- Static asset pipeline (sprite atlases, font subsetting) — defer to M5
- Replay format — defer
- Configuration (chip costs, VP target as game settings) — wire as constants in `state.py` for MVP, surface in UI later

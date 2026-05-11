_Last edited: 2026-05-11 by RUL-23 (post-RUL-69: decision-support panels live — rule preview, goals, opponents; action button labels expanded via `renderCard`)_

# client

TypeScript + Vite + PixiJS v8 browser app. Receives engine state over WebSocket, renders the table, submits player input. Engine is authoritative; client is a thin renderer.

## Surface

| Path | Status | Notes |
|---|---|---|
| `client/package.json` | scaffolded | deps: `pixi.js`; dev: `vite`, `typescript`, `@biomejs/biome`, `json-schema-to-typescript` |
| `client/tsconfig.json` | live | strict; `noUncheckedIndexedAccess`, `verbatimModuleSyntax`, `noUnusedLocals` |
| `client/vite.config.ts` | live | `strictPort: 5173`, ES2022 target |
| `biome.json` (repo root) | live | 2-space indent, double-quote, `lineWidth: 100`; ignores `src/types/generated.ts`. Lives at root (not `client/`) so the pre-commit hook (cwd=repo root) and `npm run lint` (cwd=client/) resolve the same config — Biome walks ancestors from cwd until it finds `biome.json` |
| `client/index.html` | live | minimal status badge + `#app` JSON-log container; styles inline (no CSS framework) |
| `client/src/main.ts` | live | bootstrap: connect to `ws://localhost:8765`, status flips connecting → connected → closed/error, logs `Hello` seat + protocol version. Re-renders `#rule-preview`, `#goals`, `#opponents`, `#actions` on every `StateBroadcast` (RUL-69). Action button labels flow through `renderCard` (text, not JSON); click → `ActionSubmit` + "OUTGOING" pre-block; submit-once safeguard disables peer buttons on click; buttons rebuild on every `StateBroadcast` (clear on bot turns, never on `ErrorEnvelope`). Raw envelope log moved behind `<details>` for debug |
| `client/src/net.ts` | live | `connect(url, handlers)` opens WS, parses envelopes via generated discriminated union, dispatches via `onEnvelope` / `onStatus`. `send(ws, envelope: ClientEnvelope)` for outgoing actions (RUL-67) |
| `client/src/render/cards.ts` | live | `renderCard(card)` (RUL-69): handles every `CardType` — SUBJECT (label name + `p0..p3` → "Player 0..3" absolute), QUANT (operator + N), NOUN (read description), MODIFIER (operator + magnitude), JOKER (variant), EFFECT (action verb). Mirrors `engine/src/rulso/grammar.py` semantics |
| `client/src/render/rule.ts` | live | `renderActiveRule(state)` (RUL-69): one-line preview of the active rule's slot fill state — empty slots show `[<TYPE>: ?]`; lifetime prefix when fully filled; JOKER appended via `renderCard` |
| `client/src/render/goals.ts` | live | `renderGoals(state)` (RUL-69): one human-readable line per `state.active_goals`. Uses a hand-rolled `claim_condition → prose` lookup since the engine doesn't serialise rendered text — small + stable, per ADR-0001 / hand-over allowance |
| `client/src/render/opponents.ts` | live | `renderOpponents(state, human_seat)` (RUL-69): per non-human seat, "Player N — chips, VP, status: BURN(2), MUTE …" plus dormant-label suffixes. Floating labels (LEADER/WOUNDED/GENEROUS/CURSED) recomputed client-side per ADR-0001 because the engine doesn't serialise them — **drift risk flagged as a follow-up substrate ticket** |
| `client/src/types/generated.ts` | live | regenerated from `engine/src/rulso/protocol.py` by `scripts/regenerate-types.sh`; emits every `BaseModel` reachable from `protocol.py` (`Hello` / `StateBroadcast` / `ErrorEnvelope` / `ActionSubmit` + the `GameState` transitive closure + action shapes from `legality.py`). Idempotent: byte-identical re-runs |
| `client/src/types/envelopes.ts` | live | hand-curated unions over the generated interfaces (`ServerEnvelope` / `ClientAction` / `ClientEnvelope`); pydantic2ts does not surface the `Annotated[Union[...], Field(discriminator=...)]` aliases since they're `TypeAdapter` aliases (not `BaseModel` subclasses) |

## Type generation

Engine Pydantic models are the source of shape. Re-run after every `engine/src/rulso/{protocol,state,legality}.py` change:

```bash
# from repo root
./scripts/regenerate-types.sh
```

Pipeline:

1. `pydantic2ts` (engine dev-dep) introspects `rulso.protocol` for `BaseModel` subclasses and emits a JSON Schema for each.
2. `json-schema-to-typescript` (client dev-dep, resolved via `client/node_modules/.bin/json2ts`) converts to a single `.ts` file.
3. Output written to `client/src/types/generated.ts` (committed).
4. Hand-curated `client/src/types/envelopes.ts` re-exports the unions with literal-typed `type` / `kind` discriminators for TypeScript narrowing.

## Commands

Run from `client/`:

```bash
npm install
npm run dev          # vite at :5173 (strict port)
npm run build        # tsc --noEmit + vite build → dist/
npm run typecheck    # tsc --noEmit
npm run lint         # biome check src
npm run format       # biome format --write src
```

## Smoke

Two-window check (read-only client):

```bash
# window 1 — engine
cd engine && uv run rulso-server --seed 0 --human-seat 0

# window 2 — client
cd client && npm run dev
# open http://localhost:5173
```

Expected: status badge shows `connecting` → `connected`; first `<pre>` block is `Hello{seat=0,protocol_version=1}` (also logged to console as `[rulso] Hello seat=0 protocol_version=1`); subsequent blocks are `StateBroadcast`s as the engine transitions through `round_start` / `build` / etc. RUL-67 closed the loop: when seat 0 reaches BUILD, the broadcast carries `legal_actions` and the client renders one button per action below the JSON log. Click a button → "OUTGOING" pre-block appears in the log → server applies + broadcasts the next state → bots play their turns → buttons reappear on the human's next BUILD. Game progresses to END; terminal `StateBroadcast` (`winner` set, `phase=END`) renders cleanly and the connection closes.

Caveats:

- Floating labels (LEADER / WOUNDED / GENEROUS / CURSED) are recomputed client-side per ADR-0001 — the engine doesn't currently serialise them. Drift risk: any future ADR-0001 amendment must update both engine and client. Follow-up substrate ticket open to publish labels on the wire.
- Pixi rendering / scenes / Aegean palette / animations / sound — all M5.

## Conventions

- Pixi v8 conventions land in the next sub-issue (scene/UI layout, theme constants).
- Generated types: do not edit by hand. Re-run `scripts/regenerate-types.sh`.
- One subfeature per future doc file in `docs/client/<subfeature>.md`.
- Update this readme's surface table whenever a module gains its first non-stub code.

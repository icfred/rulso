_Last edited: 2026-05-11 by RUL-66 (M3 client bootstrap — Vite + Pixi v8 + TS scaffold, WS client, generated types)_

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
| `client/src/main.ts` | live | bootstrap: connect to `ws://localhost:8765`, render envelopes as `<pre>` JSON, status flips connecting → connected → closed/error, logs `Hello` seat + protocol version |
| `client/src/net.ts` | live | `connect(url, handlers)` opens WS, parses envelopes via generated discriminated union, dispatches via `onEnvelope` / `onStatus`. Read-only — no `ActionSubmit` yet |
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

Expected: status badge shows `connecting` → `connected`; first `<pre>` block is `Hello{seat=0,protocol_version=1}` (also logged to console as `[rulso] Hello seat=0 protocol_version=1`); subsequent blocks are `StateBroadcast`s as the engine transitions through `round_start` / `build` / etc. The client stalls broadcasts when seat 0 reaches BUILD (no input submitted yet — RUL-66 is read-only; input lands in a follow-up M3 sub-issue). To watch the engine drive to END, kill the client and `uv run rulso --seed 0` (engine-only CLI; all seats bot-driven).

## Conventions

- Pixi v8 conventions land in the next sub-issue (scene/UI layout, theme constants).
- Generated types: do not edit by hand. Re-run `scripts/regenerate-types.sh`.
- One subfeature per future doc file in `docs/client/<subfeature>.md`.
- Update this readme's surface table whenever a module gains its first non-stub code.

_Last edited: 2026-05-09 by RUL-14_

# engine

Python 3.12 package. `uv` managed. Pydantic v2 state, asyncio + `websockets` server, ISMCTS bots (M3).

## Surface

| Path | Status | Notes |
|---|---|---|
| `engine/pyproject.toml` | scaffolded | deps: `pydantic>=2`, `websockets`, `pytest`; dev: `ruff` |
| `engine/src/rulso/__init__.py` | stub | package marker |
| `engine/src/rulso/state.py` | live | frozen pydantic models + constants — see [state-models.md](state-models.md) |
| `engine/src/rulso/rules.py` | stub | round flow, phase transitions |
| `engine/src/rulso/grammar.py` | stub | polymorphic card rendering |
| `engine/src/rulso/effects.py` | stub | effect application |
| `engine/src/rulso/labels.py` | stub | label recomputation |
| `engine/src/rulso/persistence.py` | stub | WHEN / WHILE rule handling |
| `engine/src/rulso/server.py` | stub | websocket entry point |
| `engine/src/rulso/protocol.py` | stub | engine↔client message types |
| `engine/src/rulso/bots/__init__.py` | stub | bots package |
| `engine/src/rulso/bots/random.py` | stub | random-legal-play bot |
| `engine/tests/test_smoke.py` | live | asserts `import rulso` works |
| `engine/tests/test_state_models.py` | live | construction, frozen rejection, JSON round-trip |

## Commands

Run from `engine/`:

```bash
uv sync                       # install
uv run pytest                 # tests
uv run ruff format            # format
uv run ruff check             # lint
uv run ruff format --check    # CI check
```

## Pre-commit hook contract

`.githooks/pre-commit` runs ruff on staged `engine/**.py` via `uv run --project engine ruff …`. Contributors only need:

- `uv` on PATH (https://docs.astral.sh/uv/)
- `uv sync` once in `engine/` to materialise the venv

No manual `PATH=` munging, no global `ruff` install. The hook resolves ruff through `uv` regardless of caller environment.

(Client side: `npm install` in `client/`; the hook calls `client/node_modules/.bin/biome` directly.)

## Conventions

- Pydantic models default to `frozen=True` (see `tech.md`).
- One subfeature per future doc file in `docs/engine/<subfeature>.md`.
- Update this readme's surface table whenever a module gains its first non-stub code.

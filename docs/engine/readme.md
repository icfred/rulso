_Last edited: 2026-05-09 by RUL-11_

# engine

Python 3.12 package. `uv` managed. Pydantic v2 state, asyncio + `websockets` server, ISMCTS bots (M3).

## Surface

| Path | Status | Notes |
|---|---|---|
| `engine/pyproject.toml` | scaffolded | deps: `pydantic>=2`, `websockets`, `pytest`; dev: `ruff` |
| `engine/src/rulso/__init__.py` | stub | package marker |
| `engine/src/rulso/state.py` | live | frozen pydantic models + constants — see [state-models.md](state-models.md) |
| `engine/src/rulso/rules.py` | live | round flow phase machine — see [round-flow.md](round-flow.md) |
| `engine/src/rulso/grammar.py` | live | IF rule grammar (M1: SUBJECT/QUANT/NOUN) — see [if-resolver.md](if-resolver.md) |
| `engine/src/rulso/effects.py` | live | IF rule effect resolver (M1 stub: +1 chip) — see [if-resolver.md](if-resolver.md) |
| `engine/src/rulso/cli.py` | live | round-by-round CLI runner — see [cli.md](cli.md) |
| `engine/src/rulso/labels.py` | stub | label recomputation |
| `engine/src/rulso/persistence.py` | stub | WHEN / WHILE rule handling |
| `engine/src/rulso/server.py` | stub | websocket entry point |
| `engine/src/rulso/protocol.py` | stub | engine↔client message types |
| `engine/src/rulso/bots/__init__.py` | stub | bots package |
| `engine/src/rulso/bots/random.py` | live | random-legal-play bot — see [bots.md](bots.md) |
| `engine/tests/test_smoke.py` | live | asserts `import rulso` works |
| `engine/tests/test_state_models.py` | live | construction, frozen rejection, JSON round-trip |
| `engine/tests/test_round_flow.py` | live | round-flow phase transitions, dealer rotation, burn tick |
| `engine/tests/test_resolver.py` | live | grammar render, SUBJECT scope, HAS evaluation, effect stub |
| `engine/tests/test_random_bot.py` | live | random bot: slot compat, MUTE, dice, discard, 1000-seed invariant |
| `engine/tests/test_cli_smoke.py` | live | CLI runner: in-process smoke + round-cap exit code |

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

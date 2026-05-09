_Last edited: 2026-05-09 by RUL-8_

# engine

Python 3.12 package. `uv` managed. Pydantic v2 state, asyncio + `websockets` server, ISMCTS bots (M3).

## Surface

| Path | Status | Notes |
|---|---|---|
| `engine/pyproject.toml` | scaffolded | deps: `pydantic>=2`, `websockets`, `pytest`; dev: `ruff` |
| `engine/src/rulso/__init__.py` | stub | package marker |
| `engine/src/rulso/state.py` | live | `Config`, `GameState`, `Player`, `Card`, `RuleBuilder`, `Slot`, `Play` (frozen Pydantic v2) |
| `engine/src/rulso/rules.py` | live | round flow phase machine — see [round-flow.md](round-flow.md) |
| `engine/src/rulso/grammar.py` | stub | polymorphic card rendering |
| `engine/src/rulso/effects.py` | stub | effect application |
| `engine/src/rulso/labels.py` | live | M1 stub returning all labels unassigned |
| `engine/src/rulso/persistence.py` | stub | WHEN / WHILE rule handling |
| `engine/src/rulso/server.py` | stub | websocket entry point |
| `engine/src/rulso/protocol.py` | stub | engine↔client message types |
| `engine/src/rulso/bots/__init__.py` | stub | bots package |
| `engine/src/rulso/bots/random.py` | stub | random-legal-play bot |
| `engine/tests/test_smoke.py` | live | asserts `import rulso` works |
| `engine/tests/test_round_flow.py` | live | RUL-8 phase machine tests |

## Commands

Run from `engine/`:

```bash
uv sync                       # install
uv run pytest                 # tests
uv run ruff format            # format
uv run ruff check             # lint
uv run ruff format --check    # CI check
```

## Conventions

- Pydantic models default to `frozen=True` (see `tech.md`).
- One subfeature per future doc file in `docs/engine/<subfeature>.md`.
- Update this readme's surface table whenever a module gains its first non-stub code.

# engine

Python game engine for Rulso. Authoritative state, rule grammar, round flow, bots, websocket server.

## Setup

```bash
uv sync
```

## Test

```bash
uv run pytest
```

## Lint / format

```bash
uv run ruff format
uv run ruff check --fix
```

## Layout

See `tech.md` at the repo root for the canonical layout. Top-level package: `src/rulso/`.

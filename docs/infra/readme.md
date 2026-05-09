_Last edited: 2026-05-09 by RUL-13_

# infra

Repo-level tooling: git hooks, CI, formatting/lint contracts.

## Files

- `.githooks/commit-msg` — enforces `RUL-<id>: ` prefix on every commit.
- `.githooks/pre-commit` — runs Biome on staged `client/**/*.{ts,tsx,js,jsx,json}` and Ruff on staged `engine/**/*.py`. No-ops when no matching files are staged.

## Hook contract

- Hooks live in `.githooks/`. Activate with `git config core.hooksPath .githooks`.
- `pre-commit` is a safety net; agents run formatters themselves before committing (see `workflows/feature-work.md`).
- Ruff is invoked via `uv run --project engine ruff …` so it resolves from `engine/.venv` regardless of caller `PATH`. Requires `uv` on `PATH` and `uv sync` having been run in `engine/`.
- Biome resolves from `client/node_modules/.bin/biome` if present, else from `PATH`. Requires `npm install` in `client/`.
- Auto-fixed files are re-staged via `git add` before the commit proceeds.
- Bypass with `--no-verify` is forbidden; fix the underlying issue.

## Fresh-clone setup

1. `git config core.hooksPath .githooks`
2. `cd engine && uv sync` (when `engine/` exists)
3. `cd client && npm install` (when `client/` exists)

No manual `PATH` munging required.

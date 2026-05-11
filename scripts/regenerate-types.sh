#!/usr/bin/env bash
# Regenerate TypeScript types for the client from Pydantic models in
# engine/src/rulso/protocol.py (which transitively pulls state.py + legality.py
# action shapes per ADR-0008).
#
# Output: client/src/types/generated.ts (committed). Re-runs are byte-identical
# given identical sources — `pydantic-to-typescript` walks the module's
# BaseModel subclasses in insertion order and json-schema-to-typescript is
# deterministic on its JSON-schema input.
#
# Requires:
#   - uv on PATH (resolves the engine venv via `uv run --project engine ...`)
#   - client/ deps installed (`npm install` in client/) — supplies json2ts
#
# Invoke from the repo root:
#   ./scripts/regenerate-types.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="${ROOT}/engine"
JSON2TS="${ROOT}/client/node_modules/.bin/json2ts"
OUT="${ROOT}/client/src/types/generated.ts"

if [ ! -x "${JSON2TS}" ]; then
  echo "ERROR: ${JSON2TS} not found. Run 'npm install' in client/." >&2
  exit 1
fi

mkdir -p "$(dirname "${OUT}")"

uv run --project "${ENGINE}" pydantic2ts \
  --module rulso.protocol \
  --output "${OUT}" \
  --json2ts-cmd "${JSON2TS}"

echo "Wrote ${OUT}"

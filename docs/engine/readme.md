_Last edited: 2026-05-10 by RUL-23 (sweep batching RUL-54: rng determinism + workflow_lessons capture)_

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
| `engine/src/rulso/effects.py` | live | IF rule resolver + revealed-effect dispatcher (RUL-39 D), comparator-dice (RUL-42 G), op-modifier fold (RUL-43 H), polymorphic NOUN reads (RUL-44 I), ANYONE/EACH scoping (RUL-41 F) — see [if-resolver.md](if-resolver.md) |
| `engine/src/rulso/cli.py` | live | round-by-round CLI runner — see [cli.md](cli.md) |
| `engine/src/rulso/labels.py` | live | LEADER/WOUNDED (M1.5) + GENEROUS/CURSED (M2 RUL-33); MARKED/CHAINED stay empty pending status-apply ticket — see [labels.md](labels.md) |
| `engine/src/rulso/cards.py` | live | yaml loader + deck builder. Covers M1.5 + M2 vocabulary (CardType.EFFECT, GoalCard, scope_mode); reads `design/cards.yaml` |
| `engine/src/rulso/legality.py` | live | small helpers for legal-action selection (M1.5: `first_card_of_type`) — see [legality.md](legality.md) |
| `engine/src/rulso/persistence.py` | live | WHEN/WHILE rule lifecycle (RUL-32) wired through the Phase 3 effect dispatcher. JOKER PERSIST_WHEN/WHILE/ECHO promote rules via `add_persistent_rule` (RUL-45 J). See [persistence.md](persistence.md) |
| `engine/src/rulso/status.py` | live | per-token apply/clear/decay matrix (BURN / MUTE / BLESSED / MARKED / CHAINED) per RUL-30 spike; round-start tick replaces M1.5 `_apply_burn_tick` (RUL-40 E). `consume_blessed_or_else` wired into `effects._lose_chips` and the BURN tick (RUL-49); zero-magnitude losses do not consume BLESSED — see [status.md](status.md) |
| `engine/src/rulso/goals.py` | live | goal-claim engine (RUL-46 K): predicate registry, per-round claim + replenish for `single`, persist for `renewable`; ADR-0005 retypes `goal_deck` / `goal_discard` / `active_goals` to `GoalCard` |
| `engine/src/rulso/server.py` | stub | websocket entry point |
| `engine/src/rulso/protocol.py` | stub | engine↔client message types |
| `engine/src/rulso/bots/__init__.py` | stub | bots package |
| `engine/src/rulso/bots/random.py` | live | random-legal-play bot + public `enumerate_legal_actions` helper (RUL-52) — see [bots.md](bots.md) |
| `engine/src/rulso/bots/human.py` | live | TTY action driver for `--human-seat` (RUL-52); EOF→Pass; reuses `bots.random.enumerate_legal_actions` for the menu |
| `engine/tests/test_smoke.py` | live | asserts `import rulso` works |
| `engine/tests/test_state_models.py` | live | construction, frozen rejection, JSON round-trip |
| `engine/tests/test_round_flow.py` | live | round-flow phase transitions, dealer rotation, burn tick |
| `engine/tests/test_resolver.py` | live | grammar render, SUBJECT scope, HAS evaluation, effect stub |
| `engine/tests/test_random_bot.py` | live | random bot: slot compat, MUTE, dice, discard, 1000-seed invariant |
| `engine/tests/test_cli_smoke.py` | live | CLI runner: in-process smoke + round-cap exit code |
| `engine/tests/test_cli_multiseed.py` | live | 20-seed CLI sweep: cap-hit + event coverage — see [m1-smoke.md](m1-smoke.md) |
| `engine/tests/test_smoke_state_transitions.py` | live | end-to-end phase walk via hand-injected fixture — see [m1-smoke.md](m1-smoke.md) |
| `engine/tests/test_smoke_resolution_edges.py` | live | resolver corners: unassigned label + failed-rule invariants — see [m1-smoke.md](m1-smoke.md) |
| `engine/tests/test_labels.py` | live | label recomputation: leader/wounded ties, empty player set |
| `engine/tests/test_cards_loader.py` | live | yaml-deck loader: schema validation, card-type coverage, frozen contract |
| `engine/tests/test_persistence.py` | live | WHEN/WHILE fire logic + capacity/eviction; FIFO + depth-3 recursion cap |
| `engine/tests/test_m1_5_watchable.py` | live | M1.5 watchable smoke: 10-seed sweep asserts winners emerge — see [m1-5-smoke.md](m1-5-smoke.md) |
| `engine/tests/test_effects_dispatch.py` | live | revealed-effect dispatcher (RUL-39 D): GAIN_CHIPS / LOSE_CHIPS / GAIN_VP / LOSE_VP / DRAW / NOOP, registry hook, target_modifier parsing |
| `engine/tests/test_effects_nouns.py` | live | polymorphic NOUN reads (RUL-44 I): `CARDS / RULES / HITS / GIFTS / ROUNDS / BURN_TOKENS` |
| `engine/tests/test_effects_comparator.py` | live | OP-only comparator dice (RUL-42 G, ADR-0002): 1d6/2d6 player choice, LT/LE/GT/GE/EQ |
| `engine/tests/test_effects_op_modifiers.py` | live | operator MODIFIER fold (RUL-43 H, ADR-0004): BUT/AND/OR set-ops on SUBJECT, MORE_THAN/AT_LEAST flip QUANT strictness |
| `engine/tests/test_effects_scope.py` | live | ANYONE / EACH_PLAYER scoping (RUL-41 F, ADR-0003): existential subset-fire-once, iterative per-player loop |
| `engine/tests/test_status.py` | live | status apply/decay (RUL-40 E): per-token matrix, round-start BURN tick, MUTE clear, `consume_blessed_or_else` primitive — see [status.md](status.md) |
| `engine/tests/test_goals.py` | live | goal-claim engine (RUL-46 K): predicate registry, single-claim discard + replenish, renewable persist |
| `engine/tests/test_jokers.py` | live | JOKER attachment (RUL-45 J): PERSIST_WHEN/WHILE promote, ECHO conditional one-shot WHEN, DOUBLE effect doubling |
| `engine/tests/test_cli_human_seat.py` | live | CLI human-seat driver (RUL-52): valid-pick happy path, invalid/out-of-range loop, EOF→Pass fallback, all 4 seats parametrised, out-of-range CLI flag rejection |
| `engine/tests/test_determinism.py` | live | end-to-end determinism past effect-deck recycle (RUL-54): byte-identical stdout on 3 seeds across back-to-back `cli.run_game` invocations + guard that the recycle threshold is actually crossed |

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

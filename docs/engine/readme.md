_Last edited: 2026-05-12 by RUL-23 (post-RUL-75: dealer SUBJECT auto-fill removed; SUBJECT slot starts empty, players play SUBJECTs from hand. Sim verified: SUBJECT plays 0 → ~22k, zero-play 13 → 5)_

# engine

Python 3.12 package. `uv` managed. Pydantic v2 state, asyncio + `websockets` server, ISMCTS bots (M3).

## Surface

| Path | Status | Notes |
|---|---|---|
| `engine/pyproject.toml` | scaffolded | deps: `pydantic>=2`, `websockets`, `pytest`; dev: `ruff` |
| `engine/src/rulso/__init__.py` | stub | package marker |
| `engine/src/rulso/state.py` | live | frozen pydantic models + constants. RUL-70 added `GameState.labels: dict[str, tuple[str, ...]]` (default empty) — wire-published floating-label registry per ADR-0001. RUL-73 bumped `VP_TO_WIN` 3→5 (post-playtest tuning) — see [state-models.md](state-models.md) |
| `engine/src/rulso/rules.py` | live | round flow phase machine + SHOP phase wiring (RUL-51): `enter_round_start` step-5 SHOP check, `complete_shop`, `apply_shop_purchase`, `shop_purchase_order`. RUL-68 added `discard_redraw(state, player_id, card_ids, *, refill_rng)` + internal `_draw_n` helper. RUL-70 added `_with_recomputed_labels(state)` helper threaded through every public mutation entry-point. RUL-75 removed the dealer SUBJECT auto-fill from `enter_round_start` step 7 — `RuleBuilder` ships with all slots open; players play SUBJECTs into the empty slot during BUILD — see [round-flow.md](round-flow.md) |
| `engine/src/rulso/grammar.py` | live | IF rule grammar (M1: SUBJECT/QUANT/NOUN) — see [if-resolver.md](if-resolver.md) |
| `engine/src/rulso/effects.py` | live | IF rule resolver + revealed-effect dispatcher (RUL-39 D), comparator-dice (RUL-42 G), op-modifier fold (RUL-43 H), polymorphic NOUN reads (RUL-44 I), ANYONE/EACH scoping (RUL-41 F), MARKED narrows EACH_PLAYER (RUL-60 M2.5) — see [if-resolver.md](if-resolver.md) |
| `engine/src/rulso/cli.py` | live | round-by-round CLI runner; RUL-68 retired the `discard_redraw_unimplemented` placeholder — `_drive_build_turn`'s `DiscardRedraw` branch now dispatches through `rules.discard_redraw` and emits `event=turn action=discard_redraw cost=…`. RUL-71 added `--ws` / `--ws-host` / `--ws-port` flags — when `--ws` is set, dispatches to `cli_ws.main_ws`. RUL-74 added `simulate` subcommand — dispatches to `simulate.run_cli` for bot-vs-bot quantitative analysis — see [cli.md](cli.md) |
| `engine/src/rulso/simulate.py` | live | bot-vs-bot batch sim harness (RUL-74): observer-wrapper pattern (no engine state mutation; same shape as `test_m2_watchable.py` test-side instrumentation per RUL-35). Wraps effects + status + goals + cards loader. CLI entry `rulso simulate --games N --summary [--analyse PATH]`; JSON dump + ≤50-line terminal summary; auto-flags zero-occurrence cards/effects/goals + winner-skew + cap-hit anomalies. Throughput ~130 games/sec (`cards.load_*` cached for the run's duration; engine yaml re-parse was 87% hot path) — see [simulate.md](simulate.md) |
| `engine/tests/test_simulate.py` | live | sim harness coverage (RUL-74): 17 tests covering byte-identical determinism (two 50-game runs), per-category metric coverage, 5 synthetic anomaly-flag triggers, engine-restoration invariant, summary length |
| `engine/src/rulso/labels.py` | live | LEADER/WOUNDED (M1.5) + GENEROUS/CURSED (M2 RUL-33); MARKED/CHAINED stay empty (status tokens, not labels). RUL-70 added `to_wire(labels_map) -> dict[str, tuple[str, ...]]` — converts internal `frozenset` shape to id-sorted-tuple wire shape (deterministic JSON) — see [labels.md](labels.md) |
| `engine/src/rulso/cards.py` | live | yaml loader + deck builder. Covers M1.5 + M2 vocabulary (CardType.EFFECT, GoalCard, scope_mode) plus SHOP offers (RUL-51 `_ShopEntry`, `load_shop_offers`); reads `design/cards.yaml` |
| `engine/src/rulso/legality.py` | live | canonical engine action surface (RUL-65): action shapes (`PlayCard` / `DiscardRedraw` / `Pass` / `PlayJoker` / `Action` discriminated union), `enumerate_legal_actions`, internal `_enumerate_plays` / `_enumerate_discards` (co-located to avoid `bots.random ↔ legality` cycle); plus M1.5 predicates `first_card_of_type` and RUL-45 `can_attach_joker` — see [legality.md](legality.md) |
| `engine/src/rulso/persistence.py` | live | WHEN/WHILE rule lifecycle (RUL-32) wired through the Phase 3 effect dispatcher. JOKER PERSIST_WHEN/WHILE/ECHO promote rules via `add_persistent_rule` (RUL-45 J). See [persistence.md](persistence.md) |
| `engine/src/rulso/status.py` | live | per-token apply/clear/decay matrix (BURN / MUTE / BLESSED / MARKED / CHAINED) per RUL-30 spike; round-start tick replaces M1.5 `_apply_burn_tick` (RUL-40 E). `consume_blessed_or_else` wired into `effects._lose_chips` and the BURN tick (RUL-49); zero-magnitude losses do not consume BLESSED — see [status.md](status.md) |
| `engine/src/rulso/goals.py` | live | goal-claim engine (RUL-46 K): predicate registry, per-round claim + replenish for `single`, persist for `renewable`; ADR-0005 retypes `goal_deck` / `goal_discard` / `active_goals` to `GoalCard` |
| `engine/src/rulso/server.py` | live | asyncio + `websockets` single-game loop (RUL-64, ADR-0008): `async def run_server(*, host, port, seed, human_seat)` + sync `def main()` (`rulso-server` console script); per-connection reader/game-loop coroutines stay in lockstep via `await asyncio.sleep(0)` after every queue-put / broadcast; preserves disjoint-rng pattern (`seed / seed^0x5EED / seed^0xD1CE / seed^0xEFFC`); rejection codes `PROTOCOL_INVALID` / `NOT_YOUR_TURN` / `ILLEGAL_ACTION`; terminal `StateBroadcast` carries `winner` + `phase=END`. RUL-67 added `_build_state_broadcast(state, human_seat)` helper threaded through every emit path — populates `legal_actions` only when `phase=BUILD AND active_seat==human_seat`. RUL-68 routes `DiscardRedraw` envelopes through `rules.discard_redraw` (refill_rng threaded via `_take_human_turn` / `_take_bot_turn`) — see [server.md](server.md) |
| `engine/src/rulso/protocol.py` | live | WS envelopes per ADR-0008 (RUL-63): `Hello` / `StateBroadcast` / `ErrorEnvelope` (server→client, `type` discriminator) + `ActionSubmit` (client→server, wraps `PlayCard | PlayJoker | DiscardRedraw` imported from `legality` — RUL-65 promoted the action surface, `kind` discriminator). `PROTOCOL_VERSION=1`; `Pass` excluded client-side (server picks on empty enumeration). RUL-67 added additive `StateBroadcast.legal_actions: tuple[ClientAction, ...] \| None` (default None; populated server-side on the human seat's BUILD turns; ADR-0008 §Consequences pre-authorises additive variants — no version bump) — see [protocol.md](protocol.md) |
| `engine/src/rulso/bots/__init__.py` | stub | bots package |
| `engine/src/rulso/bots/random.py` | live | random-legal-play bot: `choose_action` (PLAY_BIAS-weighted picker), `select_purchase` SHOP picker (RUL-51), `_find_player`. Action shapes + `enumerate_legal_actions` moved to `legality` post-RUL-65; `PLAY_BIAS = 0.75` post-RUL-55 — see [bots.md](bots.md) |
| `engine/src/rulso/bots/human.py` | live | TTY action driver for `--human-seat` (RUL-52); EOF→Pass; reuses `legality.enumerate_legal_actions` for the menu |
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
| `engine/tests/test_effects_marked_scope.py` | live | MARKED narrows EACH_PLAYER scope (RUL-60, M2.5): ≥1 MARKED → narrow; 0 MARKED → fall back to all; ANYONE / singular SUBJECTs unaffected — see [status.md](status.md) |
| `engine/tests/test_status.py` | live | status apply/decay (RUL-40 E): per-token matrix, round-start BURN tick, MUTE clear, `consume_blessed_or_else` primitive — see [status.md](status.md) |
| `engine/tests/test_goals.py` | live | goal-claim engine (RUL-46 K): predicate registry, single-claim discard + replenish, renewable persist |
| `engine/tests/test_jokers.py` | live | JOKER attachment (RUL-45 J): PERSIST_WHEN/WHILE promote, ECHO conditional one-shot WHEN, DOUBLE effect doubling |
| `engine/tests/test_cli_human_seat.py` | live | CLI human-seat driver (RUL-52): valid-pick happy path, invalid/out-of-range loop, EOF→Pass fallback, all 4 seats parametrised, out-of-range CLI flag rejection |
| `engine/tests/test_determinism.py` | live | end-to-end determinism past effect-deck recycle (RUL-54): byte-identical stdout on 3 seeds across back-to-back `cli.run_game` invocations + guard that the recycle threshold is actually crossed |
| `engine/tests/test_m2_watchable.py` | live | M2 watchable smoke (RUL-35 Wave 3 gate; floor migrated 5→7 via RUL-55 PLAY_BIAS tune, then 7→6 via RUL-61 full-vocabulary baseline; RUL-56 SHOP tuning held the 6/10 floor): 10-seed × rounds=200 sweep asserts winner floor, full M2 lifecycle coverage (WHEN/WHILE/goal/effect) via test-side wrapper instrumentation — see [m2-smoke.md](m2-smoke.md) |
| `engine/tests/test_shop.py` | live | SHOP phase coverage (RUL-51 substrate + RUL-56 M2.5 content): cadence (every `SHOP_INTERVAL=3` rounds), buy order (VP asc → chips asc → seat asc), `apply_shop_purchase` / `complete_shop` / pool-recycle / starter-pool loader / e2e CLI `event=shop_*` emission |
| `engine/tests/test_protocol.py` | live | WS envelope round-trip + dispatch + validation (RUL-63, ADR-0008): server/client `TypeAdapter` round-trip on every variant; `start_game(0)` full-state broadcast round-trip; discriminator dispatch on `type` (outer) and `kind` (inner action); rejection paths for unknown types, missing fields, `Pass` from client, invalid `ErrorCode`, dice out of range |
| `engine/tests/test_server.py` | live | WS server end-to-end (RUL-64): handshake (`Hello` seat + version), bot-only seat progression, `ActionSubmit` round-trip, three rejection codes (`PROTOCOL_INVALID` / `NOT_YOUR_TURN` / `ILLEGAL_ACTION`), terminal `StateBroadcast` on game end. RUL-67 extended: `legal_actions` populated on the human's BUILD broadcasts; None on bot turns + non-BUILD + terminal. RUL-68 added `test_discard_redraw_submission_decrements_chips_and_redraws` (chip drop + hand-size preservation post-discard). Uses `pytest-asyncio` `auto` mode (configured in `engine/pyproject.toml`) |
| `engine/tests/test_discard.py` | live | `rules.discard_redraw` substrate coverage (RUL-68): k=1/2/3 chip cost, replacement ordering from deck tail, deck-empty recycle determinism, `refill_rng=None` raises on the recycle path, five ValueErrors (non-BUILD, out-of-turn, unknown card, insufficient chips, empty `card_ids`) |
| `engine/src/rulso/cli_ws.py` | live | WS-driven CLI client (RUL-71): connects to `rulso-server` via `--ws`; thin shim — receives `Hello`, prints `StateBroadcast` events to stdout; on broadcasts carrying `legal_actions`, prompts the user via `bots/human._describe_action`; sends `ActionSubmit` envelopes; renders terminal `StateBroadcast` (`winner`, `phase=END`) and exits cleanly. No engine state mutation; consumes the same envelopes the browser does |
| `engine/tests/test_cli_ws.py` | live | WS-driven CLI client end-to-end (RUL-71): connection + handshake, bot-only-progress observer, action submission round-trip via TextIO injection (same pattern as `test_cli_human_seat.py`), end-to-end completion to `phase=END`. Uses `pytest-asyncio` `auto` mode |

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

(Client side: `npm install` in `client/`; the hook calls `client/node_modules/.bin/biome` directly from the repo root. `biome.json` lives at the **repo root** — Biome walks ancestors from cwd, so the same config resolves whether the hook (cwd=repo root) or `npm run lint` (cwd=client/) invokes it.)

## Conventions

- Pydantic models default to `frozen=True` (see `tech.md`).
- One subfeature per future doc file in `docs/engine/<subfeature>.md`.
- Update this readme's surface table whenever a module gains its first non-stub code.

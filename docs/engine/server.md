_Last edited: 2026-05-11 by RUL-64_

# server.py — single-game WebSocket loop

Asyncio WebSocket server hosting one Rulso game per process. Consumes the
protocol substrate locked by ADR-0008. Engine is authoritative — every
client submission is re-validated server-side before being applied.

## Module: `rulso.server`

### Console script

`rulso-server` (declared in `engine/pyproject.toml`) → `rulso.server:main`.

```
uv run --project engine rulso-server --host 127.0.0.1 --port 8765 \
    --seed 0 --human-seat 0
```

| Flag | Default | Notes |
|---|---|---|
| `--host` | `127.0.0.1` | Bind interface |
| `--port` | `8765` | Bind port |
| `--seed` | `0` | RNG seed; threads into `rng / refill_rng / dice_rng / effect_rng` per the disjoint-stream pattern (`seed`, `seed^0x5EED`, `seed^0xD1CE`, `seed^0xEFFC`) |
| `--human-seat` | `0` | Seat index the connecting client drives; other seats stay bot-driven via `bots.random.choose_action` |

### Public surface

| Symbol | Shape | Purpose |
|---|---|---|
| `run_server(*, host, port, seed, human_seat, on_listening=None)` | `async def -> None` | Serve one game; return when it ends. `on_listening` is a test hook invoked once with the bound port |
| `main(argv=None)` | `def -> int` | CLI entry — parses args and runs `asyncio.run(run_server(...))` |
| `classify_submission(state, human_seat)` | `def -> ErrorEnvelope \| None` | Pure helper: returns `NOT_YOUR_TURN` envelope when it is not the human's turn (no `BUILD` phase, no human active), else `None`. The reader's only check; legality (`ILLEGAL_ACTION`) lives in the game loop |
| `PROTOCOL_VERSION` | re-exported from `rulso.protocol` | Pinned in the `Hello` greeting |

### Concurrency model

| Task | Role |
|---|---|
| `_handler` | One per connection. Rejects a second concurrent connection with WebSocket close code `1013` (service overloaded) |
| `_serve_game` | Sends `Hello`, spawns `_drain_client`, runs `_run_game_loop`, cleans up on return / disconnect |
| `_drain_client` | Reads envelopes; replies with `ErrorEnvelope` for `PROTOCOL_INVALID` (parse failure) and `NOT_YOUR_TURN` (turn ownership). Queues legal-shape submissions for the game loop. Yields after every queue.put so the game loop can apply the action before the reader observes the next submission |
| `_run_game_loop` | Drives `start_game` → `advance_phase` / bot turns / shop. Broadcasts `StateBroadcast` after every transition. Awaits `action_queue` on the human's BUILD turn; auto-`pass_turn` when the human's legal set is empty. Yields once after each broadcast so the reader can drain pending submissions against the latest state |

### Broadcast cadence

Per ADR-0008, `StateBroadcast` fires on every `GameState` mutation: the initial
`start_game` state, every `advance_phase` call, every `play_card` / `play_joker` /
`pass_turn`, and every `apply_shop_purchase`.

The terminal broadcast carries `state.phase == END` and `state.winner != None`;
no separate `end_of_game` envelope (ADR-0008).

### Rejection codes

| Code | Source | Condition |
|---|---|---|
| `PROTOCOL_INVALID` | `_drain_client` | `TypeAdapter(ClientEnvelope).validate_json` raises `ValidationError` (unknown `type`, unknown action `kind`, malformed payload, …) |
| `NOT_YOUR_TURN` | `_drain_client` via `classify_submission` | Submission arrives while `state.phase != BUILD` or `state.active_seat != human_seat` |
| `ILLEGAL_ACTION` | `_run_game_loop._take_human_turn` | Submission is structurally valid and on the human's turn, but is not in `enumerate_legal_actions(state, player)` |

The server does not disconnect on a rejection — clients are free to retry.

### SHOP handling

All four seats (including the human's) are bot-driven in SHOP via
`bots.random.select_purchase`. SHOP is engine-internal per ADR-0008; clients do
not submit SHOP envelopes in MVP. `_drive_shop` walks
`shop_purchase_order` in canonical order (VP asc, chips asc, seat asc) and
broadcasts after every `apply_shop_purchase`.

### DiscardRedraw stub

`DiscardRedraw` submissions are accepted as structurally valid and treated as
`pass_turn`, matching `cli._drive_build_turn`'s placeholder until the full
discard pipeline lands in `rules.py`.

### Tests

`tests/test_server.py` — 11 tests:

- Handshake: `Hello` emitted on connect, pins seat + `PROTOCOL_VERSION`.
- Bot-only progression: server drives non-human seats without client input.
- Action round-trip: client submits a legal `PlayCard` → server applies + broadcasts next state with the human's hand shrunk.
- Rejection codes:
  - 4 unit tests of `classify_submission` covering pre-game state, non-BUILD phase, wrong seat in BUILD, and the no-error happy path.
  - Integration: `NOT_YOUR_TURN` (back-to-back legal+bogus submission; reader's yield lets the second land while a bot seat is active).
  - Integration: `ILLEGAL_ACTION` (`PlayCard` with a `card_id` not in hand, submitted on the human's turn).
  - Integration: `PROTOCOL_INVALID` (`{"type":"resign"}`); server stays open after the error.
- End-to-end: drives the client automatically through seed-0 (post-RUL-55 winning baseline) to a terminal `StateBroadcast` with `phase == END` and `winner` set.

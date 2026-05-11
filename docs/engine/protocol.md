_Last edited: 2026-05-11 by RUL-63_

# protocol.py — WebSocket envelope substrate

ADR-0008 locks the shape. JSON over websocket; snake_case keys; engine authoritative.

## Module: `rulso.protocol`

### Constants

`PROTOCOL_VERSION = 1`. Additive variants (new enum values, new union members) do not bump.

### Enums

| Enum | Values |
|---|---|
| `ErrorCode` (`StrEnum`) | `protocol_invalid`, `not_your_turn`, `illegal_action`, `unknown_action`, `internal_error` |

### Envelopes

All `frozen=True`. Server→client discriminated on `type`; client→server discriminated on `type`; inner action discriminated on `kind`.

| Envelope | Direction | Fields |
|---|---|---|
| `Hello` | server→client | `type="hello"`, `seat: int (≥0)`, `protocol_version: int` |
| `StateBroadcast` | server→client | `type="state"`, `state: GameState` |
| `ErrorEnvelope` | server→client | `type="error"`, `code: ErrorCode`, `message: str` |
| `ActionSubmit` | client→server | `type="action_submit"`, `action: ClientAction` |

### Unions

| Symbol | Members | Discriminator |
|---|---|---|
| `ServerEnvelope` | `Hello \| StateBroadcast \| ErrorEnvelope` | `type` |
| `ClientEnvelope` | `ActionSubmit` | `type` |
| `ClientAction` | `PlayCard \| PlayJoker \| DiscardRedraw` (imported from `bots.random`) | `kind` |

`Pass` is intentionally **not** in `ClientAction` — server picks it automatically when `enumerate_legal_actions` returns empty.

### Parse

```python
from pydantic import TypeAdapter
from rulso.protocol import ServerEnvelope, ClientEnvelope

server_adapter = TypeAdapter(ServerEnvelope)
client_adapter = TypeAdapter(ClientEnvelope)

msg = server_adapter.validate_json(raw_bytes)
```

### Server authority

The structured action payload in `ActionSubmit` is a hint, not a trusted claim. The server re-enumerates legal actions via `bots.random.enumerate_legal_actions(state, player)` and validates structural equality before applying. Mismatches return `ErrorEnvelope{code: ILLEGAL_ACTION}`; clients receive the unchanged state on the next broadcast.

### MVP cadence

`StateBroadcast` fires on every engine transition that mutates `GameState` (phase change, action applied, status tick, shop resolution, dice roll). Cadence is not part of the locked contract — only the envelope shape is — so a future tuning ticket can introduce coalescing or diffs without bumping `PROTOCOL_VERSION`.

### Tests

`tests/test_protocol.py` — 20 tests pinning round-trip on every variant, discriminator dispatch on both unions, and the validation-failure surface the server emits `protocol_invalid` on (unknown `type`, missing `type`, unknown action `kind`, malformed action payload, invalid `ErrorCode`, negative `seat`, client-side `Pass` submission).

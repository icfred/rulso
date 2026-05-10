_Last edited: 2026-05-10 by RUL-49_

# status.py — status-token primitives

Centralised apply / clear / decay surface for the 5 status tokens
(`burn`, `mute`, `blessed`, `marked`, `chained`). Replaces the M1.5
`rules._apply_burn_tick` helper per the RUL-30 spike
(`design/status-tokens.md`).

## Module: `rulso.status`

### Public API

| Function | Returns | Purpose |
|---|---|---|
| `apply_burn(player, magnitude=1)` | `Player` | Add BURN tokens (counter; stacks). |
| `apply_mute(player)` | `Player` | Set MUTE flag (idempotent toggle). |
| `apply_blessed(player)` | `Player` | Set BLESSED flag (idempotent toggle). |
| `apply_marked(player)` | `Player` | Set MARKED flag (idempotent toggle). |
| `apply_chained(player)` | `Player` | Set CHAINED flag (idempotent toggle). |
| `clear_burn(player)` | `Player` | Zero BURN counter. |
| `clear_chained(player)` | `Player` | Reset CHAINED flag. |
| `tick_round_start(player)` | `Player` | `round_start` step 2: drain `BURN_TICK × burn` chips, clear MUTE. |
| `tick_resolve_end(player)` | `Player` | `resolve` step 10: clear MARKED. |
| `consume_blessed_or_else(player, loss)` | `Player` | If BLESSED, cancel `loss` and clear; else apply chip loss. |

### Wiring

| Site | Call | Notes |
|---|---|---|
| `rules.enter_round_start` step 2 | `status.tick_round_start(p)` for each player | Replaced M1.5 `_apply_burn_tick` (file removed). BURN drain routes through `consume_blessed_or_else` (RUL-49). |
| `rules.enter_resolve` step 10 | `status.tick_resolve_end(p)` for each player | Net-new in M2; co-located with discard collection. |
| `effects._lose_chips` (`LOSE_CHIPS` handler) | `status.consume_blessed_or_else(p, magnitude)` per target | RUL-49: per-target so each BLESSED is consumed independently; `magnitude <= 0` short-circuits (no token consumed on zero-loss). |
| `effects.dispatch_effect` registry | 7 registrations at module load | `effects.py` imports `status` at module-bottom; `status.py` imports `effects` at top — registrations fire eagerly without circular bootstrap (`register_effect_kind` is fully defined when `status.py` runs). |

### Effect-kind registrations (M2 starter — `design/status-tokens.md` §"M2 starter subset")

| Effect kind | Card example | Handler primitive |
|---|---|---|
| `APPLY_BURN` | `eff.burn.apply.1` | `apply_burn` |
| `CLEAR_BURN` | `eff.burn.clear.1` | `clear_burn` |
| `APPLY_MUTE` | `eff.mute.apply` | `apply_mute` |
| `APPLY_BLESSED` | `eff.blessed.apply` | `apply_blessed` |
| `APPLY_MARKED` | `eff.marked.apply` | `apply_marked` |
| `APPLY_CHAINED` | `eff.chained.apply` | `apply_chained` |
| `CLEAR_CHAINED` | `eff.chained.clear` | `clear_chained` |

Unregistered kinds (`CLEAR_MUTE`, `CLEAR_BLESSED`, `CLEAR_MARKED`) raise
`NotImplementedError` from the dispatcher — there are no clearing cards for
those tokens in M2 (MUTE/BLESSED/MARKED clear via natural decay or on-use).

### Semantics

* **BURN**: counter; `BURN_TICK = 5` chips per token at `round_start` step 2.
  Tokens persist across the tick — only the chip drain ticks. Cleared by
  `CLEAR_BURN` cards (one-shot, sets `burn = 0`).
* **MUTE**: applied this round, blocks MODIFIER plays *next* round. Clears at
  `round_start` step 2 of the round after the applied round (one-round
  lifetime).
* **BLESSED**: cancels the next chip-loss the bearer suffers — including the
  BURN tick at `round_start` step 2 (RUL-49, resolves
  `design/status-tokens.md` flag 1). Decay order at the tick: BLESSED clears
  first, BURN tokens persist, MUTE clears regardless. Zero-magnitude losses
  do not consume the token.
* **MARKED**: one-round lifetime; clears at `resolve` step 10. Read by
  `EACH PLAYER` rule scoping (RUL-30 matrix; RUL-25 ANYONE/EACH ADR).
* **CHAINED**: cleared via `CLEAR_CHAINED` cards only; no natural decay.
  Blocks goal-claim eligibility (read site lives in `goals.check_claims`;
  enforcement lands when CHAINED-aware claims ship).

### Out of scope for RUL-40

* CHAINED gate inside `goals.check_claims` (gate exists conceptually; the
  consuming logic lands with the goal-claim integration ticket).
* Multi-target appliers beyond MARKED (single-target is the M2 starter).
* New status tokens (substrate change — would require ADR + `state.py`).

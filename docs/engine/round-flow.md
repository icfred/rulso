_Last edited: 2026-05-09 by RUL-8_

# rules.py — round flow phase machine

Pure-function transitions over `GameState`. Implements `design/state.md` round
flow for M1. Shop, persistent-rule WHILE tick, joker attachment, and effect
application are stubbed.

## Module: `rulso.rules`

### Public API

| Function | Returns | Purpose |
|---|---|---|
| `start_game(seed=0)` | `GameState` | Init 4 players, dealer=0, phase=ROUND_START, round=0 |
| `advance_phase(state)` | `GameState` | Advance one logical step from current phase |
| `enter_round_start(state)` | `GameState` | Run round_start steps 1-8 atomically; ends in BUILD |
| `enter_build(state)` | `GameState` | Set phase=BUILD, active_seat=(dealer+1)%PLAYER_COUNT |
| `enter_resolve(state)` | `GameState` | Run resolve steps; ends in ROUND_START or END |
| `play_card(state, card, slot_name)` | `GameState` | Active player fills a slot; advances build turn |
| `pass_turn(state)` | `GameState` | Active player passes; advances build turn |

### `advance_phase` dispatch

| Current `state.phase` | Behaviour |
|---|---|
| `LOBBY` | calls `enter_round_start` → ends in `BUILD` |
| `ROUND_START` | calls `enter_round_start` → ends in `BUILD` |
| `BUILD` (mid-revolution) | forced-pass tick; `active_seat` advances |
| `BUILD` (revolution complete, all slots filled) | → `RESOLVE` |
| `BUILD` (revolution complete, slot unfilled) | rule fails: dealer rotates → `ROUND_START` |
| `RESOLVE` | calls `enter_resolve` → `ROUND_START` (or `END` on win) |
| `SHOP` | raises `NotImplementedError("M2: shop phase")` |
| `END` | returns input unchanged |

### Build phase semantics

- `active_seat` starts at `(dealer + 1) % PLAYER_COUNT`.
- One revolution = exactly `PLAYER_COUNT` turns (`design/state.md:111`).
- Dealer plays template + slot 0 in `round_start` AND takes the final build turn.
- Each `play_card` / `pass_turn` increments `build_turns_taken` and rotates `active_seat`.
- After `PLAYER_COUNT` turns: all slots filled → `RESOLVE`; any slot empty → fail-and-rotate.

### M1 stubs

- **Shop check** (`round_start` step 5): bypassed. `SHOP_INTERVAL` trigger ignored so M1 plays without entering shop. `enter_shop` not implemented.
- **WHILE-rule tick** (`round_start` step 4): raises `NotImplementedError("M2: persistent rule WHILE tick")` if `state.persistent_rules` is non-empty. M1 never adds persistent rules.
- **JOKER attachment** (`resolve` step 5): raises `NotImplementedError("M2: joker attachment")` if `active_rule.joker_attached` is set. M1 never attaches.
- **Effect application** (`resolve` steps 1-7): no-op; rule render, scope, and effects deferred.
- **Hand refill** (`build` step 4, `resolve` step 12): no-op; deck is empty in M1.
- **Label recompute** (`round_start` step 3, `resolve` step 8): delegated to `labels.py` stub returning unassigned.
- **Goal claim** (`resolve` step 7): no-op; goals deferred.
- **Win check** (`resolve` step 9): scans `vp >= VP_TO_WIN`; transitions to `END` if found.
- **Card legality / hand membership** in `play_card`: not checked. Only slot type-match enforced.

### M1 stub rule shape

`_M1_RULE_SLOT_DEFS` defines a 4-slot rule:

| Index | Slot name | Type |
|---|---|---|
| 0 | `subject` | `SUBJECT` (filled by dealer in round_start) |
| 1 | `noun` | `NOUN` |
| 2 | `modifier` | `MODIFIER` |
| 3 | `noun_2` | `NOUN` |

`_M1_DEALER_FRAGMENT` (SUBJECT card "ANYONE") and `_M1_EFFECT_CARD` are
synthetic placeholders until `cards.yaml` lands.

### State.py additions (RUL-8)

Additive only:

- `GameState.build_turns_taken: int = 0` — turn counter inside BUILD.
- `GameState.revealed_effect: Card | None = None` — face-up effect card during a round.

### Tests

`engine/tests/test_round_flow.py`:

- `test_start_game_initializes_round_start_at_round_zero`
- `test_advance_from_round_start_enters_build_with_dealer_first_slot_filled`
- `test_play_card_fills_slot_and_advances_active_seat`
- `test_play_card_rejects_type_mismatch` / `_filled_slot` / `_unknown_slot` / `_outside_build`
- `test_build_with_all_slots_filled_transitions_to_resolve`
- `test_build_with_unfilled_slot_fails_back_to_round_start`
- `test_resolve_transitions_to_round_start_and_rotates_dealer`
- `test_advance_phase_from_resolve_invokes_enter_resolve`
- `test_dealer_rotates_across_four_rounds_via_failed_rules`
- `test_advance_from_lobby_enters_round_start`
- `test_advance_from_shop_raises_not_implemented`
- `test_advance_from_end_is_idempotent`
- `test_burn_tick_drains_chips_and_clears_mute_at_round_start`

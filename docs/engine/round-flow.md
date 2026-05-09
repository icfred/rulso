_Last edited: 2026-05-09 by RUL-8_

# round-flow

Phase machine for `lobby -> round_start -> build -> resolve -> round_start` (or `end`).
Pure functions over frozen `GameState`. M1 implements the IF path; shop and
persistent-rule paths raise `NotImplementedError("M2")`.

## Public API — `rulso.rules`

| Function | Signature | Notes |
|---|---|---|
| `start_game` | `(seed: int = 0, config: Config | None = None) -> GameState` | Returns `phase="round_start"`, `round_number=0`, dealer seat 0 |
| `advance_phase` | `(state) -> GameState` | One phase boundary per call |
| `enter_round_start` | `(state) -> GameState` | Runs steps 1-7 then `enter_build` |
| `enter_build` | `(state) -> GameState` | `active_seat = (dealer + 1) % player_count`; resets `build_turns_taken` |
| `enter_resolve` | `(state) -> GameState` | M1 stub: discards fragments, win-check, rotates dealer, refills hands |
| `play_card` | `(state, card: Card, slot_name: str) -> GameState` | Build phase only; M1 has no legality check |
| `force_pass` | `(state) -> GameState` | Build phase only |

## Phase transitions

```
lobby ──start_game──► round_start
round_start ──advance_phase──► build           (auto via enter_build)
build       ──advance_phase──► resolve         (all required slots filled)
build       ──advance_phase──► round_start     (any required slot empty: fail+rotate)
resolve     ──advance_phase──► round_start     (rotate dealer, refill hands)
resolve     ──advance_phase──► end             (winner_seat at VP_TO_WIN)
shop        ──advance_phase──► NotImplementedError("M2")
```

`advance_phase(state)` from `build` raises `ValueError` until
`build_turns_taken == player_count` (one full revolution from `dealer + 1`).

## Build turn accounting

* `active_seat` rotates by 1 on every `play_card` / `force_pass`.
* `build_turns_taken` increments on every `play_card` / `force_pass`.
* Build completes after `player_count` turns (one full revolution back to the seat that started).
* Dealer's first-slot fragment is played during `enter_round_start`, separately from the build revolution.

## M1 placeholder rule

`_make_m1_rule(round_number, dealer_seat)` synthesizes a 3-slot `RuleBuilder`:
* `template`: `Card(type="CONDITION", rule_kind="IF")`
* `slots`: `subject` (pre-filled by dealer), `noun`, `modifier`
* `plays`: `[Play(seat=dealer_seat, card=<subject>, slot_name="subject")]`

Replaced in M2 once condition cards are real and dealer's hand drives the
template choice.

## Shop guard

`enter_round_start` raises `NotImplementedError("M2 — shop phase")` when
`new_round % config.shop_interval == 0`. M1 callers either keep play below the
shop cycle or set `Config(shop_interval=10**9)`. Tests use the latter for
multi-round flow.

## Resolve M1 cuts

The full `resolve` spec (effect application, JOKER persistence, persistent-rule
trigger queue, goal claims) is deferred. M1 `enter_resolve`:
1. Discards every filled slot card.
2. Win-checks `vp >= VP_TO_WIN` -> `phase="end"` if any.
3. Rotates dealer.
4. Refills hands to `hand_size` (deck reshuffles by appending discard when empty).
5. Returns to `phase="round_start"`.

## Tests

`engine/tests/test_round_flow.py` covers DoD scenarios plus error guards:
game-start, round_start->build, all-slots-filled->resolve,
unfilled-slot->fail, 4-round dealer rotation, shop guard, winner short-circuit.

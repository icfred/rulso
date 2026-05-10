_Last edited: 2026-05-10 by RUL-47_

# rules.py — round flow phase machine

Pure-function transitions over `GameState`. Implements `design/state.md` round
flow. Shop is stubbed; persistent-rule WHILE tick is wired (no-op when no
persistent rules); JOKER attachment, effect-card draw + dispatch are wired.

## Module: `rulso.rules`

### Public API

| Function | Returns | Purpose |
|---|---|---|
| `start_game(seed=0)` | `GameState` | Init 4 players, deal `HAND_SIZE` per seat from a seeded shuffled deck; `phase=ROUND_START`, `round=0`, `dealer=0` |
| `advance_phase(state, *, rng=None)` | `GameState` | Advance one logical step from current phase; forwards `rng` to both `enter_round_start` and `enter_resolve` |
| `enter_round_start(state, *, rng=None)` | `GameState` | Run round_start steps 1-8 atomically; ends in BUILD or back to ROUND_START on dealer-no-seed; `rng` recycles `effect_discard` when step-6 draw finds an empty deck |
| `enter_build(state)` | `GameState` | Set phase=BUILD, active_seat=(dealer+1)%PLAYER_COUNT |
| `enter_resolve(state, *, rng=None)` | `GameState` | Run resolve steps incl. refill (step 12); ends in ROUND_START or END |
| `play_card(state, card, slot_name)` | `GameState` | Active player fills a slot; removes card from hand; advances build turn |
| `pass_turn(state)` | `GameState` | Active player passes; advances build turn |

### `advance_phase` dispatch

| Current `state.phase` | Behaviour |
|---|---|
| `LOBBY` | calls `enter_round_start` → ends in `BUILD` (or back to `ROUND_START` if dealer holds no seed-card) |
| `ROUND_START` | calls `enter_round_start` → ends in `BUILD` (or back to `ROUND_START` if dealer holds no seed-card) |
| `BUILD` (mid-revolution) | forced-pass tick; `active_seat` advances |
| `BUILD` (revolution complete, all slots filled) | → `RESOLVE` |
| `BUILD` (revolution complete, slot unfilled) | rule fails: dealer rotates → `ROUND_START` |
| `RESOLVE` | calls `enter_resolve(state, rng=...)` → `ROUND_START` (or `END` on win) |
| `SHOP` | raises `NotImplementedError("M2: shop phase")` |
| `END` | returns input unchanged |

### Build phase semantics

- `active_seat` starts at `(dealer + 1) % PLAYER_COUNT`.
- One revolution = exactly `PLAYER_COUNT` turns (`design/state.md:111`).
- Dealer plays template + slot 0 in `round_start` AND takes the final build turn.
- Each `play_card` / `pass_turn` increments `build_turns_taken` and rotates `active_seat`.
- After `PLAYER_COUNT` turns: all slots filled → `RESOLVE`; any slot empty → fail-and-rotate.
- `play_card` removes the played card from the active player's hand by id+identity; raises if not present.

### RNG contract (RUL-18, extended by RUL-47)

| Function | RNG usage |
|---|---|
| `start_game(seed)` | `random.Random(seed)` shuffles main deck before dealing; rng consumed and discarded |
| `enter_round_start(state, *, rng)` | Step 6 draw: shuffles `state.effect_discard` back into `state.effect_deck` when the deck is empty (RUL-47) |
| `enter_resolve(state, *, rng)` | Step 12 refill: shuffles `state.discard` back into `state.deck` when needed |
| `advance_phase(state, *, rng)` | Forwards `rng` to both `enter_round_start` and `enter_resolve`; other branches don't shuffle |

`rng=None` falls back to a fresh non-deterministic `random.Random()` for the
refill — adequate when determinism doesn't matter (ad-hoc REPL calls). Tests
and CLI pass an explicit `random.Random(seed_variant)` for reproducibility.

The seed is intentionally NOT carried on `GameState` (substrate stays
additive-only and frozen); the rng threads through the public entry points
that need it instead.

### Deal-time behaviour (RUL-18)

`start_game(seed)`:

1. Loads main deck via `cards.build_default_deck()` (50 cards in M1.5).
2. Shuffles the deck list with `random.Random(seed)`.
3. Deals `HAND_SIZE` cards to each of `PLAYER_COUNT` players in seat order.
4. Parks the remainder in `state.deck` (50 - 4×7 = 22 cards).
5. Returns `phase=ROUND_START`, `round_number=0`, `dealer_seat=0`.

Determinism: same `seed` ⇒ same hands and same `state.deck`.

### Round-start behaviour (RUL-18, extended by RUL-47)

`enter_round_start(state, *, rng=None)`:

1. Steps 2-5 unchanged (BURN tick, label recompute, WHILE guard, shop bypass).
2. **Step 6 (RUL-47 wiring)**: pop one card from `state.effect_deck` into `revealed_effect`. When the deck is empty, shuffle `state.effect_discard` back in via `rng` and pop. Both piles empty (only possible mid-game with no current `revealed_effect`) → `revealed_effect = None` (NOOP-equivalent path).
3. Step 7: draw a CONDITION template via `cards.load_condition_templates()` (M1.5 has one: `cond.if`). The template's `slots` define the active rule's slot defs (`SUBJECT / QUANT / NOUN`); the template's `kind` is the rule template (`IF / WHEN / WHILE`). The hardcoded `_M1_RULE_SLOT_DEFS` and `_M1_DEALER_FRAGMENT` are gone.
4. Step 7 (cont.): pick the first card in the dealer's hand whose type matches slot 0's type (via `legality.first_card_of_type`). If none, the rule fails immediately: `round_number` ticks (round was attempted), dealer rotates, `active_rule=None`, the just-drawn `revealed_effect` is pushed to `effect_discard` (RUL-47 — no card-loss on rule failure per `design/effects-inventory.md`), return to `ROUND_START`.
5. Step 7 (cont.): otherwise remove the chosen card from the dealer's hand, fill slot 0, record the play, build the `RuleBuilder`, and step 8: transition to BUILD.

### Resolve behaviour (RUL-18)

`enter_resolve(state, *, rng=None)`:

1. **Steps 1-4 (new wiring)**: `effects.resolve_if_rule(state, state.active_rule)` renders the rule, scopes SUBJECT (label-aware per ADR-0001), evaluates `HAS [QUANT] [NOUN]` per scoped player, and applies the M1.5 stub effect (+1 VP per match). IF-only in M1.5; WHEN/WHILE land with persistent rules (M2).
2. Step 5: joker — guarded above.
3. **Step 6 (RUL-26 wiring)**: `persistence.check_when_triggers(state, labels)` — no-op when `state.persistent_rules == ()`. Real WHEN-trigger firing lands with the M2 WHEN-rule feature ticket.
4. Step 7: goal claim — M2 stub.
5. Step 8: label recompute — implicit (computed-not-stored).
6. Step 9: win check unchanged.
7. **Step 10 (RUL-47 wiring)**: discard played fragments AND push `revealed_effect` onto `effect_discard` (mirrors fragment cleanup so the effect deck stays recyclable). `_fail_rule_and_rotate` does the same on rule-failure paths.
8. Step 11: rotate dealer unchanged.
9. **Step 12 (new)**: `_refill_hands` brings every player back up to `HAND_SIZE`. When `state.deck` empties mid-refill, shuffles `state.discard` back into the deck via `rng` and continues. If both deck and discard are empty, that player's hand stays under `HAND_SIZE`.
10. Step 13: transition to ROUND_START unchanged.

### Substrate naming reconciliation (RUL-18)

Two divergences between `cards.yaml` and the runtime engine were resolved at
the data layer:

| Card name (was) | Card name (now) | Reason |
|---|---|---|
| SUBJECT `seat_0..seat_3` | `p0..p3` | Match `Player.id` from `start_game` so `effects._scope_subject` matches without a translation step |
| SUBJECT `LEADER` / `WOUNDED` | `THE LEADER` / `THE WOUNDED` | Match keys in `labels.LABEL_NAMES` per ADR-0001 |

`cards.yaml` ids tracked the rename too (`subj.seat_0` → `subj.p0`). No
substrate file (`state.py`, `effects.py`, `labels.py`, `grammar.py`,
`cards.py`) was edited.

### M1 stubs that survive

- **Shop check** (`round_start` step 5): bypassed.
- **WHILE-rule tick** (`round_start` step 4): wired to `persistence.tick_while_rules` (RUL-26); no-op when `state.persistent_rules == ()`. Real per-rule evaluation lands with the M2 WHILE-rule feature ticket.
- **JOKER attachment** (`resolve` step 5): raises `NotImplementedError("M2: joker attachment")` if `active_rule.joker_attached` is set. M1 never attaches.
- **Effect application** (`resolve` steps 1-4): wired to `effects.resolve_if_rule` for IF rules. WHEN/WHILE templates raise no error (only IF lands in M1.5's CONDITION deck) but their effects won't apply until M2 persistent rules land.
- **Goal claim** (`resolve` step 7): no-op; goals deferred.
- **Win check** (`resolve` step 9): scans `vp >= VP_TO_WIN`; transitions to `END` if found.

### Tests

`engine/tests/test_round_flow.py` (refreshed for RUL-18):

Deal / determinism:
- `test_start_game_deals_full_hands_per_seat`
- `test_start_game_is_deterministic_under_same_seed`
- `test_start_game_differs_across_seeds`
- `test_start_game_uses_no_cards_outside_main_deck`

Round-start:
- `test_advance_from_round_start_enters_build_with_dealer_first_slot_filled`
- `test_round_start_slot_defs_match_condition_template`
- `test_dealer_first_slot_card_came_from_dealer_hand`
- `test_round_start_fails_immediately_when_dealer_has_no_seed_card`

Build / resolve / play:
- `test_play_card_fills_slot_and_advances_active_seat`
- `test_play_card_removes_card_from_active_player_hand`
- `test_play_card_rejects_type_mismatch` / `_filled_slot` / `_unknown_slot` / `_outside_build`
- `test_build_with_all_slots_filled_transitions_to_resolve`
- `test_build_with_unfilled_slot_fails_back_to_round_start`
- `test_resolve_transitions_to_round_start_and_rotates_dealer`
- `test_advance_phase_from_resolve_invokes_enter_resolve`

Refill (RUL-18):
- `test_refill_replenishes_hands_to_hand_size_after_resolve`
- `test_refill_shuffles_discard_back_when_deck_empties`

Effect-deck draw / discard (RUL-47):
- `test_round_start_reveals_real_card_from_seeded_effect_deck`
- `test_round_start_pop_is_deterministic_under_seed`
- `test_resolve_appends_consumed_effect_to_effect_discard`
- `test_failed_rule_pushes_revealed_effect_to_effect_discard`
- `test_dealer_no_seed_failure_pushes_revealed_effect_to_effect_discard`
- `test_effect_deck_recycles_when_empty`
- `test_effect_deck_recycle_is_seed_deterministic`
- `test_multi_round_game_conserves_effect_card_total`

Misc:
- `test_dealer_rotates_across_four_rounds_via_failed_rules`
- `test_advance_from_lobby_enters_round_start`
- `test_advance_from_shop_raises_not_implemented`
- `test_advance_from_end_is_idempotent`
- `test_burn_tick_drains_chips_and_clears_mute_at_round_start`

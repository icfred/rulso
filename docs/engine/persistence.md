_Last edited: 2026-05-10 by RUL-32_

# persistence.py — WHEN / WHILE rule dispatch

Pure-function entry points the round-flow machine calls into. RUL-26 added the
scaffolding; RUL-32 ships the real fire logic for `tick_while_rules` and
`check_when_triggers`. Effect application is a Phase 2 stub — Phase 3 replaces
it with a `revealed_effect`-driven dispatcher.

## Module: `rulso.persistence`

### Public API

| Function | Returns | Purpose |
|---|---|---|
| `tick_while_rules(state, labels)` | `GameState` | `round_start` step 4: re-evaluate every WHILE rule. Fires; rule persists. |
| `check_when_triggers(state, labels)` | `GameState` | `resolve` step 6: fire matching WHEN rules FIFO; discard each on fire. |
| `add_persistent_rule(state, rule, kind)` | `GameState` | Append a WHEN/WHILE rule; evict oldest at `MAX_PERSISTENT_RULES`. |

### Wiring

| Caller | Site | Behaviour when `state.persistent_rules == ()` |
|---|---|---|
| `rules.enter_round_start` | step 4 | Skipped — preserves M1.5 path bit-for-bit |
| `rules.enter_resolve` | step 6 (post-effects) | Skipped — preserves M1.5 path bit-for-bit |

### Fire model (RUL-32 / Phase 2 stub)

`_try_fire_persistent_rule` promotes a WHEN/WHILE `RuleBuilder` to
`RuleKind.IF` (slot shape is identical: SUBJECT/QUANT/NOUN) and routes through
`effects.resolve_if_rule`, which renders, scopes, evaluates `HAS [QUANT] [NOUN]`
and applies the M1.5 +1 VP stub. Identity comparison against the input state
tells the dispatcher whether the rule fired.

Phase 3 effect dispatcher replaces this with `revealed_effect`-driven dispatch
and adds the "fire on relevant state changes" hook for WHILE called out in
`design/state.md`.

### WHILE semantics (`tick_while_rules`)

- Walks `persistent_rules` in insertion order; only `kind=WHILE` entries fire.
- Fires when SUBJECT scope is non-empty AND HAS evaluates true.
- Persists after fire — leaves `persistent_rules` only via removal cards
  (M2-out-of-scope) or game end.
- **Dormancy**: SUBJECT referencing an unassigned label (e.g. CURSED in M1.5)
  produces empty scope → no fire → rule stays for the next tick.
- Labels are recomputed after each fire so subsequent WHILE rules see the
  current state (e.g. LEADER may shift on a VP gain).

### WHEN semantics (`check_when_triggers`)

- FIFO walk: first WHEN whose scope is non-empty AND HAS evaluates true fires,
  is discarded from `persistent_rules`, and the walk recurses on the new state.
- **Recursion cap**: `_MAX_WHEN_RECURSION_DEPTH = 3` per `design/state.md`
  "Edge Case Index — WHEN rule fires during another rule's resolve". Rules
  beyond the cap remain in `persistent_rules` for the next resolve.
- Dormant SUBJECTs (unassigned label, unknown player id) → no fire, no discard.
- Labels recomputed after each fire so chained WHENs see current label holders.

### Capacity (`add_persistent_rule`)

`add_persistent_rule` enforces `len(persistent_rules) ≤ MAX_PERSISTENT_RULES`
via FIFO eviction (drop index 0, append at the tail) per
`design/state.md` "Persistent Rules — Lifetimes". Default `created_by` is
`state.players[state.dealer_seat].id`; M2 features attaching via JOKER may
extend the signature to accept an explicit player id.

### Tests

`engine/tests/test_persistence.py`:

- `test_tick_while_rules_returns_state_unchanged_when_no_persistent_rules`
- `test_check_when_triggers_returns_state_unchanged_when_no_persistent_rules`
- `test_add_persistent_rule_appends_when_under_capacity`
- `test_add_persistent_rule_evicts_oldest_at_capacity`
- `test_add_persistent_rule_rejects_if_kind`
- `test_tick_while_rules_fires_when_scope_matches`
- `test_tick_while_rules_persists_across_multiple_ticks`
- `test_tick_while_rules_dormant_label_no_op`
- `test_tick_while_rules_skips_when_kind_rules`
- `test_check_when_triggers_fires_once_and_discards`
- `test_check_when_triggers_unknown_subject_id_is_no_op`
- `test_check_when_triggers_dormant_label_no_op`
- `test_check_when_triggers_recursion_terminates_at_depth_3`
- `test_check_when_triggers_fires_in_fifo_order`
- `test_check_when_triggers_skips_while_kind_rules`
- `test_tick_while_and_check_when_coexist`

_Last edited: 2026-05-10 by RUL-26_

# persistence.py — WHEN / WHILE rule dispatch

M2 substrate scaffolding (RUL-26). Pure-function entry points the round-flow
machine wires through. Real firing logic lands with the M2 persistence-rule
feature tickets; this module provides the dispatch surface they target.

## Module: `rulso.persistence`

### Public API

| Function | Returns | Purpose |
|---|---|---|
| `tick_while_rules(state, labels)` | `GameState` | `round_start` step 4: re-evaluate every WHILE rule. Stub: no-op. |
| `check_when_triggers(state, labels)` | `GameState` | `resolve` step 6: fire matching WHEN rules after effects. Stub: no-op. |
| `add_persistent_rule(state, rule, kind)` | `GameState` | Append a WHEN/WHILE rule; evict oldest at `MAX_PERSISTENT_RULES`. |

### Wiring (RUL-26)

| Caller | Site | Behaviour when `state.persistent_rules == ()` |
|---|---|---|
| `rules.enter_round_start` | step 4 | Skipped — preserves M1.5 path bit-for-bit |
| `rules.enter_resolve` | step 6 (post-effects) | Skipped — preserves M1.5 path bit-for-bit |

### Capacity

`add_persistent_rule` enforces `len(persistent_rules) ≤ MAX_PERSISTENT_RULES`
via FIFO eviction (drop index 0, append at the tail) per
`design/state.md` "Persistent Rules — Lifetimes".

### Created-by attribution

`add_persistent_rule` uses `state.players[state.dealer_seat].id` as the
default `created_by`. M2 features that attach via JOKER may extend the
signature to accept an explicit player id.

### Stub guarantees

* `tick_while_rules(state, labels)` — returns `state` unchanged for any input.
* `check_when_triggers(state, labels)` — returns `state` unchanged for any input.
* `add_persistent_rule(state, rule, IF)` — raises `ValueError`; IF rules don't
  persist.

### Tests

`engine/tests/test_persistence.py`:

- `test_tick_while_rules_returns_state_unchanged_when_no_persistent_rules`
- `test_check_when_triggers_returns_state_unchanged_when_no_persistent_rules`
- `test_add_persistent_rule_appends_when_under_capacity`
- `test_add_persistent_rule_evicts_oldest_at_capacity`
- `test_add_persistent_rule_rejects_if_kind`

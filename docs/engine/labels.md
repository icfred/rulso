_Last edited: 2026-05-10 by RUL-33_

# labels.py — floating-label computation

Pure function over `GameState`. Computed each round; never stored on state.

## Module: `rulso.labels`

### Public API

| Symbol | Purpose |
|---|---|
| `recompute_labels(state) -> dict[str, frozenset[str]]` | Return label-name → frozenset[player_id] mapping |
| `LABEL_NAMES` | Tuple of all label keys (stable iteration order) |
| `LEADER` / `WOUNDED` / `GENEROUS` / `CURSED` / `MARKED` / `CHAINED` | Label-name string constants |

### Coverage

| Label | Rule | Status | Landed in |
|---|---|---|---|
| `THE LEADER` | `argmax(player.vp)` | live | RUL-19 |
| `THE WOUNDED` | `argmin(player.chips)` | live | RUL-19 |
| `THE GENEROUS` | `argmax(player.history.cards_given_this_game)` | live | RUL-33 |
| `THE CURSED` | `argmax(player.status.burn)` | live | RUL-33 |
| `THE MARKED` | `Player.status.marked` | M2 — empty frozenset | (M2 status-apply) |
| `THE CHAINED` | `Player.status.chained` | M2 — empty frozenset | (M2 status-apply) |

### Tie-break policy

Ties → all tied players hold the label. Per ADR-0001 (supersedes
`design/state.md`'s original "ties → unassigned").

GENEROUS / CURSED additionally honour a **zero → empty** rule: if no player
has given a card / taken a burn, the label has no holder.

### Edge cases

| Input | Output |
|---|---|
| `state.players` empty | every key → `frozenset()` |
| All players tied on vp / chips | every player id in `LEADER` / `WOUNDED` |
| All players at zero `cards_given_this_game` | `GENEROUS` → `frozenset()` |
| All players at zero `status.burn` | `CURSED` → `frozenset()` |
| All players tied at the same positive `cards_given_this_game` / `status.burn` | every player id in `GENEROUS` / `CURSED` |

### Call sites

- `rules.enter_round_start` step 3 invokes `recompute_labels` on the post-burn-tick players (canonical design step 3 hook). M1 has no live consumer here — WHILE-rule ticks are M2.
- `effects.resolve_if_rule(state, rule, labels=...)` accepts a pre-computed mapping; `_scope_subject` looks up label SUBJECTs against it. When `labels=None`, the resolver recomputes from `state` (RUL-22). See `docs/engine/if-resolver.md`.

Labels are never stored on `GameState` (ADR-0001). They flow as a transient parameter from caller to resolver.

### Tests

`engine/tests/test_labels.py`:

- `test_returns_all_label_keys` — every name in `LABEL_NAMES` present
- `test_single_leader_max_vp` / `test_tied_leaders_all_hold_label`
- `test_single_wounded_min_chips` / `test_tied_wounded_all_hold_label`
- `test_all_zero_vp_means_every_player_is_leader`
- `test_all_equal_chips_means_every_player_is_wounded`
- `test_empty_player_set_returns_all_empty_frozensets`
- `test_single_generous_max_cards_given` / `test_tied_generous_all_hold_label`
- `test_generous_all_zero_means_empty` / `test_generous_all_equal_positive_means_all_tied`
- `test_single_cursed_max_burn` / `test_tied_cursed_all_hold_label`
- `test_cursed_no_burn_means_empty` / `test_cursed_all_equal_burn_means_all_tied`
- `test_marked_and_chained_remain_empty`
- `test_returns_frozensets`
- `test_pure_function_does_not_mutate_state`

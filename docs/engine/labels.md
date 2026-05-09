_Last edited: 2026-05-09 by RUL-19_

# labels.py — floating-label computation

Pure function over `GameState`. Computed each round; never stored on state.

## Module: `rulso.labels`

### Public API

| Symbol | Purpose |
|---|---|
| `recompute_labels(state) -> dict[str, frozenset[str]]` | Return label-name → frozenset[player_id] mapping |
| `LABEL_NAMES` | Tuple of all label keys (stable iteration order) |
| `LEADER` / `WOUNDED` / `GENEROUS` / `CURSED` / `MARKED` / `CHAINED` | Label-name string constants |

### M1.5 coverage (RUL-19)

| Label | Rule | Status |
|---|---|---|
| `THE LEADER` | `argmax(player.vp)` | live |
| `THE WOUNDED` | `argmin(player.chips)` | live |
| `THE GENEROUS` | `argmax(player.history.cards_given_this_game)` | M2 — empty frozenset |
| `THE CURSED` | `argmax(player.status.burn)` | M2 — empty frozenset |
| `THE MARKED` | `Player.status.marked` | M2 — empty frozenset |
| `THE CHAINED` | `Player.status.chained` | M2 — empty frozenset |

### Tie-break policy

Ties → all tied players hold the label. Diverges from `design/state.md`'s
"ties → unassigned"; Linear (RUL-19) is the source of truth.

### Edge cases

| Input | Output |
|---|---|
| `state.players` empty | every key → `frozenset()` |
| All players tied on vp / chips | every player id in `LEADER` / `WOUNDED` |

### Call site

`rules.enter_round_start` step 3 invokes `recompute_labels` on the post-burn-tick
players. The return value is currently unconsumed: `effects._scope_subject`
still returns `frozenset()` for any label-name SUBJECT. Wiring labels into
SUBJECT scoping is a separate ticket.

### Tests

`engine/tests/test_labels.py`:

- `test_returns_all_label_keys` — every name in `LABEL_NAMES` present
- `test_single_leader_max_vp` / `test_tied_leaders_all_hold_label`
- `test_single_wounded_min_chips` / `test_tied_wounded_all_hold_label`
- `test_all_zero_vp_means_every_player_is_leader`
- `test_all_equal_chips_means_every_player_is_wounded`
- `test_empty_player_set_returns_all_empty_frozensets`
- `test_m2_stub_labels_are_empty`
- `test_returns_frozensets`
- `test_pure_function_does_not_mutate_state`

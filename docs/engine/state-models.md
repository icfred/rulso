_Last edited: 2026-05-09 by RUL-8_

# state.py — Pydantic models

Canonical schema for game state. Mirrors `design/state.md`. No game logic.

## Module: `rulso.state`

### Constants

`PLAYER_COUNT=4`, `HAND_SIZE=7`, `STARTING_CHIPS=50`, `VP_TO_WIN=3`, `ACTIVE_GOALS=3`, `SHOP_INTERVAL=3`, `MAX_PERSISTENT_RULES=5`, `DISCARD_COST=5`, `BURN_TICK=5`.

### Enums (`StrEnum`)

| Enum | Values |
|---|---|
| `Phase` | `lobby`, `round_start`, `build`, `resolve`, `shop`, `end` |
| `CardType` | `SUBJECT`, `NOUN`, `MODIFIER`, `JOKER` |
| `RuleKind` | `IF`, `WHEN`, `WHILE` |

### Models

All `frozen=True`. Collections are `tuple[...]` so frozen instances are deeply immutable.

| Model | Fields |
|---|---|
| `Card` | `id: str`, `type: CardType`, `name: str` |
| `PlayerStatus` | `burn: int`, `mute/blessed/marked/chained: bool` |
| `PlayerHistory` | `rules_completed_this_game: int`, `cards_given_this_game: int`, `last_round_was_hit: bool` |
| `Player` | `id`, `seat`, `chips`, `vp`, `hand: tuple[Card, ...]`, `status`, `history` |
| `Slot` | `name: str`, `type: CardType`, `filled_by: Card \| None`, `modifiers: tuple[Card, ...]` |
| `Play` | `player_id: str`, `card: Card`, `slot: str` |
| `RuleBuilder` | `template: RuleKind`, `slots: tuple[Slot, ...]`, `plays: tuple[Play, ...]`, `joker_attached: Card \| None` |
| `PersistentRule` | `kind: RuleKind` (WHEN\|WHILE), `rule: RuleBuilder`, `created_round: int`, `created_by: str` |
| `LastRoll` | `player_id: str`, `value: int`, `dice_count: int` |
| `GameState` | `phase`, `round_number`, `dealer_seat`, `active_seat`, `players`, `deck`, `discard`, `effect_deck`, `effect_discard`, `goal_deck`, `goal_discard`, `active_goals`, `active_rule: RuleBuilder \| None`, `persistent_rules`, `last_roll: LastRoll \| None`, `winner: Player \| None`, `build_turns_taken: int` (RUL-8), `revealed_effect: Card \| None` (RUL-8) |

### Update pattern

```python
next_state = state.model_copy(update={"phase": Phase.BUILD, "active_seat": 1})
```

### JSON

`model_dump_json()` / `model_validate_json()` round-trip; tested in `tests/test_state_models.py`.

### Computed (not stored)

Floating labels (LEADER / WOUNDED / GENEROUS / CURSED) live in `labels.py`, not on `Player`.

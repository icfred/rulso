_Last edited: 2026-05-10 by RUL-17_

# cards.py — yaml loader

M1.5 card catalogue. Reads `design/cards.yaml`, validates with Pydantic,
exposes the playable deck. Read-only consumer of `state.py`.

## Module: `rulso.cards`

### Public API

| Symbol | Returns | Notes |
|---|---|---|
| `load_cards(path=None)` | `tuple[Card, ...]` | Non-CONDITION cards, deduped (one per id). Default path: `design/cards.yaml`. |
| `load_condition_templates(path=None)` | `tuple[ConditionTemplate, ...]` | CONDITION templates only. M1.5 ships `IF`. |
| `build_default_deck(cards=None, *, path=None)` | `Decks` | Multiplies per-id `copies` from the yaml. `cards` filters the eligible pool. |

### Models

| Model | Frozen? | Fields |
|---|---|---|
| `ConditionSlot` | yes | `name: str`, `type: CardType` |
| `ConditionTemplate` | yes | `id`, `name`, `kind: RuleKind`, `slots: tuple[ConditionSlot, ...]` |
| `Decks` (`NamedTuple`) | n/a | `main: tuple[Card, ...]`, `conditions: tuple[ConditionTemplate, ...]` |

`ConditionTemplate` is **not** a `Card` because `state.CardType` deliberately
omits CONDITION. Conditions live in their own deck (drawn by the dealer at
`round_start` step 7).

### `name` conventions (the resolver's read key)

| Card type | `name` form | Example |
|---|---|---|
| SUBJECT (literal seat) | `seat_<i>` | `seat_2` |
| SUBJECT (label) | bare keyword | `LEADER`, `WOUNDED` |
| NOUN | bare keyword | `CHIPS`, `VP` |
| MODIFIER (comparator) | `<OP>:<N>` | `LT:5`, `GE:3` |
| CONDITION | bare keyword | `IF` |

OPs: `GE GT LE LT EQ`. M1.5 bakes N into the card; M2 will reintroduce dice
(see `design/cards-inventory.md` design tension #2).

### M1.5 starter subset

| Section | Unique kinds | Physical copies |
|---|---|---|
| CONDITION | 1 (IF) | 1 (separate condition deck) |
| SUBJECT | 6 (`seat_0..3`, `LEADER`, `WOUNDED`) | 18 (3 each) |
| NOUN | 2 (`CHIPS`, `VP`) | 8 (4 each) |
| MODIFIER | 12 (5 OPs × spread of N) | 24 (2 each) |
| **Main deck total** | **20** | **50** |

Deck size 50 ≥ 28 (4 players × `HAND_SIZE` 7) so RUL-18's opening deal fits.

### Schema validation

Yaml schema is enforced by `_Schema` (Pydantic). Malformed input raises
`ValueError("cards.yaml schema validation failed: …")` with the underlying
`ValidationError` chained. Empty file → `ValueError("…is empty")`. Missing
file → `FileNotFoundError`.

### Substrate boundaries (do not edit from this module)

- `state.py` — read-only. `Card`, `CardType`, `RuleKind` are imported as-is.
- `grammar.py` — slot names `SUBJECT/QUANT/NOUN` are mirrored in cards.yaml's
  CONDITION template.
- `effects.py` — reads `card.name`. Naming choices in cards.yaml are made to
  match what the resolver expects once RUL-18 wires hands.

### Open follow-ups for RUL-18 (handover artefact)

The naming `seat_0..3` and `LEADER`/`WOUNDED` was chosen per the RUL-17
hand-over spec, not the current resolver state. RUL-18 must reconcile:

- `Player.id` is currently `p0..p3` (set in `rules.start_game`); SUBJECT
  literals here are `seat_0..3`.
- `effects._LABEL_NAMES` reads `THE LEADER` / `THE WOUNDED`; SUBJECT label
  cards here are `LEADER` / `WOUNDED`.

Either align Player IDs / label constants to the cards, or add a translation
layer when wiring deals. Substrate edit lives with RUL-18, not here.

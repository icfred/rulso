_Last edited: 2026-05-09 by RUL-10_

# bots

## Action type

Defined in `engine/src/rulso/bots/random.py` (bots package, not state.py). Pydantic v2 frozen discriminated union on `kind`:

| Class | `kind` | Extra fields |
|---|---|---|
| `PlayCard` | `"play_card"` | `card_id: str`, `slot: str`, `dice: 1\|2\|None` |
| `DiscardRedraw` | `"discard_redraw"` | `card_ids: tuple[str, ...]` (1..3) |
| `Pass` | `"pass"` | — |

`Action = Annotated[PlayCard | DiscardRedraw | Pass, Field(discriminator="kind")]`

Kept in `bots/` for now. Promote to `state.py` or `protocol.py` when the protocol layer needs to serialise player actions.

## random bot

`engine/src/rulso/bots/random.py` — `choose_action(state, player_id, rng) -> Action`

- Pure function. `rng: random.Random` injected; deterministic for a given seed.
- Only enumerates actions when `phase == BUILD`; returns `Pass` for all other phases.
- Action space flattened to a list; uniform sample via `rng.choice`.

### Legal-action rules

**PlayCard** — one entry per (card, open-slot) pair where `card.type == slot.type`:
- Filled slots are excluded.
- MUTE token on player excludes all MODIFIER plays.
- MODIFIER plays generate two entries: `dice=1` and `dice=2` (1d6 / 2d6). All MODIFIER plays treated as comparators in M1 (no per-card metadata yet).
- JOKER cards have no slot-type match → never emitted in M1.

**DiscardRedraw** — one entry per combination of `k` cards (k ∈ 1..min(3, hand_size, chips // DISCARD_COST)):
- Requires `chips >= DISCARD_COST (5)` and non-empty hand.
- All subsets of size 1..3 are enumerated, so the bot can bias toward discards when hands are full. Acceptable for a baseline bot.

**Pass** — returned when the combined list is empty.

### Operator-attach (MODIFIER on filled slot)

Not modelled in M1. Per design/state.md MODIFIER can attach as an operator to any filled slot. The random bot only fills open slots by type. This can be added when the rule-builder in `rules.py` supports operator attachment.

### RNG injection

Callers construct `random.Random(seed)` and pass it in. The bot does not call `random.seed()` or access any global RNG.

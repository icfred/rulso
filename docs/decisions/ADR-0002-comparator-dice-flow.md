# ADR-0002 — Comparator dice flow

**Status**: Accepted (2026-05-10)

## Context

`design/state.md` Phase: build step 2 mandates that comparator MODIFIER cards carry an inline dice roll: the player chooses 1d6 or 2d6 at play time, rolls publicly, and the value sets the QUANT slot's number. M1.5 deferred dice and pre-baked N into `card.name` (`LT:5`, `GT:10`, etc. — see `design/cards-inventory.md` "MODIFIER — comparator" section).

For M2, the inventory's "Design tension #2" surfaces two options:
- **(a) OP-only cards.** `card.name = "LT"`. Card encodes the operator. Dice mode (1d6 vs 2d6) and resolved N come from the play action.
- **(b) OP + dice-mode cards.** `card.name = "LT:1D6"`, `"LT:2D6"`. Card encodes operator AND dice mode. Player rolls; the action carries only the resolved N.

Trade-offs:

| Concern | (a) OP-only | (b) OP + mode |
|---|---|---|
| Card-kind count (M2 comparators) | 5 (LT/LE/GT/GE/EQ) | 10 (5 ops × 2 modes) |
| Per-play decisions | Player picks dice mode each play | Card pre-commits the mode |
| Inventory naming convention | Bare OP token | `OP:DICE` split-on-`:` |
| `play_card` action shape | Grows: `{card_id, slot, dice_mode, dice_roll}` | Grows: `{card_id, slot, dice_roll}` |
| Strategic depth | Dice-mode choice is a recurring decision | Mode pre-decided; only roll varies |

## Decision

**Adopt (a): cards encode OP only; dice mode chosen at play time.**

Rationale:
- `state.md` already designates "1d6 or 2d6 player choice" as the comparator-play decision. Encoding the mode on the card removes that choice — defeats the design intent. A 1d6/2d6 toggle on the play action preserves it.
- Halves the M2 comparator card-kind count (5 vs 10), keeping the deck flatter and the inventory easier to reason about.
- The action already carries a roll value. Adding a `dice_mode` field is a one-field extension, not a new schema axis.

## Examples

1. Player plays `mod.cmp.lt` (`name = "LT"`) into the QUANT slot. Chooses 2d6, rolls 7. Slot resolves to `LT 7`. Rendered rule: `IF SEAT 0 HAS LESS THAN 7 CHIPS → +1 VP`.
2. Player plays `mod.cmp.eq` (`name = "EQ"`). Chooses 1d6 for the tighter range, rolls 3. Slot resolves to `EQ 3`. Rule: `IF LEADER HAS EXACTLY 3 VP → +1 VP`. (1d6 is the strategic pick when EQ — narrower range raises hit probability.)

## Consequences

- **`effects.py`**: comparator evaluation reads `(op, n)` where `op` comes from `card.name` (M2 path) and `n` comes from the action's `dice_roll` field. M1.5 path (`name = "LT:5"`) is preserved by splitting on `:` — if a second segment exists, it's the baked N; otherwise read N from the action.
- **`grammar.py`**: comparator render = `"<OP-text> <N>"` with `<OP-text>` from a static map (`LT → "LESS THAN"`, etc.). Optional roll display (`(1d6=5)`) for narration.
- **`cards.yaml` / `design/cards-inventory.md`**: M2 introduces 5 comparator cards (`mod.cmp.lt`, `mod.cmp.le`, `mod.cmp.gt`, `mod.cmp.ge`, `mod.cmp.eq`) with bare-OP `name`. M1.5's pre-baked `LT:5`/`GT:10`/etc. are grandfathered M1.5-only artefacts; M2 deck builder filters them out.
- **`play_card` action schema**: extends with `dice_mode: 1 | 2` and `dice_roll: int` for QUANT plays. Both fields required when the played card is a bare-OP comparator; both ignored when the card carries a baked N.
- **Bots**: action generators must enumerate `(card, dice_mode)` pairs for legal QUANT plays and select per the bot's heuristic. Roll value is sampled by the engine, not chosen by the bot.
- **Naming convention update**: `cards-inventory.md` "MODIFIER — comparator" Naming section needs a follow-up note that M2 comparators have bare-OP `name`. Single-line ratification, not a structural rewrite.

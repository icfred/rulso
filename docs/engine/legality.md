_Last edited: 2026-05-10 by RUL-18_

# legality.py — shared legality predicates

Tiny pure helpers shared between `rules.py` (dealer's first-slot pick at
`enter_round_start`) and (eventually) `bots/random.py`. Lives in its own
module so `rules.py` doesn't reach into `bots/` for a shared check.

No state mutation, no I/O. Type-match only — MUTE / BLESSED / dice options
and discard affordability stay in the bot since they bear on action shape,
not on "is this card legal in this slot?".

## Module: `rulso.legality`

### Public API

| Function | Returns | Purpose |
|---|---|---|
| `first_card_of_type(hand, card_type)` | `Card \| None` | First card in `hand` whose type matches `card_type`, or `None` |

### Order semantics

`first_card_of_type` is order-stable (tuple iteration order). The
deterministic deal in `start_game` plus tuple-stable hands means the dealer's
auto-pick at round_start is also deterministic given a fixed seed.

### Why a separate module

`bots/random.py:_enumerate_plays` does a richer enumeration (slot iteration,
MUTE-blocked MODIFIER, dice options). `rules.enter_round_start` only needs
"any card of this type". Sharing a tiny helper avoids `rules.py` importing
`bots/`.

### Tests

Covered indirectly through `test_round_flow.py` round-start tests
(`test_dealer_first_slot_card_came_from_dealer_hand`,
`test_round_start_fails_immediately_when_dealer_has_no_seed_card`).

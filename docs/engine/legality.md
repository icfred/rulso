_Last edited: 2026-05-11 by RUL-23 (RUL-65 promoted action surface from `bots.random`)_

# legality.py — engine action surface

Canonical home for the action vocabulary every engine driver consumes: the random bot, the human TTY driver, the WS protocol envelope, and any future driver (ISMCTS rollouts, replay). Pre-RUL-65 these shapes lived in `bots/random.py`; the move makes the protocol layer's "no drift" guarantee (ADR-0008) trivial — `protocol.ClientAction` and `bots.random.choose_action` resolve to the same Pydantic class objects because there is exactly one definition site.

Pure module: no I/O, no module-level mutable state, no RNG. Imports from `state.py` and `effects.py` only.

## Module: `rulso.legality`

### Action shapes (RUL-65)

Frozen Pydantic v2 models, each tagged on `kind` for discriminated-union dispatch.

| Class | `kind` | Fields | Used by |
|---|---|---|---|
| `PlayCard` | `"play_card"` | `card_id: str`, `slot: str`, `dice: Literal[1, 2] \| None` | bot, human, client |
| `DiscardRedraw` | `"discard_redraw"` | `card_ids: tuple[str, ...]` | bot, human, client |
| `Pass` | `"pass"` | (no payload) | bot, human, server-side only — never submitted by a client (ADR-0008) |
| `PlayJoker` | `"play_joker"` | `card_id: str` | bot, human, client (RUL-45 — JOKERs bind to `RuleBuilder.joker_attached`, not a slot) |

`Action = Annotated[PlayCard \| DiscardRedraw \| Pass \| PlayJoker, Field(discriminator="kind")]` is the discriminated union the bot's `choose_action` returns. The protocol's narrower `ClientAction = PlayCard \| DiscardRedraw \| PlayJoker` excludes `Pass` per ADR-0008.

### Public predicates + enumeration

| Function | Returns | Purpose |
|---|---|---|
| `first_card_of_type(hand, card_type)` | `Card \| None` | Order-stable first match — used by `rules.enter_round_start` for the dealer's auto-pick |
| `can_attach_joker(rule, card)` | `bool` | RUL-45: `card` is a JOKER, `rule` is non-`None`, no joker already attached |
| `enumerate_legal_actions(state, player)` | `list[PlayCard \| PlayJoker \| DiscardRedraw]` | Raw structural enumeration for BUILD phase. Same predicates as the bot, no `PLAY_BIAS` weighting, no RNG, no `Pass` (caller picks `Pass` when the list is empty). Consumed by `bots/human.py` for menu rendering and `server.py` for client-action validation |

### Internal helpers

`_enumerate_plays` and `_enumerate_discards` (and the `_OP_ONLY_*` constants from RUL-42) are co-located with `enumerate_legal_actions` rather than left in `bots/random.py`. Reason: `bots/random.py` already imports `can_attach_joker` from `legality`, so moving the enumerators back across the boundary would create a cycle. `bots.random.choose_action` re-imports both helpers from `legality` for its own `plays` / `discards` split.

### Order semantics

`first_card_of_type` and the enumerators iterate tuples — order-stable given the deterministic deal in `start_game`. `enumerate_legal_actions`'s output order is structural (slot iteration × hand iteration × dice variants), so the human-seat menu is reproducible given a fixed seed.

### Tests

| Test file | Coverage |
|---|---|
| `test_round_flow.py` | `first_card_of_type` indirectly via dealer round-start tests |
| `test_random_bot.py` | `enumerate_legal_actions` via the bot's `choose_action` invariants (1000-seed sweep) |
| `test_jokers.py` | `can_attach_joker` + `PlayJoker` enumeration paths (PERSIST_WHEN/WHILE/DOUBLE/ECHO) |
| `test_cli_human_seat.py` | `enumerate_legal_actions` via the human menu (4-seat parametrised) |
| `test_protocol.py` | Action-shape JSON round-trip via `TypeAdapter(ClientEnvelope)` |
| `test_server.py` | `enumerate_legal_actions` is the server's `ILLEGAL_ACTION` gate (RUL-64) |

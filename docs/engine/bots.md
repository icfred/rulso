_Last edited: 2026-05-10 by RUL-53_

# bots

## Action type

Defined in `engine/src/rulso/bots/random.py` (bots package, not state.py). Pydantic v2 frozen discriminated union on `kind`:

| Class | `kind` | Extra fields |
|---|---|---|
| `PlayCard` | `"play_card"` | `card_id: str`, `slot: str`, `dice: 1\|2\|None` |
| `DiscardRedraw` | `"discard_redraw"` | `card_ids: tuple[str, ...]` (1..3) |
| `Pass` | `"pass"` | — |
| `PlayJoker` | `"play_joker"` | `card_id: str` (RUL-45 — attaches to the rule as a whole, not a slot) |

`Action = Annotated[PlayCard | DiscardRedraw | Pass | PlayJoker, Field(discriminator="kind")]`

Kept in `bots/` for now. Promote to `state.py` or `protocol.py` when the protocol layer needs to serialise player actions.

## random bot

`engine/src/rulso/bots/random.py` — `choose_action(state, player_id, rng) -> Action`

- Pure function. `rng: random.Random` injected; deterministic for a given seed.
- Only enumerates actions when `phase == BUILD`; returns `Pass` for all other phases.
- Plays (`PlayCard` ∪ `PlayJoker`) and discards enumerated separately. When both pools are non-empty, a play is chosen with probability `PLAY_BIAS = 0.85` (single `rng.random()` coin flip), otherwise uniform `rng.choice` within whichever pool is non-empty. Reason: hand=7 + chips=50 makes the discard space (~63 actions) swamp the play space (1..4); uniform sampling stalls rule resolution. Bias preserves rule-resolve throughput while leaving exploration in the discard pool.

### Legal-action rules

**PlayCard** — one entry per (card, open-slot) pair where `card.type == slot.type`:
- Filled slots are excluded.
- MUTE token on player excludes all MODIFIER plays.
- Comparator MODIFIER plays generate two entries: `dice=1` and `dice=2` (1d6 / 2d6).
- **RUL-43**: operator MODIFIERs (`BUT`/`AND`/`OR`/`MORE_THAN`/`AT_LEAST`, per `effects.is_operator_modifier` / `OPERATOR_MODIFIER_NAMES`) share `CardType.MODIFIER` with comparators but attach to a filled slot's `modifiers` tuple rather than `filled_by`. The dedicated `play_operator` action shape lands when ADR-0004's legality extension does — until then the bot **skips** them inside `_enumerate_plays`, so it never picks one that would dead-end at fold time. The card stays in hand rather than crashing the rule-builder's `_parse_quant` on a QUANT mis-fill.

**PlayJoker** (RUL-45) — one entry per distinct JOKER in hand, gated by `legality.can_attach_joker(rule, card)`:
- An active rule exists.
- The rule has no joker yet attached (`rule.joker_attached is None` — one joker per rule per `design/state.md` "JOKER attachment").
- The card is `CardType.JOKER`.

JOKERs do not fill a slot (no JOKER slot exists in any CONDITION template); they bind to the rule as a whole via `RuleBuilder.joker_attached` and resolve in `rules.play_joker` / `effects.resolve_if_rule`. MUTE does **not** block JOKER plays (per `design/state.md` "Status Tokens", MUTE blocks only MODIFIER cards). Variant semantics (encoded in `card.name`, four variants from `design/cards-inventory.md`):

| `card.name` | Resolution |
|---|---|
| `JOKER:PERSIST_WHEN` | Promote rule to WHEN; lodge in `persistent_rules` after this round's effect fires |
| `JOKER:PERSIST_WHILE` | Same as above, with WHILE |
| `JOKER:DOUBLE` | Dispatched IF effect runs twice on the matching scope (wrapper inside `effects.resolve_if_rule`) |
| `JOKER:ECHO` | Promote to a one-shot WHEN so the rule re-evaluates at the next resolve's WHEN-trigger check |

Enumeration de-duplicates by `card.id` so the bot never produces multiple `PlayJoker` entries for the same physical joker card.

**DiscardRedraw** — one entry per combination of `k` cards (k ∈ 1..min(3, hand_size, chips // DISCARD_COST)):
- Requires `chips >= DISCARD_COST (5)` and non-empty hand.
- All subsets of size 1..3 are enumerated. The play-over-discard bias on `choose_action` counteracts the resulting size disparity between the two pools.

**Pass** — returned when the combined list is empty.

### Operator-attach (MODIFIER on filled slot)

Not yet modelled as its own action shape. Per `design/state.md` and ADR-0004 a MODIFIER may attach as an operator to any filled slot (`Slot.modifiers`). RUL-43 added the **filter** in `_enumerate_plays` so the random bot does not propose operator MODIFIERs as `PlayCard` plays; the dedicated `play_operator` action shape will land alongside ADR-0004's legality extension and the rule-builder support in `rules.py`.

### enumerate_legal_actions

`bots.random.enumerate_legal_actions(state, player) -> list[PlayCard | PlayJoker | DiscardRedraw]` (RUL-52). Public helper returning the raw legal-action union without `PLAY_BIAS` weighting and without the `Pass` fallback. Pure structural enumeration: same predicates as the bot, no RNG. Returns `[]` outside `Phase.BUILD`; an empty list is the caller's signal to pick `Pass`.

This is the canonical legal-action enumeration surface for any non-bot driver — human seat (below), replay tooling, ISMCTS rollouts. Distinguish from `choose_action`, which is the `PLAY_BIAS`-weighted picker the random bot uses for itself.

### RNG injection

Callers construct `random.Random(seed)` and pass it in. The bot does not call `random.seed()` or access any global RNG.

## human bot

`engine/src/rulso/bots/human.py` — `select_action(state, player, *, stdin, stdout) -> Action` (RUL-52).

TTY action driver. Mirrors the random bot's action shapes (`PlayCard` / `PlayJoker` / `DiscardRedraw` / `Pass`) and consumes `bots.random.enumerate_legal_actions` so the human's menu is identical to the bot's legal set. Pure I/O wiring — the engine's pure functions stay untouched.

- **Indexed menu**: each legal action is rendered as `[i] {description}`; the human types `0..N-1`. Invalid (non-integer) or out-of-range input loops without crashing — an event line is emitted to stdout for log-grep, then the prompt waits for another read.
- **EOF → Pass**: reaching EOF on stdin (piped script ending, stalled session) emits `event=human_input outcome=eof_pass` and returns `Pass()` so a stalled or piped game still terminates cleanly.
- **No legal action**: `enumerate_legal_actions` returns `[]` ⇒ `select_action` skips the menu, writes `no legal action — pass forced.`, and returns `Pass()`.
- **stdin / stdout injection**: keyword-only parameters; the watchable CLI passes `sys.stdin`/`sys.stdout`, tests pipe scripted input directly without monkey-patching `sys.stdin`.
- **Seat selection**: `--human-seat 0..3` on the watchable CLI parametrises which seat is human-driven; the other seats keep running the random bot.

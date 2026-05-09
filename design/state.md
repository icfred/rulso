# Rulso — Game State & Round Flow

Players collaboratively/competitively build IF/WHEN/WHILE rules from typed fragment cards.
First player to `VP_TO_WIN` victory points wins.

This document is the canonical spec for game state, round flow, and edge cases.
It does **not** define specific cards (see `cards.yaml`) or grammar render rules (see `grammar.md`).

---

## Constants (MVP defaults — tunable)

| Constant | Value | Notes |
|---|---|---|
| `PLAYER_COUNT` | 4 | MVP locks 4; range 3–6 later |
| `HAND_SIZE` | 7 | mixed pool, no per-type slots |
| `STARTING_CHIPS` | 50 | |
| `VP_TO_WIN` | 3 | |
| `ACTIVE_GOALS` | 3 | always face-up |
| `SHOP_INTERVAL` | 3 | shop runs every N rounds |
| `MAX_PERSISTENT_RULES` | 5 | WHEN + WHILE combined; oldest evicts |
| `DISCARD_COST` | 5 chips/card | swap on your turn, max 3/turn |
| `BURN_TICK` | 5 chips/token | per BURN at round start |

---

## Entities

### `GameState`
- `phase`: `lobby | round_start | build | resolve | shop | end`
- `round_number`: int
- `dealer_seat`: int — rotates left each round
- `active_seat`: int — whose turn during build
- `players[]`: `Player`
- `deck`, `discard`: card pile
- `effect_deck`, `effect_discard`
- `goal_deck`, `goal_discard`, `active_goals[3]`
- `active_rule`: `RuleBuilder` | null
- `persistent_rules[]`: `PersistentRule`
- `last_roll`: { player_id, value, dice_count } | null — for history references
- `winner`: `Player` | null

### `Player`
- `id`, `seat`
- `chips`, `vp`
- `hand[]`: cards
- `status`: `{ burn: int, mute: bool, blessed: bool, marked: bool, chained: bool }`
- `history`: `{ rules_completed_this_game, cards_given_this_game, last_round_was_hit }`

### `RuleBuilder` (during build phase)
- `template`: from condition card (IF/WHEN/WHILE)
- `slots[]`: `{ name, type, filled_by, modifiers[] }`
- `plays[]`: ordered list of (player, card, slot) — for history & resolver
- `joker_attached`: card | null

### `PersistentRule`
- `kind`: `WHEN | WHILE`
- `rule`: frozen rule structure
- `created_round`, `created_by`

### Labels (computed, not stored)
- `THE LEADER`: argmax(chips); ties → unassigned
- `THE WOUNDED`: argmin(chips); ties → unassigned
- `THE GENEROUS`: argmax(cards_given_this_game); ties or zero → unassigned
- `THE CURSED`: argmax(burn); ties or zero → unassigned

A rule referencing an unassigned label resolves to "no matches"; the effect doesn't fire.

---

## Game Start (one-time)

1. Shuffle all decks.
2. Deal `HAND_SIZE` cards to each player.
3. Reveal 3 face-up goal cards.
4. Each player: chips = `STARTING_CHIPS`, vp = 0, status = empty, history = empty.
5. Dealer = seat 1 (or random for replay).
6. `round_number` = 0.
7. Transition → `round_start`.

---

## Round Flow

### Phase: `round_start`

1. `round_number += 1`.
2. **Status tick**: each player loses `BURN_TICK × burn_count` chips. MUTE flags from prior round expire here. (BURN tokens themselves persist.)
3. **Recompute labels**.
4. **WHILE-rule tick**: re-evaluate each WHILE rule against current state; apply matching effects.
5. **Shop check**: if `round_number % SHOP_INTERVAL == 0`, transition → `shop`, return after.
6. Reveal effect card from `effect_deck` (face-up, alongside the active rule area).
7. Dealer plays the condition template (IF/WHEN/WHILE) + first slot fragment.
8. Transition → `build`.

### Phase: `build`

`active_seat` starts at `(dealer_seat + 1) % PLAYER_COUNT`.

On each player's turn:
1. **Optional**: spend chips to discard ≤ 3 cards from hand and redraw (`DISCARD_COST` per card). Only allowed before playing.
2. **Required**: play one card whose type is slot-compatible with an open or modifiable slot.
   - SUBJECT cards fill SUBJECT slot.
   - NOUN cards fill NOUN slot.
   - MODIFIER cards either fill the QUANT slot (comparators) or attach to any filled slot (operators).
   - Comparator MODIFIERs (`MORE-THAN`, `LESS-THAN`, `EXACTLY`) include an inline dice roll: player chooses 1d6 or 2d6 at play time. The roll value sets the slot's number. Roll is public; recorded in `last_roll`.
   - JOKER cards have card-specific behavior (see cards.yaml).
3. **Forced pass** if player has no legal card and no chips (or chooses not to spend) for redraw. The pass advances `active_seat` without filling a slot.
4. End of turn: refill hand to `HAND_SIZE`. `active_seat` advances.

**Build ends when** all players (incl. dealer) have had one turn. The pass is exactly one full revolution.

After the pass:
- If all required slots filled → transition → `resolve`.
- If any required slot unfilled → rule **fails**: discard fragments, no effects, no goal claims, dealer rotates, transition → `round_start`.

### Phase: `resolve`

1. **Render the rule**: walk slots in order, resolve polymorphic card renders by neighbor context (see `grammar.md`).
2. **Determine subject scope**: which players match the SUBJECT clause.
3. **Evaluate condition** for each scoped player:
   - HAS-style conditions read current state.
   - ROLLS-style conditions: each scoped player rolls 1d6 publicly; record in `last_roll` (most recent overwrites).
4. **Apply effect** to every player satisfying the IF clause (every state mutation logged for history).
5. **JOKER attachment**: if a persistence-Joker was played, move the rule into `persistent_rules` (kind = WHEN or WHILE per Joker variant) instead of discarding fragments.
6. **Persistent rule trigger check**: any state change above may satisfy an active WHEN. If so, queue and fire (FIFO). Recursion depth capped at 3 to prevent runaway chains.
7. **Goal claim check**: for each active goal, evaluate claim condition:
   - Single-claim goals: first matching player claims +VP, goal discards, draw replacement.
   - Renewable goals: every match this round awards VP; goal stays.
   - Multi-goal triggers in one round: award left-to-right.
8. **Recompute labels**.
9. **Win check**: any player at `VP_TO_WIN` → transition → `end`.
10. **Cleanup**: discard played fragments (except those locked into persistent_rules), expire MARKED tokens, decrement transient timers.
11. Rotate dealer (`dealer_seat = (dealer_seat + 1) % PLAYER_COUNT`).
12. Refill hands to `HAND_SIZE`.
13. Transition → `round_start`.

### Phase: `shop`

1. Draw 4 special cards from `shop_deck` face-up with chip prices.
2. **Purchase order**: ascending VP, ties broken by lowest chips, ties broken by seat.
3. Each player in order: may purchase one card (cost paid in chips). Card goes to hand (counts against `HAND_SIZE`; player must discard if over).
4. Unsold cards: discard.
5. Transition → continuation of `round_start` (does **not** consume the round counter — `round_start` resumes from step 6).

### Phase: `end`

- Game over. Display winner, final standings, rule history.

---

## Persistent Rules — Lifetimes

| Kind | When evaluated | When discarded |
|---|---|---|
| `WHEN` | Every state mutation during `resolve` (with depth cap) | First match → fire on matched player → discard |
| `WHILE` | Start of every `round_start` (step 4) AND on relevant state changes | Only by clearing card / game end |

Capacity: `persistent_rules.length ≤ MAX_PERSISTENT_RULES`. Adding a 6th evicts the oldest.

A persistent rule whose SUBJECT references an **unassigned** label sits dormant until the label fills.

---

## Status Tokens

| Token | Effect | Lifetime |
|---|---|---|
| `BURN` | Owner loses `BURN_TICK` chips per token at `round_start` step 2 | Persists until removed by clearing card |
| `MUTE` | Cannot play MODIFIER cards next round | Cleared at end of the round it applied |
| `BLESSED` | Next chip-loss effect on bearer is canceled | Cleared on use |
| `MARKED` | Next rule targeting `EACH PLAYER` only hits MARKED players | Cleared at end of `resolve` |
| `CHAINED` | Cannot claim goal cards while held | Cleared by removal cards only |

---

## Edge Case Index

- **Empty deck**: reshuffle discard into deck.
- **Player at 0 chips**: still plays; can't redraw or shop.
- **Joker held with no eligible rule**: hold to next round.
- **Tie at `VP_TO_WIN`**: tie-breaker = highest chips, then highest hand size, then seat.
- **Persistent rule clears its own subject mid-fire**: complete the current effect, then the next iteration finds no match.
- **WHEN rule fires during another rule's resolve**: enqueue; process after the parent rule's effect application completes.
- **Polymorphic card with ambiguous neighbors**: grammar resolver picks the leftmost legal render; documented per-card in `cards.yaml`.

---

## Open Questions / Deferred

- Player count > 4 — defer to post-MVP.
- Bot AI behavior tree — see `ai.md` later.
- Specific effect catalogue and card list — see `cards.yaml`.
- Polymorphic render rules per card — see `grammar.md` (or extend `cards.yaml`).
- Tutorial / onboarding flow — defer.
- Spectator / replay mode — defer.

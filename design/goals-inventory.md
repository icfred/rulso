_Last edited: 2026-05-10 by RUL-28_

# Rulso — Goal-card Inventory

Goal cards live in their own deck (`GameState.goal_deck` / `goal_discard` /
`active_goals[3]`, per `design/state.md`). At any moment, three are face-up.
At the end of every `resolve` phase (step 7 "Goal claim check") the engine
evaluates each active goal's `claim_condition` against each player; matches
award VP per the goal's `claim_kind` and `vp_award`.

This file is the design contract for the M2 goal-card vocabulary. It mirrors
`design/cards-inventory.md` in shape: schema, naming, an M2 starter subset, and
the semantic edge cases the resolver must handle. It does **not** define
chip prices, art, dynamic generation, or drafting.

`design/cards.yaml` (RUL-17) realises a subset of `cards-inventory.md`. A future
M2 engine ticket will realise this inventory similarly — likely as a separate
`design/goals.yaml` once the engine `GoalCard` type lands (see "Schema fit"
below).

---

## Schema

Each goal-card definition has the following fields:

| Field | Type | Purpose |
|---|---|---|
| `id` | string, dotted lowercase | Engine-stable identifier. Used for deck ops, telemetry, replays. Never user-visible. |
| `name` | string, uppercase render-token | What the resolver / UI reads. Bare keyword (e.g. `THE_BANKER`); colon-separated for any future parameters (mirrors `cards-inventory.md`). |
| `claim_condition` | string, predicate id | Lookup key into a registry (`goal_predicates.py` — name TBD). Resolves to a pure function `(player: Player, state: GameState) → bool`. **Not** an AST; mirrors the way `cards.yaml` keeps `name` as a render-token and lets the engine dispatch. |
| `vp_award` | int | Victory points the matching player receives on claim. M2 starter set uses `1` uniformly; the field exists for future tuning. |
| `claim_kind` | enum: `single` \| `renewable` | `single` = first match wins, goal discards, draw replacement. `renewable` = every matching player this round scores `vp_award`; goal stays face-up. |

`claim_condition` resolves to a registered predicate, **not** a string-encoded
expression — the inventory below documents the plain-language intent and
pseudocode body so the engine ticket can transcribe each into a function with
a stable id.

### Schema fit

The current engine `Card` model (`engine/src/rulso/state.py`) carries only
`id / type / name`. Goals need `claim_condition`, `vp_award`, `claim_kind` —
none of which fit `Card`. `GameState.active_goals` is currently typed
`tuple[Card, ...]`; the M2 ticket will introduce a `GoalCard` model and retype
the field, additive to the existing schema. **Flagged for the engine ticket.**

---

## Naming convention

- `id` — engine-stable: `goal.<theme>` (e.g. `goal.banker`). Mirrors
  `cards-inventory.md`'s `<category>.<form>` pattern.
- `name` — render-token, uppercase, single underscore-joined word: `THE_BANKER`,
  `FREE_AGENT`. The leading `THE_` follows the floating-label idiom (`THE LEADER`,
  `THE WOUNDED`); render layer may rewrite to title-case at presentation.
- Predicate ids — snake_case, descriptive: `chips_at_least_75`. Lowercase only
  so they don't collide with `name` (uppercase).

---

## Predicate vocabulary

A goal predicate is a pure function `(player, state) → bool`. It MAY read:

- **Player fields**: `id`, `seat`, `chips`, `vp`, `len(hand)`.
- **Player status**: `status.burn`, `status.mute`, `status.blessed`,
  `status.marked`, `status.chained`.
- **Player history**: `history.rules_completed_this_game`,
  `history.cards_given_this_game`, `history.last_round_was_hit`.
- **GameState**: `round_number`, `players` (read-only iteration — e.g. for
  "highest of all players" comparisons), `dealer_seat`.
- **Computed labels**: the `recompute_labels(state)` mapping, i.e. whether the
  player holds `THE_LEADER`, `THE_WOUNDED`, `THE_GENEROUS`, `THE_CURSED`.

A goal predicate MUST NOT read:

- `persistent_rules` — goal predicates are state-shape claims, not rule-presence
  claims. Reading persistent_rules invites coupling between goal evaluation and
  rule lifecycle that the resolve step ordering (step 6 vs step 7) would have
  to mediate.
- `active_rule` / `revealed_effect` — phase-transient; goals are evaluated
  after rule resolution, not during.
- `deck` / `discard` / `goal_deck` / `goal_discard` — knowledge of what's left
  in the deck shouldn't influence goal claims.
- `last_roll` — phase-transient; rolls happen during build/resolve, goals don't
  reference them.

**Reading the labels mapping** is allowed because labels are pure derivations
of `players` state (see ADR-0001) — semantically equivalent to reading the
underlying fields directly, but more readable.

---

## Claim-check semantics

### When evaluated

Per `design/state.md`, `resolve` step 7. This sits **after** rule effect
application (step 4), persistent-rule firing (step 6), and **before** label
recompute (step 8) and win-check (step 9). Implications:

- A player whose VP just rose to `VP_TO_WIN` from a goal claim wins on the
  same `resolve` (step 9 sees the new VP).
- A goal evaluated against state where the LEADER label has not yet been
  recomputed reads the **previous round's** labels — but the labels in step 8
  are recomputed *after* claim-check, meaning step 7 reads labels that already
  reflect step 4's effect mutations because labels are computed lazily, not
  stored. Effectively: step 7 sees the labels-as-derived-from-current-players.
  No change required to state.md; documenting the implication.

### Evaluation order across goals

Per `state.md`: "Multi-goal triggers in one round: award left-to-right."
`active_goals` is an ordered tuple of length `ACTIVE_GOALS = 3`; index 0 is
leftmost. The engine evaluates goals in `active_goals` index order. Each
goal's claim resolution (including any VP mutation) is committed before the
next goal evaluates — so a player whose VP rises from goal A may newly satisfy
or newly fail goal B's predicate on the same step.

### Tie-break: multiple players satisfy a single-claim goal

State.md says "first matching player claims +VP". Within a single `resolve`
step there is no temporal "first" — all players are evaluated simultaneously.
Pick: **ascending VP, ties broken by ascending chips, ties broken by seat order
starting from `dealer_seat`** (mirroring the shop purchase order in
`Phase: shop` step 2). This is catch-up-leaning, consistent with the shop's
pity-bias.

Worked example: goal `THE_BANKER` (chips ≥ 75) is active. Players P1 (vp=1, chips=80),
P2 (vp=0, chips=78), P3 (vp=1, chips=75) all satisfy. Tie-break:

1. Lowest VP: P2 (vp=0) wins outright.
2. P2 claims +1 VP; goal discards; replacement drawn from `goal_deck`.

If two players tie on VP, ties on chips, then seat order from dealer breaks
the final tie.

### Renewable goals — repeated firing

A renewable goal evaluates against every player every round. Each player whose
predicate returns true at step 7 receives `vp_award`. The goal stays in
`active_goals`; it does NOT discard.

**Same-player repeated firing across rounds**: a renewable goal a player
satisfies for N consecutive rounds awards N × `vp_award` total — once per round.
A renewable goal does NOT fire multiple times within a single resolve step
even if state mutates between sub-steps; step 7 is one evaluation pass.

**Bait-and-switch**: nothing prevents a player from gaming a renewable goal
each round. Balance comes from `vp_award` size and how easy the predicate is
to game. The M2 starter set keeps `vp_award = 1` and pairs the only renewable
goal (`THE_HOARDER`) with a state condition (full hand) that requires actively
playing few chip-discards.

### CHAINED interaction

Per `state.md` status table: "CHAINED: Cannot claim goal cards while held".
At step 7, the engine **skips** any player with `player.status.chained = True`
during goal evaluation — the predicate is not called, and the player is
treated as not matching. Implications:

- A single-claim goal where every matching player is CHAINED stays in
  `active_goals` for the next round (effectively dormant). Behaviour matches
  unassigned-label dormancy in `cards-inventory.md`.
- A renewable goal awards 0 to a CHAINED player even if their state matches.
  When the CHAINED token clears, eligibility resumes the next round.
- Tie-break for single-claim ignores CHAINED players entirely — they're
  filtered out before the VP / chips / seat tie-break runs.

### Replenishment

After a single-claim goal discards (and only after a single-claim discard —
renewable goals never discard from claim-check):

1. Pop the discarded goal from its index in `active_goals`.
2. Draw the top of `goal_deck` into that index.
3. If `goal_deck` is empty: shuffle `goal_discard` into `goal_deck`, then draw.
   (Mirrors `state.md`'s Edge Case Index: "Empty deck: reshuffle discard into
   deck.")
4. If both `goal_deck` and `goal_discard` are empty: leave the slot empty.
   `active_goals` becomes shorter (effectively `len < 3`); the game continues
   with fewer active goals. **Pick**: game continues with fewer goals — does
   NOT terminate. Rationale: terminal "out of goals" condition would prematurely
   end games where some renewable goals remain face-up; the win condition
   (`VP_TO_WIN`) is the canonical terminal trigger.

The engine MUST tolerate `len(active_goals) < ACTIVE_GOALS` after a deck
exhaustion. Goal evaluation iterates the tuple as-is.

---

## M2 starter subset

Total **7 unique goal kinds**. Each pick justified by **what it tests in the
goal-evaluation pipeline**.

### Single-claim (6)

| id | name | claim_condition | vp_award | tests |
|---|---|---|---|---|
| `goal.banker` | `THE_BANKER` | `chips >= 75` | 1 | basic chips-threshold predicate; positive-direction read |
| `goal.debtor` | `THE_DEBTOR` | `chips < 10` | 1 | inverted-direction read; pairs with WOUNDED-style state |
| `goal.builder` | `THE_BUILDER` | `history.rules_completed_this_game >= 3` | 1 | history field read; exercises the rules-completed counter the resolver writes after step 5 |
| `goal.philanthropist` | `THE_PHILANTHROPIST` | `history.cards_given_this_game >= 2` | 1 | second history field; aligns with `THE_GENEROUS` label |
| `goal.survivor` | `THE_SURVIVOR` | `status.burn >= 2` | 1 | status-token read; positive (token-presence) predicate |
| `goal.free_agent` | `THE_FREE_AGENT` | `round_number >= 5 AND status.burn == 0 AND not status.mute AND not status.marked AND not status.chained AND not status.blessed` | 1 | compound predicate; reads round_number from GameState; status-clean (token-absence) predicate; only achievable mid-game (round gate ensures it isn't claimed at start) |

### Renewable (1)

| id | name | claim_condition | vp_award | tests |
|---|---|---|---|---|
| `goal.hoarder` | `THE_HOARDER` | `len(hand) >= HAND_SIZE` (i.e. 7) | 1 | renewable-claim path; awards every round a player ends in `resolve` with full hand; tests `claim_kind=renewable` deck-stay logic |

### Pseudocode predicates

```python
def chips_at_least_75(player, state):    # goal.banker
    return player.chips >= 75

def chips_under_10(player, state):       # goal.debtor
    return player.chips < 10

def rules_completed_at_least_3(player, state):   # goal.builder
    return player.history.rules_completed_this_game >= 3

def gifts_at_least_2(player, state):     # goal.philanthropist
    return player.history.cards_given_this_game >= 2

def burn_at_least_2(player, state):      # goal.survivor
    return player.status.burn >= 2

def free_agent(player, state):           # goal.free_agent
    s = player.status
    return (
        state.round_number >= 5
        and s.burn == 0
        and not s.mute
        and not s.blessed
        and not s.marked
        and not s.chained
    )

def full_hand(player, state):            # goal.hoarder
    from rulso.state import HAND_SIZE
    return len(player.hand) >= HAND_SIZE
```

### Coverage rationale

Six predicate-input categories exercised by 7 goals:

- chips: `THE_BANKER`, `THE_DEBTOR` (both directions)
- hand size: `THE_HOARDER`
- history: `THE_BUILDER`, `THE_PHILANTHROPIST`
- status (positive): `THE_SURVIVOR`
- status (clean): `THE_FREE_AGENT`
- round_number: `THE_FREE_AGENT` (gates compound predicate)

All seven goals read **only** state-shape; none read persistent_rules, decks,
or transient phase fields — exercising the predicate-vocabulary boundary.

`vp_award = 1` for all seven; tuning is deferred. With three face-up at a
time and `VP_TO_WIN = 3`, claiming three single-claims in three rounds is the
fastest theoretical win; renewable `THE_HOARDER` provides the slow-burn
alternative.

---

## Out of scope

- **Chip prices.** Goals are passive face-up cards, not shop items.
- **Art / sprite mapping.** Aesthetic concern.
- **Dynamic generation.** Predicates and `vp_award` are static at deck build.
- **Drafting / mulligan.** No hand-of-goals mechanic; the deck is shuffled
  once at game start.
- **Variable `vp_award`.** All seven starter goals award 1. The schema
  supports variable awards; M2 keeps it simple.
- **Goal-card-grants-status / goal-side-effects.** Goals award VP only;
  mutating other state is reserved for effect cards.
- **Player-targeted goals (e.g. "knock out P3").** Anti-pattern in a
  single-bot MVP — goals reward state achievement, not identity.

---

## Coordination notes

### With RUL-30 (status-tokens spike)

`THE_FREE_AGENT` reads all five status tokens (`burn`, `mute`, `blessed`,
`marked`, `chained`). `THE_SURVIVOR` reads `burn` only. CHAINED interaction
applies to all goal claims (not just CHAINED-naming goals) — see
"Claim-check semantics" above.

Naming alignment: this doc uses `status.burn`, `status.mute`, etc. — matching
`engine/src/rulso/state.py:PlayerStatus`. RUL-30 should not rename these
fields without an ADR.

### With RUL-29 (effects spike)

If RUL-29 introduces an effect kind that directly grants `+VP`, that path is
**separate** from goal claim. Effects mutate state during `resolve` step 4;
goals award VP at step 7. They can stack within the same round (effect grants
VP → step 7 sees the new VP → goal also fires). Documenting now to prevent
"why did the player get +2 VP this round?" confusion.

Naming alignment: effects target VP via the existing `Player.vp` field — the
same field goals read for win-condition purposes. No new VP-resource concept
required.

---

## Design tensions surfaced

1. **`Card` shape doesn't fit goals.** `engine/src/rulso/state.py:Card` lacks
   `claim_condition / vp_award / claim_kind`. M2 engine ticket must introduce
   `GoalCard` (or extend `Card` with optional fields and a discriminator).
   `GameState.active_goals` retypes from `tuple[Card, ...]` to
   `tuple[GoalCard, ...]`. Additive change; flagged for ADR before the engine
   ticket lands.

2. **Predicate registry vs predicate AST.** This doc proposes a string-id
   registry (`predicate_id` → registered Python function). Cleaner than an AST,
   but tightly couples deck data to engine code (renaming a predicate breaks
   YAML). Alternative: a small predicate DSL in YAML
   (`{ field: chips, op: ">=", value: 75 }`). Registry wins for M2 because
   compound predicates (`THE_FREE_AGENT`) and history-field reads stretch a
   DSL fast. Worth a future ADR if the goal-card set grows beyond ~20.

3. **Tie-break for single-claim goals is unspecified in `state.md`.** This
   doc picks ascending-VP / ascending-chips / dealer-seat order, mirroring
   the shop. State.md should be amended (or this pick locked into an ADR) to
   make the tie-break authoritative across resolver implementations.

4. **Renewable goals interact with the win-check uncomfortably.** A
   renewable goal awarding 1 VP per round to multiple players each round
   inflates VP rapidly; the M2 starter keeps to one renewable goal with a
   "play few cards" trade-off. Future tuning: should renewable goals award
   `vp_award` to **only one** matching player per round (closest to single-claim
   semantics), or to all? This doc picks "all matching", but flagging.

5. **Goal exhaustion (both decks empty) doesn't terminate the game.** State.md
   doesn't speak to this; this doc picks "continue with fewer active goals".
   An alternative — terminate the game and pick winner by current VP — would
   constitute a second terminal condition alongside `VP_TO_WIN`. Locking to
   "continue with fewer" via this doc; future ADR if the call needs revisiting.

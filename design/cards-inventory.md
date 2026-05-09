_Last edited: 2026-05-09 by RUL-16_

# Rulso — Card Inventory

The full intended card vocabulary across M1.5 and M2. This is the design contract; `design/cards.yaml` (RUL-17) realises a subset.

This file defines:
- card categories and the slot model they plug into
- naming conventions (`id` and `name`) the resolver will read
- per-card rendering edge cases worth knowing before implementation
- the **M1.5 starter subset** (~20 cards, called out per section)

It does **not** define per-card render rules, full effect catalogues, or YAML schemas.

---

## Slot model (recap of `design/state.md`)

A rule built during `build` has these slots, in order:

| Slot | Filled by | Required? |
|---|---|---|
| `CONDITION` | CONDITION card (only the dealer's first play) | yes |
| `SUBJECT` | SUBJECT card | yes |
| `QUANT` | comparator MODIFIER card | yes for HAS-style; no for ROLLS-style |
| `NOUN` | NOUN card | yes for HAS-style |
| (attached) | operator MODIFIER card → any filled slot | optional |
| (attached) | JOKER → entire rule | optional |

Reads a complete HAS-style rule:
> `[CONDITION] [SUBJECT] HAS [QUANT] [NOUN]` → effect

The verb `HAS` is implicit in the CONDITION template — it isn't its own card.

---

## Naming convention

Two fields per card, read by separate engine layers:

- **`id`** — engine-stable, dotted, lowercase: `<category>.<form>[.N]`. Used for deck ops, telemetry, replays. Never user-visible.
- **`name`** — render-token the resolver / grammar reads to produce text. Uppercase, colon-separated for parameters (`LT:5`, `SEAT:2`). Used in `card.name` lookups by `grammar.py` and `effects.py`.

The resolver reads `card.name` only — `id` exists for pile management.

Numeric parameters in `name` always follow `:` and are decimal integers. Composite names (e.g. `JOKER:PERSIST_WHEN`) use single-colon to keep splitting simple.

---

## CONDITION

Templates that own a rule's lifetime + slot shape. Always the dealer's first play (`build` phase, step 1 of `round_start` setup).

| id | name | kind | slot shape | M1.5 |
|---|---|---|---|---|
| `cond.if` | `IF` | one-shot | `[SUBJECT, QUANT, NOUN]` | ✓ |
| `cond.when` | `WHEN` | persistent, fires once on match | `[SUBJECT, QUANT, NOUN]` | M2 |
| `cond.while` | `WHILE` | persistent, fires repeatedly | `[SUBJECT, QUANT, NOUN]` | M2 |

**Slot affinity**: `CONDITION` slot only.
**`name` semantics**: bare keyword. Resolver dispatches on it for lifetime handling (`rules.py` → `persistence.py` for WHEN/WHILE; one-shot path for IF).
**Render edge case**: WHEN/WHILE rules render the same way as IF when displayed in the persistent area; the keyword is preserved as the leading token.

---

## SUBJECT

Who the rule scopes over. Resolved against `GameState.players` at `resolve` step 2.

### Literal seats (M1.5)

| id | name | resolves to | notes |
|---|---|---|---|
| `subj.seat_0` | `SEAT:0` | `players[0]` | |
| `subj.seat_1` | `SEAT:1` | `players[1]` | |
| `subj.seat_2` | `SEAT:2` | `players[2]` | |
| `subj.seat_3` | `SEAT:3` | `players[3]` | |

**Slot affinity**: `SUBJECT` slot.
**`name` semantics**: `SEAT:N`, where N is parsed as the seat index. Resolver does `int(name.split(":")[1])`.
**Render**: `"SEAT 0"` (UI may substitute the player's display name).
**Edge case**: in `PLAYER_COUNT < 4` lobbies, seats above the count are illegal cards; the deck builder must filter.

### Labels

Computed at `round_start` step 3 / `resolve` step 8 (`labels.py`).

| id | name | resolves to | M1.5 |
|---|---|---|---|
| `subj.leader` | `LEADER` | argmax(vp) — see note | ✓ (M1.5 uses argmax(vp)) |
| `subj.wounded` | `WOUNDED` | argmin(chips) | ✓ |
| `subj.generous` | `GENEROUS` | argmax(cards_given_this_game) | M2 |
| `subj.cursed` | `CURSED` | argmax(burn) | M2 |

**Note — LEADER definition drift**: `state.md` defines LEADER as `argmax(chips)`. RUL-15 specifies LEADER = `argmax(vp)` for M1.5. This is a real divergence. Flagged for ADR before M2 — see "Design tensions" below.

**Slot affinity**: `SUBJECT` slot.
**`name` semantics**: bare label keyword. Resolver looks up the computed seat in `GameState.labels[name]`.
**Render edge case**: label resolves to `None` (unassigned, e.g. ties or zero) → `state.md` says "no matches; effect doesn't fire". Engine must treat this as an empty subject scope, not an error. Persistent rule with unassigned subject sits **dormant**, re-checked next tick.

### Polymorphic (M2)

| id | name | semantics |
|---|---|---|
| `subj.anyone` | `ANYONE` | existential — fires once if **any** player matches; effect targets only the matching player(s) |
| `subj.each` | `EACH_PLAYER` | universal-iterative — evaluates per-player; effect applies to each that matches |

**Render edge case**: `ANYONE` and `EACH_PLAYER` look identical in the rule sentence but produce different scoping. Disambiguation lives in `name`, not in render text. Documented now to prevent future "why are these two different cards?" confusion.

---

## NOUN

What state property the comparator reads. Read by `effects.py` / `rules.py` evaluator.

### M1.5 nouns

| id | name | reads | notes |
|---|---|---|---|
| `noun.chips` | `CHIPS` | `player.chips` | core resource |
| `noun.vp` | `VP` | `player.vp` | also hooks to win condition |

### M2 nouns

| id | name | reads |
|---|---|---|
| `noun.cards` | `CARDS` | `len(player.hand)` |
| `noun.rules` | `RULES` | count of persistent rules naming the player as subject |
| `noun.hits` | `HITS` | count of effects landed on the player this game |
| `noun.gifts` | `GIFTS` | `player.history.cards_given_this_game` |
| `noun.rounds` | `ROUNDS` | `state.round_number` (player-agnostic; treated as broadcast) |
| `noun.burn` | `BURN_TOKENS` | `player.status.burn` |

**Slot affinity**: `NOUN` slot.
**`name` semantics**: bare keyword. Evaluator dispatches `noun_value(player, state, name) → int`.
**Render edge case**: `ROUNDS` is player-agnostic. With `EACH PLAYER`, it still evaluates once globally — every iteration sees the same value. Worth a render note when the rule reads "EACH PLAYER HAS MORE THAN 5 ROUNDS" (semantically odd; legal-but-confusing).

---

## MODIFIER — comparator (QUANT)

Comparator + threshold. Fills the `QUANT` slot.

### Naming

`name` format: `<OP>:<N>` where OP ∈ `{LT, LE, GT, GE, EQ}` and N is the integer threshold.

State.md (`Phase: build`) says comparators carry a dice roll selecting N at play time (1d6 or 2d6 player choice). M1.5 defers dice — comparators have **pre-baked N**, encoded in the card's `name`. M2 reintroduces dice; the dice flow can override or set N at play time, possibly making `name` carry only the OP (e.g. `LT`) and N filled at play. **This is a flagged design tension** — see below.

### M1.5 comparators (5 cards)

| id | name | M1.5 |
|---|---|---|
| `mod.cmp.lt.5` | `LT:5` | ✓ |
| `mod.cmp.lt.20` | `LT:20` | ✓ |
| `mod.cmp.gt.10` | `GT:10` | ✓ |
| `mod.cmp.ge.3` | `GE:3` | ✓ |
| `mod.cmp.eq.5` | `EQ:5` | ✓ |

These pick the 5 distinct OPs; N values vary across the standard win-state range to exercise true / false / boundary cases against starting chips (50) and starting VP (0).

### M2 comparators

The full 5-OP × dice-driven N matrix. Either:
- (a) cards encode OP only (`LT`), N filled at play from dice — fewer card kinds; or
- (b) cards encode OP + dice mode (`LT:1D6`, `LT:2D6`), N filled at play — preserves a "mode" knob in the card itself.

Choice deferred to M2 ADR.

**Slot affinity**: `QUANT` slot only.
**`name` semantics**: split on `:`; first part = OP token; second part = literal N (M1.5) or dice spec (M2).
**Render edge case**: comparator inverts in colloquial readings — "HAS LESS THAN 5" reads naturally, "HAS GREATER THAN OR EQUAL TO 3" reads stiffly. UI may swap to "AT LEAST 3" / "AT MOST 5"; the **`name` token is canonical**, render is cosmetic.

---

## MODIFIER — operator (attached) — M2

Operators don't fill a slot; they **attach** to an already-filled slot, modifying its evaluation. (`build` step 2: "MODIFIER cards … attach to any filled slot".)

| id | name | attaches to | semantics |
|---|---|---|---|
| `mod.op.but` | `BUT` | SUBJECT | exclusion — narrows scope to "everyone except X" when applied to a label or seat |
| `mod.op.and` | `AND` | SUBJECT, NOUN | conjunction — adds a second SUBJECT/NOUN to a scope or read |
| `mod.op.or` | `OR` | SUBJECT, NOUN | disjunction |
| `mod.op.more_than` | `MORE_THAN` | QUANT | combinator with comparator — strict-rather-than-non-strict variant |
| `mod.op.at_least` | `AT_LEAST` | QUANT | non-strict variant override |

All M2. Listed for completeness; final attachment grammar is an M2 ADR.

**Slot affinity**: attached, not slotted. Workers reading the M2 implementation should expect `RuleBuilder.slots[i].modifiers[]` to hold these.
**Render edge case**: operator chaining (`BUT NOT THE LEADER AND THE WOUNDED`) requires precedence rules. Defer to M2 grammar ADR; not in this inventory.

---

## JOKER — M2

JOKERs attach to the rule as a whole (`RuleBuilder.joker_attached`). They convert the rule's lifetime, double its resolution, or mutate scope.

| id | name | M2 effect |
|---|---|---|
| `jkr.persist_when` | `JOKER:PERSIST_WHEN` | converts IF rule into WHEN persistent rule on resolve |
| `jkr.persist_while` | `JOKER:PERSIST_WHILE` | converts IF rule into WHILE persistent rule |
| `jkr.double` | `JOKER:DOUBLE` | rule resolves twice in a row |
| `jkr.echo` | `JOKER:ECHO` | next round, the same rule template fires again with fresh slot fills |

All M2. Deferred to M2 ADR for finalisation; this list is provisional.

**Slot affinity**: rule-level attachment.
**`name` semantics**: prefix `JOKER:` + variant. Resolver dispatches on the suffix.
**Render edge case**: JOKERs render as a sigil beside the rule, not as a word in the rule. Persistent jokers freeze fragments into `persistent_rules` instead of discarding (`resolve` step 5).

---

## M1.5 starter subset

Total **14 unique card kinds** → ~20 physical cards once duplicated for deck size. Each pick justified by **what it tests in the resolver pipeline**.

### CONDITION (1)

| Card | Tests |
|---|---|
| `cond.if` (`IF`) | CONDITION slot fill, rule-shape `[SUBJECT, QUANT, NOUN]`, one-shot lifetime path. WHEN/WHILE deferred. |

### SUBJECT (6)

| Card | Tests |
|---|---|
| `subj.seat_0..3` (`SEAT:0..3`) | literal seat resolution; deterministic SUBJECT scope; covers full 4-player table |
| `subj.leader` (`LEADER`) | label-resolution path; argmax-of-vp lookup (M1.5 redefinition) |
| `subj.wounded` (`WOUNDED`) | label-resolution path; argmin-of-chips lookup; **unassigned-label dormancy** test (when chips tied) |

Six cards because: four seats prove literal scope; LEADER/WOUNDED prove the label pipeline. Other labels (GENEROUS, CURSED) need history fields the engine doesn't yet populate; deferred to M2.

### NOUN (2)

| Card | Tests |
|---|---|
| `noun.chips` (`CHIPS`) | core state read; chip-comparator path |
| `noun.vp` (`VP`) | NOUN dispatch generalises beyond chips; ensures the noun-evaluator is data-driven, not hardcoded; also exercises VP read which the win check already uses |

### MODIFIER — comparator (5)

| Card | Tests |
|---|---|
| `mod.cmp.lt.5` (`LT:5`) | strict less-than, low boundary; matches WOUNDED-type situations |
| `mod.cmp.lt.20` (`LT:20`) | strict less-than, high boundary; many players match early game |
| `mod.cmp.gt.10` (`GT:10`) | strict greater-than; opposite-direction comparison path |
| `mod.cmp.ge.3` (`GE:3`) | non-strict ≥; boundary-equality path; differs from GT |
| `mod.cmp.eq.5` (`EQ:5`) | exact-equality path; rare-match case (proves "no match → no fire") |

Five cards because RUL-15 mandates "5 comparator MODs at varied N" and these cover the 5 distinct OPs. Varied N (3, 5, 10, 20) ensures the resolver handles different match-rate regimes.

### Out of M1.5

- WHEN, WHILE conditions
- ANYONE, EACH PLAYER subjects (polymorphic scope)
- GENEROUS, CURSED, MARKED, CHAINED labels
- All NOUNs beyond CHIPS/VP
- All operator MODIFIERs (AND/OR/BUT/MORE_THAN/AT_LEAST)
- All JOKERs
- Goal cards (separate deck — design lives elsewhere)
- Effect cards (separate deck — design lives elsewhere)
- Dice-driven comparator N (M1.5 bakes N into the card)

---

## Design tensions surfaced (need ADR before M2)

1. **LEADER definition: chips vs vp.** `state.md` says `argmax(chips)`; RUL-15 says `argmax(vp)`. Either change `state.md` to follow RUL-15, or keep `state.md` and update RUL-15. M1.5 implementation will pick one; an ADR should lock it before M2 expands the label set.

2. **Comparator dice flow vs baked N.** `state.md` mandates dice rolls at play for comparator N. M1.5 defers dice and bakes N. M2 must decide whether comparator cards are "OP-only" (dice fills N) or "OP + dice mode" (cards differentiate 1d6 vs 2d6). Affects card-kind count and naming convention.

3. **`ANYONE` vs `EACH_PLAYER` semantics.** Both look like "all players" in render text but diverge in scoping (existential vs universal). Need a written grammar rule before M2 introduces them, or workers will conflate them.

4. **Operator MODIFIER attachment grammar.** `state.md` permits MODIFIERs to "attach to any filled slot" — but precedence and conflict rules (e.g. two `BUT` modifiers on the same SUBJECT) are unspecified. M2 ADR.

5. **Card `name` as canonical token.** This document declares `name` is the resolver's read key (not `id`, not the rendered text). Should be ratified — it has implications for telemetry and replay tooling.

---

## Items deferred from this inventory

- Per-card render rules (which neighbours change rendering, e.g. polymorphic NOUNs). Deferred to M2 grammar work.
- Full effect catalogue beyond the M1.5 stub (+1 VP). M2.
- Goal-card and effect-card decks. Separate inventories; live in their own design docs when scoped.
- Status-token cards (BURN-applier, BLESSED-granter, etc.) — defer; status apply paths are M2.
- SHOP-deck cards. Separate from the rule-fragment deck; out of scope here.
- Card art / sprite mapping. Aesthetic concern, not inventory.
- Per-card chip prices for the SHOP. M2+.

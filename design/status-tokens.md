_Last edited: 2026-05-10 by RUL-30_

# Rulso — Status Tokens

Application sources, interaction matrix, and decay semantics for the 5 status tokens defined in `design/state.md`. Complements (does not replace) `design/state.md` "Status Tokens" + `Phase: round_start` step 2 + `Phase: resolve` step 10.

This file defines:
- the 5 tokens, restated for self-containment
- which cards or effects apply each token (M2 starter subset)
- how tokens interact with each other and with rule resolution
- decay semantics, per token, in one table
- engine-side dispatch recommendation (apply paths vs decay paths)

It does **not** define yaml schemas, render text, or specific effect-card prices.

---

## Recap — the 5 tokens (from `design/state.md`)

| Token | Effect | Lifetime |
|---|---|---|
| `BURN` | Owner loses `BURN_TICK` chips per token at `round_start` step 2 | Persists until removed by clearing card |
| `MUTE` | Cannot play MODIFIER cards next round | Cleared at end of the round it applied |
| `BLESSED` | Next chip-loss effect on bearer is cancelled | Cleared on use |
| `MARKED` | Next rule targeting `EACH PLAYER` only hits MARKED players | Cleared at end of `resolve` |
| `CHAINED` | Cannot claim goal cards while held | Cleared by removal cards only |

State fields (`engine/src/rulso/state.py` `PlayerStatus`):

| Field | Type | Notes |
|---|---|---|
| `burn` | `int` | counter — multiple BURN tokens stack |
| `mute` | `bool` | one-bit; not stackable |
| `blessed` | `bool` | one-bit; not stackable (re-application is a no-op while held) |
| `marked` | `bool` | one-bit; not stackable |
| `chained` | `bool` | one-bit; not stackable |

Only `burn` is countable. The others are toggles — re-applying a token already held is a **no-op** (does not refresh, does not stack). RUL-29 should mirror these field shapes when defining status-applying effect signatures.

---

## Application sources per token

Status-applying cards live in the **effect deck** (revealed at `round_start` step 6 by `rules.enter_round_start`). Status-clearing cards also live in the effect deck. Status apply/clear is **never** wired through SUBJECT/NOUN/MODIFIER fragments and **never** through JOKERs — they are post-resolve effect-card payloads.

### BURN
- **Applies**: targeted-burn effects (e.g. `eff.burn_target`) — adds 1 BURN to one player chosen by effect-card payload (`THE LOSER`, scoped subject, etc.).
- **Clears**: BURN-removal effect cards (`eff.douse`) — sets `burn = 0` on a target. Removing one-by-one is deferred (M2 starter clears all at once).
- **Stack semantics**: counter; multiple applies sum. `BURN_TICK = 5` chips per token at `round_start` step 2.

### MUTE
- **Applies**: silencing effects (e.g. `eff.silence`) — sets `mute = True` on a target. The current round is the **applied** round; the **next** round's MODIFIER plays are blocked. Cleared at the start of the round after that.
- **Clears**: natural-tick only (`round_start` step 2 — already implemented in `rules._apply_burn_tick`). No clearing card.

### BLESSED
- **Applies**: blessing effects (e.g. `eff.bless`) — sets `blessed = True` on a target.
- **Clears**: on-use only — fires when a chip-loss effect targets the bearer. No natural decay; no clearing card.

### MARKED
- **Applies**: marking effects (e.g. `eff.mark`) — sets `marked = True` on one or more targets, payload-defined.
- **Clears**: natural-tick only (`resolve` step 10 — "expire MARKED tokens" already named in `design/state.md`).

### CHAINED
- **Applies**: chaining effects (e.g. `eff.chain`) — sets `chained = True` on a target.
- **Clears**: removal effect cards only (`eff.unchain`). No natural decay.

Coordination with RUL-29 (effect-card spike): the effect-card catalogue should expose status-apply / status-clear payloads keyed on the field names `burn` / `mute` / `blessed` / `marked` / `chained` exactly. Any divergence in token naming silently no-ops the apply path at runtime (per `docs/workflow_lessons.md` "data-doc name check" lesson).

---

## Interaction matrix

### MUTE + tries to play MODIFIER

`design/state.md` build step 2: "MODIFIER cards either fill the QUANT slot (comparators) or attach to any filled slot (operators)". MUTE blocks **all MODIFIER plays** for one round — both comparator and operator MODIFIERs.

**JOKER is its own `CardType` (`CardType.JOKER` ≠ `CardType.MODIFIER`).** A MUTEd player **may** still play a JOKER. Justification: state.md and `state.py` lock JOKER as a separate type; MUTE's effect is "Cannot play MODIFIER" — strict reading by type. Polymorphic-rare JOKERs are valuable enough that broadening MUTE to cover them would silently rebalance. No state.md amendment needed.

**Edge case — MUTEd player has only MODIFIERs and no chips for redraw**: forced pass (`design/state.md` build step 3). MUTE turns the build phase into a forced-pass for that player; rule may fail if a required slot was their responsibility.

**Edge case — MUTEd dealer's first slot fragment**: condition templates are pre-filled by the dealer at `round_start` step 7 (before BUILD), so MUTE applied **this** round does not block the dealer's seed card. MUTE applied **last** round blocks `round_start` step 7 if the seed slot's first-legal card is a MODIFIER and the dealer holds only MODIFIERs of the seed slot type — but seed slot type is currently SUBJECT (per cards-inventory's IF template `[SUBJECT, QUANT, NOUN]`), so the path doesn't fire in M2. **Flag for revisit** if condition templates with a MODIFIER seed slot are added later.

### BLESSED + would lose chips

State.md says: "Next chip-loss effect on bearer is cancelled. Cleared on use." Authoritative reading: BLESSED cancels **the first** chip-loss effect resolved against the bearer. It does **not** cancel:
- BURN tick at `round_start` step 2 (per state.md, BURN tick is the status-tick step, not a "chip-loss effect"). **Flag**: the spec is silent here. Proposed: BLESSED **does** cancel the BURN tick of one round (first applied tick after BLESSED set), then clears. This makes BLESSED a meaningful counter to BURN — otherwise BURN+BLESSED is functionally just BURN.
- DISCARD_COST chips spent voluntarily during BUILD. Voluntary spends are not "chip-loss effects". Confirmed.

**Multiple chip-losses fire same turn**: BLESSED cancels **only the first**. Subsequent chip-losses fire normally. Determination order: by step order in `resolve` (effect application steps) — first chip-loss in resolution order is cancelled, BLESSED clears, the next is paid in full.

**Flag for state.md**: amend "BLESSED" line to read: "Next chip-loss the bearer would suffer (including BURN tick) is cancelled. Cleared on use." Orchestrator decision.

### MARKED + non-MARKED + `EACH PLAYER` rule

State.md: "Next rule targeting `EACH PLAYER` only hits MARKED players".

Three interpretive cases:

| Case | Behaviour |
|---|---|
| ≥1 player MARKED at scope time | Scope narrows to MARKED holders only. Effect applies N times where N = count of MARKED holders. |
| 0 MARKED at scope time, but rule targets `EACH PLAYER` | **Ambiguous in state.md.** Proposed: scope falls back to all players (rule fires normally). MARKED is a "diversion" token; absence of holders should not silently consume the rule. |
| Rule does not target `EACH PLAYER` (e.g. `LEADER`, `SEAT:N`) | MARKED has no effect on this rule. MARKED tokens persist (still cleared at end of `resolve` as normal). |

**Flag for state.md**: amend "MARKED" line to read: "Next rule targeting `EACH PLAYER` is scoped to MARKED players when ≥1 holder; otherwise fires normally on all players. Cleared at end of `resolve`." Orchestrator decision.

**Coordination with RUL-25 (ANYONE / EACH ADR)**: `EACH_PLAYER` is the polymorphic SUBJECT token name in `design/cards-inventory.md`. MARKED interacts with this token specifically — `ANYONE` is unaffected (existential, not universal-iterative). Confirm in ADR-0003.

### CHAINED + goal-claim trigger

State.md: "Cannot claim goal cards while held".

`Phase: resolve` step 7 (goal claim check) is where this enforces. Proposed dispatch:
- For **single-claim goals**: skip CHAINED player when iterating "first matching player". A CHAINED player who would otherwise be the first matcher is bypassed; the next matcher claims. If no non-CHAINED matcher, the goal is unclaimed this round (deferred to next).
- For **renewable goals**: CHAINED holders in the matching set do not receive VP this round; non-CHAINED matchers do. The goal stays.
- **Multi-goal triggers in one round**: CHAINED applies independently per goal — no carry-over.

**Coordination with RUL-28 (goal-card spike)**: RUL-28 owns the goal-claim algorithm. This doc commits to the **gate** (CHAINED skips claim); RUL-28 ratifies the iteration order. If RUL-28 deviates, this doc updates to match.

### BURN tick takes player below 0 chips

State.md edge case: "Player at 0 chips: still plays; can't redraw or shop". `engine/src/rulso/rules.py` `_apply_burn_tick` floors at zero: `max(0, player.chips - BURN_TICK * burn)`. **Confirmed** — chips never go negative; player remains alive; BURN tokens persist past the floor. No state.md amendment.

**Edge case — BURN + 0 chips**: BURN tokens still tick (no-op on chips, but logged). The player's redraw and shop access remain blocked until chips return. BLESSED would cancel the tick once (per the BLESSED amendment proposed above) but BURN tokens themselves are not removed by BLESSED.

---

## Decay semantics — single table

| Token | Decay path | When | Site |
|---|---|---|---|
| `BURN` | clearing card only | effect resolution | `effects.py` (status-clear payload) |
| `MUTE` | natural tick — at `round_start` step 2 of the round **after** the applied round | every round | `rules.enter_round_start` (`_apply_burn_tick` already does this; rename `_apply_status_tick` post-RUL-30) |
| `BLESSED` | on-use — first chip-loss effect to hit bearer cancels the loss and clears the token | resolve effect application | `effects.py` chip-loss helper |
| `MARKED` | natural tick — at `resolve` step 10 ("Cleanup … expire MARKED tokens") | every resolve | `rules.enter_resolve` |
| `CHAINED` | removal card only | effect resolution | `effects.py` (status-clear payload) |

Three decay sites: `round_start` step 2, `resolve` step 10, and chip-loss helper. Two clearing-card decays: `effects.py` apply-clear payloads.

---

## M2 starter subset of status-applying cards

Effect-deck cards. **7 unique kinds**, justifying coverage of the 5 tokens + 2 clearing cards (BURN and CHAINED, the only tokens without natural decay).

| id | name | applies / clears | target | M2 |
|---|---|---|---|---|
| `eff.burn_target` | `BURN_TARGET` | applies BURN +1 | one player (payload-scoped) | ✓ |
| `eff.douse` | `DOUSE` | clears BURN (sets `burn = 0`) | one player | ✓ |
| `eff.silence` | `SILENCE` | applies MUTE | one player | ✓ |
| `eff.bless` | `BLESS` | applies BLESSED | one player | ✓ |
| `eff.mark` | `MARK` | applies MARKED | one or more players (payload-scoped) | ✓ |
| `eff.chain` | `CHAIN` | applies CHAINED | one player | ✓ |
| `eff.unchain` | `UNCHAIN` | clears CHAINED | one player | ✓ |

**Deck placement**: all 7 in the **effect deck** (`GameState.effect_deck`), revealed at `round_start` step 6. Rationale:
- Effect cards land alongside the active rule and modify its outcome — status apply is the natural fit.
- Status-token cards as JOKER variants would bind status apply to JOKER rarity; status interactions are a core mechanic, not a rare tactical option.
- Status-token cards as SHOP-deck cards would gate status access to lowest-VP players — backwards (status is a **disruption** mechanic, not a catch-up reward).

**Out of M2 starter**:
- Per-card chip prices (effect cards aren't priced; they're random reveals).
- Multi-target appliers (e.g. "BURN ALL" — defer; M2 starter is single-target except MARK).
- Self-targeting appliers (e.g. "Mark yourself for next round" — defer).
- Conditional appliers ("If X then BURN Y" — defer; effect cards in M2 starter are unconditional payloads).
- Token transfer ("move BURN from player A to B" — defer; out of scope here).

Coordination with RUL-29 (effect-card spike): RUL-29 owns the **complete** effect-card catalogue. RUL-29 should integrate these 7 status-applying cards as a sub-section of its inventory; this doc names them so RUL-29 doesn't re-derive a different naming.

---

## Engine-side dispatch recommendation

**Recommendation: introduce `engine/src/rulso/status.py`** as the centralised module for all token transitions. Rationale:

- Decay paths span 3 sites (`rules.enter_round_start`, `rules.enter_resolve` cleanup, `effects.py` chip-loss helper). Without centralisation, each site re-implements `PlayerStatus.model_copy(update={...})` calls and the field-name surface drifts.
- Apply paths live in `effects.py` (status-applying effect cards). Centralising the **mutation primitives** in `status.py` lets `effects.py` call `status.apply_burn(player)` rather than open-coding the model_copy.
- The current `_apply_burn_tick` in `rules.py` already conflates BURN tick and MUTE clear — it's correct for M1.5 (only those two transitions exist) but won't scale once MARKED and BLESSED apply/clear land. Rename to `_apply_status_tick` and delegate to `status.py`.

### Module split

| Path | Owner | Functions |
|---|---|---|
| Apply | `status.py` | `apply_burn(player) -> Player`, `apply_mute(player)`, `apply_blessed(player)`, `apply_mark(player)`, `apply_chain(player)`, `clear_burn(player)`, `clear_chain(player)` |
| Decay tick — round_start step 2 | `rules.py` calls `status.tick_round_start(player) -> Player` | clears MUTE; ticks BURN against chips |
| Decay tick — resolve step 10 | `rules.py` calls `status.tick_resolve_end(player) -> Player` | clears MARKED |
| Decay on-use — BLESSED | `effects.py` chip-loss helper calls `status.consume_blessed_or_else(player, loss) -> Player` | if BLESSED set, return player with blessed=False and unchanged chips; else apply chip loss |

### Why not put apply paths in `effects.py`

`effects.py` resolves IF rules — its scope is rule resolution, not effect-card payload application. M2 will introduce an effect-card resolver (parallel to `effects.resolve_if_rule`) that consumes the revealed effect card after the rule resolves. That resolver delegates token transitions to `status.py`. Keeping apply primitives in `status.py` (not `effects.py`) lets the effect-card resolver and the rule resolver both call into the same surface without circular dependencies.

### Why not extend `rules.py` directly

`rules.py` is the phase machine — pure phase-step logic. Token semantics belong adjacent to `state.py` (the data shape) rather than buried in phase orchestration. The rules-side hook is one line: `players = tuple(status.tick_round_start(p) for p in state.players)`.

### Engine-side ticket consequence

The follow-up engine ticket should:
1. Create `engine/src/rulso/status.py` with the surface above.
2. Move `_apply_burn_tick` body into `status.tick_round_start`; rules.py calls it.
3. Add `status.tick_resolve_end` call at `enter_resolve` step 10 (currently no MARKED logic — this is net-new).
4. Add `status.consume_blessed_or_else` integration to `effects.py` (currently no BLESSED logic — this is net-new).
5. Apply-paths land with the effect-card resolver ticket (consumes the 7 cards above as effect-card payloads).

The engine ticket may deviate if it finds a reason — the Stop conditions on this spike permit divergence; this doc records the recommended shape and the why.

---

## Out of scope for RUL-30

- **New status tokens beyond the 5.** Adding tokens (e.g. SHIELDED, BANNED) is a substrate change; would require ADR + state.py field addition.
- **Status-token chaining** (e.g. "BLESSED clears 1 BURN" or "MARKED implies BLESSED"). All 5 tokens are independent in M2.
- **Status-token-aware bots** — M3 (heuristic bots ignore status today; ISMCTS will discover status interactions naturally).
- **Status-token UI / iconography** — M5 (sigils, animations, palette).
- **Status-token telemetry / replay** — M5+.
- **Per-card balancing of effect-card payloads** — defer to playtest.

---

## Flagged for orchestrator decision (state.md amendments)

Per Stop conditions, the following are state.md ambiguities surfaced during this spike. Orchestrator decides whether to amend `design/state.md` or absorb the clarification here.

1. **BLESSED + BURN tick**: should BLESSED cancel the BURN tick at `round_start` step 2? Proposal: yes (token is meaningful only if it counters BURN). Amend state.md's BLESSED line.
2. **MARKED + EACH PLAYER, zero MARKED holders**: should `EACH PLAYER` fire on all players (proposal) or fire on no one (literal reading)? Proposal: fire on all. Amend state.md's MARKED line.
3. **MUTE + future MODIFIER-seed condition templates**: deferred — no current templates seed with MODIFIER, but flag for revisit when WHILE/WHEN templates expand.

This doc proceeds on the proposals. If the orchestrator amends state.md to reject them, this doc updates accordingly.

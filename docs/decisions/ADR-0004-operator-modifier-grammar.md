# ADR-0004 — Operator MODIFIER attachment grammar and precedence

**Status**: Accepted (2026-05-10)

## Context

`design/state.md` Phase: build step 2 permits MODIFIERs to "attach to any filled slot", but precedence and conflict rules are unspecified. `design/cards-inventory.md` "MODIFIER — operator (M2)" lists the operator catalogue (`BUT`, `AND`, `OR`, `MORE_THAN`, `AT_LEAST`) and notes that grammar precedence is deferred to this ADR.

Tension #4 in cards-inventory.md flags four open questions:
- (i) Two `BUT` modifiers on the same SUBJECT — additive or conflicting?
- (ii) Chaining order — does play order matter?
- (iii) Slot-operator compatibility — which operators legally attach to which slots?
- (iv) Interaction with `RuleBuilder.slots[i].modifiers[]` storage — order and dispatch.

Without a written grammar, M2 workers will silently invent rules; replays diverge between deck variants; bot legality checks split. Lock the grammar now.

## Decision

### Slot-operator compatibility matrix

| Operator | SUBJECT | NOUN | QUANT | Semantics |
|---|---|---|---|---|
| `BUT` | ✓ | ✗ | ✗ | Set difference. Subtracts the operator's right-hand SUBJECT-card payload from the slot's current scope. |
| `AND` | ✓ | ✓ | ✗ | SUBJECT: set union. NOUN: multi-noun read combined as **sum**. |
| `OR` | ✓ | ✓ | ✗ | SUBJECT: set union (alias of AND for SUBJECT). NOUN: multi-noun read combined as **max**. |
| `MORE_THAN` | ✗ | ✗ | ✓ | Strictness override: forces `>` (drops the equality from `≥`). |
| `AT_LEAST` | ✗ | ✗ | ✓ | Strictness override: forces `≥` (adds equality to `>`). |

Operators carry no slot-payload of their own except for SUBJECT-targeted ones (`BUT`, `AND`, `OR`), which require a subsequent SUBJECT-card play to supply the right-hand side. M2 build-legality treats a SUBJECT operator as opening a "pending RHS" state on the slot until the next SUBJECT card is played. NOUN operators behave the same way against the NOUN slot. QUANT operators (`MORE_THAN`, `AT_LEAST`) have no RHS — they're standalone modifiers.

### Precedence and chaining

- **Modifiers fold left-to-right in attachment (play) order.** `RuleBuilder.slots[i].modifiers` is an ordered tuple; append-order = play-order. Resolver iterates the tuple and folds.
- **Two `BUT`s on same SUBJECT are additive.** Each subtracts further. `LEADER BUT WOUNDED BUT MARKED` → start with LEADER scope, exclude WOUNDED holders, then exclude MARKED holders. Empty-result → rule resolves "no match".
- **Conflicting QUANT overrides resolve last-write-wins.** If both `MORE_THAN` and `AT_LEAST` attach to the same comparator, the later attachment wins. Engine does not reject; legality permits; replay determinism is preserved by the ordered tuple.
- **No hard cap on operators per slot.** Deck composition tunes expressiveness in M2 (`MAX_PERSISTENT_RULES = 5` already caps the persistent-rule space; per-slot operator count is unbounded).
- **Operator must be legal at play time.** Build-phase legality (extension to `legality.py`): an operator MODIFIER is playable only if (a) at least one slot is filled and (b) the operator's `targets` set intersects the kinds of currently-filled slots and (c) any pending RHS state from a prior operator is satisfied (i.e. you can't play `BUT` on a slot that already has an unresolved `BUT` waiting for its SUBJECT).

### Storage on `RuleBuilder`

`RuleBuilder.slots[i].modifiers: tuple[Card, ...]` already exists in `state.md` Entities. M2 keeps it as the single ordered store; no parallel list. Each entry is the operator-MODIFIER card; SUBJECT/NOUN-card RHS plays for `BUT`/`AND`/`OR` append additional entries to the SAME `modifiers` tuple in pairs (operator, then RHS card). Resolver walks the tuple in pairs for SUBJECT/NOUN ops; standalone for QUANT ops.

## Examples

State: p0=15 chips, p1=12, p2=5, p3=8, vp all 0. LEADER unassigned (vp tie); WOUNDED = {p2}.

1. **`IF LEADER BUT WOUNDED HAS GT 5 CHIPS → +1 VP`**. SUBJECT slot: base scope = LEADER candidate (here all four players, vp tied per ADR-0001). Modifiers = `(BUT, WOUNDED-card)`. Fold: LEADER ∖ WOUNDED → {p0, p1, p3}. Comparator GT 5: all three satisfy → effect fires with scope {p0, p1, p3}.

2. **`IF SEAT 0 HAS GT 5 AT_LEAST CHIPS → +1 VP`**. QUANT slot: comparator = `GT 5`, modifiers = `(AT_LEAST,)`. Fold: AT_LEAST converts to `≥`. Effective check: `chips ≥ 5`. p0=15 satisfies. Render: `"AT LEAST 5 CHIPS"`.

3. **`IF EACH PLAYER HAS GT 5 OR VP CHIPS → +1 VP`**. NOUN slot: base = `CHIPS`, modifiers = `(OR, VP-card)`. Fold for OR-on-NOUN: `max(player.chips, player.vp)`. Per-iteration (ADR-0003 iterative): p0 max=15, p1=12, p2=5, p3=8. GT 5 satisfied by p0, p1, p3. Three iterations fire.

4. **Conflict resolution**: `IF SEAT 0 HAS GT 5 AT_LEAST MORE_THAN CHIPS → +1 VP`. QUANT modifiers = `(AT_LEAST, MORE_THAN)`. Last-write-wins: MORE_THAN re-strictifies to `>`. Net effect identical to original `GT 5`. Permitted, not rejected.

## Consequences

- **`state.py`**: `RuleBuilder.slots[i].modifiers: tuple[Card, ...]` ratified as the canonical ordered store. **Additive only** — no rename, no shape change. SUBJECT/NOUN operators encode their RHS as the *next* tuple entry; QUANT operators stand alone.
- **`effects.py`**: new helpers `_fold_subject_modifiers(scope, modifiers)`, `_fold_noun_modifiers(reads, modifiers)`, `_fold_quant_modifiers(op, modifiers)`. Each consumes the tuple in attachment order. Top-level `resolve_if_rule` invokes them before evaluating the comparator.
- **`grammar.py`**: render walks `(slot.card, slot.modifiers)` and emits operators inline between the slot's base render and the RHS card's render, using a static op-text map (`BUT → "BUT NOT"`, `AND → "AND"`, `OR → "OR"`, `MORE_THAN → "STRICTLY MORE THAN"`, `AT_LEAST → "AT LEAST"`). Order preserved.
- **`cards.yaml`**: operator MODIFIER schema gains `targets: list[Literal["SUBJECT", "NOUN", "QUANT"]]`. Loader (RUL-17) extends to validate `targets` is non-empty and uses only the three slot kinds.
- **`legality.py`**: `legal_actions` extends to compute (a) which operators are playable given the current filled slots, (b) whether the operator awaits a RHS (state machine inside `RuleBuilder`), and (c) which SUBJECT/NOUN cards are playable as RHS to satisfy a pending operator. New helper: `pending_rhs_kind(rule_builder) -> Literal["SUBJECT", "NOUN"] | None`.
- **`bots/random.py`**: legality enumeration grows; bot picks from the enlarged set unchanged. Heuristic remains random-legal at this layer.
- **No render edge case for SUBJECT operators**: render is always `"<base> <op-text> <rhs>"`; e.g. `"LEADER BUT NOT WOUNDED"`. The "BUT NOT" wording resolves the `BUT` ambiguity in colloquial English.
- **Determinism**: replay correctness depends on `slots[i].modifiers` being an ordered tuple. Already specified in `state.md` Entities.
- **Out of scope for this ADR**: status-token-targeted operators (e.g. `EXCEPT MARKED`), JOKER interactions with the modifier tuple, and the "operator-on-empty-slot" case (forbidden by legality, no further design needed).

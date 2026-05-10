# ADR-0003 — `ANYONE` vs `EACH_PLAYER` scoping semantics

**Status**: Accepted (2026-05-10)

## Context

`design/cards-inventory.md` "SUBJECT → Polymorphic (M2)" introduces two SUBJECT cards that look textually identical to "any player" but diverge in scoping:

| id | name | semantics |
|---|---|---|
| `subj.anyone` | `ANYONE` | existential — fires once if any player matches; effect targets matching players |
| `subj.each` | `EACH_PLAYER` | universal-iterative — per-player evaluation; effect applies per match |

`design/state.md` Phase: resolve steps 2-4 define a single-pass model: determine subject scope → evaluate condition → apply effect. That model assumes the rule resolves once. ANYONE/EACH_PLAYER force a divergence — universal-iterative cards must apply the effect N times for N satisfying players, which has knock-on consequences for WHEN cascade triggers (`resolve` step 6) and goal-claim checks (step 7).

Tension #3 in cards-inventory.md flags this: a written grammar rule must lock how each card interacts with `_scope_subject` (already labels-aware after RUL-22) and how multiple matches accumulate effects, before M2 introduces them.

## Decision

Introduce a **scope-mode enum** on every SUBJECT card. M2 dispatches `effects.resolve_if_rule` on this enum.

| Scope mode | Cards | Resolver behaviour |
|---|---|---|
| `singular` | `SEAT:N`, `LEADER`, `WOUNDED`, `GENEROUS`, `CURSED` | Subject scope = 0 or N players (label may resolve to multiple per ADR-0001). Condition evaluated against the scope as a single set; effect fires once with the scope as targets. |
| `existential` | `ANYONE` | Subject candidate = all players. Condition tested per-player; subject scope = subset that satisfies. Rule fires **once** if subset is non-empty; effect targets the satisfying subset. One cascade event. |
| `iterative` | `EACH_PLAYER` | Subject candidate = all players. For each player, evaluate condition independently; if satisfied, apply effect independently. Rule fires **N times** for N satisfying players. N cascade events, in seat order. |

`_scope_subject(state, subject_card)` returns the **candidate set** (the players the rule may target). The resolver branches on `subject_card.scope_mode` for what to do with that set.

The render text for ANYONE and EACH_PLAYER stays distinct: `"ANYONE"` and `"EACH PLAYER"`. The disambiguation lives in the SUBJECT card's `name` token (canonical) and the engine's scope-mode enum. UI may add a glyph (e.g. `∃` vs `∀`) but it's cosmetic.

## Examples

State: p0=15 chips, p1=12, p2=5, p3=8.

1. **`IF ANYONE HAS GT 10 CHIPS → +1 VP`**. Candidate = {p0..p3}. Per-player check: {p0, p1} satisfy. Single fire: p0 and p1 each receive +1 VP from one resolution event. Goal checks (`resolve` step 7) run once. WHEN cascade pool sees one event with two state mutations.

2. **`IF EACH PLAYER HAS GT 10 CHIPS → +1 VP`**. Candidate = {p0..p3}. Iteration 1 (p0): satisfies → +1 VP, cascade event 1, goal check 1. Iteration 2 (p1): satisfies → +1 VP, cascade event 2, goal check 2. Iterations 3-4 (p2, p3): no match, no fire. Net: 2 VP awarded total, 2 cascade events, 2 goal checks.

3. **`IF ANYONE HAS LT 5 CHIPS → +1 VP TO LEADER`**. Candidate = {p0..p3}. Per-player check: {} satisfy (p2 has exactly 5, not less). Empty subset → rule resolves "no match", no effect, per `state.md` semantics.

4. **Cascade divergence**: same effect on the same matching state produces 1× cascade for ANYONE vs N× for EACH_PLAYER. Bot AI and `MAX_PERSISTENT_RULES` interact differently with the two cards. EACH_PLAYER is strictly the higher-cascade option.

## Consequences

- **`state.py`**: SUBJECT card schema gains `scope_mode: Literal["singular", "existential", "iterative"]`. **Additive** per substrate watchpoint — no rename of existing fields. M1.5 cards default to `singular`.
- **`effects.py`**: `_scope_subject` return remains the set of candidate players (it's already labels-aware). New top-level `resolve_if_rule` dispatch on `subject_card.scope_mode`:
  - `singular` → existing path.
  - `existential` → narrow candidate to satisfying subset, fire once with subset as targets.
  - `iterative` → loop satisfying players in seat order, fire effect per player as a discrete resolution event.
- **`grammar.py`**: render maps `subj.anyone.name → "ANYONE"`, `subj.each.name → "EACH PLAYER"`. Render text alone is not a disambiguator — engineers and UI must read scope_mode for behaviour.
- **`cards.yaml`**: M2 SUBJECT cards `subj.anyone` and `subj.each` ship with explicit `scope_mode`. Loader (RUL-17) must accept the new field; missing value defaults to `singular` for back-compat with M1.5 cards.
- **WHEN/WHILE cascades** (`resolve` step 6): `iterative` SUBJECT produces one cascade-eligible event per iteration. The depth-3 recursion cap applies per-cascade, not per-rule — N=4 iterations can each trigger up to depth-3 chains. Acceptable; no cap escalation.
- **Goal claim checks** (`resolve` step 7): run once per fire. `iterative` produces N goal checks; first-match-wins single-claim goals can therefore award up to N VPs in one rule resolution if N players match.
- **`labels.py` interaction**: a label-targeted effect inside an `iterative` rule re-reads labels per iteration if a prior iteration mutated the relevant input (chips for WOUNDED, vp for LEADER). Per-iteration recomputation deferred — `state.md` already says label recompute happens at `round_start` step 3 and `resolve` step 8. **Within-resolve label drift** is a known artefact; revisit if M2 surfaces a correctness bug.
- **Iteration order**: seat order, ascending from `(dealer_seat + 1) % PLAYER_COUNT` to mirror build-phase turn order. Deterministic for replay.

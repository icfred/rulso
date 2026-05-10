# ADR-0005 — `GoalCard` typing for `goal_deck` / `goal_discard` / `active_goals`

**Status**: Accepted (2026-05-10)

## Context

`GameState.goal_deck`, `GameState.goal_discard`, and `GameState.active_goals` were typed as `tuple[Card, ...]` (or `tuple[Card | None, ...]` for `active_goals`) when RUL-26 introduced them. The substrate field placeholders were correct for M1.5 (the deck started empty; nothing read it) but `Card` lacks the goal-specific fields (`claim_condition`, `vp_award`, `claim_kind`) that goal-claim semantics require.

RUL-31 introduced the `GoalCard` model with the missing fields and a `load_goal_cards()` loader. RUL-46 (M2 Phase 3 K) wired the goal-claim engine: `start_game` seeds `goal_deck` and `active_goals` from `load_goal_cards()`, and `enter_resolve` step 7 invokes `goals.check_claims`.

`Card` and `GoalCard` are distinct Pydantic v2 frozen models with non-overlapping field sets. Constructing a `GoalCard` instance and assigning it to a `tuple[Card, ...]` field is rejected at validation time.

`design/goals-inventory.md:319` flagged this guard explicitly:

> `GameState.active_goals` retypes from `tuple[Card, ...]` to `tuple[GoalCard, ...]`. Additive change; flagged for ADR before the engine ticket lands.

The ADR was not authored before RUL-46 dispatched; the worker performed the retype and called it out in the hand-back. This ADR ratifies that choice post-hoc.

## Decision

Retype the three goal-pile fields on `GameState`:

| Field | Old | New |
|---|---|---|
| `goal_deck` | `tuple[Card, ...]` | `tuple[GoalCard, ...]` |
| `goal_discard` | `tuple[Card, ...]` | `tuple[GoalCard, ...]` |
| `active_goals` | `tuple[Card \| None, ...]` | `tuple[GoalCard \| None, ...]` |

Substrate-watchpoint exception: PROJECT_CONTEXT.md says `state.py` edits are additive-only — no renames, retypes, or removals. This retype is a substrate narrowing (`Card` ⊃ `GoalCard` semantically; the new type accepts a strict subset of values previously accepted by the old type) of a field that was empty across all M1 / M1.5 paths. No code anywhere on `main` constructed a `Card` instance for these fields.

The retype is anticipated by RUL-26's introducer (the field was a placeholder for M2) and explicitly called out in RUL-28's spike output.

## Consequences

- **`state.py`**: three field annotations narrow from `Card` to `GoalCard`. Pydantic v2 frozen models continue to validate.
- **`cards.py`**: `load_goal_cards()` already returns `tuple[GoalCard, ...]`; matches the new field type.
- **`goals.py`**: per-round claim hook and predicate registry consume `GoalCard.claim_condition`, `claim_kind`, `vp_award` directly — no field-availability fallback needed.
- **`rules.py`**: `start_game` seeds `goal_deck` and `active_goals` with `GoalCard` instances; `enter_resolve` invokes `goals.check_claims`. No changes to other phase logic.
- **Tests**: `test_smoke_resolution_edges.py` updated its helper from a `Card` stub to a real `GoalCard` because the previous stub never matched the field type post-retype.
- **Forward compatibility**: future goal-card variants extend `GoalCard` (new predicates, new claim_kind enum values, new vp_award shapes). Stays compatible with this ADR.
- **Substrate-watchpoint guidance updated**: PROJECT_CONTEXT.md should reflect that "additive-only" allows narrowing of placeholder fields whose introducer explicitly flagged them as M2 substrate. RUL-26's `goal_*` fields were placeholders; field narrowings of placeholders aren't the kind of substrate change the watchpoint was written to prevent.
- **Process lesson**: ADRs anticipated by spikes should land before the engine ticket dispatches, not after. Captured in `docs/workflow_lessons.md`.

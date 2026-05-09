_Last edited: 2026-05-10 by RUL-22_

# if-resolver — grammar and effect resolution

## Modules

- `rulso.grammar` — renders a `RuleBuilder` into a structured `IfRule`
- `rulso.effects` — scopes, evaluates, and applies an IF rule to `GameState`

---

## Module: `rulso.grammar`

### Public API

| Symbol | Type | Purpose |
|---|---|---|
| `IfRule` | `BaseModel(frozen)` | Structured view: `subject: Card`, `quant: Card`, `noun: Card` |
| `render_if_rule(rule)` | `RuleBuilder → IfRule` | Pull SUBJECT / QUANT / NOUN slots off a built rule |

### Slot contract

`render_if_rule` expects a `RuleBuilder` with `template=IF` and three named slots:

| Slot name | Card type | Semantics |
|---|---|---|
| `SUBJECT` | `SUBJECT` | Whose state is evaluated |
| `QUANT` | `MODIFIER` | Comparator + threshold (see below) |
| `NOUN` | `NOUN` | Which resource to read |

Raises `ValueError` if: template ≠ IF, any slot is missing, type mismatch, or slot unfilled.

No string formatting — narration is out of scope (separate ticket).

---

## Module: `rulso.effects`

### Public API

| Function | Signature | Purpose |
|---|---|---|
| `resolve_if_rule` | `(GameState, RuleBuilder, labels=None) → GameState` | Full resolution pipeline |

`labels` is the optional pre-computed mapping returned by `rulso.labels.recompute_labels`. When omitted, the resolver recomputes from `state` itself. Labels are **never stored on `GameState`** — they enter as a transient parameter (ADR-0001 / `design/state.md` "computed, not stored").

### Pipeline

1. `grammar.render_if_rule(rule)` → `IfRule`
2. `_scope_subject(state, subject, labels)` → `frozenset[player_id]`
3. `_evaluate_has(player, rule)` for each scoped player
4. `_apply_stub_effect(state, matching_ids)` → updated `GameState`

All steps pure; input state never mutated (Pydantic `model_copy`).

---

## SUBJECT scope rules

`subject.name` controls the scope:

| `subject.name` value | Scope | M1.5 behaviour |
|---|---|---|
| `THE LEADER` / `THE WOUNDED` | Label (live, RUL-19) | Look up holders in the `labels` mapping; effect fires for each holder satisfying HAS |
| `THE GENEROUS` / `THE CURSED` / `THE MARKED` / `THE CHAINED` | Label (M2 stub) | Empty frozenset until status / history derivations land — no effect |
| Any other string | Literal player id | Matches the single `Player` with that `id`, or `frozenset()` if absent |

Label names come from `rulso.labels.LABEL_NAMES`. Tie-break policy: ties → all tied players hold the label (ADR-0001).

Polymorphic SUBJECTs (`ANYONE`, `EACH PLAYER`, etc.) arrive with `cards.yaml` in M2.

---

## QUANT card encoding (M1)

QUANT cards use `name = "<OP>:<N>"` (e.g. `"GE:5"`, `"LT:3"`).

| Op | Comparison |
|---|---|
| `GE` | `≥` |
| `GT` | `>` |
| `LE` | `≤` |
| `LT` | `<` |
| `EQ` | `==` |

In the full game, comparator MODIFIERs inline a dice roll (`LastRoll`); `OP:N` is an M1 bridge until that pipeline exists.

---

## NOUN vocabulary (M1)

| `noun.name` | `Player` attribute |
|---|---|
| `CHIPS` | `chips` |
| `VP` | `vp` |

Extend with `cards.yaml` in M2.

---

## M1.5 stub effect

`_apply_stub_effect` adds `+1 VP` to every satisfying player. Awarding VP rather than chips lets games actually terminate at `VP_TO_WIN = 3`. Real effect application (driven by `revealed_effect` and `cards.yaml`) lands in M2.

---

## NotImplementedError / deferred

- Polymorphic SUBJECT resolution (ANYONE, EACH PLAYER) — M2
- WHEN / WHILE persistence — M2
- Real effect catalogue — M2
- M2-stub labels (GENEROUS / CURSED / MARKED / CHAINED) return `frozenset()` until their derivations land in M2; rules referencing them resolve to no matches

---

## Tests

`engine/tests/test_resolver.py`:

- `test_render_if_rule_returns_correct_cards`
- `test_render_if_rule_rejects_non_if_template`
- `test_render_if_rule_rejects_missing_slot`
- `test_render_if_rule_rejects_unfilled_slot`
- `test_scope_single_player_has_true_fires_effect`
- `test_scope_single_player_has_false_skips_effect`
- `test_scope_single_player_unknown_id_is_no_match`
- `test_label_subject_leader_single_holder_fires_for_holder` (RUL-22)
- `test_label_subject_leader_tied_holders_all_fire` (RUL-22)
- `test_label_subject_wounded_empty_player_set_is_no_op` (RUL-22)
- `test_label_subject_wounded_filters_by_has` (RUL-22)
- `test_label_subject_generous_m2_stub_no_effect`
- `test_label_subject_cursed_m2_stub_no_effect`
- `test_label_subject_uses_explicit_labels_argument` (RUL-22)
- `test_label_subject_explicit_labels_match_recompute` (RUL-22)
- `test_has_gt_true` / `test_has_gt_false_on_equal` / `test_has_le_true` / `test_has_lt_true` / `test_has_eq_true`
- `test_noun_vp`
- `test_resolve_if_rule_returns_new_state_and_does_not_mutate_input`

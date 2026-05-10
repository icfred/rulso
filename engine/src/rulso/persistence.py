"""WHEN / WHILE persistent-rule dispatch surface (RUL-26 scaffolding).

Three pure-function entry points the round-flow machine wires through. Real
firing logic lands with the M2 persistence-rule features; this module ships the
M2 substrate so feature tickets fan out without colliding here.

* :func:`tick_while_rules` — re-evaluate every WHILE rule at ``round_start``.
* :func:`check_when_triggers` — fire matching WHEN rules after ``resolve``.
* :func:`add_persistent_rule` — append a WHEN/WHILE rule, evicting the oldest
  when at ``MAX_PERSISTENT_RULES`` capacity (per ``design/state.md``).

``tick_while_rules`` and ``check_when_triggers`` accept a pre-computed labels
mapping (the shape returned by :func:`rulso.labels.recompute_labels`) so callers
that already hold the round's labels avoid recomputing. When the input state
carries no persistent rules, both functions return the input unchanged — this
preserves M1.5 behaviour through the new wiring.

All functions are pure; the input ``GameState`` is never mutated.
"""

from __future__ import annotations

from rulso.state import (
    MAX_PERSISTENT_RULES,
    GameState,
    PersistentRule,
    RuleBuilder,
    RuleKind,
)


def tick_while_rules(
    state: GameState,
    labels: dict[str, frozenset[str]],
) -> GameState:
    """Step 4 of ``round_start``: re-evaluate every active WHILE rule.

    Stub: returns ``state`` unchanged. Real per-WHILE-rule evaluation and
    effect application land with the M2 WHILE-rule feature ticket.
    """
    if not state.persistent_rules:
        return state
    return state


def check_when_triggers(
    state: GameState,
    labels: dict[str, frozenset[str]],
) -> GameState:
    """Step 6 of ``resolve``: fire matching WHEN rules after effect application.

    Stub: returns ``state`` unchanged. Real WHEN-trigger detection (with FIFO
    queueing and the depth-3 recursion cap from ``design/state.md``) lands with
    the M2 WHEN-rule feature ticket.
    """
    if not state.persistent_rules:
        return state
    return state


def add_persistent_rule(
    state: GameState,
    rule: RuleBuilder,
    kind: RuleKind,
) -> GameState:
    """Append a WHEN/WHILE rule to ``state.persistent_rules``, evicting if full.

    Capacity is ``MAX_PERSISTENT_RULES``; overflow drops the oldest entry
    (FIFO eviction per ``design/state.md`` "Persistent Rules — Lifetimes").

    ``kind`` must be ``RuleKind.WHEN`` or ``RuleKind.WHILE``; ``IF`` rules
    are one-shot and never persist.
    """
    if kind not in (RuleKind.WHEN, RuleKind.WHILE):
        raise ValueError(f"persistent rules must be WHEN or WHILE, got {kind}")
    creator = state.players[state.dealer_seat].id if state.players else ""
    new_rule = PersistentRule(
        kind=kind,
        rule=rule,
        created_round=state.round_number,
        created_by=creator,
    )
    existing = state.persistent_rules
    if len(existing) >= MAX_PERSISTENT_RULES:
        existing = existing[1:]
    return state.model_copy(update={"persistent_rules": existing + (new_rule,)})

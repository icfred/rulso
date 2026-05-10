"""WHEN / WHILE persistent-rule dispatch surface.

Three pure-function entry points the round-flow machine wires through. RUL-32
ships the real fire logic for ``tick_while_rules`` and ``check_when_triggers``;
``add_persistent_rule`` is unchanged from RUL-26.

* :func:`tick_while_rules` — re-evaluate every WHILE rule at ``round_start``.
* :func:`check_when_triggers` — fire matching WHEN rules after ``resolve``.
* :func:`add_persistent_rule` — append a WHEN/WHILE rule, evicting the oldest
  when at ``MAX_PERSISTENT_RULES`` capacity (per ``design/state.md``).

Effect application is currently a Phase 2 stub: WHEN/WHILE rules promote their
template to ``IF`` and reuse :func:`rulso.effects.resolve_if_rule`, which
applies the M1.5 +1 VP stub. The Phase 3 effect-dispatcher will replace this
with ``revealed_effect``-driven dispatch and add the "fire on relevant state
changes" hook for WHILE rules called out in ``design/state.md``.

All functions are pure; the input ``GameState`` is never mutated.
"""

from __future__ import annotations

from rulso import effects
from rulso.labels import recompute_labels
from rulso.state import (
    MAX_PERSISTENT_RULES,
    GameState,
    PersistentRule,
    RuleBuilder,
    RuleKind,
)

# Cap on chained WHEN fires per resolve, per design/state.md "Edge Case Index —
# WHEN rule fires during another rule's resolve". Prevents runaway chains where
# each fire's state mutation re-arms another WHEN.
_MAX_WHEN_RECURSION_DEPTH: int = 3


def tick_while_rules(
    state: GameState,
    labels: dict[str, frozenset[str]],
) -> GameState:
    """Step 4 of ``round_start``: re-evaluate every active WHILE rule.

    Walks ``persistent_rules`` in insertion order. For each WHILE rule, fires
    the effect when the SUBJECT scope is non-empty AND HAS evaluates true.
    WHILE rules persist after firing — they leave ``persistent_rules`` only
    via removal cards (M2-out-of-scope) or game end.

    A rule whose SUBJECT references an unassigned label sits dormant: the
    ``effects.resolve_if_rule`` empty-scope path returns state unchanged and
    the rule stays in ``persistent_rules`` for the next tick.

    ``labels`` is the round's pre-computed label mapping; intra-tick fires
    that mutate state may shift label holders (e.g. LEADER on VP gain), so
    labels are recomputed after each fire so subsequent WHILE rules see the
    current state.

    Phase 3 will add the "fire on relevant state changes" hook from
    ``design/state.md``; today only the round_start tick triggers re-evaluation.
    """
    if not state.persistent_rules:
        return state
    new_state = state
    current_labels = labels
    for persistent in state.persistent_rules:
        if persistent.kind is not RuleKind.WHILE:
            continue
        fired = _try_fire_persistent_rule(new_state, persistent.rule, current_labels)
        if fired is not new_state:
            new_state = fired
            current_labels = recompute_labels(new_state)
    return new_state


def check_when_triggers(
    state: GameState,
    labels: dict[str, frozenset[str]],
) -> GameState:
    """Step 6 of ``resolve``: fire matching WHEN rules after effect application.

    Walks ``persistent_rules`` in insertion (FIFO) order. The first WHEN whose
    scope is non-empty AND HAS evaluates true fires its effect, is discarded
    from ``persistent_rules``, and the walk recurses — the firing may have
    mutated state in a way that satisfies a sibling WHEN. Recursion is capped
    at ``_MAX_WHEN_RECURSION_DEPTH`` (3) per ``design/state.md`` "Edge Case
    Index"; rules beyond the cap remain in ``persistent_rules`` for the next
    resolve.

    Dormant-label SUBJECTs (label currently held by no player) and unknown-id
    SUBJECTs both produce empty scope → no fire → rule stays.
    """
    if not state.persistent_rules:
        return state
    return _check_when_recursive(state, labels, depth=0)


def _check_when_recursive(
    state: GameState,
    labels: dict[str, frozenset[str]],
    depth: int,
) -> GameState:
    if depth >= _MAX_WHEN_RECURSION_DEPTH:
        return state
    for i, persistent in enumerate(state.persistent_rules):
        if persistent.kind is not RuleKind.WHEN:
            continue
        fired = _try_fire_persistent_rule(state, persistent.rule, labels)
        if fired is state:
            continue
        new_persistent = state.persistent_rules[:i] + state.persistent_rules[i + 1 :]
        fired = fired.model_copy(update={"persistent_rules": new_persistent})
        return _check_when_recursive(fired, recompute_labels(fired), depth + 1)
    return state


def _try_fire_persistent_rule(
    state: GameState,
    rule: RuleBuilder,
    labels: dict[str, frozenset[str]],
) -> GameState:
    """Apply a WHEN/WHILE rule's effect via the IF resolver (Phase 2 stub).

    Phase 3 effect-dispatcher will replace this with ``revealed_effect``-driven
    dispatch. For now WHEN/WHILE share the IF rule shape (SUBJECT/QUANT/NOUN
    slots), so the rule is promoted to ``RuleKind.IF`` and routed through
    :func:`effects.resolve_if_rule` — which renders, scopes, evaluates HAS,
    and applies the +1 VP stub. Identity comparison against the input state
    tells callers whether the rule fired.
    """
    if_shaped = rule.model_copy(update={"template": RuleKind.IF})
    return effects.resolve_if_rule(state, if_shaped, labels)


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

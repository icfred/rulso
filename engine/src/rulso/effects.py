"""IF rule effect resolver and revealed-effect dispatcher.

Two related public entry points:

* :func:`resolve_if_rule` — scopes a rule's SUBJECT, evaluates its HAS clause,
  and dispatches the round's revealed effect to every matching player.
* :func:`dispatch_effect` — parses a revealed effect card's ``name`` per
  ``design/effects-inventory.md`` (``<KIND>[:<MAG>][@<TARGET_MOD>]``), looks up
  a handler in the module-level registry, and applies it to the resolved
  target set.

A registry hook (:func:`register_effect_kind`) lets later Phase-3 tickets
attach status / JOKER handlers without serial dependency on this ticket.

Operator MODIFIER fold (RUL-43, ADR-0004):
  * SUBJECT-targeted ops (``BUT``, ``AND``, ``OR``) walk
    ``Slot.modifiers`` in (op, rhs-card) pairs and fold over the base scope —
    ``BUT`` = set difference, ``AND``/``OR`` = set union (per ADR table).
  * NOUN-targeted ops (``AND``, ``OR``) walk the NOUN slot's modifiers in
    (op, rhs-card) pairs — ``AND`` = sum, ``OR`` = max.
  * QUANT-targeted ops (``MORE_THAN``, ``AT_LEAST``) are standalone (no RHS);
    they override the comparator's strictness — ``MORE_THAN`` strips equality
    (GE→GT, LE→LT), ``AT_LEAST`` adds equality (GT→GE, LT→LE). Conflicts
    resolve last-write-wins.
  * Singular path (no operator MODIFIERs on any slot) is byte-identical to
    the M1.5 resolver.

Pure functions: input ``GameState`` is never mutated; a new state is returned.
"""

from __future__ import annotations

from collections.abc import Callable

from rulso.grammar import IfRule, render_if_rule
from rulso.labels import LABEL_NAMES, recompute_labels
from rulso.state import Card, GameState, Player, RuleBuilder

# M1 NOUN vocabulary — render-name → ``Player`` attribute holding the value.
_PLAYER_RESOURCE_NOUNS: dict[str, str] = {"CHIPS": "chips", "VP": "vp"}

# RUL-44 M2 polymorphic NOUN render-names. Resolved by ``_noun_value`` against
# fields outside ``Player.{chips,vp}`` (hand size, history counters, status,
# state-level reads). ``HITS`` reads ``PlayerHistory.hits_taken_this_game``
# (RUL-26).
_M2_NOUN_NAMES: frozenset[str] = frozenset(
    {"CARDS", "RULES", "HITS", "GIFTS", "ROUNDS", "BURN_TOKENS"}
)

# Target-modifier tokens parsed from ``name`` after ``@``. The default
# (no ``@`` suffix) is ``all_matched``. Token vocabulary tracks
# ``design/effects-inventory.md`` "target_modifier semantics".
_TARGET_MOD_TOKENS: dict[str, str] = {
    "EXCEPT_MATCHED": "everyone_except_matched",
    "ACTIVE_SEAT": "active_seat_only",
    "DEALER": "dealer_only",
}

# Status-applying / status-clearing kinds raise NotImplementedError until
# RUL-40 (M2 Phase 3 E) wires the ``Player.status`` mutations.
_STATUS_PENDING_KINDS: frozenset[str] = frozenset(
    {
        "APPLY_BURN",
        "APPLY_MUTE",
        "APPLY_BLESSED",
        "APPLY_MARKED",
        "APPLY_CHAINED",
        "CLEAR_BURN",
        "CLEAR_MUTE",
        "CLEAR_BLESSED",
        "CLEAR_MARKED",
        "CLEAR_CHAINED",
    }
)


# --- Registry ---------------------------------------------------------------

EffectHandler = Callable[[GameState, frozenset[str], int], GameState]
"""Signature for an effect-kind handler: ``(state, targets, magnitude) -> state``.

``targets`` is the resolved target set (after ``target_modifier`` rewrite).
``magnitude`` defaults to 1 when the effect card omits ``:<MAG>``.
"""


_EFFECT_HANDLERS: dict[str, EffectHandler] = {}


def register_effect_kind(kind: str, handler: EffectHandler) -> None:
    """Register an effect handler for ``kind``. Last write wins.

    Parallel-safe extension hook for RUL-40 (status apply/clear) and RUL-44
    (JOKER attachment) — they import this module and register their handlers
    at import time without modifying this file.
    """
    _EFFECT_HANDLERS[kind] = handler


# --- Public entry points ----------------------------------------------------

# RUL-42 (G): OP-only comparator MODIFIERs per ADR-0002. The card encodes the
# operator only; N is drawn at play time from 1d6 or 2d6 (player choice). The
# rolled value lives on ``state.last_roll`` and is baked into a transient
# ``OP:N`` quant card before evaluation — leaves the slot's ``filled_by``
# untouched (so discard sees the original OP-only card on resolve cleanup).
_OP_ONLY_COMPARATOR_NAMES: frozenset[str] = frozenset({"LT", "LE", "GT", "GE", "EQ"})

# RUL-43 (ADR-0004): operator MODIFIER catalogue. Operator MODIFIERs share
# ``CardType.MODIFIER`` with comparators; their semantics fork on ``card.name``.
OPERATOR_MODIFIER_NAMES: frozenset[str] = frozenset({"BUT", "AND", "OR", "MORE_THAN", "AT_LEAST"})

# RUL-45 (J): JOKER:DOUBLE token. Kept local so resolve_if_rule can detect it
# without importing rules.py (which would create a circular import); the
# string is duplicated by design — rules.py owns the canonical catalogue.
_JOKER_DOUBLE_NAME: str = "JOKER:DOUBLE"


def is_operator_modifier(card: Card) -> bool:
    """Return ``True`` if ``card`` is an operator MODIFIER (ADR-0004).

    Operator MODIFIERs live alongside comparator MODIFIERs in the ``MODIFIER``
    type but are routed through ``Slot.modifiers`` (attached) rather than
    ``Slot.filled_by`` (filled). Callers that walk hands by ``card.type`` use
    this predicate to skip them.
    """
    return card.name in OPERATOR_MODIFIER_NAMES


def resolve_if_rule(
    state: GameState,
    rule: RuleBuilder,
    labels: dict[str, frozenset[str]] | None = None,
) -> GameState:
    """Resolve an IF rule against ``state`` and return the updated state.

    Pipeline:
      1. Render the rule (``grammar.render_if_rule``).
      2. Scope SUBJECT → frozenset of candidate player ids (label-aware,
         scope-mode aware), then fold any SUBJECT-targeted operator MODIFIERs
         (BUT / AND / OR per ADR-0004).
      3. Evaluate ``HAS [QUANT] [NOUN]`` for each candidate player, applying
         the NOUN- and QUANT-targeted operator MODIFIERs.
      4. Fire ``state.revealed_effect`` per ``Card.scope_mode`` (ADR-0003):
         * ``singular`` — fire once with the satisfying subset as targets.
         * ``existential`` (``ANYONE``) — fire once with the satisfying subset
           as targets; rule does not fire if the subset is empty.
         * ``iterative`` (``EACH_PLAYER``) — fire once per satisfying player
           in seat order from ``state.active_seat``; each fire is a discrete
           cascade event with that single player as targets.

    ``labels`` is an optional pre-computed label-name → frozenset[player_id]
    mapping (the shape returned by ``rulso.labels.recompute_labels``). When
    omitted, the resolver recomputes from ``state``. Pass it explicitly when a
    caller already holds the round's labels (e.g. ``rules.enter_resolve``)
    to avoid double computation. Labels are never stored on ``GameState``
    (per ADR-0001 / ``design/state.md`` "computed, not stored").

    SUBJECTs scoped to an empty candidate set, HAS-false branches across
    every candidate, and a missing ``revealed_effect`` all return the input
    state unchanged.
    """
    structured = render_if_rule(rule)
    # RUL-42 (G): OP-only comparator → bake the rolled N into a transient
    # quant card per ADR-0002. The slot's filled_by is left untouched.
    structured = _bake_quant_dice(structured, state)
    if labels is None:
        labels = recompute_labels(state)
    base_scope = _scope_subject(state, structured.subject, labels)
    scoped = _fold_subject_modifiers(state, base_scope, structured.subject_modifiers, labels)
    if not scoped:
        return state
    mode = structured.subject.scope_mode
    if mode == "iterative":
        # ADR-0003: one discrete fire per matching player, seat order from
        # ``state.active_seat``. Each fire is its own cascade event.
        result = state
        for player in _seat_ordered_players(state):
            if player.id in scoped and _evaluate_has(state, player, structured):
                result = dispatch_effect(result, result.revealed_effect, frozenset({player.id}))
        return result
    # ``singular`` and ``existential`` (ADR-0003): single fire with the
    # satisfying subset as targets. Empty subset → rule does not fire.
    matching = frozenset(
        p.id for p in state.players if p.id in scoped and _evaluate_has(state, p, structured)
    )
    if not matching:
        return state
    state = dispatch_effect(state, state.revealed_effect, matching)
    # RUL-45 (J): JOKER:DOUBLE — re-dispatch the same effect on the same
    # matching set, mirroring the H-style post-fold wrapper rather than
    # touching the dispatcher core. The matching set is frozen at first
    # dispatch — DOUBLE doubles the effect, not the scope evaluation.
    if rule.joker_attached is not None and rule.joker_attached.name == _JOKER_DOUBLE_NAME:
        state = dispatch_effect(state, state.revealed_effect, matching)
    return state


def dispatch_effect(
    state: GameState,
    revealed_effect: Card | None,
    scope: frozenset[str],
) -> GameState:
    """Apply ``revealed_effect`` to ``scope`` and return the new state.

    Parses ``revealed_effect.name`` as ``<KIND>[:<MAG>][@<TARGET_MOD>]`` per
    ``design/effects-inventory.md``. The ``KIND`` token selects a handler from
    the module registry; the optional ``MAG`` is forwarded to the handler
    (defaulting to ``1``); the optional ``TARGET_MOD`` rewrites ``scope`` to
    the actual target set before the handler runs.

    Returns ``state`` unchanged when:
      * ``revealed_effect`` is ``None`` (no card revealed yet)
      * ``KIND`` is ``NOOP``
      * the resolved target set is empty

    Raises:
      * :class:`NotImplementedError` for status-applying / -clearing kinds
        (wired by RUL-40 in this Phase 3 fan).
      * :class:`ValueError` for malformed ``name`` tokens or unknown kinds.
    """
    if revealed_effect is None:
        return state
    kind, magnitude, target_mod = _parse_effect_name(revealed_effect.name)
    handler = _EFFECT_HANDLERS.get(kind)
    if handler is None:
        # Status kinds are pending RUL-40; until registered, raise the
        # phase-3 stub so the dispatcher fails loudly rather than silently
        # no-op'ing a status-applying card. RUL-40 registers a real handler
        # and lifts the raise; the registry check above takes precedence.
        if kind in _STATUS_PENDING_KINDS:
            raise NotImplementedError("M2 Phase 3 E: status apply")
        raise ValueError(f"unknown effect kind {kind!r} in {revealed_effect.name!r}")
    targets = _resolve_targets(state, scope, target_mod)
    if not targets:
        return state
    return handler(state, targets, magnitude)


# --- Parsing ----------------------------------------------------------------


def _parse_effect_name(name: str) -> tuple[str, int, str]:
    """Parse ``<KIND>[:<MAG>][@<TARGET_MOD>]`` → (kind, magnitude, target_mod).

    Default magnitude is ``1`` when ``:<MAG>`` is absent. Default
    ``target_mod`` is ``"all_matched"`` when ``@<TARGET_MOD>`` is absent.
    """
    body, _, target_token = name.partition("@")
    kind, sep, mag_str = body.partition(":")
    if not kind:
        raise ValueError(f"effect name {name!r} has empty KIND")
    if sep and not mag_str:
        raise ValueError(f"effect name {name!r} has ':' with no magnitude")
    magnitude = 1
    if mag_str:
        try:
            magnitude = int(mag_str)
        except ValueError as e:
            raise ValueError(f"effect name {name!r} has non-integer magnitude") from e
        if magnitude < 0:
            raise ValueError(f"effect name {name!r} has negative magnitude")
    target_mod = "all_matched"
    if target_token:
        token_mod = _TARGET_MOD_TOKENS.get(target_token)
        if token_mod is None:
            raise ValueError(f"effect name {name!r} has unknown target token {target_token!r}")
        target_mod = token_mod
    return kind, magnitude, target_mod


def _resolve_targets(
    state: GameState,
    matched: frozenset[str],
    target_mod: str,
) -> frozenset[str]:
    """Rewrite the matched-player set per ``target_modifier``.

    ``all_matched`` → input set unchanged.
    ``everyone_except_matched`` → all players ``\\setminus`` matched.
    ``active_seat_only`` → ``{players[active_seat].id}``.
    ``dealer_only`` → ``{players[dealer_seat].id}``.
    """
    if target_mod == "all_matched":
        return matched
    if target_mod == "everyone_except_matched":
        return frozenset(p.id for p in state.players if p.id not in matched)
    if target_mod == "active_seat_only":
        if not state.players:
            return frozenset()
        return frozenset({state.players[state.active_seat].id})
    if target_mod == "dealer_only":
        if not state.players:
            return frozenset()
        return frozenset({state.players[state.dealer_seat].id})
    raise ValueError(f"unknown target_modifier {target_mod!r}")


# --- Built-in handlers ------------------------------------------------------


def _gain_chips(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
    return _patch_players(
        state,
        targets,
        lambda p: p.model_copy(update={"chips": p.chips + magnitude}),
    )


def _lose_chips(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
    # RUL-49: route per-player chip loss through ``status.consume_blessed_or_else``
    # so each target's BLESSED is consumed independently. ``magnitude <= 0`` is
    # a no-op (consuming BLESSED on a zero-loss event would be a silent bug).
    if magnitude <= 0:
        return state
    return _patch_players(
        state,
        targets,
        lambda p: status.consume_blessed_or_else(p, magnitude),
    )


def _gain_vp(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
    return _patch_players(
        state,
        targets,
        lambda p: p.model_copy(update={"vp": p.vp + magnitude}),
    )


def _lose_vp(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
    return _patch_players(
        state,
        targets,
        lambda p: p.model_copy(update={"vp": max(0, p.vp - magnitude)}),
    )


def _draw(state: GameState, targets: frozenset[str], magnitude: int) -> GameState:
    """Each target draws ``magnitude`` cards from ``state.deck``.

    Deck-empty handling: drawing stops when the deck runs out — a bare draw
    has no rng for a discard reshuffle (the resolve-step refill at
    ``rules.enter_resolve`` step 12 owns that path with its rng-injected
    shuffle). A future ticket can add an explicit rng forwarding hook if the
    starter ``DRAW:2`` ever needs to deplete the deck mid-resolve.
    """
    if magnitude <= 0:
        return state
    deck = list(state.deck)
    new_players: list[Player] = []
    for player in state.players:
        if player.id not in targets or not deck:
            new_players.append(player)
            continue
        # Pop one-at-a-time to mirror rules._refill_hands' deck.pop() ordering
        # — drawn top-card-first so hand append order is "top, then below".
        take = min(magnitude, len(deck))
        drawn = tuple(deck.pop() for _ in range(take))
        new_players.append(player.model_copy(update={"hand": player.hand + drawn}))
    return state.model_copy(update={"players": tuple(new_players), "deck": tuple(deck)})


def _noop(state: GameState, _targets: frozenset[str], _magnitude: int) -> GameState:
    return state


register_effect_kind("GAIN_CHIPS", _gain_chips)
register_effect_kind("LOSE_CHIPS", _lose_chips)
register_effect_kind("GAIN_VP", _gain_vp)
register_effect_kind("LOSE_VP", _lose_vp)
register_effect_kind("DRAW", _draw)
register_effect_kind("NOOP", _noop)

# RUL-40: import status for its side-effect — :mod:`rulso.status` registers
# APPLY_BURN / CLEAR_BURN / APPLY_MUTE / APPLY_BLESSED / APPLY_MARKED /
# APPLY_CHAINED / CLEAR_CHAINED handlers against the registry above. Placed
# at module-bottom so ``register_effect_kind`` is fully defined when
# ``status.py`` runs its registration block (avoids the partial-import
# bootstrap problem).
from rulso import status  # noqa: E402

# --- Internals --------------------------------------------------------------


def _patch_players(
    state: GameState,
    targets: frozenset[str],
    patch: Callable[[Player], Player],
) -> GameState:
    """Apply ``patch`` to every player in ``targets``; return new state."""
    new_players = tuple(patch(p) if p.id in targets else p for p in state.players)
    return state.model_copy(update={"players": new_players})


def _scope_subject(
    state: GameState,
    subject: Card,
    labels: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Resolve a SUBJECT card to the set of candidate player ids.

    Branches on ``subject.scope_mode`` (RUL-41, ADR-0003):
      * ``singular`` (default) — literal seat or label lookup. ``subject.name``
        in :data:`labels.LABEL_NAMES` looks up the round's holders (live for
        LEADER/WOUNDED/GENEROUS/CURSED; empty for the M2-stubbed MARKED and
        CHAINED). Any other value is treated as a literal player id; the
        candidate set is the matching player or ``frozenset()`` if absent.
      * ``existential`` (``ANYONE``) / ``iterative`` (``EACH_PLAYER``) — every
        seat is a candidate. ``resolve_if_rule`` then iterates the candidates
        in seat order from ``state.active_seat`` and applies scope-mode-specific
        firing semantics.
    """
    if subject.scope_mode in ("existential", "iterative"):
        return frozenset(p.id for p in state.players)
    if subject.name in LABEL_NAMES:
        return labels.get(subject.name, frozenset())
    return frozenset(p.id for p in state.players if p.id == subject.name)


def _seat_ordered_players(state: GameState) -> tuple[Player, ...]:
    """Players ordered by seat ascending, starting at ``state.active_seat``.

    ``rules.start_game`` lays ``state.players`` out so position == seat;
    ``state.active_seat`` is the position index of the active player. For an
    empty roster this returns an empty tuple. The wrap-around ordering is
    deterministic, which keeps iterative resolution replay-stable.
    """
    n = len(state.players)
    if n == 0:
        return ()
    start = state.active_seat % n
    return tuple(state.players[(start + i) % n] for i in range(n))


def _fold_subject_modifiers(
    state: GameState,
    base: frozenset[str],
    modifiers: tuple[Card, ...],
    labels: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Fold SUBJECT-targeted operator MODIFIERs over ``base`` (ADR-0004).

    ``modifiers`` is read in (op, rhs-card) pairs. ``BUT`` subtracts the RHS's
    own scope from the result; ``AND`` and ``OR`` union it in (per ADR-0004
    table — both are "set union" on SUBJECT, ``OR`` aliasing ``AND``). Empty
    ``modifiers`` returns ``base`` unchanged — the singular path.
    """
    if not modifiers:
        return base
    result = base
    i = 0
    while i < len(modifiers):
        op = modifiers[i]
        if op.name not in {"BUT", "AND", "OR"}:
            raise ValueError(f"unexpected SUBJECT operator {op.name!r}; expected one of BUT/AND/OR")
        if i + 1 >= len(modifiers):
            raise ValueError(f"SUBJECT operator {op.name!r} missing RHS card in modifiers tuple")
        rhs = modifiers[i + 1]
        rhs_scope = _scope_subject(state, rhs, labels)
        if op.name == "BUT":
            result = result - rhs_scope
        else:  # AND / OR — both unions per ADR-0004.
            result = result | rhs_scope
        i += 2
    return result


def _evaluate_has(state: GameState, player: Player, rule: IfRule) -> bool:
    """Evaluate ``HAS [QUANT] [NOUN]`` for a single player.

    ``state`` is read for the player-agnostic ``ROUNDS`` NOUN and for the
    cross-player ``RULES`` count (``state.persistent_rules``). All other
    NOUNs read from the player itself. Folds NOUN-targeted operator
    MODIFIERs over the base read (``AND`` = sum, ``OR`` = max) and
    QUANT-targeted operator MODIFIERs over the comparator op
    (``MORE_THAN`` strips equality, ``AT_LEAST`` adds equality;
    last-write-wins per ADR-0004).
    """
    value = _fold_noun_value(state, player, rule.noun, rule.noun_modifiers)
    op, threshold = _parse_quant(rule.quant)
    op = _fold_quant_op(op, rule.quant_modifiers)
    return _compare(value, op, threshold)


def _noun_value(state: GameState, player: Player, noun_name: str) -> int:
    """Resolve a NOUN render-name to its integer reading for ``player``.

    Dispatch order:
      1. M1 player-resource NOUNs (``CHIPS``, ``VP``) — direct attribute read.
      2. M2 polymorphic NOUNs (``CARDS``, ``RULES``, ``HITS``, ``GIFTS``,
         ``ROUNDS``, ``BURN_TOKENS``) — sourced per ``design/cards-inventory.md``.

    Unknown NOUN names raise ``ValueError``; the resolver does not silently
    no-op (silent zero would be indistinguishable from a legitimate zero
    reading and mask data bugs).
    """
    attr = _PLAYER_RESOURCE_NOUNS.get(noun_name)
    if attr is not None:
        return getattr(player, attr)
    if noun_name == "CARDS":
        return len(player.hand)
    if noun_name == "RULES":
        return sum(1 for r in state.persistent_rules if r.created_by == player.id)
    if noun_name == "HITS":
        return player.history.hits_taken_this_game
    if noun_name == "GIFTS":
        return player.history.cards_given_this_game
    if noun_name == "ROUNDS":
        return state.round_number
    if noun_name == "BURN_TOKENS":
        return player.status.burn
    known = sorted(set(_PLAYER_RESOURCE_NOUNS) | _M2_NOUN_NAMES)
    raise ValueError(f"unknown NOUN {noun_name!r}; supported: {known}")


def _fold_noun_value(
    state: GameState, player: Player, base_noun: Card, modifiers: tuple[Card, ...]
) -> int:
    """Fold NOUN-targeted operator MODIFIERs over the base ``Player`` read.

    Walks ``modifiers`` in (op, rhs-card) pairs: ``AND`` sums the RHS read into
    the running total, ``OR`` takes the max (per ADR-0004 NOUN column).
    Empty ``modifiers`` returns the base read unchanged — the singular path.
    """
    value = _noun_value(state, player, base_noun.name)
    if not modifiers:
        return value
    i = 0
    while i < len(modifiers):
        op = modifiers[i]
        if op.name not in {"AND", "OR"}:
            raise ValueError(f"unexpected NOUN operator {op.name!r}; expected one of AND/OR")
        if i + 1 >= len(modifiers):
            raise ValueError(f"NOUN operator {op.name!r} missing RHS card in modifiers tuple")
        rhs = modifiers[i + 1]
        rhs_value = _noun_value(state, player, rhs.name)
        if op.name == "AND":
            value = value + rhs_value
        else:  # OR
            value = max(value, rhs_value)
        i += 2
    return value


def _parse_quant(quant: Card) -> tuple[str, int]:
    """Parse a QUANT card's ``name`` as ``"<OP>:<N>"`` (e.g. ``"GE:5"``).

    Operators: ``GE`` ≥, ``GT`` >, ``LE`` ≤, ``LT`` <, ``EQ`` ==.

    M1.5 baked-N comparators carry both fields in ``name``. M2 OP-only
    comparators (per ADR-0002) draw N from dice at play time;
    :func:`_bake_quant_dice` rewrites those into ``OP:N`` form before this
    parser sees them, so by here every QUANT card carries an ``:N`` segment.
    """
    raw = quant.name
    if ":" not in raw:
        raise ValueError(f"QUANT card name {raw!r} not in form 'OP:N'")
    op, n = raw.split(":", 1)
    return op, int(n)


def _bake_quant_dice(rule: IfRule, state: GameState) -> IfRule:
    """Resolve OP-only comparator dice per ADR-0002.

    If the QUANT card encodes an operator only (``LT`` / ``LE`` / ``GT`` /
    ``GE`` / ``EQ`` — no ``:N`` segment), reads the drawn N from
    ``state.last_roll.value`` and returns a new :class:`IfRule` with the QUANT
    rebuilt as a transient ``OP:N`` card. Baked-N quants pass through
    unchanged. Pure: input ``rule`` and ``state`` are not mutated.

    Raises :class:`ValueError` if the QUANT is OP-only but ``state.last_roll``
    is ``None`` — signals a missing ``play_card`` → roll wiring upstream.
    """
    quant = rule.quant
    if quant.name not in _OP_ONLY_COMPARATOR_NAMES:
        return rule
    if state.last_roll is None:
        raise ValueError(
            f"OP-only comparator {quant.name!r} has no last_roll; "
            "play_card must record the roll before resolve"
        )
    baked = quant.model_copy(update={"name": f"{quant.name}:{state.last_roll.value}"})
    return rule.model_copy(update={"quant": baked})


def _fold_quant_op(op: str, modifiers: tuple[Card, ...]) -> str:
    """Apply QUANT-targeted operator MODIFIERs to ``op`` (ADR-0004).

    ``MORE_THAN`` strips equality (GE→GT, LE→LT) — forces strict comparison.
    ``AT_LEAST`` adds equality (GT→GE, LT→LE) — forces non-strict.
    Equality ``EQ`` is unaffected by either modifier (no strict/non-strict
    axis to toggle). Conflicts resolve last-write-wins per ADR example 4.
    """
    for mod in modifiers:
        if mod.name == "MORE_THAN":
            if op == "GE":
                op = "GT"
            elif op == "LE":
                op = "LT"
        elif mod.name == "AT_LEAST":
            if op == "GT":
                op = "GE"
            elif op == "LT":
                op = "LE"
        else:
            raise ValueError(
                f"unexpected QUANT operator {mod.name!r}; expected MORE_THAN or AT_LEAST"
            )
    return op


def _compare(value: int, op: str, threshold: int) -> bool:
    if op == "GE":
        return value >= threshold
    if op == "GT":
        return value > threshold
    if op == "LE":
        return value <= threshold
    if op == "LT":
        return value < threshold
    if op == "EQ":
        return value == threshold
    raise ValueError(f"unknown comparator op {op!r}")

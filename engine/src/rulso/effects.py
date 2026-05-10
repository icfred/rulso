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
# state-level reads). All field names verified against state.py — ``HITS`` uses
# ``PlayerHistory.hits_taken_this_game`` (RUL-26), not the placeholder
# ``hits_this_round`` named in inventory text.
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


def resolve_if_rule(
    state: GameState,
    rule: RuleBuilder,
    labels: dict[str, frozenset[str]] | None = None,
) -> GameState:
    """Resolve an IF rule against ``state`` and return the updated state.

    Pipeline:
      1. Render the rule (``grammar.render_if_rule``).
      2. Scope SUBJECT → frozenset of player ids (label-aware).
      3. Evaluate ``HAS [QUANT] [NOUN]`` for each scoped player.
      4. Dispatch ``state.revealed_effect`` to every satisfying player via
         :func:`dispatch_effect`.

    ``labels`` is an optional pre-computed label-name → frozenset[player_id]
    mapping (the shape returned by ``rulso.labels.recompute_labels``). When
    omitted, the resolver recomputes from ``state``. Pass it explicitly when a
    caller already holds the round's labels (e.g. ``rules.enter_resolve``)
    to avoid double computation. Labels are never stored on ``GameState``
    (per ADR-0001 / ``design/state.md`` "computed, not stored").

    SUBJECTs scoped to an empty label set, HAS-false branches, and a missing
    ``revealed_effect`` all return the input state unchanged.
    """
    structured = render_if_rule(rule)
    if labels is None:
        labels = recompute_labels(state)
    scoped = _scope_subject(state, structured.subject, labels)
    if not scoped:
        return state
    matching = frozenset(
        p.id for p in state.players if p.id in scoped and _evaluate_has(state, p, structured)
    )
    if not matching:
        return state
    return dispatch_effect(state, state.revealed_effect, matching)


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
    return _patch_players(
        state,
        targets,
        lambda p: p.model_copy(update={"chips": max(0, p.chips - magnitude)}),
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
    """Resolve a SUBJECT card to the set of player ids in scope.

    ``subject.name`` controls the scope:
      * One of ``labels.LABEL_NAMES`` → look up that label in ``labels``.
        Live labels (LEADER, WOUNDED) return the holders for the round; M2-
        stubbed labels (GENEROUS, CURSED, MARKED, CHAINED) return ``frozenset()``
        until their derivations land.
      * Any other value → literal player id; matches the ``Player`` with that
        id, or ``frozenset()`` if no such player.

    Polymorphic SUBJECTs (e.g. ``ANYONE``, ``EACH PLAYER``) land with the
    card catalogue in M2.
    """
    if subject.name in LABEL_NAMES:
        return labels.get(subject.name, frozenset())
    return frozenset(p.id for p in state.players if p.id == subject.name)


def _evaluate_has(state: GameState, player: Player, rule: IfRule) -> bool:
    """Evaluate ``HAS [QUANT] [NOUN]`` for a single player.

    ``state`` is read for the player-agnostic ``ROUNDS`` NOUN and for the
    cross-player ``RULES`` count (``state.persistent_rules``). All other
    NOUNs read from the player itself.
    """
    value = _noun_value(state, player, rule.noun.name)
    op, threshold = _parse_quant(rule.quant)
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


def _parse_quant(quant: Card) -> tuple[str, int]:
    """Parse a QUANT card's ``name`` as ``"<OP>:<N>"`` (e.g. ``"GE:5"``).

    Operators: ``GE`` ≥, ``GT`` >, ``LE`` ≤, ``LT`` <, ``EQ`` ==.

    Comparator MODIFIERs in the full game inline a dice roll (see
    ``design/state.md``); the ``OP:N`` shorthand is M1's bridge until that
    pipeline lands.
    """
    raw = quant.name
    if ":" not in raw:
        raise ValueError(f"QUANT card name {raw!r} not in form 'OP:N'")
    op, n = raw.split(":", 1)
    return op, int(n)


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

"""IF rule effect resolver.

``resolve_if_rule`` is the single public entry point. It scopes a rule's
SUBJECT to a set of player ids, evaluates ``HAS [QUANT] [NOUN]`` against each
scoped player, and applies the M1.5 stub effect (+1 VP) to every satisfying
player. The real effect catalogue lands with ``cards.yaml`` in M2.

Pure function: input ``GameState`` is never mutated; a new state is returned.
"""

from __future__ import annotations

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

# M1.5 stub effect: each satisfying player gains this many VP. Awarding VP
# (rather than chips) lets games actually terminate at VP_TO_WIN. Real effect
# application (driven by ``revealed_effect`` + cards.yaml) lands in M2.
_STUB_VP_GAIN: int = 1


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
      4. Apply the M1.5 stub effect (+1 VP) to every satisfying player.

    ``labels`` is an optional pre-computed label-name → frozenset[player_id]
    mapping (the shape returned by ``rulso.labels.recompute_labels``). When
    omitted, the resolver recomputes from ``state``. Pass it explicitly when a
    caller already holds the round's labels (e.g. ``rules.enter_resolve``)
    to avoid double computation. Labels are never stored on ``GameState``
    (per ADR-0001 / ``design/state.md`` "computed, not stored").

    SUBJECTs scoped to an empty label set and HAS-false branches return the
    input state unchanged.
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
    return _apply_stub_effect(state, matching)


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


def _apply_stub_effect(state: GameState, matching_ids: frozenset[str]) -> GameState:
    """M1.5 stub: +``_STUB_VP_GAIN`` VP to every player in ``matching_ids``."""
    new_players = tuple(
        p.model_copy(update={"vp": p.vp + _STUB_VP_GAIN}) if p.id in matching_ids else p
        for p in state.players
    )
    return state.model_copy(update={"players": new_players})

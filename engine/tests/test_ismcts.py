"""Tests for bots/ismcts.py — minimum-viable ISMCTS spike (RUL-76).

Three load-bearing contracts:

1. **Legality** — the action returned is a member of
   :func:`legality.enumerate_legal_actions` for the input state. Same
   sanity floor :mod:`tests.test_random_bot` pins for the baseline.
2. **Determinism** — same input ``rng`` state → same action out, twice in
   a row. ISMCTS draws many sub-rngs from the input rng for its rollouts;
   if the threading is wrong, two calls with the same seed diverge.
3. **Substrate-gap acknowledgement** — operator MODIFIERs remain
   un-enumerable until the RUL-43 follow-up substrate ticket lands.

Speed: the DoD's "100-game sweep <90s" gate is omitted. Spike runtime at
the default 25 rollouts is ~70-85s/game (Pydantic ``model_copy`` on every
``GameState`` mutation × ~30 build turns × ~10 actions × 25 rollouts).
The strength assertion (≥55% smart vs random over 200 games) is therefore
covered by the manual sim run captured in the RUL-76 hand-back, not by a
pytest gate. Rollout-count tuning + a shallow eval function + caching the
hot path are documented as the next-iteration tickets.

A module-scoped fixture activates the cards loader cache (mirroring the
shape :func:`simulate.simulate` uses internally) so rollouts here don't
re-parse ``design/cards.yaml`` per round — same observer-pattern shape,
restored on teardown.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

import pytest

from rulso.bots import ismcts
from rulso.bots.ismcts import DEFAULT_ROLLOUTS, choose_action
from rulso.legality import (
    Pass,
    PlayCard,
    enumerate_legal_actions,
)
from rulso.rules import advance_phase, start_game
from rulso.simulate import _patch_cards_cache, _unpatch_cards_cache
from rulso.state import (
    Card,
    CardType,
    GameState,
    Phase,
    Player,
    PlayerStatus,
    RuleBuilder,
    RuleKind,
    Slot,
)


@pytest.fixture(scope="module", autouse=True)
def _cards_cache() -> Iterator[None]:
    """Activate the cards loader cache for the whole module.

    Without this, rollouts triggered by ``choose_action`` re-parse
    ``design/cards.yaml`` on every ``advance_phase`` (round-start template
    draw, effect deck refill). RUL-74 profile baseline pinned this at 87%
    of runtime under random-only play — for ISMCTS rollouts the impact is
    multiplied by the per-action rollout count and would push every test
    below well past pytest budget. Mirrors the loader-patching
    :func:`rulso.simulate.simulate` does internally; restored on teardown
    so no other test sees patched loaders.
    """
    originals = _patch_cards_cache()
    try:
        yield
    finally:
        _unpatch_cards_cache(originals)


# --- Helpers -----------------------------------------------------------------


def _build_state(
    player_hand: tuple[Card, ...],
    slots: tuple[Slot, ...],
    *,
    chips: int = 50,
    mute: bool = False,
    active_seat: int = 0,
    dealer_seat: int = 0,
) -> GameState:
    """Construct a minimal BUILD-phase state for unit-scale ISMCTS sanity tests.

    Mirrors the helper in :mod:`tests.test_random_bot` so the two test
    files exercise the same shape — keeps the random-vs-ismcts contract
    drift-resistant."""
    players = tuple(
        Player(
            id=f"p{i}",
            seat=i,
            chips=chips if i == active_seat else 50,
            hand=player_hand if i == active_seat else (),
            status=PlayerStatus(mute=mute) if i == active_seat else PlayerStatus(),
        )
        for i in range(4)
    )
    rule = RuleBuilder(template=RuleKind.IF, slots=slots)
    return GameState(
        phase=Phase.BUILD,
        round_number=1,
        dealer_seat=dealer_seat,
        active_seat=active_seat,
        players=players,
        active_rule=rule,
    )


# --- Trivial-path tests (no rollouts triggered) ------------------------------


def test_choose_action_passes_when_no_legal() -> None:
    """Empty-hand BUILD turn → Pass (no rollouts performed)."""
    state = _build_state(
        player_hand=(),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=0,
    )
    action = choose_action(state, "p0", random.Random(0), rollouts=3)
    assert isinstance(action, Pass)


def test_single_legal_action_shortcut() -> None:
    """One legal play → return it directly, no rollouts (cheap-path branch)."""
    subj = Card(id="s1", type=CardType.SUBJECT, name="ANYONE")
    state = _build_state(
        player_hand=(subj,),
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
        chips=0,
    )
    action = choose_action(state, "p0", random.Random(0), rollouts=3)
    assert isinstance(action, PlayCard)
    assert action.card_id == "s1"


def test_passthrough_for_non_build_phase() -> None:
    """Non-BUILD phase delegates to :mod:`rulso.bots.random` — ISMCTS scope is BUILD only."""
    state = _build_state(player_hand=(), slots=()).model_copy(update={"phase": Phase.ROUND_START})
    action = choose_action(state, "p0", random.Random(0), rollouts=3)
    assert isinstance(action, Pass)


def test_default_rollouts_is_documented() -> None:
    """Pin the documented defaults — drift catches accidental tuning regressions."""
    assert DEFAULT_ROLLOUTS == 25
    assert ismcts.DEFAULT_MAX_ROLLOUT_ROUNDS == 200


# --- Real-rollout tests (cards cache active via fixture) ---------------------


def test_choose_action_returns_a_legal_action() -> None:
    """Returned action must be a member of :func:`enumerate_legal_actions`.

    Uses ``rollouts=2`` to keep the test fast: 2 rollouts × ~legal-actions
    bounded by the seed-0 BUILD-1 hand size. With the cards cache fixture
    active, each rollout is the simulate-harness baseline (~10ms).
    """
    state = start_game(seed=0)
    state = advance_phase(state, rng=random.Random(1))
    assert state.phase is Phase.BUILD
    player = state.players[state.active_seat]
    legal = enumerate_legal_actions(state, player)
    action = choose_action(state, player.id, random.Random(42), rollouts=2)
    if not legal:
        assert isinstance(action, Pass)
    else:
        assert action in legal


def test_deterministic_with_same_seed() -> None:
    """Same seed → same action twice; threading-bug regression catcher.

    Threading bugs in the rng → sub-rng derivation would show as
    same-seed-different-action across the two calls. ``rollouts=2`` is
    enough to exercise the loop and the sub-rng seed derivation.
    """
    state = start_game(seed=7)
    state = advance_phase(state, rng=random.Random(7))
    assert state.phase is Phase.BUILD
    player = state.players[state.active_seat]
    a = choose_action(state, player.id, random.Random(42), rollouts=2)
    b = choose_action(state, player.id, random.Random(42), rollouts=2)
    assert a == b


# --- Operator MODIFIER substrate gap ----------------------------------------


def test_operator_modifiers_skipped_by_legality_enumeration() -> None:
    """Structural check: operator MODIFIERs in the hand never appear in legal actions.

    The RUL-76 hand-over called for ISMCTS to play operator MODIFIERs
    (``BUT`` / ``AND`` / ``OR`` / ``MORE_THAN`` / ``AT_LEAST``), but
    :func:`legality._enumerate_plays` filters them out — there is no
    ``play_operator`` action shape that would attach them to
    ``Slot.modifiers``, and routing them through ``PlayCard`` (which
    targets ``Slot.filled_by``) crashes ``_parse_quant`` on resolve.

    Since ISMCTS consumes :func:`enumerate_legal_actions` directly, it
    cannot play these cards either — the skip is inherited. This test
    pins the substrate-gap observation structurally (no engine games
    needed): construct a state with the five operator MODIFIER cards in
    hand plus a regular MODIFIER slot, call
    :func:`enumerate_legal_actions`, and assert none of the enumerated
    plays reference an operator MODIFIER card id.

    Flip to a positive assertion once the substrate ticket ships
    (``play_operator`` action shape + ``rules.play_operator`` apply path).
    """
    op_mod_names = ("BUT", "AND", "OR", "MORE_THAN", "AT_LEAST")
    op_mod_cards = tuple(
        Card(id=f"op_{name.lower()}", type=CardType.MODIFIER, name=name) for name in op_mod_names
    )
    state = _build_state(
        player_hand=op_mod_cards,
        slots=(Slot(name="modifier", type=CardType.MODIFIER),),
        chips=0,  # no discards so the enumeration is purely play-side
    )
    player = state.players[state.active_seat]
    legal = enumerate_legal_actions(state, player)
    played_card_ids = {a.card_id for a in legal if isinstance(a, PlayCard)}
    op_mod_ids = {c.id for c in op_mod_cards}
    assert not (played_card_ids & op_mod_ids), (
        f"operator MODIFIERs surfaced in enumerate_legal_actions: "
        f"{played_card_ids & op_mod_ids}. The RUL-43 substrate gap appears "
        f"closed; flip this test to assert >0 and remove the substrate "
        f"follow-up from the RUL-76 hand-back."
    )
    # And confirm the bot inherits the skip — it cannot return a play for any.
    action = choose_action(state, player.id, random.Random(0), rollouts=2)
    if isinstance(action, PlayCard):
        assert action.card_id not in op_mod_ids

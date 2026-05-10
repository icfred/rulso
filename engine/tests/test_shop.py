"""SHOP-phase coverage (RUL-51).

Pins the three DoD bullets from the RUL-51 hand-over:

* SHOP fires on the right round indices (every ``SHOP_INTERVAL`` rounds —
  3, 6, 9, … per ``design/state.md``).
* Buy order is correct: ascending VP, ties broken by lowest chips, then by
  seat (canonical ``design/state.md`` SHOP step 2 ordering — the hand-over's
  "ties by ``Player.id``" matches seat order for ``p0..p3``).
* Engine returns to ROUND_START of the next round after SHOP completes.

The CLI / smoke paths run with ``shop_pool=()`` (no ``shop_cards`` in
cards.yaml yet) so SHOP never enters in normal play. These tests synthesise
``shop_pool`` directly to exercise the substrate.
"""

from __future__ import annotations

import random

from rulso.cards import load_condition_templates
from rulso.rules import (
    advance_phase,
    apply_shop_purchase,
    complete_shop,
    enter_round_start,
    pass_turn,
    shop_purchase_order,
    start_game,
)
from rulso.state import (
    PLAYER_COUNT,
    SHOP_INTERVAL,
    Card,
    CardType,
    GameState,
    Phase,
    Player,
    ShopOffer,
)


def _offer(oid: str, price: int) -> ShopOffer:
    return ShopOffer(
        card=Card(id=oid, type=CardType.NOUN, name=oid),
        price=price,
    )


def _with_shop_pool(state: GameState, *offers: ShopOffer) -> GameState:
    """Inject offers into ``shop_pool``; pop order is right-to-left (LIFO)."""
    return state.model_copy(update={"shop_pool": offers})


def _seat_with_hand(seat: int, hand: tuple[Card, ...]) -> Player:
    return Player(id=f"p{seat}", seat=seat, hand=hand)


def _seed_subject_for_dealer(state: GameState) -> GameState:
    """Place a SUBJECT card in the dealer's hand so step 7 doesn't fail."""
    seed_subject = Card(id="subj.p0", type=CardType.SUBJECT, name="p0")
    dealer = state.players[state.dealer_seat]
    new_dealer = dealer.model_copy(update={"hand": (seed_subject,) + dealer.hand})
    new_players = tuple(new_dealer if p.seat == state.dealer_seat else p for p in state.players)
    return state.model_copy(update={"players": new_players})


# --- Cadence -------------------------------------------------------------


def test_shop_does_not_fire_on_non_cadence_rounds() -> None:
    """Rounds 1, 2 (not multiples of SHOP_INTERVAL=3) skip SHOP entry."""
    state = GameState(
        phase=Phase.ROUND_START,
        round_number=0,
        players=tuple(_seat_with_hand(i, ()) for i in range(PLAYER_COUNT)),
    )
    state = _with_shop_pool(state, _offer("shop.a", 10), _offer("shop.b", 5))
    # Round 1: cadence check fails (1 % 3 != 0).
    out = enter_round_start(state, rng=random.Random(0))
    assert out.phase is not Phase.SHOP
    # Round 2: same.
    state2 = state.model_copy(update={"round_number": 1})
    out2 = enter_round_start(state2, rng=random.Random(0))
    assert out2.phase is not Phase.SHOP


def test_shop_fires_on_cadence_when_offers_available() -> None:
    """Round 3 (SHOP_INTERVAL=3 hits) with a non-empty shop_pool enters Phase.SHOP."""
    assert SHOP_INTERVAL == 3
    state = GameState(
        phase=Phase.ROUND_START,
        round_number=2,  # advances to 3 → cadence hit
        players=tuple(_seat_with_hand(i, ()) for i in range(PLAYER_COUNT)),
    )
    state = _with_shop_pool(state, _offer("shop.a", 10), _offer("shop.b", 5))
    out = enter_round_start(state, rng=random.Random(0))
    assert out.phase is Phase.SHOP
    assert out.round_number == 3
    # Up to 4 offers drawn; pool had 2 so both are on the table.
    assert len(out.shop_offer) == 2


def test_shop_skipped_when_cadence_hits_but_no_offers_available() -> None:
    """Cadence hits round 3 but ``shop_pool`` + ``shop_discard`` are both empty.

    No SHOP transition; round_start proceeds directly to steps 6-8.
    """
    state = GameState(
        phase=Phase.ROUND_START,
        round_number=2,
        # Dealer (seat 0) holds a SUBJECT so the round doesn't fail at step 7.
        players=tuple(
            _seat_with_hand(
                i,
                (Card(id="subj.p0", type=CardType.SUBJECT, name="p0"),) if i == 0 else (),
            )
            for i in range(PLAYER_COUNT)
        ),
    )
    out = enter_round_start(state, rng=random.Random(0))
    # SHOP would have skipped → went straight into BUILD on dealer seed.
    assert out.phase is Phase.BUILD
    assert out.round_number == 3


def test_shop_fires_repeatedly_at_each_cadence_interval() -> None:
    """SHOP fires on rounds 3, 6, 9 — independent of intervening dealer fails."""
    base = GameState(
        phase=Phase.ROUND_START,
        round_number=0,
        players=tuple(_seat_with_hand(i, ()) for i in range(PLAYER_COUNT)),
    )
    base = _with_shop_pool(base, _offer("shop.a", 10))
    for round_index in (3, 6, 9):
        state = base.model_copy(update={"round_number": round_index - 1})
        out = enter_round_start(state, rng=random.Random(round_index))
        assert out.phase is Phase.SHOP, f"round {round_index}: expected SHOP, got {out.phase}"


# --- Buy order -----------------------------------------------------------


def test_shop_purchase_order_ascending_vp_then_chips_then_seat() -> None:
    """Canonical ``design/state.md`` SHOP step 2 ordering.

    Constructed mix: p0 has highest VP, p3 has lowest. Among the tied-at-VP
    middle group, the lower-chips player goes first; among the tied-at-chips
    pair, seat tie-breaks ascending.
    """
    players = (
        Player(id="p0", seat=0, vp=2, chips=50),  # highest VP → last
        Player(id="p1", seat=1, vp=1, chips=20),  # tied vp=1, fewer chips → before p2
        Player(id="p2", seat=2, vp=1, chips=40),
        Player(id="p3", seat=3, vp=0, chips=10),  # lowest VP → first
    )
    state = GameState(phase=Phase.SHOP, players=players)
    assert shop_purchase_order(state) == ("p3", "p1", "p2", "p0")


def test_shop_purchase_order_seat_breaks_chips_tie() -> None:
    """When VP and chips tie, seat order (== ``Player.id`` for p0..p3) breaks."""
    players = (
        Player(id="p0", seat=0, vp=0, chips=50),
        Player(id="p1", seat=1, vp=0, chips=50),
        Player(id="p2", seat=2, vp=0, chips=50),
        Player(id="p3", seat=3, vp=0, chips=50),
    )
    state = GameState(phase=Phase.SHOP, players=players)
    assert shop_purchase_order(state) == ("p0", "p1", "p2", "p3")


def test_apply_shop_purchase_deducts_chips_and_appends_to_hand() -> None:
    players = (
        Player(id="p0", seat=0, chips=50, hand=()),
        Player(id="p1", seat=1, chips=50, hand=()),
        Player(id="p2", seat=2, chips=50, hand=()),
        Player(id="p3", seat=3, chips=50, hand=()),
    )
    state = GameState(
        phase=Phase.SHOP,
        players=players,
        shop_offer=(_offer("shop.a", 10), _offer("shop.b", 5)),
    )
    out = apply_shop_purchase(state, "p1", offer_index=0)
    p1 = next(p for p in out.players if p.id == "p1")
    assert p1.chips == 40
    assert len(p1.hand) == 1
    assert p1.hand[0].id == "shop.a"
    # Other players untouched.
    for pid in ("p0", "p2", "p3"):
        assert next(p for p in out.players if p.id == pid).chips == 50
    # Remaining offer narrowed.
    assert len(out.shop_offer) == 1
    assert out.shop_offer[0].card.id == "shop.b"


def test_apply_shop_purchase_rejects_unaffordable() -> None:
    import pytest

    players = tuple(Player(id=f"p{i}", seat=i, chips=5) for i in range(PLAYER_COUNT))
    state = GameState(
        phase=Phase.SHOP,
        players=players,
        shop_offer=(_offer("shop.a", 100),),
    )
    with pytest.raises(ValueError, match="cannot afford"):
        apply_shop_purchase(state, "p0", offer_index=0)


# --- SHOP → next round_start ---------------------------------------------


def test_complete_shop_pushes_unsold_to_discard_and_resumes_round_start() -> None:
    """SHOP close: unsold offers move to ``shop_discard``; flow resumes to BUILD."""
    seed_subject = Card(id="subj.p0", type=CardType.SUBJECT, name="p0")
    players = (
        Player(id="p0", seat=0, chips=50, hand=(seed_subject,)),
        Player(id="p1", seat=1, chips=50, hand=()),
        Player(id="p2", seat=2, chips=50, hand=()),
        Player(id="p3", seat=3, chips=50, hand=()),
    )
    state = GameState(
        phase=Phase.SHOP,
        round_number=3,
        dealer_seat=0,
        players=players,
        shop_offer=(_offer("shop.a", 10), _offer("shop.b", 5)),
    )
    out = complete_shop(state, rng=random.Random(0))
    assert out.phase is Phase.BUILD
    # Round_number does NOT advance (SHOP doesn't consume the counter).
    assert out.round_number == 3
    # Unsold offers landed in discard; offer cleared.
    assert out.shop_offer == ()
    assert len(out.shop_discard) == 2


def test_shop_round_completes_then_engine_reaches_next_round_start() -> None:
    """End-to-end: SHOP fires, completes, then the engine reaches the next round.

    Drives one full SHOP round and then walks through BUILD + RESOLVE to
    confirm the cycle returns to ROUND_START of the next round (round 4).
    """
    seed_subject = Card(id="subj.p0", type=CardType.SUBJECT, name="p0")
    second_subject = Card(id="subj.p0_b", type=CardType.SUBJECT, name="p0")
    players = (
        Player(id="p0", seat=0, chips=50, hand=(seed_subject, second_subject)),
        Player(id="p1", seat=1, chips=50, hand=(second_subject,)),
        Player(id="p2", seat=2, chips=50, hand=(second_subject,)),
        Player(id="p3", seat=3, chips=50, hand=(second_subject,)),
    )
    state = GameState(
        phase=Phase.ROUND_START,
        round_number=2,
        dealer_seat=0,
        players=players,
        shop_pool=(_offer("shop.a", 10),),
    )
    out = enter_round_start(state, rng=random.Random(0))
    assert out.phase is Phase.SHOP
    # Cheapest-affordable bot would have picked the offer; here we drive a
    # canonical skip so the run exercises the "all skip → unsold discard" path.
    out = advance_phase(out, rng=random.Random(1))
    assert out.phase is Phase.BUILD
    assert out.round_number == 3
    # Drive BUILD turns via pass_turn so the rule fails on missing slots,
    # then we land back at ROUND_START of the next round (round 4).
    for _ in range(PLAYER_COUNT - 1):
        out = pass_turn(out)
    out = pass_turn(out)
    # After the build revolution, the rule fails (slots unfilled) → ROUND_START.
    assert out.phase is Phase.ROUND_START
    # round_number stays at 3 until enter_round_start ticks it again.
    assert out.round_number == 3


# --- Pool recycle --------------------------------------------------------


def test_shop_recycles_discard_when_pool_drained() -> None:
    """Once ``shop_pool`` empties, draws recycle ``shop_discard`` via rng."""
    state = GameState(
        phase=Phase.ROUND_START,
        round_number=2,
        players=tuple(_seat_with_hand(i, ()) for i in range(PLAYER_COUNT)),
        shop_pool=(),
        shop_discard=(_offer("shop.a", 10), _offer("shop.b", 5)),
    )
    out = enter_round_start(state, rng=random.Random(0))
    # SHOP entered because shop_discard had offers to recycle.
    assert out.phase is Phase.SHOP
    assert len(out.shop_offer) == 2
    # Pool now drained, discard cleared by recycle.
    assert out.shop_pool == ()
    assert out.shop_discard == ()


# --- start_game integration ---------------------------------------------


def test_start_game_initialises_empty_shop_pool() -> None:
    """M2 ships with no ``shop_cards`` — ``shop_pool`` starts empty."""
    state = start_game(seed=0)
    assert state.shop_pool == ()
    assert state.shop_offer == ()
    assert state.shop_discard == ()


def test_condition_templates_load_ok_unaffected_by_shop_schema_addition() -> None:
    """``shop_cards`` schema addition is additive; existing loaders stay green."""
    templates = load_condition_templates()
    assert len(templates) >= 1

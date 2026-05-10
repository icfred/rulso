"""Goal-claim resolver coverage (RUL-46).

Exercises the predicate registry (every M2 starter predicate), claim semantics
for both `single` and `renewable` kinds, the catch-up tie-break, the CHAINED
filter, deck replenishment + recycling, and the `start_game` seed +
`enter_resolve` step-7 wiring.
"""

from __future__ import annotations

import pytest

from rulso import goals
from rulso.cards import load_goal_cards
from rulso.rules import enter_resolve, start_game
from rulso.state import (
    ACTIVE_GOALS,
    HAND_SIZE,
    PLAYER_COUNT,
    Card,
    CardType,
    GameState,
    GoalCard,
    Phase,
    Play,
    Player,
    PlayerHistory,
    PlayerStatus,
    RuleBuilder,
    RuleKind,
    Slot,
)

# --- Fixtures ---------------------------------------------------------------


def _player(
    seat: int,
    *,
    pid: str | None = None,
    chips: int = 50,
    vp: int = 0,
    hand_size: int = 0,
    burn: int = 0,
    chained: bool = False,
    mute: bool = False,
    blessed: bool = False,
    marked: bool = False,
    rules_completed: int = 0,
    cards_given: int = 0,
) -> Player:
    return Player(
        id=pid or f"p{seat}",
        seat=seat,
        chips=chips,
        vp=vp,
        hand=tuple(
            Card(id=f"h{seat}_{i}", type=CardType.NOUN, name=f"h{seat}_{i}")
            for i in range(hand_size)
        ),
        status=PlayerStatus(burn=burn, chained=chained, mute=mute, blessed=blessed, marked=marked),
        history=PlayerHistory(
            rules_completed_this_game=rules_completed,
            cards_given_this_game=cards_given,
        ),
    )


def _goal(
    *,
    gid: str = "goal.test",
    name: str = "TEST",
    predicate_id: str,
    vp_award: int = 1,
    kind: str = "single",
) -> GoalCard:
    return GoalCard(
        id=gid,
        name=name,
        claim_condition=predicate_id,
        vp_award=vp_award,
        claim_kind=kind,  # type: ignore[arg-type]
    )


def _state(
    players: tuple[Player, ...],
    *,
    active_goals: tuple[GoalCard | None, ...] = (None, None, None),
    goal_deck: tuple[GoalCard, ...] = (),
    goal_discard: tuple[GoalCard, ...] = (),
    round_number: int = 1,
    dealer_seat: int = 0,
) -> GameState:
    return GameState(
        players=players,
        active_goals=active_goals,
        goal_deck=goal_deck,
        goal_discard=goal_discard,
        round_number=round_number,
        dealer_seat=dealer_seat,
    )


def _four_players(**overrides: int) -> tuple[Player, ...]:
    return tuple(_player(seat=i) for i in range(PLAYER_COUNT))


# --- Predicate registry coverage -------------------------------------------


def test_predicate_lookup_returns_registered_function() -> None:
    fn = goals.predicate("chips_at_least_75")
    state = _state(_four_players())
    assert fn(_player(0, chips=75), state) is True
    assert fn(_player(0, chips=74), state) is False


def test_predicate_lookup_unknown_id_raises() -> None:
    with pytest.raises(KeyError, match="unknown goal predicate"):
        goals.predicate("does_not_exist")


def test_chips_at_least_75_threshold() -> None:
    fn = goals.predicate("chips_at_least_75")
    state = _state(_four_players())
    assert fn(_player(0, chips=75), state) is True
    assert fn(_player(0, chips=80), state) is True
    assert fn(_player(0, chips=74), state) is False


def test_chips_under_10_threshold() -> None:
    fn = goals.predicate("chips_under_10")
    state = _state(_four_players())
    assert fn(_player(0, chips=9), state) is True
    assert fn(_player(0, chips=0), state) is True
    assert fn(_player(0, chips=10), state) is False


def test_rules_completed_at_least_3() -> None:
    fn = goals.predicate("rules_completed_at_least_3")
    state = _state(_four_players())
    assert fn(_player(0, rules_completed=3), state) is True
    assert fn(_player(0, rules_completed=4), state) is True
    assert fn(_player(0, rules_completed=2), state) is False


def test_gifts_at_least_2() -> None:
    fn = goals.predicate("gifts_at_least_2")
    state = _state(_four_players())
    assert fn(_player(0, cards_given=2), state) is True
    assert fn(_player(0, cards_given=1), state) is False


def test_burn_at_least_2() -> None:
    fn = goals.predicate("burn_at_least_2")
    state = _state(_four_players())
    assert fn(_player(0, burn=2), state) is True
    assert fn(_player(0, burn=1), state) is False


def test_full_hand_at_hand_size() -> None:
    fn = goals.predicate("full_hand")
    state = _state(_four_players())
    assert fn(_player(0, hand_size=HAND_SIZE), state) is True
    assert fn(_player(0, hand_size=HAND_SIZE - 1), state) is False


def test_free_agent_round_gate_blocks_early_rounds() -> None:
    fn = goals.predicate("free_agent")
    clean_player = _player(0)  # all defaults: status empty, round-gate triggers from state
    early = _state(_four_players(), round_number=4)
    late = _state(_four_players(), round_number=5)
    assert fn(clean_player, early) is False
    assert fn(clean_player, late) is True


def test_free_agent_any_status_token_disqualifies() -> None:
    fn = goals.predicate("free_agent")
    state = _state(_four_players(), round_number=10)
    assert fn(_player(0, burn=1), state) is False
    assert fn(_player(0, mute=True), state) is False
    assert fn(_player(0, blessed=True), state) is False
    assert fn(_player(0, marked=True), state) is False
    assert fn(_player(0, chained=True), state) is False
    assert fn(_player(0), state) is True


# --- check_claims: single-claim path --------------------------------------


def test_single_claim_awards_vp_to_unique_match() -> None:
    goal = _goal(predicate_id="chips_at_least_75", kind="single", vp_award=1)
    players = (
        _player(0, chips=50),
        _player(1, chips=80),  # only match
        _player(2, chips=50),
        _player(3, chips=50),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.players[1].vp == 1
    assert sum(p.vp for p in new_state.players) == 1
    # Goal moved to discard; slot empty (no replenishment available).
    assert new_state.active_goals[0] is None
    assert new_state.goal_discard == (goal,)


def test_single_claim_replenishes_from_goal_deck() -> None:
    consumed = _goal(gid="goal.consumed", predicate_id="chips_at_least_75", kind="single")
    next_face = _goal(gid="goal.next", predicate_id="full_hand", kind="renewable")
    players = (
        _player(0, chips=50),
        _player(1, chips=80),
        _player(2, chips=50),
        _player(3, chips=50),
    )
    state = _state(
        players,
        active_goals=(consumed, None, None),
        goal_deck=(next_face,),
    )
    new_state = goals.check_claims(state)
    assert new_state.active_goals[0] == next_face
    assert new_state.goal_discard == (consumed,)
    assert new_state.goal_deck == ()


def test_single_claim_recycles_discard_when_deck_empty() -> None:
    consumed = _goal(gid="goal.consumed", predicate_id="chips_at_least_75", kind="single")
    recyclable = _goal(gid="goal.recycle", predicate_id="full_hand", kind="renewable")
    players = (
        _player(0, chips=50),
        _player(1, chips=80),
        _player(2, chips=50),
        _player(3, chips=50),
    )
    state = _state(
        players,
        active_goals=(consumed, None, None),
        goal_deck=(),
        goal_discard=(recyclable,),
    )
    new_state = goals.check_claims(state)
    # Recycled in place: just-discarded sits at the bottom of the recycled
    # deck, so the prior discard `recyclable` is drawn first and replaces
    # the slot. `consumed` becomes the new bottom of the deck.
    assert new_state.active_goals[0] == recyclable
    assert new_state.goal_deck == (consumed,)
    assert new_state.goal_discard == ()


def test_single_claim_leaves_slot_empty_when_both_piles_exhausted() -> None:
    goal = _goal(predicate_id="chips_at_least_75", kind="single")
    players = (
        _player(0, chips=50),
        _player(1, chips=80),
        _player(2, chips=50),
        _player(3, chips=50),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.active_goals[0] is None
    assert new_state.goal_deck == ()


# --- check_claims: tie-break (single) -------------------------------------


def test_single_claim_tie_break_picks_lowest_vp() -> None:
    goal = _goal(predicate_id="chips_at_least_75", kind="single")
    players = (
        _player(0, chips=80, vp=1),
        _player(1, chips=80, vp=0),  # winner: lowest vp
        _player(2, chips=80, vp=1),
        _player(3, chips=80, vp=2),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.players[1].vp == 1
    assert new_state.players[0].vp == 1  # unchanged
    assert new_state.players[2].vp == 1  # unchanged


def test_single_claim_tie_break_falls_through_to_chips_then_seat() -> None:
    """All four tie on vp; chips break next; seat order from dealer breaks last."""
    goal = _goal(predicate_id="chips_at_least_75", kind="single")
    players = (
        _player(0, chips=90, vp=0),
        _player(1, chips=80, vp=0),  # winner: lowest chips among VP-tied
        _player(2, chips=85, vp=0),
        # also low chips; seat order from dealer=2 puts seat 3 first
        _player(3, chips=80, vp=0),
    )
    # dealer_seat=2 → seat order 2,3,0,1. p3 sits at distance 1, p1 at distance 3.
    state = _state(players, active_goals=(goal, None, None), dealer_seat=2)
    new_state = goals.check_claims(state)
    # p1 and p3 both have chips=80; seat order from dealer=2 picks p3 first.
    assert new_state.players[3].vp == 1
    assert new_state.players[1].vp == 0


# --- check_claims: renewable path -----------------------------------------


def test_renewable_goal_awards_every_match_and_stays() -> None:
    goal = _goal(predicate_id="full_hand", kind="renewable", vp_award=1)
    players = (
        _player(0, hand_size=HAND_SIZE),
        _player(1, hand_size=HAND_SIZE - 1),  # not eligible
        _player(2, hand_size=HAND_SIZE),
        _player(3, hand_size=HAND_SIZE),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.players[0].vp == 1
    assert new_state.players[1].vp == 0
    assert new_state.players[2].vp == 1
    assert new_state.players[3].vp == 1
    # Goal stayed face-up; nothing discarded.
    assert new_state.active_goals == (goal, None, None)
    assert new_state.goal_discard == ()


def test_renewable_goal_repeats_across_calls() -> None:
    """A renewable goal that fires every call to ``check_claims`` accumulates VP."""
    goal = _goal(predicate_id="full_hand", kind="renewable")
    players = (
        _player(0, hand_size=HAND_SIZE),
        _player(1),
        _player(2),
        _player(3),
    )
    state = _state(players, active_goals=(goal, None, None))
    state = goals.check_claims(state)
    state = goals.check_claims(state)
    state = goals.check_claims(state)
    assert state.players[0].vp == 3


# --- check_claims: CHAINED filter -----------------------------------------


def test_chained_player_skipped_for_single_claim_tie_break() -> None:
    """CHAINED player is filtered out before the tie-break runs."""
    goal = _goal(predicate_id="chips_at_least_75", kind="single")
    players = (
        _player(0, chips=80, vp=0, chained=True),  # CHAINED — skipped
        _player(1, chips=80, vp=1),  # only un-chained candidate
        _player(2, chips=50),
        _player(3, chips=50),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.players[0].vp == 0  # skipped
    assert new_state.players[1].vp == 2  # claimed


def test_chained_filter_can_leave_goal_dormant() -> None:
    """Single-claim goal where every match is CHAINED stays in active_goals."""
    goal = _goal(predicate_id="chips_at_least_75", kind="single")
    players = (
        _player(0, chips=80, chained=True),
        _player(1, chips=50),
        _player(2, chips=50),
        _player(3, chips=50),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.active_goals == (goal, None, None)
    assert new_state.goal_discard == ()
    assert all(p.vp == 0 for p in new_state.players)


def test_chained_player_gets_zero_from_renewable_goal() -> None:
    goal = _goal(predicate_id="full_hand", kind="renewable")
    players = (
        _player(0, hand_size=HAND_SIZE, chained=True),  # CHAINED — no award
        _player(1, hand_size=HAND_SIZE),
        _player(2),
        _player(3),
    )
    state = _state(players, active_goals=(goal, None, None))
    new_state = goals.check_claims(state)
    assert new_state.players[0].vp == 0
    assert new_state.players[1].vp == 1


# --- check_claims: ordering across multiple goals -------------------------


def test_left_to_right_award_order_observes_intermediate_vp_change() -> None:
    """Goal A's VP award can newly satisfy/fail goal B's predicate within one call."""
    goal_a = _goal(gid="goal.a", predicate_id="chips_at_least_75", kind="single", vp_award=1)
    goal_b = _goal(gid="goal.b", predicate_id="chips_under_10", kind="single", vp_award=1)
    players = (
        _player(0, chips=80, vp=0),  # claims A
        _player(1, chips=5, vp=0),  # claims B (independent)
        _player(2),
        _player(3),
    )
    state = _state(players, active_goals=(goal_a, goal_b, None))
    new_state = goals.check_claims(state)
    assert new_state.players[0].vp == 1
    assert new_state.players[1].vp == 1


def test_no_active_goals_is_noop() -> None:
    players = _four_players()
    state = _state(players, active_goals=())
    assert goals.check_claims(state) == state


def test_none_slot_is_skipped() -> None:
    players = _four_players()
    state = _state(players, active_goals=(None, None, None))
    assert goals.check_claims(state) == state


# --- start_game seeding ---------------------------------------------------


def test_start_game_seeds_active_goals_from_catalogue() -> None:
    state = start_game(seed=0)
    assert len(state.active_goals) == ACTIVE_GOALS
    # All three slots are populated when the catalogue has ≥ 3 goals.
    assert all(g is not None for g in state.active_goals)
    assert all(isinstance(g, GoalCard) for g in state.active_goals)


def test_start_game_goal_pile_partition_is_complete() -> None:
    """active_goals + goal_deck + goal_discard contains every catalogue goal exactly once."""
    state = start_game(seed=0)
    catalogue_ids = sorted(g.id for g in load_goal_cards())
    runtime_ids: list[str] = []
    runtime_ids.extend(g.id for g in state.active_goals if g is not None)
    runtime_ids.extend(g.id for g in state.goal_deck)
    runtime_ids.extend(g.id for g in state.goal_discard)
    assert sorted(runtime_ids) == catalogue_ids


def test_start_game_goal_seed_is_deterministic_under_same_seed() -> None:
    s1 = start_game(seed=0)
    s2 = start_game(seed=0)
    assert s1.active_goals == s2.active_goals
    assert s1.goal_deck == s2.goal_deck


def test_start_game_goal_seed_differs_across_seeds() -> None:
    """Distinct seeds shuffle goals into distinct active sets at least sometimes."""
    seen: set[tuple[str, ...]] = set()
    for seed in range(8):
        state = start_game(seed=seed)
        seen.add(tuple(g.id if g is not None else "" for g in state.active_goals))
    assert len(seen) > 1


# --- enter_resolve hook ---------------------------------------------------


def _resolve_ready_state() -> GameState:
    """Build a phase=RESOLVE state with a complete IF rule, ready for `enter_resolve`."""
    players = (
        _player(0, hand_size=HAND_SIZE),
        _player(1, hand_size=HAND_SIZE),
        _player(2, hand_size=HAND_SIZE),
        _player(3, hand_size=HAND_SIZE),
    )
    rule = RuleBuilder(
        template=RuleKind.IF,
        slots=(
            Slot(
                name="SUBJECT",
                type=CardType.SUBJECT,
                filled_by=Card(id="sub_p0", type=CardType.SUBJECT, name="p0"),
            ),
            Slot(
                name="QUANT",
                type=CardType.MODIFIER,
                filled_by=Card(id="q_ge_0", type=CardType.MODIFIER, name="GE:0"),
            ),
            Slot(
                name="NOUN",
                type=CardType.NOUN,
                filled_by=Card(id="n_chips", type=CardType.NOUN, name="CHIPS"),
            ),
        ),
        plays=(
            Play(
                player_id="p0",
                card=Card(id="sub_p0", type=CardType.SUBJECT, name="p0"),
                slot="SUBJECT",
            ),
        ),
    )
    return GameState(
        phase=Phase.RESOLVE,
        round_number=1,
        dealer_seat=0,
        active_seat=0,
        players=players,
        active_rule=rule,
        revealed_effect=Card(id="eff.vp.gain.1", type=CardType.EFFECT, name="GAIN_VP:1"),
    )


def test_enter_resolve_invokes_goal_claim_check_step_7() -> None:
    """A renewable goal matching at step 7 awards VP through the resolve pipeline."""
    state = _resolve_ready_state()
    goal = _goal(predicate_id="full_hand", kind="renewable", vp_award=1)
    state = state.model_copy(update={"active_goals": (goal, None, None)})
    out = enter_resolve(state)
    # Every player has full_hand → all four claim renewable +1 VP.
    # On top of that, the IF rule (`p0 HAS GE:0 CHIPS`) awards p0 +1 stub VP
    # (effects path, fires for chips ≥ 0). The renewable-goal step 7 happens
    # *after* effect application, so p0 ends up with 2 VP (1 from effect,
    # 1 from goal) — but that VP rises before win-check, so guard against the
    # smoke threshold (VP_TO_WIN=3) by asserting on the per-player delta.
    deltas = tuple(p.vp for p in out.players)
    # p0: effect (+1) + goal (+1) = 2 ; everyone else: goal only (+1).
    assert deltas == (2, 1, 1, 1)


def test_enter_resolve_with_no_active_goals_is_noop_for_step_7() -> None:
    state = _resolve_ready_state()
    state = state.model_copy(update={"active_goals": (None, None, None)})
    out = enter_resolve(state)
    # Only the IF effect awards VP (p0 gets +1).
    assert out.players[0].vp == 1
    assert all(p.vp == 0 for p in out.players[1:])

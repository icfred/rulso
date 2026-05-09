import pytest

from rulso.rules import (
    advance_phase,
    enter_resolve,
    pass_turn,
    play_card,
    start_game,
)
from rulso.state import (
    PLAYER_COUNT,
    Card,
    CardType,
    GameState,
    Phase,
    Player,
)


def _card(cid: str, type_: CardType) -> Card:
    return Card(id=cid, type=type_, name=cid)


def _drive_to_first_build() -> GameState:
    state = start_game()
    return advance_phase(state)


def test_start_game_initializes_round_start_at_round_zero() -> None:
    state = start_game()
    assert state.phase is Phase.ROUND_START
    assert state.round_number == 0
    assert state.dealer_seat == 0
    assert len(state.players) == PLAYER_COUNT
    assert all(state.players[i].seat == i for i in range(PLAYER_COUNT))
    assert state.active_rule is None


def test_advance_from_round_start_enters_build_with_dealer_first_slot_filled() -> None:
    state = _drive_to_first_build()
    assert state.phase is Phase.BUILD
    assert state.round_number == 1
    assert state.dealer_seat == 0
    assert state.active_seat == 1
    assert state.build_turns_taken == 0
    assert state.revealed_effect is not None
    assert state.active_rule is not None
    slots = state.active_rule.slots
    assert len(slots) == 4
    assert slots[0].filled_by is not None
    assert all(s.filled_by is None for s in slots[1:])
    assert state.active_rule.plays[0].player_id == "p0"


def test_play_card_fills_slot_and_advances_active_seat() -> None:
    state = _drive_to_first_build()
    state = play_card(state, _card("n1", CardType.NOUN), "noun")
    assert state.active_rule.slots[1].filled_by.id == "n1"
    assert state.active_seat == 2
    assert state.build_turns_taken == 1
    assert state.phase is Phase.BUILD


def test_play_card_rejects_type_mismatch() -> None:
    state = _drive_to_first_build()
    with pytest.raises(ValueError, match="does not match slot type"):
        play_card(state, _card("bad", CardType.SUBJECT), "noun")


def test_play_card_rejects_filled_slot() -> None:
    state = _drive_to_first_build()
    with pytest.raises(ValueError, match="already filled"):
        play_card(state, _card("dup", CardType.SUBJECT), "subject")


def test_play_card_rejects_unknown_slot() -> None:
    state = _drive_to_first_build()
    with pytest.raises(ValueError, match="unknown slot"):
        play_card(state, _card("n1", CardType.NOUN), "no_such_slot")


def test_play_card_outside_build_raises() -> None:
    state = start_game()
    with pytest.raises(ValueError, match="requires phase=BUILD"):
        play_card(state, _card("n1", CardType.NOUN), "noun")


def test_build_with_all_slots_filled_transitions_to_resolve() -> None:
    state = _drive_to_first_build()
    state = play_card(state, _card("n1", CardType.NOUN), "noun")
    state = play_card(state, _card("m1", CardType.MODIFIER), "modifier")
    state = play_card(state, _card("n2", CardType.NOUN), "noun_2")
    state = pass_turn(state)  # dealer's build turn — all slots already filled
    assert state.phase is Phase.RESOLVE
    assert state.build_turns_taken == PLAYER_COUNT
    assert all(s.filled_by is not None for s in state.active_rule.slots)


def test_build_with_unfilled_slot_fails_back_to_round_start() -> None:
    state = _drive_to_first_build()
    state = play_card(state, _card("n1", CardType.NOUN), "noun")
    state = pass_turn(state)
    state = play_card(state, _card("n2", CardType.NOUN), "noun_2")
    state = pass_turn(state)
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1
    assert state.active_rule is None
    # Played fragments + dealer's slot 0 fragment all moved to discard.
    assert len(state.discard) == 3


def test_resolve_transitions_to_round_start_and_rotates_dealer() -> None:
    state = _drive_to_first_build()
    state = play_card(state, _card("n1", CardType.NOUN), "noun")
    state = play_card(state, _card("m1", CardType.MODIFIER), "modifier")
    state = play_card(state, _card("n2", CardType.NOUN), "noun_2")
    state = pass_turn(state)
    assert state.phase is Phase.RESOLVE
    state = enter_resolve(state)
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1
    assert state.active_rule is None
    assert state.revealed_effect is None
    assert len(state.discard) == 4


def test_advance_phase_from_resolve_invokes_enter_resolve() -> None:
    state = _drive_to_first_build()
    state = play_card(state, _card("n1", CardType.NOUN), "noun")
    state = play_card(state, _card("m1", CardType.MODIFIER), "modifier")
    state = play_card(state, _card("n2", CardType.NOUN), "noun_2")
    state = pass_turn(state)
    state = advance_phase(state)
    assert state.phase is Phase.ROUND_START
    assert state.dealer_seat == 1


def test_dealer_rotates_across_four_rounds_via_failed_rules() -> None:
    state = start_game()
    seen_dealers: list[int] = []
    seen_rounds: list[int] = []
    for _ in range(PLAYER_COUNT):
        state = advance_phase(state)
        assert state.phase is Phase.BUILD
        seen_dealers.append(state.dealer_seat)
        seen_rounds.append(state.round_number)
        for _ in range(PLAYER_COUNT):
            state = advance_phase(state)
        assert state.phase is Phase.ROUND_START
    assert seen_dealers == [0, 1, 2, 3]
    assert seen_rounds == [1, 2, 3, 4]


def test_advance_from_lobby_enters_round_start() -> None:
    state = GameState(
        phase=Phase.LOBBY,
        players=tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT)),
    )
    state = advance_phase(state)
    assert state.phase is Phase.BUILD
    assert state.round_number == 1


def test_advance_from_shop_raises_not_implemented() -> None:
    state = GameState(
        phase=Phase.SHOP,
        players=tuple(Player(id=f"p{i}", seat=i) for i in range(PLAYER_COUNT)),
    )
    with pytest.raises(NotImplementedError, match="shop"):
        advance_phase(state)


def test_advance_from_end_is_idempotent() -> None:
    state = GameState(phase=Phase.END)
    assert advance_phase(state) == state


def test_burn_tick_drains_chips_and_clears_mute_at_round_start() -> None:
    from rulso.state import PlayerStatus

    state = start_game()
    burned = state.players[0].model_copy(
        update={
            "chips": 30,
            "status": PlayerStatus(burn=2, mute=True),
        }
    )
    state = state.model_copy(update={"players": (burned,) + state.players[1:]})
    state = advance_phase(state)
    p0 = state.players[0]
    assert p0.chips == 30 - 5 * 2
    assert p0.status.burn == 2  # BURN persists; only the chip drain ticks.
    assert p0.status.mute is False

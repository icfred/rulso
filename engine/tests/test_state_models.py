import pytest
from pydantic import ValidationError

from rulso.state import (
    ACTIVE_GOALS,
    BURN_TICK,
    DISCARD_COST,
    HAND_SIZE,
    MAX_PERSISTENT_RULES,
    PLAYER_COUNT,
    SHOP_INTERVAL,
    STARTING_CHIPS,
    VP_TO_WIN,
    Card,
    CardType,
    GameState,
    LastRoll,
    PersistentRule,
    Phase,
    Play,
    Player,
    PlayerHistory,
    PlayerStatus,
    RuleBuilder,
    RuleKind,
    Slot,
)


def _card(card_id: str = "c1", type_: CardType = CardType.SUBJECT) -> Card:
    return Card(id=card_id, type=type_, name=card_id)


def _player(seat: int = 0, pid: str | None = None) -> Player:
    return Player(id=pid or f"p{seat}", seat=seat)


def test_constants_match_design_spec() -> None:
    assert PLAYER_COUNT == 4
    assert HAND_SIZE == 7
    assert STARTING_CHIPS == 50
    assert VP_TO_WIN == 5
    assert ACTIVE_GOALS == 3
    assert SHOP_INTERVAL == 3
    assert MAX_PERSISTENT_RULES == 5
    assert DISCARD_COST == 5
    assert BURN_TICK == 5


def test_player_construction_with_defaults() -> None:
    p = _player(seat=2, pid="alice")
    assert p.seat == 2
    assert p.chips == STARTING_CHIPS
    assert p.vp == 0
    assert p.hand == ()
    assert p.status == PlayerStatus()
    assert p.history == PlayerHistory()


def test_player_status_and_history_defaults() -> None:
    s = PlayerStatus()
    assert s.burn == 0
    assert s.mute is False
    assert s.blessed is False
    assert s.marked is False
    assert s.chained is False

    h = PlayerHistory()
    assert h.rules_completed_this_game == 0
    assert h.cards_given_this_game == 0
    assert h.last_round_was_hit is False


def test_gamestate_construction_with_defaults() -> None:
    g = GameState()
    assert g.phase is Phase.LOBBY
    assert g.round_number == 0
    assert g.players == ()
    assert g.active_rule is None
    assert g.winner is None
    assert g.last_roll is None


def test_gamestate_with_full_payload() -> None:
    card = _card("subject_each_player", CardType.SUBJECT)
    slot = Slot(name="subject", type=CardType.SUBJECT, filled_by=card)
    play = Play(player_id="p0", card=card, slot="subject")
    rule = RuleBuilder(template=RuleKind.IF, slots=(slot,), plays=(play,))
    persistent = PersistentRule(kind=RuleKind.WHEN, rule=rule, created_round=2, created_by="p0")
    g = GameState(
        phase=Phase.BUILD,
        round_number=2,
        dealer_seat=0,
        active_seat=1,
        players=tuple(_player(seat=i) for i in range(PLAYER_COUNT)),
        active_rule=rule,
        persistent_rules=(persistent,),
        last_roll=LastRoll(player_id="p1", value=5, dice_count=1),
    )
    assert len(g.players) == PLAYER_COUNT
    assert g.active_rule is rule
    assert g.persistent_rules[0].kind is RuleKind.WHEN
    assert g.last_roll.value == 5


def test_player_is_frozen() -> None:
    p = _player()
    with pytest.raises(ValidationError):
        p.chips = 0


def test_gamestate_is_frozen() -> None:
    g = GameState()
    with pytest.raises(ValidationError):
        g.round_number = 99


def test_player_round_trip_json() -> None:
    p = Player(
        id="alice",
        seat=0,
        chips=42,
        vp=1,
        hand=(_card("a", CardType.SUBJECT), _card("b", CardType.NOUN)),
        status=PlayerStatus(burn=2, marked=True),
        history=PlayerHistory(rules_completed_this_game=3, last_round_was_hit=True),
    )
    restored = Player.model_validate_json(p.model_dump_json())
    assert restored == p


def test_gamestate_round_trip_json() -> None:
    rule = RuleBuilder(
        template=RuleKind.WHILE,
        slots=(Slot(name="subject", type=CardType.SUBJECT),),
    )
    g = GameState(
        phase=Phase.RESOLVE,
        round_number=4,
        active_seat=2,
        players=(
            Player(id="p0", seat=0, chips=10),
            Player(id="p1", seat=1, vp=2),
        ),
        active_rule=rule,
        last_roll=LastRoll(player_id="p1", value=8, dice_count=2),
    )
    restored = GameState.model_validate_json(g.model_dump_json())
    assert restored == g


def test_model_copy_update_pattern() -> None:
    g = GameState()
    advanced = g.model_copy(update={"round_number": g.round_number + 1, "phase": Phase.BUILD})
    assert g.round_number == 0
    assert advanced.round_number == 1
    assert advanced.phase is Phase.BUILD


# --- RUL-70: GameState.labels field round-trip ------------------------------


def test_gamestate_labels_field_default_is_empty_dict() -> None:
    g = GameState()
    assert g.labels == {}


def test_gamestate_labels_round_trip_json() -> None:
    """Wire shape ``dict[str, tuple[str, ...]]`` survives JSON round-trip."""
    g = GameState(
        labels={
            "THE LEADER": ("p0", "p1"),
            "THE WOUNDED": ("p2",),
            "THE GENEROUS": (),
            "THE CURSED": (),
            "THE MARKED": (),
            "THE CHAINED": (),
        },
    )
    restored = GameState.model_validate_json(g.model_dump_json())
    assert restored == g
    assert restored.labels["THE LEADER"] == ("p0", "p1")
    assert isinstance(restored.labels["THE LEADER"], tuple)


def test_gamestate_labels_serialises_as_json_object_of_arrays() -> None:
    g = GameState(labels={"THE LEADER": ("p0",)})
    raw = g.model_dump_json()
    assert '"labels":{"THE LEADER":["p0"]}' in raw

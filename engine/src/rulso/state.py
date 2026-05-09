"""Pydantic v2 data shapes for Rulso game state.

Mirrors the canonical contract in `design/state.md`. No game logic lives here;
this module is the schema other engine modules read from and write through.

All models are frozen. Update with ``model_copy``::

    new_state = state.model_copy(update={"round_number": state.round_number + 1})

Collection fields use ``tuple`` so frozen instances are deeply immutable —
``list.append`` would otherwise bypass field-assignment locking.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

PLAYER_COUNT: int = 4
HAND_SIZE: int = 7
STARTING_CHIPS: int = 50
VP_TO_WIN: int = 3
ACTIVE_GOALS: int = 3
SHOP_INTERVAL: int = 3
MAX_PERSISTENT_RULES: int = 5
DISCARD_COST: int = 5
BURN_TICK: int = 5


class Phase(StrEnum):
    LOBBY = "lobby"
    ROUND_START = "round_start"
    BUILD = "build"
    RESOLVE = "resolve"
    SHOP = "shop"
    END = "end"


class CardType(StrEnum):
    SUBJECT = "SUBJECT"
    NOUN = "NOUN"
    MODIFIER = "MODIFIER"
    JOKER = "JOKER"


class RuleKind(StrEnum):
    IF = "IF"
    WHEN = "WHEN"
    WHILE = "WHILE"


_FROZEN = ConfigDict(frozen=True)


class Card(BaseModel):
    model_config = _FROZEN

    id: str
    type: CardType
    name: str


class PlayerStatus(BaseModel):
    model_config = _FROZEN

    burn: int = 0
    mute: bool = False
    blessed: bool = False
    marked: bool = False
    chained: bool = False


class PlayerHistory(BaseModel):
    model_config = _FROZEN

    rules_completed_this_game: int = 0
    cards_given_this_game: int = 0
    last_round_was_hit: bool = False


class Player(BaseModel):
    model_config = _FROZEN

    id: str
    seat: int
    chips: int = STARTING_CHIPS
    vp: int = 0
    hand: tuple[Card, ...] = ()
    status: PlayerStatus = Field(default_factory=PlayerStatus)
    history: PlayerHistory = Field(default_factory=PlayerHistory)


class Slot(BaseModel):
    model_config = _FROZEN

    name: str
    type: CardType
    filled_by: Card | None = None
    modifiers: tuple[Card, ...] = ()


class Play(BaseModel):
    model_config = _FROZEN

    player_id: str
    card: Card
    slot: str


class RuleBuilder(BaseModel):
    model_config = _FROZEN

    template: RuleKind
    slots: tuple[Slot, ...] = ()
    plays: tuple[Play, ...] = ()
    joker_attached: Card | None = None


class PersistentRule(BaseModel):
    """A WHEN or WHILE rule locked into play.

    `kind` is restricted to ``RuleKind.WHEN`` or ``RuleKind.WHILE``;
    ``IF`` rules are one-shot and never persist.
    """

    model_config = _FROZEN

    kind: RuleKind
    rule: RuleBuilder
    created_round: int
    created_by: str


class LastRoll(BaseModel):
    model_config = _FROZEN

    player_id: str
    value: int
    dice_count: int


class GameState(BaseModel):
    """Top-level immutable game state.

    Update via ``model_copy``::

        next_state = state.model_copy(
            update={"phase": Phase.BUILD, "active_seat": 1},
        )
    """

    model_config = _FROZEN

    phase: Phase = Phase.LOBBY
    round_number: int = 0
    dealer_seat: int = 0
    active_seat: int = 0
    players: tuple[Player, ...] = ()
    deck: tuple[Card, ...] = ()
    discard: tuple[Card, ...] = ()
    effect_deck: tuple[Card, ...] = ()
    effect_discard: tuple[Card, ...] = ()
    goal_deck: tuple[Card, ...] = ()
    goal_discard: tuple[Card, ...] = ()
    active_goals: tuple[Card, ...] = ()
    active_rule: RuleBuilder | None = None
    persistent_rules: tuple[PersistentRule, ...] = ()
    last_roll: LastRoll | None = None
    winner: Player | None = None

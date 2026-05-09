"""Game state models. Pydantic v2, frozen."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Phase = Literal["lobby", "round_start", "build", "resolve", "shop", "end"]
CardType = Literal["SUBJECT", "NOUN", "MODIFIER", "JOKER", "CONDITION"]
RuleKind = Literal["IF", "WHEN", "WHILE"]
SlotKind = Literal["SUBJECT", "NOUN", "MODIFIER", "QUANT"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Config(FrozenModel):
    """Tunable game constants. See design/state.md for rationale."""

    player_count: int = 4
    hand_size: int = 7
    starting_chips: int = 50
    vp_to_win: int = 3
    active_goals: int = 3
    shop_interval: int = 3
    max_persistent_rules: int = 5
    discard_cost: int = 5
    burn_tick: int = 5


class Card(FrozenModel):
    id: str
    type: CardType
    text: str = ""
    rule_kind: RuleKind | None = None
    is_comparator: bool = False


class StatusTokens(FrozenModel):
    burn: int = 0
    mute: bool = False
    blessed: bool = False
    marked: bool = False
    chained: bool = False


class PlayerHistory(FrozenModel):
    rules_completed_this_game: int = 0
    cards_given_this_game: int = 0
    last_round_was_hit: bool = False


class Player(FrozenModel):
    id: str
    seat: int
    chips: int = 50
    vp: int = 0
    hand: tuple[Card, ...] = ()
    status: StatusTokens = StatusTokens()
    history: PlayerHistory = PlayerHistory()


class Slot(FrozenModel):
    name: str
    kind: SlotKind
    required: bool = True
    filled_by: Card | None = None
    modifiers: tuple[Card, ...] = ()


class Play(FrozenModel):
    seat: int
    card: Card | None
    slot_name: str | None


class RuleBuilder(FrozenModel):
    template: Card
    slots: tuple[Slot, ...]
    plays: tuple[Play, ...] = ()
    joker_attached: Card | None = None


class PersistentRule(FrozenModel):
    kind: Literal["WHEN", "WHILE"]
    rule: RuleBuilder
    created_round: int
    created_seat: int


class LastRoll(FrozenModel):
    seat: int
    value: int
    dice_count: int


class GameState(FrozenModel):
    config: Config = Config()
    phase: Phase = "lobby"
    round_number: int = 0
    dealer_seat: int = 0
    active_seat: int = 0
    build_turns_taken: int = 0
    players: tuple[Player, ...] = ()
    deck: tuple[Card, ...] = ()
    discard: tuple[Card, ...] = ()
    effect_deck: tuple[Card, ...] = ()
    effect_discard: tuple[Card, ...] = ()
    revealed_effect: Card | None = None
    goal_deck: tuple[Card, ...] = ()
    goal_discard: tuple[Card, ...] = ()
    active_goals: tuple[Card, ...] = ()
    active_rule: RuleBuilder | None = None
    persistent_rules: tuple[PersistentRule, ...] = ()
    last_roll: LastRoll | None = None
    winner_seat: int | None = None
    seed: int = 0

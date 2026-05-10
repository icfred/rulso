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
from typing import Literal

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
    # RUL-31: effect cards live in their own deck (`GameState.effect_deck`),
    # revealed at round_start step 6 per `design/effects-inventory.md`.
    EFFECT = "EFFECT"


# RUL-31 (ADR-0003): SUBJECT scoping mode. Cards default to ``singular``;
# polymorphic SUBJECTs (`ANYONE`, `EACH_PLAYER`) override. Read by the M2
# resolver; ignored for non-SUBJECT cards.
ScopeMode = Literal["singular", "existential", "iterative"]


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
    # RUL-31 (ADR-0003): SUBJECT scoping. Default ``singular`` preserves M1.5
    # behaviour for every existing card; ``existential`` (ANYONE) and
    # ``iterative`` (EACH_PLAYER) are set on the polymorphic SUBJECTs only.
    scope_mode: ScopeMode = "singular"


class GoalCard(BaseModel):
    """Goal card — face-up VP-award objective per ``design/goals-inventory.md``.

    Lives in its own deck (``GameState.goal_deck`` / ``goal_discard`` /
    ``active_goals``); not a :class:`Card` because its payload (predicate id,
    VP award, claim kind) doesn't fit the uniform ``Card`` shape.

    ``claim_condition`` is a **registry key** (snake_case predicate id), not
    an expression — the engine resolves it to a function ``(player, state) →
    bool`` at evaluation time. ``claim_kind`` controls life-cycle: ``"single"``
    discards on first match and replenishes from ``goal_deck``; ``"renewable"``
    stays face-up and awards ``vp_award`` to every matching player each round.
    """

    model_config = _FROZEN

    id: str
    name: str
    claim_condition: str
    vp_award: int
    claim_kind: Literal["single", "renewable"]


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
    # RUL-26: hit-history counter; consumed by M2 NOUN `hits` and follow-on labels.
    hits_taken_this_game: int = 0
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
    # RUL-46: retype goal piles + face-up slots to GoalCard per
    # design/goals-inventory.md ("Schema fit"). RUL-26 stubbed these as Card
    # before GoalCard existed; ratifying the spike-locked shape — no field
    # renamed or removed, the value type narrows from Card to GoalCard.
    goal_deck: tuple[GoalCard, ...] = ()
    goal_discard: tuple[GoalCard, ...] = ()
    # RUL-26: 3 face-up goal slots per design/state.md; None marks an empty slot.
    active_goals: tuple[GoalCard | None, ...] = (None, None, None)
    # RUL-26: SHOP-card pile; populated when SHOP card content lands in M2.
    shop_deck: tuple[Card, ...] = ()
    active_rule: RuleBuilder | None = None
    persistent_rules: tuple[PersistentRule, ...] = ()
    last_roll: LastRoll | None = None
    winner: Player | None = None
    # Added by RUL-8 (round flow phase machine). Additive only — see docs/engine/round-flow.md.
    build_turns_taken: int = 0
    revealed_effect: Card | None = None

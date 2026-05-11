"""WebSocket protocol envelopes for engine↔client traffic (M3, ADR-0008).

JSON over websocket, snake_case keys. Engine is authoritative: client sends
intent (:class:`ActionSubmit`), engine validates and broadcasts the resulting
``GameState`` via :class:`StateBroadcast`. Full state on every transition;
diff protocol is a future optimisation.

Discriminated unions:

* Server → client envelopes are tagged on ``type`` and dispatched via
  :data:`ServerEnvelope` (:class:`Hello` / :class:`StateBroadcast` /
  :class:`ErrorEnvelope`).
* Client → server envelopes are tagged on ``type`` and dispatched via
  :data:`ClientEnvelope` (:class:`ActionSubmit`).
* Inside :class:`ActionSubmit`, the wrapped action is itself a discriminated
  union — tagged on ``kind`` (existing engine convention; see
  :mod:`rulso.legality`). Action shapes are imported, not redefined, so
  the wire format and the engine's internal action model stay one and the
  same; no risk of structural drift.

Parse with :class:`pydantic.TypeAdapter`::

    from pydantic import TypeAdapter
    adapter = TypeAdapter(ServerEnvelope)
    msg = adapter.validate_json(raw_bytes)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from rulso.legality import DiscardRedraw, PlayCard, PlayJoker
from rulso.state import GameState

PROTOCOL_VERSION: int = 1

_FROZEN = ConfigDict(frozen=True)


class ErrorCode(StrEnum):
    """Error categories an engine may emit to a client.

    Additive: new variants extend this enum without protocol-version bump.
    """

    PROTOCOL_INVALID = "protocol_invalid"
    NOT_YOUR_TURN = "not_your_turn"
    ILLEGAL_ACTION = "illegal_action"
    UNKNOWN_ACTION = "unknown_action"
    INTERNAL_ERROR = "internal_error"


# Client-submittable action union. ``Pass`` is intentionally excluded — the
# server picks ``Pass`` automatically when ``enumerate_legal_actions`` returns
# empty; clients never submit it. The union reuses the engine's existing
# action shapes verbatim via import — no duplicate definitions.
ClientAction = Annotated[
    PlayCard | PlayJoker | DiscardRedraw,
    Field(discriminator="kind"),
]


class Hello(BaseModel):
    """Server → client greeting, sent once after a connection is accepted.

    Assigns the human's seat and pins the protocol version. Subsequent
    incompatible envelope changes bump :data:`PROTOCOL_VERSION`.
    """

    model_config = _FROZEN

    type: Literal["hello"] = "hello"
    seat: int = Field(ge=0)
    protocol_version: int


class StateBroadcast(BaseModel):
    """Server → client full-state push.

    Sent on every engine transition that mutates ``GameState`` (phase change,
    action applied, status tick, shop resolution). MVP cadence is "every
    transition" per ADR-0008; a diff protocol is a future additive variant.

    ``legal_actions`` is populated only on broadcasts where the human seat is
    active in BUILD — the client renders one button per entry and submits the
    chosen action via :class:`ActionSubmit`. ``None`` on every other broadcast
    (bot turns, non-BUILD phases, terminal state). Additive per ADR-0008
    §Consequences — no ``PROTOCOL_VERSION`` bump.
    """

    model_config = _FROZEN

    type: Literal["state"] = "state"
    state: GameState
    legal_actions: tuple[ClientAction, ...] | None = None


class ErrorEnvelope(BaseModel):
    """Server → client protocol/legality violation.

    ``code`` keeps the categorisation machine-readable; ``message`` is the
    human-readable explanation. The server does not disconnect on protocol
    error — it returns the envelope and waits for a corrected submission.
    """

    model_config = _FROZEN

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


class ActionSubmit(BaseModel):
    """Client → server: submit one action for the active turn.

    The wrapped :data:`ClientAction` carries the engine's existing action
    shape. The server re-enumerates legal actions for the submitter's seat
    and validates structural equality before applying — never trusts the
    submitted payload's legality on its face.
    """

    model_config = _FROZEN

    type: Literal["action_submit"] = "action_submit"
    action: ClientAction


ServerEnvelope = Annotated[
    Hello | StateBroadcast | ErrorEnvelope,
    Field(discriminator="type"),
]
"""Discriminated union of every envelope the engine sends to a client."""


ClientEnvelope = Annotated[
    ActionSubmit,
    Field(discriminator="type"),
]
"""Discriminated union of every envelope a client sends to the engine.

Singular today; remains a tagged union so future client→server variants
(reconnect, replay-request) extend additively without callers re-shaping
their parse path.
"""

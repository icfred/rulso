"""Round-trip and validation tests for the WS protocol envelopes (RUL-63).

The protocol substrate (`rulso.protocol`) defines the wire format every M3
sub-issue consumes. These tests pin the discriminator-based dispatch, the
JSON round-trip for both envelope unions, and the validation failures the
server relies on for ``ErrorCode.PROTOCOL_INVALID`` emission.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from rulso.legality import DiscardRedraw, PlayCard, PlayJoker
from rulso.protocol import (
    PROTOCOL_VERSION,
    ActionSubmit,
    ClientEnvelope,
    ErrorCode,
    ErrorEnvelope,
    Hello,
    ServerEnvelope,
    StateBroadcast,
)
from rulso.rules import start_game

SERVER_ADAPTER = TypeAdapter(ServerEnvelope)
CLIENT_ADAPTER = TypeAdapter(ClientEnvelope)


def test_protocol_version_is_int_one() -> None:
    """Pin the M3 baseline so a silent bump is caught."""
    assert PROTOCOL_VERSION == 1


# --- server-envelope round-trip --------------------------------------------


def test_hello_round_trip() -> None:
    msg = Hello(seat=0, protocol_version=PROTOCOL_VERSION)
    parsed = SERVER_ADAPTER.validate_json(msg.model_dump_json())
    assert parsed == msg
    assert isinstance(parsed, Hello)


def test_state_broadcast_round_trip_with_real_game_state() -> None:
    """Full-state envelope round-trips a `start_game(0)` snapshot byte-for-byte.

    Catches any regression that drops a GameState field from the broadcast
    (e.g. forgetting to re-serialise ``revealed_effect`` or ``shop_pool``).
    """
    state = start_game(0)
    msg = StateBroadcast(state=state)
    raw = msg.model_dump_json()
    parsed = SERVER_ADAPTER.validate_json(raw)
    assert isinstance(parsed, StateBroadcast)
    assert parsed == msg
    assert parsed.state == state


def test_error_envelope_round_trip() -> None:
    msg = ErrorEnvelope(code=ErrorCode.ILLEGAL_ACTION, message="slot already filled")
    parsed = SERVER_ADAPTER.validate_json(msg.model_dump_json())
    assert parsed == msg
    assert isinstance(parsed, ErrorEnvelope)


def test_error_envelope_serialises_code_as_snake_case_string() -> None:
    """`ErrorCode` is a `StrEnum`; JSON value is the snake_case literal."""
    msg = ErrorEnvelope(code=ErrorCode.NOT_YOUR_TURN, message="seat 2 active")
    raw = msg.model_dump_json()
    assert '"code":"not_your_turn"' in raw


# --- client-envelope round-trip --------------------------------------------


def test_action_submit_play_card_round_trip() -> None:
    action = PlayCard(card_id="subj.leader", slot="SUBJECT", dice=None)
    msg = ActionSubmit(action=action)
    parsed = CLIENT_ADAPTER.validate_json(msg.model_dump_json())
    assert parsed == msg
    assert isinstance(parsed, ActionSubmit)
    assert isinstance(parsed.action, PlayCard)


def test_action_submit_play_card_with_dice_round_trip() -> None:
    action = PlayCard(card_id="mod.cmp.gt", slot="QUANT", dice=2)
    msg = ActionSubmit(action=action)
    parsed = CLIENT_ADAPTER.validate_json(msg.model_dump_json())
    assert parsed == msg
    assert isinstance(parsed.action, PlayCard)
    assert parsed.action.dice == 2


def test_action_submit_play_joker_round_trip() -> None:
    action = PlayJoker(card_id="jkr.double")
    msg = ActionSubmit(action=action)
    parsed = CLIENT_ADAPTER.validate_json(msg.model_dump_json())
    assert parsed == msg
    assert isinstance(parsed.action, PlayJoker)


def test_action_submit_discard_redraw_round_trip() -> None:
    action = DiscardRedraw(card_ids=("c1", "c2", "c3"))
    msg = ActionSubmit(action=action)
    parsed = CLIENT_ADAPTER.validate_json(msg.model_dump_json())
    assert parsed == msg
    assert isinstance(parsed.action, DiscardRedraw)
    assert parsed.action.card_ids == ("c1", "c2", "c3")


# --- discriminated-dispatch correctness ------------------------------------


def test_server_envelope_dispatches_by_type_discriminator() -> None:
    """Each envelope variant is selected purely by the ``type`` tag."""
    hello = SERVER_ADAPTER.validate_json('{"type":"hello","seat":1,"protocol_version":1}')
    assert isinstance(hello, Hello)
    err = SERVER_ADAPTER.validate_json('{"type":"error","code":"illegal_action","message":"x"}')
    assert isinstance(err, ErrorEnvelope)


def test_client_action_dispatches_by_kind_discriminator() -> None:
    """Inner action union is tagged on ``kind`` (engine convention, not ``type``)."""
    raw = '{"type":"action_submit","action":{"kind":"discard_redraw","card_ids":["a","b"]}}'
    parsed = CLIENT_ADAPTER.validate_json(raw)
    assert isinstance(parsed, ActionSubmit)
    assert isinstance(parsed.action, DiscardRedraw)


# --- validation failures (the surface the server emits PROTOCOL_INVALID on) -


def test_unknown_server_type_rejected() -> None:
    with pytest.raises(ValidationError):
        SERVER_ADAPTER.validate_json('{"type":"goodbye"}')


def test_unknown_client_type_rejected() -> None:
    with pytest.raises(ValidationError):
        CLIENT_ADAPTER.validate_json('{"type":"resign"}')


def test_unknown_action_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        CLIENT_ADAPTER.validate_json('{"type":"action_submit","action":{"kind":"surrender"}}')


def test_pass_action_is_not_a_legal_client_submission() -> None:
    """``Pass`` is server-side only; clients never submit it."""
    with pytest.raises(ValidationError):
        CLIENT_ADAPTER.validate_json('{"type":"action_submit","action":{"kind":"pass"}}')


def test_missing_type_rejected() -> None:
    with pytest.raises(ValidationError):
        SERVER_ADAPTER.validate_json('{"seat":0,"protocol_version":1}')


def test_hello_negative_seat_rejected() -> None:
    with pytest.raises(ValidationError):
        Hello(seat=-1, protocol_version=PROTOCOL_VERSION)


def test_state_broadcast_missing_state_field_rejected() -> None:
    with pytest.raises(ValidationError):
        SERVER_ADAPTER.validate_json('{"type":"state"}')


def test_invalid_error_code_rejected() -> None:
    with pytest.raises(ValidationError):
        SERVER_ADAPTER.validate_json('{"type":"error","code":"oops","message":"unspecified"}')


def test_action_submit_with_bad_dice_value_rejected() -> None:
    """Action shapes inherit constraints from ``legality`` (e.g. ``dice ∈ {1, 2, None}``)."""
    with pytest.raises(ValidationError):
        CLIENT_ADAPTER.validate_json(
            '{"type":"action_submit","action":'
            '{"kind":"play_card","card_id":"x","slot":"s","dice":3}}'
        )

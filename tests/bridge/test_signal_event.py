from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.bridge.signal_event import SignalEvent


def test_valid_signal_parses(signal_payload):
    event = SignalEvent.model_validate(signal_payload)
    assert event.symbol == "BTCUSDT"
    assert event.side == "buy"
    assert event.ttl_seconds == 900


@pytest.mark.parametrize(
    "missing",
    [
        "signal_id",
        "symbol",
        "venue",
        "ts_event",
        "horizon",
        "side",
        "score",
        "confidence",
        "source",
        "model_version",
        "ttl_seconds",
    ],
)
def test_missing_required_field_rejected(make_payload, missing):
    payload = make_payload()
    payload.pop(missing)
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)


def test_unknown_extra_field_rejected(make_payload):
    payload = make_payload(extra_field="nope")
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "signal.v2"),
        ("side", "long"),
        ("score", 1.5),
        ("score", -1.5),
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("ttl_seconds", 0),
        ("ttl_seconds", -1),
    ],
)
def test_invalid_values_rejected(make_payload, field, value):
    payload = make_payload(**{field: value})
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)


def test_signal_event_is_immutable(signal_event):
    with pytest.raises(PydanticValidationError):
        signal_event.symbol = "ETHUSDT"  # type: ignore[misc]

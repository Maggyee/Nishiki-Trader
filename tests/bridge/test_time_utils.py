from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.bridge.signal_event import SignalEvent
from apps.bridge.time_utils import TimeUnitError, ensure_ns, to_ns

REFERENCE_NS = 1_778_760_000_000_000_000  # 2026-05-14T12:00:00Z
REFERENCE_US = REFERENCE_NS // 1_000
REFERENCE_MS = REFERENCE_NS // 1_000_000


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (REFERENCE_NS, "ns", REFERENCE_NS),
        (REFERENCE_US, "us", REFERENCE_NS),
        (REFERENCE_MS, "ms", REFERENCE_NS),
    ],
)
def test_to_ns_unit_boundaries(value, unit, expected):
    assert to_ns(value, unit) == expected


def test_to_ns_rejects_unknown_unit():
    with pytest.raises(TimeUnitError):
        to_ns(REFERENCE_MS, "seconds")  # type: ignore[arg-type]


def test_to_ns_rejects_non_int():
    with pytest.raises(TimeUnitError):
        to_ns(float(REFERENCE_NS), "ns")  # type: ignore[arg-type]


def test_to_ns_rejects_negative():
    with pytest.raises(TimeUnitError):
        to_ns(-1, "ns")


def test_ensure_ns_accepts_ns_range():
    assert ensure_ns(REFERENCE_NS) == REFERENCE_NS


@pytest.mark.parametrize("bad_value", [REFERENCE_MS, REFERENCE_US])
def test_ensure_ns_rejects_ms_or_us_input(bad_value):
    with pytest.raises(TimeUnitError):
        ensure_ns(bad_value)


def test_signal_event_rejects_non_ns_ts(make_payload):
    payload = make_payload(ts_event=REFERENCE_MS)
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)

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


# ----- ADR-005 §2.1: source family prefix ---------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "manual_research",
        "manual_morning_review",
        "rule_baseline_v1",
        "rule_ema_rsi",
        "freqai_v1",
        "freqai_lgbm_15m",
        "llm_overnight_review",
        "llm_news_sentiment_v2",
    ],
)
def test_source_family_prefix_accepted(make_payload, source):
    payload = make_payload(source=source)
    event = SignalEvent.model_validate(payload)
    assert event.source == source


@pytest.mark.parametrize(
    "source",
    [
        "unknown_source",
        "agent_v1",  # `agent` is not one of the 4 families
        "manual",  # missing variant
        "manual_",  # variant must have at least one char
        "rule_",  # ditto
        "manual-research",  # hyphen disallowed
        "Manual_research",  # uppercase disallowed
        "manual_Research",  # uppercase in variant disallowed
        "rule_BTC",  # uppercase in variant disallowed
        "rule_3-day",  # hyphen disallowed
        "freqai_lgbm.15m",  # dot disallowed
        "llm news",  # space disallowed
        "_manual_research",  # leading underscore disallowed
        "",  # empty
    ],
)
def test_source_family_prefix_rejected(make_payload, source):
    payload = make_payload(source=source)
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)


def test_source_variant_must_start_with_alphanumeric(make_payload):
    # ADR-005 §2.1: variant must start with [a-z0-9], not "_"
    payload = make_payload(source="manual__double_underscore")
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)


def test_existing_demo_and_rule_sources_pass_under_adr_005(make_payload):
    # Smoke-test that the two sources already living in production signals.db
    # remain valid after ADR-005's prefix gate kicks in.
    for source in ("manual_research", "rule_baseline_v1"):
        SignalEvent.model_validate(make_payload(source=source))


@pytest.mark.parametrize(
    ("side", "score"),
    [
        ("buy", -0.1),
        ("sell", 0.1),
        ("flat", 0.2),
    ],
)
def test_side_score_conflict_rejected(make_payload, side, score):
    payload = make_payload(side=side, score=score, signal_id=f"conflict-{side}-{score}")
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("side", "score"),
    [
        ("buy", 0.0),
        ("sell", 0.0),
        ("sell", -0.4),
        ("flat", 0.0),
    ],
)
def test_side_score_boundary_values_accepted(make_payload, side, score):
    event = SignalEvent.model_validate(
        make_payload(side=side, score=score, signal_id=f"ok-{side}-{score}")
    )
    assert event.side == side
    assert event.score == score

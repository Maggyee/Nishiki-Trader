from __future__ import annotations

from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.signal_consumer import (
    ConsumerConfig,
    SignalConsumer,
    evaluate,
)


def test_accept_valid_signal(signal_event, config):
    outcome = evaluate(signal_event, config, now_ns=signal_event.ts_event)
    assert outcome.decision == "accept"
    assert outcome.reason is None


def test_reject_venue_mismatch(make_payload, config):
    event = SignalEvent.model_validate(make_payload(venue="COINBASE"))
    outcome = evaluate(event, config, now_ns=event.ts_event)
    assert outcome.decision == "reject_venue"


def test_reject_unauthorized_source(make_payload, config):
    event = SignalEvent.model_validate(make_payload(source="llm_rogue"))
    outcome = evaluate(event, config, now_ns=event.ts_event)
    assert outcome.decision == "reject_unauthorized_source"


def test_reject_unauthorized_model(make_payload, config):
    event = SignalEvent.model_validate(make_payload(model_version="9999-99-99"))
    outcome = evaluate(event, config, now_ns=event.ts_event)
    assert outcome.decision == "reject_unauthorized_model"


def test_expired_signal(signal_event, config):
    now_ns = signal_event.ts_event + (signal_event.ttl_seconds + 1) * 1_000_000_000
    outcome = evaluate(signal_event, config, now_ns=now_ns)
    assert outcome.decision == "expired"


def test_reject_low_confidence(make_payload, config):
    event = SignalEvent.model_validate(make_payload(confidence=0.10))
    outcome = evaluate(event, config, now_ns=event.ts_event)
    assert outcome.decision == "reject_low_confidence"


def test_consume_pending_marks_store(store, signal_event, config):
    store.write(signal_event)
    consumer = SignalConsumer(store, config)
    outcomes = consumer.consume_pending(now_ns=signal_event.ts_event)
    assert [o.decision for o in outcomes] == ["accept"]
    row = store.get(signal_event.signal_id)
    assert row["status"] == "consumed"
    assert row["consumed_at"] is not None


def test_consume_pending_marks_expired(store, signal_event, config):
    store.write(signal_event)
    expired_now = signal_event.ts_event + (signal_event.ttl_seconds + 5) * 1_000_000_000
    consumer = SignalConsumer(store, config)
    outcomes = consumer.consume_pending(now_ns=expired_now)
    assert [o.decision for o in outcomes] == ["expired"]
    assert store.get(signal_event.signal_id)["status"] == "expired"


def test_consume_pending_marks_rejected(store, make_payload, config):
    event = SignalEvent.model_validate(make_payload(confidence=0.1))
    store.write(event)
    consumer = SignalConsumer(store, config)
    outcomes = consumer.consume_pending(now_ns=event.ts_event)
    assert outcomes[0].decision == "reject_low_confidence"
    row = store.get(event.signal_id)
    assert row["status"] == "rejected"
    assert "confidence" in (row["reason"] or "")


def test_consume_pending_is_idempotent(store, signal_event, config):
    store.write(signal_event)
    consumer = SignalConsumer(store, config)
    first = consumer.consume_pending(now_ns=signal_event.ts_event)
    second = consumer.consume_pending(now_ns=signal_event.ts_event)
    assert [o.decision for o in first] == ["accept"]
    assert second == []  # already consumed; no pending rows left


def test_consumer_module_has_no_trading_api_calls():
    from apps.strategies_nautilus import signal_consumer

    source = (signal_consumer.__file__,)
    assert source  # sanity
    # Read source bytes once and assert forbidden substrings absent
    with open(signal_consumer.__file__, "rb") as f:
        text = f.read().decode()
    for forbidden in (
        "nautilus_trader",
        "freqtrade",
        "requests.",
        "httpx.",
        "ccxt.",
        "ExecutionEngine",
        "binance",
    ):
        assert forbidden not in text, f"forbidden token '{forbidden}' found in signal_consumer.py"


def test_consumer_handles_min_confidence_boundary(make_payload, config):
    boundary = ConsumerConfig(
        venue=config.venue,
        auth=config.auth,
        min_confidence=0.61,
    )
    event = SignalEvent.model_validate(make_payload(confidence=0.61))
    outcome = evaluate(event, boundary, now_ns=event.ts_event)
    assert outcome.decision == "accept"

    event_below = SignalEvent.model_validate(
        make_payload(confidence=0.60, signal_id="below-boundary")
    )
    outcome_below = evaluate(event_below, boundary, now_ns=event_below.ts_event)
    assert outcome_below.decision == "reject_low_confidence"

"""Unit tests for ADR-008 §6.6 signal source abstraction.

These tests cover the pure-Python ``StaticSignalSource`` and
``SignalStorePollingSource`` implementations attached to
``BaselineNautilusStrategy``. The strategy itself (which depends on the
native ``nautilus_trader.trading.strategy.Strategy`` runtime) is exercised
end-to-end in ``test_backtest_reproducibility.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    SignalStorePollingSource,
    StaticSignalSource,
)

SOURCE = "freqai_linear_v1"
MODEL = "linear-mom-train20240105"

# ts_event must be in the SignalEvent validator's allowed nanosecond range
# (roughly 2001..2099). Use 2024-01-01 as the base and offset from there.
BASE_NS = 1_704_067_200_000_000_000


def _event(signal_id: str, ts_ns: int, *, source: str = SOURCE) -> SignalEvent:
    return SignalEvent(
        signal_id=signal_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        ts_event=ts_ns,
        horizon="1m",
        side="buy",
        score=0.5,
        confidence=0.7,
        source=source,
        model_version=MODEL,
        ttl_seconds=60,
    )


def test_static_source_pops_in_ts_event_then_signal_id_order():
    events = [
        _event("c", BASE_NS + 1_000_000_000),
        _event("a", BASE_NS + 500_000_000),
        _event("b", BASE_NS + 1_000_000_000),
    ]
    src = StaticSignalSource(events=events)

    popped = src.pop_due(until_ns=BASE_NS + 2_000_000_000)

    assert [e.signal_id for e in popped] == ["a", "b", "c"]


def test_static_source_advances_cursor_and_never_replays():
    src = StaticSignalSource(
        events=[
            _event("a", BASE_NS + 100),
            _event("b", BASE_NS + 200),
            _event("c", BASE_NS + 300),
        ]
    )

    first = src.pop_due(until_ns=BASE_NS + 150)
    second = src.pop_due(until_ns=BASE_NS + 250)
    third = src.pop_due(until_ns=BASE_NS + 999)
    fourth = src.pop_due(until_ns=BASE_NS + 999)

    assert [e.signal_id for e in first] == ["a"]
    assert [e.signal_id for e in second] == ["b"]
    assert [e.signal_id for e in third] == ["c"]
    assert fourth == []


def test_polling_source_only_returns_new_events_for_filter(tmp_path: Path):
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("s1", BASE_NS + 1_000), now_ns=0)
    store.write(_event("s2", BASE_NS + 2_000), now_ns=0)
    store.write(
        _event("other", BASE_NS + 1_500, source="rule_baseline_v1"),
        now_ns=0,
    )

    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS,
    )

    popped = src.pop_due(until_ns=BASE_NS + 2_000)

    assert [e.signal_id for e in popped] == ["s1", "s2"]


def test_polling_source_advances_cursor_past_last_seen_ts(tmp_path: Path):
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("s1", BASE_NS + 1_000), now_ns=0)
    store.write(_event("s2", BASE_NS + 2_000), now_ns=0)

    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS,
    )

    first = src.pop_due(until_ns=BASE_NS + 1_500)
    assert [e.signal_id for e in first] == ["s1"]
    assert src.cursor_ns == BASE_NS + 1_001

    second = src.pop_due(until_ns=BASE_NS + 1_999)
    assert second == []

    third = src.pop_due(until_ns=BASE_NS + 2_500)
    assert [e.signal_id for e in third] == ["s2"]
    assert src.cursor_ns == BASE_NS + 2_001

    repeat = src.pop_due(until_ns=BASE_NS + 2_500)
    assert repeat == []


def test_polling_source_returns_signal_inserted_late_at_same_timestamp(
    tmp_path: Path,
):
    store = SignalStore(tmp_path / "signals.db")
    signal_ts = BASE_NS + 1_000
    store.write(_event("first", signal_ts), now_ns=0)
    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS,
    )

    assert [event.signal_id for event in src.pop_due(signal_ts)] == ["first"]

    store.write(_event("late-same-ts", signal_ts), now_ns=1)
    assert [
        event.signal_id for event in src.pop_due(signal_ts + 1_000)
    ] == ["late-same-ts"]
    assert src.pop_due(signal_ts + 1_000) == []


def test_polling_source_returns_out_of_order_signal_inserted_after_high_water(
    tmp_path: Path,
):
    store = SignalStore(tmp_path / "signals.db")
    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS,
    )
    store.write(_event("newer", BASE_NS + 2_000), now_ns=0)
    assert [
        event.signal_id for event in src.pop_due(BASE_NS + 3_000)
    ] == ["newer"]

    store.write(_event("late-older", BASE_NS + 1_000), now_ns=1)
    assert [
        event.signal_id for event in src.pop_due(BASE_NS + 3_000)
    ] == ["late-older"]


def test_polling_source_skips_history_before_initial_cursor(tmp_path: Path):
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("old1", BASE_NS + 100), now_ns=0)
    store.write(_event("old2", BASE_NS + 200), now_ns=0)
    store.write(_event("new1", BASE_NS + 1_000), now_ns=0)
    store.write(_event("new2", BASE_NS + 1_100), now_ns=0)

    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS + 500,
    )

    popped = src.pop_due(until_ns=BASE_NS + 2_000)

    assert [e.signal_id for e in popped] == ["new1", "new2"]


def test_polling_source_returns_empty_when_until_before_cursor(tmp_path: Path):
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("s1", BASE_NS + 5_000), now_ns=0)

    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS + 3_000,
    )

    # Bar timestamps must never run backwards. Treat as no-op without
    # mutating cursor.
    assert src.pop_due(until_ns=BASE_NS + 2_000) == []
    assert src.cursor_ns == BASE_NS + 3_000


def test_polling_source_reset_cursor_preserves_seen_state(tmp_path: Path):
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("s1", BASE_NS + 1_000), now_ns=0)
    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=BASE_NS,
    )
    assert [event.signal_id for event in src.pop_due(BASE_NS + 2_000)] == ["s1"]

    src.reset_cursor(BASE_NS + 500)

    assert src.cursor_ns == BASE_NS + 500
    assert src.last_popped_ns == BASE_NS + 1_000
    assert src.pop_due(BASE_NS + 2_000) == []

    store.write(_event("s2", BASE_NS + 1_500), now_ns=1)
    assert [event.signal_id for event in src.pop_due(BASE_NS + 2_000)] == ["s2"]


@pytest.mark.parametrize("initial_cursor", [-1, 0, BASE_NS])
def test_polling_source_low_initial_cursor_returns_all_history(
    tmp_path: Path,
    initial_cursor: int,
):
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("s1", BASE_NS + 100), now_ns=0)

    src = SignalStorePollingSource(
        store=store,
        source=SOURCE,
        model_version=MODEL,
        cursor_ns=initial_cursor,
    )

    popped = src.pop_due(until_ns=BASE_NS + 200)

    assert [e.signal_id for e in popped] == ["s1"]

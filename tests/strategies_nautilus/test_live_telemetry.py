"""Unit tests for the ADR-008 §6.6 live telemetry reader."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    SignalStorePollingSource,
)
from apps.strategies_nautilus.runners.first_testnet_canary import (
    FirstCanaryStrategySpec,
    build_live_telemetry_reader,
    build_register_strategies,
    build_signal_source,
)
from apps.strategies_nautilus.runners.live_telemetry import LiveTelemetryReader

SOURCE = "freqai_linear_v1"
MODEL = "linear-mom-train20240105"
BASE_NS = 1_704_067_200_000_000_000

VALID_SPEC_KWARGS = dict(
    source=SOURCE,
    model_version=MODEL,
    signal_store_path=Path("data/bridge/signals.db"),
    instrument_id_str="BTCUSDT.BINANCE",
    bar_type_str="BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
    trade_size=Decimal("0.001"),
    base_currency_code="USDT",
    venue="BINANCE",
    position_pct_multiplier=0.1,
)


def _event(signal_id: str, ts_ns: int) -> SignalEvent:
    return SignalEvent(
        signal_id=signal_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        ts_event=ts_ns,
        horizon="1m",
        side="buy",
        score=0.5,
        confidence=0.7,
        source=SOURCE,
        model_version=MODEL,
        ttl_seconds=60,
    )


# ---------------------------------------------------------------------------
# SignalStorePollingSource.last_popped_ns
# ---------------------------------------------------------------------------


def test_polling_source_last_popped_ns_starts_none(tmp_path: Path) -> None:
    store = SignalStore(tmp_path / "signals.db")
    src = SignalStorePollingSource(
        store=store, source=SOURCE, model_version=MODEL, cursor_ns=BASE_NS
    )
    assert src.last_popped_ns is None


def test_polling_source_last_popped_ns_tracks_max_ts(tmp_path: Path) -> None:
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("a", BASE_NS + 100), now_ns=0)
    store.write(_event("b", BASE_NS + 300), now_ns=0)
    store.write(_event("c", BASE_NS + 200), now_ns=0)

    src = SignalStorePollingSource(
        store=store, source=SOURCE, model_version=MODEL, cursor_ns=BASE_NS
    )

    src.pop_due(until_ns=BASE_NS + 500)

    assert src.last_popped_ns == BASE_NS + 300
    assert src.cursor_ns == BASE_NS + 301


def test_polling_source_last_popped_ns_keeps_old_value_on_empty_pop(
    tmp_path: Path,
) -> None:
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("a", BASE_NS + 100), now_ns=0)

    src = SignalStorePollingSource(
        store=store, source=SOURCE, model_version=MODEL, cursor_ns=BASE_NS
    )
    src.pop_due(until_ns=BASE_NS + 200)
    assert src.last_popped_ns == BASE_NS + 100

    src.pop_due(until_ns=BASE_NS + 500)

    assert src.last_popped_ns == BASE_NS + 100


# ---------------------------------------------------------------------------
# LiveTelemetryReader
# ---------------------------------------------------------------------------


class _FakeMoney:
    def __init__(self, value: float) -> None:
        self._value = value

    def as_double(self) -> float:
        return self._value


class _FakePortfolio:
    def __init__(self, equity_map: dict[Any, _FakeMoney] | None) -> None:
        self._equity_map = equity_map

    def equity(self, *, venue: Any) -> dict[Any, _FakeMoney] | None:
        return self._equity_map


class _FakeCache:
    def __init__(
        self,
        *,
        open_orders: list[Any] | None = None,
        open_positions: list[Any] | None = None,
        bar: Any = None,
        raises_bar: Exception | None = None,
    ) -> None:
        self._orders = open_orders or []
        self._positions = open_positions or []
        self._bar = bar
        self._raises_bar = raises_bar

    def orders_open(self, *, venue: Any) -> list[Any]:
        return list(self._orders)

    def positions_open(self, *, venue: Any) -> list[Any]:
        return list(self._positions)

    def bar(self, bar_type: Any) -> Any:
        if self._raises_bar is not None:
            raise self._raises_bar
        return self._bar


class _FakeEngine:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected

    def check_connected(self) -> bool:
        return self._connected

    def set_connected(self, value: bool) -> None:
        self._connected = value


class _FakeKernel:
    def __init__(
        self,
        *,
        data_connected: bool = True,
        exec_connected: bool = True,
    ) -> None:
        self.data_engine = _FakeEngine(data_connected)
        self.exec_engine = _FakeEngine(exec_connected)


class _FakeNode:
    def __init__(
        self,
        *,
        equity_map: dict[Any, _FakeMoney] | None = None,
        open_orders: list[Any] | None = None,
        open_positions: list[Any] | None = None,
        bar: Any = None,
        raises_bar: Exception | None = None,
        kernel: _FakeKernel | None = None,
    ) -> None:
        self.portfolio = _FakePortfolio(equity_map)
        self.cache = _FakeCache(
            open_orders=open_orders,
            open_positions=open_positions,
            bar=bar,
            raises_bar=raises_bar,
        )
        if kernel is not None:
            self.kernel = kernel


def _reader(spec_overrides: dict | None = None, **kwargs: Any) -> LiveTelemetryReader:
    spec = FirstCanaryStrategySpec(**VALID_SPEC_KWARGS)
    reader = build_live_telemetry_reader(spec, **kwargs)
    if spec_overrides:
        for k, v in spec_overrides.items():
            setattr(reader, k, v)
    return reader


def test_reader_returns_safe_defaults_when_node_not_bound() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)

    sample = reader()

    assert sample.account_total_usdt == 10000.0
    assert sample.daily_pnl == 0.0
    assert sample.open_orders == 0
    assert sample.open_positions == 0
    assert sample.last_bar_ns is None
    assert sample.last_signal_ns is None
    assert sample.ws_connected is True
    assert sample.exchange_error_count == 0
    assert sample.ws_reconnect_count == 0


def test_reader_reads_account_total_from_portfolio() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    node = _FakeNode(equity_map={reader.base_currency: _FakeMoney(86774.67)})
    reader.bind_node(node)

    sample = reader()

    assert sample.account_total_usdt == 86774.67


def test_reader_falls_back_to_starting_balance_when_portfolio_empty() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(_FakeNode(equity_map=None))

    sample = reader()

    assert sample.account_total_usdt == 10000.0


def test_reader_reads_open_orders_and_positions_lengths() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            open_orders=["o1", "o2", "o3"],
            open_positions=["p1"],
        )
    )

    sample = reader()

    assert sample.open_orders == 3
    assert sample.open_positions == 1


def test_reader_reads_last_bar_ns_from_cache() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    bar = MagicMock()
    bar.ts_event = 1_714_521_540_000_000_000
    reader.bind_node(
        _FakeNode(equity_map={reader.base_currency: _FakeMoney(10000.0)}, bar=bar)
    )

    sample = reader()

    assert sample.last_bar_ns == 1_714_521_540_000_000_000


def test_reader_last_bar_ns_none_when_cache_raises() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            raises_bar=RuntimeError("cache miss"),
        )
    )

    sample = reader()

    assert sample.last_bar_ns is None


def test_reader_reads_last_signal_ns_from_polling_source(tmp_path: Path) -> None:
    store = SignalStore(tmp_path / "signals.db")
    store.write(_event("a", BASE_NS + 1_500_000_000), now_ns=0)

    source = SignalStorePollingSource(
        store=store, source=SOURCE, model_version=MODEL, cursor_ns=BASE_NS
    )
    source.pop_due(until_ns=BASE_NS + 2_000_000_000)

    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS),
        starting_balance=10000.0,
        signal_source=source,
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(_FakeNode(equity_map={reader.base_currency: _FakeMoney(10000.0)}))

    sample = reader()

    assert sample.last_signal_ns == BASE_NS + 1_500_000_000


def test_reader_day_anchor_returns_zero_first_call_then_diff_same_day() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    state = {"now": datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)}

    def clock() -> datetime:
        return state["now"]

    reader._clock = clock

    totals = iter([10000.0, 10076.0, 9923.0])

    class _StepNode:
        @property
        def portfolio(self) -> Any:
            return _FakePortfolio({reader.base_currency: _FakeMoney(next(totals))})

        @property
        def cache(self) -> Any:
            return _FakeCache()

    reader.bind_node(_StepNode())

    s1 = reader()
    assert s1.daily_pnl == 0.0
    assert s1.account_total_usdt == 10000.0

    state["now"] += timedelta(minutes=30)
    s2 = reader()
    assert pytest.approx(s2.daily_pnl) == 76.0

    state["now"] += timedelta(hours=1)
    s3 = reader()
    assert pytest.approx(s3.daily_pnl) == -77.0


def test_reader_day_anchor_resets_on_new_utc_day() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    state = {"now": datetime(2026, 5, 20, 23, 30, 0, tzinfo=UTC)}
    reader._clock = lambda: state["now"]

    totals = iter([10100.0, 9900.0])

    class _StepNode:
        @property
        def portfolio(self) -> Any:
            return _FakePortfolio({reader.base_currency: _FakeMoney(next(totals))})

        @property
        def cache(self) -> Any:
            return _FakeCache()

    reader.bind_node(_StepNode())

    s1 = reader()
    assert s1.daily_pnl == 0.0

    state["now"] = datetime(2026, 5, 21, 0, 30, 0, tzinfo=UTC)
    s2 = reader()
    assert s2.daily_pnl == 0.0
    assert s2.account_total_usdt == 9900.0


def test_reader_catches_node_exceptions_and_returns_defaults() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)

    class _BoomNode:
        @property
        def portfolio(self) -> Any:
            raise RuntimeError("kaboom")

    reader.bind_node(_BoomNode())

    sample = reader()

    assert sample.account_total_usdt == 10000.0
    assert sample.daily_pnl == 0.0
    assert sample.open_orders == 0
    assert sample.open_positions == 0


def test_reader_ws_connected_true_when_kernel_engines_connected() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            kernel=_FakeKernel(data_connected=True, exec_connected=True),
        )
    )

    sample = reader()

    assert sample.ws_connected is True
    assert sample.ws_reconnect_count == 0


def test_reader_ws_connected_suppresses_startup_false_before_first_connect() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            kernel=_FakeKernel(data_connected=False, exec_connected=True),
        )
    )

    sample = reader()

    assert sample.ws_connected is True
    assert sample.ws_reconnect_count == 0


def test_reader_ws_connected_false_when_data_engine_disconnects_after_connect() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    kernel = _FakeKernel(data_connected=True, exec_connected=True)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            kernel=kernel,
        )
    )
    assert reader().ws_connected is True

    kernel.data_engine.set_connected(False)
    sample = reader()

    assert sample.ws_connected is False


def test_reader_ws_connected_false_when_exec_engine_disconnects_after_connect() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    kernel = _FakeKernel(data_connected=True, exec_connected=True)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            kernel=kernel,
        )
    )
    assert reader().ws_connected is True

    kernel.exec_engine.set_connected(False)

    sample = reader()

    assert sample.ws_connected is False


def test_reader_ws_reconnect_count_increments_on_false_to_true_edge() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    kernel = _FakeKernel(data_connected=True, exec_connected=True)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            kernel=kernel,
        )
    )

    s1 = reader()
    assert s1.ws_connected is True
    assert s1.ws_reconnect_count == 0

    kernel.data_engine.set_connected(False)
    s2 = reader()
    assert s2.ws_connected is False
    assert s2.ws_reconnect_count == 0

    kernel.data_engine.set_connected(True)
    s3 = reader()
    assert s3.ws_connected is True
    assert s3.ws_reconnect_count == 1

    kernel.exec_engine.set_connected(False)
    s4 = reader()
    assert s4.ws_connected is False
    assert s4.ws_reconnect_count == 1

    kernel.exec_engine.set_connected(True)
    s5 = reader()
    assert s5.ws_connected is True
    assert s5.ws_reconnect_count == 2


def test_reader_ws_reconnect_count_does_not_increment_when_staying_connected() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(
        _FakeNode(
            equity_map={reader.base_currency: _FakeMoney(10000.0)},
            kernel=_FakeKernel(data_connected=True, exec_connected=True),
        )
    )

    for _ in range(5):
        sample = reader()
        assert sample.ws_connected is True
        assert sample.ws_reconnect_count == 0


def test_reader_ws_connected_keeps_prev_when_kernel_read_raises() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)

    class _BoomKernel:
        @property
        def data_engine(self) -> Any:
            raise RuntimeError("kaboom")

    portfolio = _FakePortfolio({reader.base_currency: _FakeMoney(10000.0)})
    cache = _FakeCache()

    class _NodeWithBoomKernel:
        def __init__(self) -> None:
            self.portfolio = portfolio
            self.cache = cache
            self.kernel = _BoomKernel()

    reader.bind_node(_NodeWithBoomKernel())

    sample = reader()

    assert sample.ws_connected is True
    assert sample.ws_reconnect_count == 0


def test_reader_ws_connected_falls_back_to_prev_when_node_has_no_kernel() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    reader.bind_node(
        _FakeNode(equity_map={reader.base_currency: _FakeMoney(10000.0)})
    )

    sample = reader()

    assert sample.ws_connected is True
    assert sample.ws_reconnect_count == 0


def test_reader_bind_node_is_idempotent() -> None:
    reader = build_live_telemetry_reader(
        FirstCanaryStrategySpec(**VALID_SPEC_KWARGS), starting_balance=10000.0
    )
    reader._clock = lambda: datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    node_a = _FakeNode(equity_map={reader.base_currency: _FakeMoney(100.0)})
    node_b = _FakeNode(equity_map={reader.base_currency: _FakeMoney(200.0)})

    reader.bind_node(node_a)
    reader.bind_node(node_b)

    sample = reader()
    assert sample.account_total_usdt == 200.0


# ---------------------------------------------------------------------------
# build_signal_source helper
# ---------------------------------------------------------------------------


def test_build_signal_source_uses_injected_clock_for_initial_cursor(
    tmp_path: Path,
) -> None:
    db = tmp_path / "signals.db"
    SignalStore(db)
    spec = FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "signal_store_path": db})

    source = build_signal_source(spec, clock_ns=lambda: 1_716_038_400_000_000_000)

    assert source.cursor_ns == 1_716_038_400_000_000_000
    assert source.source == SOURCE
    assert source.model_version == MODEL
    assert source.last_popped_ns is None


def test_build_signal_source_honours_explicit_initial_cursor(tmp_path: Path) -> None:
    db = tmp_path / "signals.db"
    SignalStore(db)
    spec = FirstCanaryStrategySpec(
        **{
            **VALID_SPEC_KWARGS,
            "signal_store_path": db,
            "initial_cursor_ns": 1_704_067_200_000_000_000,
        }
    )

    source = build_signal_source(spec, clock_ns=lambda: 99)

    assert source.cursor_ns == 1_704_067_200_000_000_000


# ---------------------------------------------------------------------------
# build_register_strategies accepts pre-built signal_source
# ---------------------------------------------------------------------------


def test_build_register_strategies_uses_supplied_signal_source(tmp_path: Path) -> None:
    db = tmp_path / "signals.db"
    SignalStore(db)
    spec = FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "signal_store_path": db})
    source = build_signal_source(spec, clock_ns=lambda: 12345)
    captured: dict[str, Any] = {}

    def sink(node: Any, strategy: Any) -> None:
        captured["strategy"] = strategy

    register = build_register_strategies(
        spec,
        lineage=[],
        signal_source=source,
        strategy_sink=sink,
    )
    register(MagicMock())

    assert captured["strategy"]._signal_source is source


def test_build_register_strategies_builds_own_source_when_omitted(
    tmp_path: Path,
) -> None:
    db = tmp_path / "signals.db"
    SignalStore(db)
    spec = FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "signal_store_path": db})
    captured: dict[str, Any] = {}

    def sink(node: Any, strategy: Any) -> None:
        captured["strategy"] = strategy

    register = build_register_strategies(
        spec,
        lineage=[],
        clock_ns=lambda: 12345,
        strategy_sink=sink,
    )
    register(MagicMock())

    src = captured["strategy"]._signal_source
    assert src.cursor_ns == 12345


# ---------------------------------------------------------------------------
# build_live_telemetry_reader helper plumbs spec fields correctly
# ---------------------------------------------------------------------------


def test_build_live_telemetry_reader_plumbs_spec_fields() -> None:
    spec = FirstCanaryStrategySpec(**VALID_SPEC_KWARGS)
    source = SignalStorePollingSource(
        store=MagicMock(), source=SOURCE, model_version=MODEL, cursor_ns=0
    )

    reader = build_live_telemetry_reader(
        spec, starting_balance=12345.0, signal_source=source
    )

    assert str(reader.venue) == "BINANCE"
    assert str(reader.bar_type) == "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"
    assert reader.base_currency.code == "USDT"
    assert reader.starting_balance == 12345.0
    assert reader.signal_source is source


# ---------------------------------------------------------------------------
# testnet_runner bind_node hook
# ---------------------------------------------------------------------------


def test_run_long_running_testnet_calls_reader_bind_node_after_build(
    tmp_path: Path,
) -> None:
    from apps.strategies_nautilus.runners.testnet_runner import (
        GitState,
        LongRunningTestnetSettings,
        StartupSettings,
        TestnetRuntimeTelemetry,
        run_long_running_testnet,
    )

    retros_dir = tmp_path / "retros"
    retros_dir.mkdir(parents=True, exist_ok=True)
    (retros_dir / "2026-05-17-freqai-linear-v1-hold-paper-simulated.md").write_text(
        "\n".join(
            [
                "# Promotion review — freqai_linear_v1 / linear-mom-train20240105",
                "## 1. Source / model",
                "- source: `freqai_linear_v1`",
                "- model_version: `linear-mom-train20240105`",
                "## 2. Current vs target policy",
                "- current_stage: `paper_simulated`",
                "- target_stage: `paper_simulated`",
                "## 7. Conclusion",
                "- decision: **HOLD**",
                "- decision_allowed: **yes**",
                "",
            ]
        ),
        encoding="utf-8",
    )
    valid_env = {"BINANCE_TESTNET_API_KEY": "K" * 40, "BINANCE_TESTNET_API_SECRET": "S" * 40}
    settings = StartupSettings(
        mode="testnet",
        kind="testnet",
        allow_real_credentials=True,
        source=SOURCE,
        model_version=MODEL,
        policy_position_pct_multiplier=0.1,
        retros_dir=retros_dir,
        repo_root=tmp_path,
        operator="pytest",
    )
    run_settings = LongRunningTestnetSettings(
        output_root=tmp_path / "data" / "testnet",
        instrument_ids=("BTCUSDT.BINANCE",),
        starting_balance=10000.0,
        max_run_seconds=0.05,
        telemetry_poll_seconds=0.001,
        heartbeat_interval_seconds=30.0,
        emergency_fill_timeout_seconds=1.0,
        emergency_poll_interval_seconds=0.1,
    )

    base = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)

    def frozen_clock():
        state = {"t": base}

        def _now():
            current = state["t"]
            state["t"] = current + timedelta(seconds=1)
            return current

        return _now

    bind_calls: list[Any] = []

    class _Reader:
        def __call__(self) -> TestnetRuntimeTelemetry:
            return TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0)

        def bind_node(self, node: Any) -> None:
            bind_calls.append(node)

    class _BlockingNode:
        def __init__(self, cfg: Any) -> None:
            self.cfg = cfg
            self.trader = MagicMock()
            self.trader.strategies = []
            self.trader.actors = []
            self.stop_called = False

        def add_data_client_factory(self, *_args: Any) -> None:
            return None

        def add_exec_client_factory(self, *_args: Any) -> None:
            return None

        def build(self) -> None:
            return None

        def run(self, raise_exception: bool = False) -> None:
            while not self.stop_called:
                time.sleep(0.001)

        def stop(self) -> None:
            self.stop_called = True

        def dispose(self) -> None:
            return None

    holder: dict[str, _BlockingNode] = {}

    def factory(cfg: Any) -> _BlockingNode:
        node = _BlockingNode(cfg)
        holder["node"] = node
        return node

    reader = _Reader()
    result = run_long_running_testnet(
        settings,
        run_settings,
        env=valid_env,
        git_state=GitState(commit="a" * 40, dirty=False),
        node_factory=factory,
        clock=frozen_clock(),
        telemetry_reader=reader,
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        run_id="20260520-120000Z-bind0001",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert len(bind_calls) == 1
    assert bind_calls[0] is holder["node"]

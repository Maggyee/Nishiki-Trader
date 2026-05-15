"""End-to-end smoke + reproducibility tests for `backtest_runner.run_backtest`.

Two synthetic backtests with identical inputs must produce:
- bit-for-bit identical `fills.parquet` (ADR-004 §2.4)
- equal `stats_pnls` and `stats_returns` in the manifest
- identical row counts in `orders / positions / signal_lineage`

`run_id`, `started_at`, `finished_at`, and `elapsed_seconds` are explicitly
excluded by ADR-004 §2.4.
"""

from __future__ import annotations

import filecmp
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    BaselineNautilusStrategy,
    BaselineNautilusStrategyParams,
)
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig
from apps.strategies_nautilus.runners.backtest_runner import (
    BacktestRunnerConfig,
    run_backtest,
)

BASE_TS_NS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z
ONE_MIN_NS = 60_000_000_000


@pytest.fixture
def btcusdt_instrument():
    return TestInstrumentProvider.btcusdt_binance()


@pytest.fixture
def bar_type(btcusdt_instrument):
    return BarType.from_str(f"{btcusdt_instrument.id}-1-MINUTE-LAST-EXTERNAL")


def _make_bars(btcusdt_instrument, bar_type):
    # OHLC built so that low <= min(open, close) and high >= max(open, close)
    # for every row — Bar validation enforces this invariant.
    opens =  [50000, 50100, 50200, 50300, 50200, 50100, 50000, 49900, 49800, 49700]
    closes = [50100, 50200, 50300, 50200, 50100, 50000, 49900, 49800, 49700, 49600]
    df = pd.DataFrame(
        {
            "open": opens,
            "high": [max(o, c) + 50 for o, c in zip(opens, closes, strict=True)],
            "low":  [min(o, c) - 50 for o, c in zip(opens, closes, strict=True)],
            "close": closes,
            "volume": [10.0, 12.5, 8.3, 15.1, 9.2, 11.7, 7.5, 13.0, 14.4, 10.8],
        },
        index=pd.date_range(
            pd.Timestamp("2026-01-01T00:00:00Z"),
            periods=10,
            freq="1min",
        ),
    )
    df.index.name = "timestamp"
    return BarDataWrangler(bar_type, btcusdt_instrument).process(df)


@pytest.fixture
def signals(make_payload):
    return [
        SignalEvent.model_validate(
            make_payload(
                signal_id="repro-buy-1",
                ts_event=BASE_TS_NS + 2 * ONE_MIN_NS,
                side="buy",
                ttl_seconds=900,
            )
        ),
        SignalEvent.model_validate(
            make_payload(
                signal_id="repro-flat-2",
                ts_event=BASE_TS_NS + 5 * ONE_MIN_NS,
                side="flat",
                ttl_seconds=900,
            )
        ),
        SignalEvent.model_validate(
            make_payload(
                signal_id="repro-sell-3",
                ts_event=BASE_TS_NS + 7 * ONE_MIN_NS,
                side="sell",
                ttl_seconds=900,
            )
        ),
    ]


@pytest.fixture
def signal_store_path(tmp_path, signals):
    store = SignalStore(tmp_path / "signals.db")
    for s in signals:
        store.write(s)
    return tmp_path / "signals.db"


def _build_config(
    *,
    output_root: Path,
    instrument,
    bar_type,
    bars,
    signals,
    signal_store_path: Path,
) -> BacktestRunnerConfig:
    return BacktestRunnerConfig(
        output_root=output_root,
        instrument=instrument,
        bars=bars,
        bar_type=bar_type,
        signals=signals,
        baseline_config=BaselineStrategyConfig(
            venue="BINANCE",
            auth=Authorization(
                allowed_sources=frozenset({"freqai_v1"}),
                allowed_model_versions=frozenset({"2026-05-14"}),
            ),
            min_confidence=0.5,
            max_position_pct=0.05,
            daily_drawdown_stop_pct=0.05,
        ),
        trade_size=Decimal("0.001"),
        starting_balance=Money(100_000, USDT),
        base_currency=USDT,
        signal_store_path=signal_store_path,
        signal_filter={"source": "freqai_v1"},
        machine_id="pytest",
        git_commit="0" * 40,
        git_dirty=False,
    )


def test_run_backtest_writes_manifest_and_parquet(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path
):
    bars = _make_bars(btcusdt_instrument, bar_type)
    config = _build_config(
        output_root=tmp_path / "backtests",
        instrument=btcusdt_instrument,
        bar_type=bar_type,
        bars=bars,
        signals=signals,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(config)

    assert (result.output_dir / "run_manifest.json").exists()
    for name in (
        "orders",
        "fills",
        "positions",
        "account_balances",
        "signal_lineage",
    ):
        assert (result.output_dir / f"{name}.parquet").exists(), f"{name}.parquet missing"

    assert result.manifest.schema_version == "backtest.v1"
    assert result.manifest.run_id.startswith("20")
    assert result.manifest.signal_source.row_count == len(signals)
    assert result.manifest.signal_source.store_sha256
    assert result.manifest.totals.iterations >= 0
    assert "BINANCE" in result.manifest.venues
    assert "BTCUSDT.BINANCE" in result.manifest.instruments


def test_signal_lineage_records_every_signal(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path
):
    bars = _make_bars(btcusdt_instrument, bar_type)
    config = _build_config(
        output_root=tmp_path / "backtests",
        instrument=btcusdt_instrument,
        bar_type=bar_type,
        bars=bars,
        signals=signals,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(config)
    lineage_df = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert sorted(lineage_df["signal_id"].tolist()) == sorted(s.signal_id for s in signals)


def test_signal_ids_round_trip_to_reports(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path
):
    bars = _make_bars(btcusdt_instrument, bar_type)
    config = _build_config(
        output_root=tmp_path / "backtests",
        instrument=btcusdt_instrument,
        bar_type=bar_type,
        bars=bars,
        signals=signals,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(config)

    orders = pd.read_parquet(result.output_dir / "orders.parquet")
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    positions = pd.read_parquet(result.output_dir / "positions.parquet")
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")

    assert "signal_id" in orders.columns
    assert "signal_id" in fills.columns
    assert "signal_ids" in positions.columns

    assert {"repro-buy-1", "repro-flat-2", "repro-sell-3"}.issubset(
        set(orders["signal_id"])
    )
    assert {"repro-buy-1", "repro-flat-2", "repro-sell-3"}.issubset(
        set(fills["signal_id"])
    )

    by_signal = lineage.set_index("signal_id")
    assert by_signal.loc["repro-buy-1", "order_ids"]
    assert by_signal.loc["repro-buy-1", "fill_ids"]
    assert by_signal.loc["repro-flat-2", "order_ids"]
    assert by_signal.loc["repro-flat-2", "fill_ids"]


def test_backtest_reproducibility(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path
):
    # Build two configs with identical inputs and run independently.
    bars1 = _make_bars(btcusdt_instrument, bar_type)
    bars2 = _make_bars(btcusdt_instrument, bar_type)

    cfg1 = _build_config(
        output_root=tmp_path / "run1",
        instrument=btcusdt_instrument,
        bar_type=bar_type,
        bars=bars1,
        signals=signals,
        signal_store_path=signal_store_path,
    )
    cfg2 = _build_config(
        output_root=tmp_path / "run2",
        instrument=btcusdt_instrument,
        bar_type=bar_type,
        bars=bars2,
        signals=signals,
        signal_store_path=signal_store_path,
    )

    r1 = run_backtest(cfg1)
    r2 = run_backtest(cfg2)

    # ADR-004 §2.4: fills.parquet must be bit-for-bit identical between runs.
    assert filecmp.cmp(
        r1.output_dir / "fills.parquet",
        r2.output_dir / "fills.parquet",
        shallow=False,
    ), "fills.parquet differs between runs"

    # stats_pnls per currency must be equal (NaN-aware via JSON round-trip).
    s1 = json.loads(json.dumps(r1.manifest.stats_pnls))
    s2 = json.loads(json.dumps(r2.manifest.stats_pnls))
    assert s1 == s2, f"stats_pnls diverged: {s1} vs {s2}"

    # stats_returns must also match.
    assert (
        json.loads(json.dumps(r1.manifest.stats_returns))
        == json.loads(json.dumps(r2.manifest.stats_returns))
    )

    # totals must match (counts of iterations/events/orders/positions/fills).
    assert r1.manifest.totals == r2.manifest.totals

    # The store SHA-256 must be identical (same input bytes).
    assert r1.manifest.signal_source.store_sha256 == r2.manifest.signal_source.store_sha256

    # The run_id, started_at, finished_at are expected to differ; the ADR
    # explicitly excludes those four fields from the reproducibility set.
    assert r1.run_id != r2.run_id


def test_nautilus_wrapper_updates_daily_kill_switch(
    btcusdt_instrument, bar_type, signals
):
    config = BaselineStrategyConfig(
        venue="BINANCE",
        auth=Authorization(
            allowed_sources=frozenset({"freqai_v1"}),
            allowed_model_versions=frozenset({"2026-05-14"}),
        ),
        min_confidence=0.5,
        max_position_pct=0.05,
        daily_drawdown_stop_pct=0.05,
    )
    strategy = BaselineNautilusStrategy(
        BaselineNautilusStrategyParams(
            instrument_id=btcusdt_instrument.id,
            bar_type=bar_type,
            signals=signals,
            baseline_config=config,
            trade_size=Decimal("0.001"),
            equity_currency=USDT,
        )
    )
    equity_values = iter([10_000.0, 9_400.0, 9_400.0])
    strategy._current_equity = lambda: next(equity_values)  # type: ignore[method-assign]

    strategy._update_daily_risk_state(BASE_TS_NS)
    assert strategy._baseline.kill_switch_engaged is False

    strategy._update_daily_risk_state(BASE_TS_NS + ONE_MIN_NS)
    assert strategy._baseline.kill_switch_engaged is True

    strategy._update_daily_risk_state(BASE_TS_NS + 24 * 60 * ONE_MIN_NS)
    assert strategy._baseline.kill_switch_engaged is False

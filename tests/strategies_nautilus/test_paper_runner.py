"""Tests for ADR-007 simulated paper runner."""

from __future__ import annotations

import inspect
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization, SourcePolicy
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig
from apps.strategies_nautilus.runners import paper_runner
from apps.strategies_nautilus.runners.paper_runner import (
    PaperRunnerConfig,
    main,
    run_paper_session,
)

BASE_TS_NS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z
ONE_MIN_NS = 60_000_000_000


@pytest.fixture
def btcusdt_instrument():
    return TestInstrumentProvider.btcusdt_binance()


@pytest.fixture
def bar_type(btcusdt_instrument):
    return BarType.from_str(f"{btcusdt_instrument.id}-1-MINUTE-LAST-EXTERNAL")


def _make_bars(btcusdt_instrument, bar_type, closes: list[float], *, start_ns: int):
    index = pd.date_range(
        pd.Timestamp(start_ns, unit="ns", tz="UTC"),
        periods=len(closes),
        freq="1min",
    )
    return _make_bars_at_index(btcusdt_instrument, bar_type, closes, index)


def _make_bars_at_index(btcusdt_instrument, bar_type, closes: list[float], index):
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 5 for c in closes],
            "low": [c - 5 for c in closes],
            "close": closes,
            "volume": [10.0] * len(closes),
        },
        index=index,
    )
    df.index.name = "timestamp"
    return BarDataWrangler(bar_type, btcusdt_instrument).process(df)


def _write_catalog(tmp_path: Path, btcusdt_instrument, bar_type, closes, *, start_ns=BASE_TS_NS):
    path = tmp_path / "catalog"
    path.mkdir()
    catalog = ParquetDataCatalog(str(path.resolve()))
    catalog.write_data([btcusdt_instrument])
    catalog.write_data(
        _make_bars(btcusdt_instrument, bar_type, closes, start_ns=start_ns)
    )
    return path


def _write_catalog_at_times(
    tmp_path: Path,
    btcusdt_instrument,
    bar_type,
    closes,
    ts_events: list[int],
):
    path = tmp_path / "catalog"
    path.mkdir()
    catalog = ParquetDataCatalog(str(path.resolve()))
    catalog.write_data([btcusdt_instrument])
    index = pd.DatetimeIndex(
        [pd.Timestamp(ts, unit="ns", tz="UTC") for ts in ts_events],
        name="timestamp",
    )
    catalog.write_data(
        _make_bars_at_index(btcusdt_instrument, bar_type, closes, index)
    )
    return path


def _signal(
    *,
    signal_id: str,
    ts_event: int,
    side: str = "buy",
    source: str = "freqai_v1",
    model_version: str = "2026-05-14",
    ttl_seconds: int = 900,
    confidence: float = 0.70,
) -> SignalEvent:
    return SignalEvent.model_validate(
        {
            "schema_version": "signal.v1",
            "signal_id": signal_id,
            "symbol": "BTCUSDT",
            "venue": "BINANCE",
            "ts_event": ts_event,
            "horizon": "15m",
            "side": side,
            "score": {"buy": 0.7, "sell": -0.7, "flat": 0.0}[side],
            "confidence": confidence,
            "source": source,
            "model_version": model_version,
            "ttl_seconds": ttl_seconds,
            "features_hash": None,
            "metadata": {"test": "paper_runner"},
        }
    )


def _write_signals(tmp_path: Path, signals: list[SignalEvent]) -> Path:
    path = tmp_path / "signals.db"
    store = SignalStore(path)
    for signal in signals:
        store.write(signal)
    return path


def _config(
    *,
    tmp_path: Path,
    catalog_path: Path,
    bar_type,
    signal_store_path: Path,
    policies: dict[tuple[str, str], SourcePolicy] | None = None,
    allowed_sources: frozenset[str] = frozenset({"freqai_v1"}),
    allowed_model_versions: frozenset[str] = frozenset({"2026-05-14"}),
    daily_drawdown_stop_pct: float = 0.05,
    max_signal_lag_seconds: int = 900,
    heartbeat_interval_seconds: int = 60,
    previous_run_id: str | None = None,
    restart_reason: str | None = None,
) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        output_root=tmp_path / "paper",
        catalog_path=catalog_path,
        instrument_id="BTCUSDT.BINANCE",
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        baseline_config=BaselineStrategyConfig(
            venue="BINANCE",
            auth=Authorization(
                allowed_sources=allowed_sources,
                allowed_model_versions=allowed_model_versions,
                policies=policies or {},
            ),
            min_confidence=0.5,
            max_position_pct=0.05,
            daily_drawdown_stop_pct=daily_drawdown_stop_pct,
        ),
        trade_size=Decimal("1"),
        starting_balance=Money(1_000, USDT),
        base_currency=USDT,
        signal_filter={"source": "freqai_v1", "model_version": "2026-05-14"},
        git_commit="0" * 40,
        git_dirty=False,
        machine_id="pytest",
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        max_signal_lag_seconds=max_signal_lag_seconds,
        operator="pytest",
        previous_run_id=previous_run_id,
        restart_reason=restart_reason,
    )


def test_dry_run_policy_writes_paper_bundle_without_orders_or_fills(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _write_catalog(tmp_path, btcusdt_instrument, bar_type, [100, 101, 102])
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-buy", ts_event=BASE_TS_NS + ONE_MIN_NS)],
    )
    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            policies={("freqai_v1", "2026-05-14"): SourcePolicy(dry_run=True)},
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert result.manifest.kind == "paper"
    assert result.output_dir.parent == tmp_path / "paper"
    assert manifest["kind"] == "paper"
    assert manifest["runtime"]["mode"] == "paper"
    assert manifest["runtime"]["order_mode"] == "simulated"
    assert manifest["totals"]["orders"] == 0
    assert manifest["totals"]["fills"] == 0
    assert manifest["strategies"][0]["params"]["policies"][0]["dry_run"] is True

    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage["signal_id"].tolist() == ["paper-buy"]
    assert lineage.loc[0, "decision"] == "target_long"
    assert lineage.loc[0, "reason"] == "dry_run"
    assert (result.output_dir / "logs" / "strategy.log").exists()
    assert (result.output_dir / "logs" / "risk.log").exists()


def test_simulated_policy_writes_orders_fills_positions_with_signal_ids(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 101, 102, 103, 104],
    )
    signals = [
        _signal(signal_id="paper-buy", ts_event=BASE_TS_NS + ONE_MIN_NS, side="buy"),
        _signal(signal_id="paper-flat", ts_event=BASE_TS_NS + 3 * ONE_MIN_NS, side="flat"),
    ]
    signal_store_path = _write_signals(tmp_path, signals)

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["totals"]["orders"] == 2
    assert manifest["totals"]["fills"] == 2
    assert manifest["totals"]["positions"] == 1
    orders = pd.read_parquet(result.output_dir / "orders.parquet")
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    positions = pd.read_parquet(result.output_dir / "positions.parquet")
    assert set(orders["signal_id"]) == {"paper-buy", "paper-flat"}
    assert set(fills["signal_id"]) == {"paper-buy", "paper-flat"}
    assert positions.loc[0, "signal_ids"] == "paper-buy,paper-flat"


def test_account_balances_track_equity_curve_and_drawdown(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 90, 80, 120],
    )
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-buy", ts_event=BASE_TS_NS, side="buy")],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
        )
    )

    account = pd.read_parquet(result.output_dir / "account_balances.parquet")
    assert account["total"].tolist() == [1000.0, 990.0, 980.0, 1020.0]
    assert account["locked"].tolist() == [100.0, 90.0, 80.0, 120.0]
    stats = result.manifest.stats_pnls["USDT"]
    assert stats["PnL (total)"] == 20.0
    assert stats["Max Drawdown (Abs)"] == -20.0
    assert stats["Max Drawdown (Pct)"] == -0.02
    assert result.manifest.stats_returns["max_drawdown"] == -0.02


def test_incremental_polling_writes_runtime_heartbeats_and_cursor_metadata(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 101, 102],
    )
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-buy", ts_event=BASE_TS_NS + ONE_MIN_NS)],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            heartbeat_interval_seconds=60,
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    runtime = manifest["runtime"]
    assert runtime["polling_mode"] == "incremental"
    assert runtime["poll_count"] == 3
    assert runtime["first_processed_ns"] == BASE_TS_NS
    assert runtime["processed_until_ns"] == BASE_TS_NS + 2 * ONE_MIN_NS
    assert runtime["expected_bar_interval_ns"] == ONE_MIN_NS
    assert runtime["heartbeat_count"] == 3
    heartbeat_lines = (
        result.output_dir / "logs" / "heartbeat.jsonl"
    ).read_text().splitlines()
    assert len(heartbeat_lines) == runtime["heartbeat_count"]
    assert '"event": "poll"' in (result.output_dir / "logs" / "runtime.log").read_text()


def test_previous_run_id_resumes_from_previous_processed_cursor(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 101, 102, 103],
    )
    signal_store_path = _write_signals(
        tmp_path,
        [
            _signal(signal_id="paper-old", ts_event=BASE_TS_NS + ONE_MIN_NS),
            _signal(signal_id="paper-resumed", ts_event=BASE_TS_NS + 2 * ONE_MIN_NS),
        ],
    )
    previous_run_id = "20260101-000000Z-00000000"
    previous_dir = tmp_path / "paper" / previous_run_id
    previous_dir.mkdir(parents=True)
    previous_processed_until = BASE_TS_NS + ONE_MIN_NS
    (previous_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "backtest_end": "2026-01-01T00:01:00.000Z",
                "runtime": {
                    "processed_until_ns": previous_processed_until,
                    "restart_sequence": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            previous_run_id=previous_run_id,
            restart_reason="pytest_restart",
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    runtime = manifest["runtime"]
    assert manifest["backtest_start"] == "2026-01-01T00:02:00.000Z"
    assert runtime["previous_run_id"] == previous_run_id
    assert runtime["previous_manifest_found"] is True
    assert runtime["previous_processed_until_ns"] == previous_processed_until
    assert runtime["resume_from_ns"] == previous_processed_until + 1
    assert runtime["catalog_start_overridden"] is True
    assert runtime["restart_sequence"] == 3
    assert runtime["restart_reason"] == "pytest_restart"


def test_market_data_gap_blocks_signals_inside_missing_interval(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _write_catalog_at_times(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 102],
        [BASE_TS_NS, BASE_TS_NS + 2 * ONE_MIN_NS],
    )
    signal_store_path = _write_signals(
        tmp_path,
        [
            _signal(
                signal_id="paper-gap-buy",
                ts_event=BASE_TS_NS + ONE_MIN_NS,
                ttl_seconds=3600,
            )
        ],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            max_signal_lag_seconds=3600,
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["runtime"]["data_gap_count"] == 1
    assert manifest["totals"]["orders"] == 0
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage.loc[0, "decision"] == "skip"
    assert lineage.loc[0, "reason"].startswith("data_gap:")
    assert '"event": "data_gap"' in (
        result.output_dir / "logs" / "runtime.log"
    ).read_text()


def test_signal_lag_blocks_new_paper_open(tmp_path, btcusdt_instrument, bar_type):
    first_bar_ns = BASE_TS_NS + 10 * ONE_MIN_NS
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 101, 102],
        start_ns=first_bar_ns,
    )
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-stale-buy", ts_event=BASE_TS_NS, ttl_seconds=3600)],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            max_signal_lag_seconds=60,
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["totals"]["orders"] == 0
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage.loc[0, "decision"] == "skip"
    assert lineage.loc[0, "reason"].startswith("signal_lag:")


def test_expired_signal_blocks_paper_order(tmp_path, btcusdt_instrument, bar_type):
    first_bar_ns = BASE_TS_NS + ONE_MIN_NS
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 101, 102],
        start_ns=first_bar_ns,
    )
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-expired-buy", ts_event=BASE_TS_NS, ttl_seconds=1)],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            max_signal_lag_seconds=3600,
        )
    )

    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage.loc[0, "decision"] == "skip"
    assert lineage.loc[0, "reason"].startswith("expired:")
    assert pd.read_parquet(result.output_dir / "orders.parquet").empty


def test_unauthorized_source_blocks_paper_order(tmp_path, btcusdt_instrument, bar_type):
    catalog_path = _write_catalog(tmp_path, btcusdt_instrument, bar_type, [100, 101, 102])
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-unauthorized", ts_event=BASE_TS_NS + ONE_MIN_NS)],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            allowed_sources=frozenset({"rule_baseline_v1"}),
        )
    )

    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage.loc[0, "decision"] == "skip"
    assert lineage.loc[0, "reason"].startswith("reject_unauthorized_source")
    assert pd.read_parquet(result.output_dir / "fills.parquet").empty


def test_kill_switch_blocks_new_paper_opens(tmp_path, btcusdt_instrument, bar_type):
    catalog_path = _write_catalog(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        [100, 80, 80, 80],
    )
    signal_store_path = _write_signals(
        tmp_path,
        [
            _signal(signal_id="paper-buy", ts_event=BASE_TS_NS, side="buy"),
            _signal(signal_id="paper-sell", ts_event=BASE_TS_NS + 2 * ONE_MIN_NS, side="sell"),
        ],
    )

    result = run_paper_session(
        _config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            daily_drawdown_stop_pct=0.001,
        )
    )

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["totals"]["orders"] == 1
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    by_signal = lineage.set_index("signal_id")
    assert by_signal.loc["paper-buy", "decision"] == "target_long"
    assert by_signal.loc["paper-sell", "decision"] == "skip"
    assert by_signal.loc["paper-sell", "reason"].startswith("kill_switch")


def test_cli_entrypoint_runs_simulated_paper_session(
    tmp_path, btcusdt_instrument, bar_type, capsys
):
    catalog_path = _write_catalog(tmp_path, btcusdt_instrument, bar_type, [100, 101, 102])
    signal_store_path = _write_signals(
        tmp_path,
        [_signal(signal_id="paper-cli-buy", ts_event=BASE_TS_NS + ONE_MIN_NS)],
    )
    output_root = tmp_path / "paper-cli"

    rc = main(
        [
            "--output-root",
            str(output_root),
            "--catalog-path",
            str(catalog_path),
            "--instrument-id",
            "BTCUSDT.BINANCE",
            "--bar-type",
            str(bar_type),
            "--signal-store-path",
            str(signal_store_path),
            "--signal-source",
            "freqai_v1",
            "--signal-model-version",
            "2026-05-14",
            "--trade-size",
            "1",
            "--starting-balance",
            "1000",
            "--machine-id",
            "pytest",
            "--policy-dry-run",
        ]
    )

    assert rc == 0
    output_dir = Path(capsys.readouterr().out.strip())
    manifest = json.loads((output_dir / "run_manifest.json").read_text())
    assert output_dir.parent == output_root
    assert manifest["kind"] == "paper"
    assert manifest["runtime"]["order_mode"] == "simulated"
    assert manifest["totals"]["orders"] == 0


def test_paper_runner_has_no_live_order_or_secret_access_tokens(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "do-not-read")
    source = inspect.getsource(paper_runner)
    forbidden = (
        "os.environ",
        "getenv",
        "BINANCE_API_KEY",
        "BINANCE_SECRET",
        "submit_order",
        "LiveExec",
        "LiveData",
        "BinanceLive",
    )
    for token in forbidden:
        assert token not in source

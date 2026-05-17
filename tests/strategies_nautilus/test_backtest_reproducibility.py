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
import pyarrow as pa
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
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    BaselineNautilusStrategy,
    BaselineNautilusStrategyParams,
)
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig
from apps.strategies_nautilus.runners.backtest_runner import (
    BacktestRunnerConfig,
    SidecarSchemaError,
    main,
    run_backtest,
    validate_sidecar,
    validate_sidecar_bundle,
)
from apps.strategies_nautilus.runners.compare_backtests import (
    compare_backtest_runs,
)
from apps.strategies_nautilus.runners.compare_backtests import (
    main as compare_main,
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


@pytest.fixture
def catalog_path(tmp_path, btcusdt_instrument, bar_type):
    path = tmp_path / "catalog"
    path.mkdir()
    catalog = ParquetDataCatalog(str(path.resolve()))
    catalog.write_data([btcusdt_instrument])
    catalog.write_data(_make_bars(btcusdt_instrument, bar_type))
    return path


def _build_config(
    *,
    output_root: Path,
    catalog_path: Path,
    instrument_id: str,
    bar_type,
    signal_store_path: Path,
    policies: dict[tuple[str, str], SourcePolicy] | None = None,
) -> BacktestRunnerConfig:
    return BacktestRunnerConfig(
        output_root=output_root,
        catalog_path=catalog_path,
        instrument_id=instrument_id,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        baseline_config=BaselineStrategyConfig(
            venue="BINANCE",
            auth=Authorization(
                allowed_sources=frozenset({"freqai_v1"}),
                allowed_model_versions=frozenset({"2026-05-14"}),
                policies=policies or {},
            ),
            min_confidence=0.5,
            max_position_pct=0.05,
            daily_drawdown_stop_pct=0.05,
        ),
        trade_size=Decimal("0.001"),
        starting_balance=Money(100_000, USDT),
        base_currency=USDT,
        signal_filter={"source": "freqai_v1"},
        machine_id="pytest",
        git_commit="0" * 40,
        git_dirty=False,
    )


def test_run_backtest_writes_manifest_and_parquet(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
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
    assert result.manifest.data_catalog.path == str(catalog_path)
    assert result.manifest.data_catalog.instruments[0].rows == 10
    validate_sidecar_bundle(result.output_dir)


def test_signal_lineage_records_every_signal(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(config)
    lineage_df = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert sorted(lineage_df["signal_id"].tolist()) == sorted(s.signal_id for s in signals)


def test_runner_replays_filtered_signals_from_store(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    signals,
    signal_store_path,
    catalog_path,
    make_payload,
):
    store = SignalStore(signal_store_path)
    store.write(
        SignalEvent.model_validate(
            make_payload(
                signal_id="manual-extra",
                source="manual_research",
                model_version="2026-05-14",
                ts_event=BASE_TS_NS + 3 * ONE_MIN_NS,
            )
        )
    )
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(config)

    lineage_df = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert sorted(lineage_df["signal_id"].tolist()) == sorted(s.signal_id for s in signals)
    assert result.manifest.signal_source.row_count == len(signals)
    assert result.manifest.signal_source.filter == {"source": "freqai_v1"}


def test_signal_ids_round_trip_to_reports(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
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
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path, catalog_path
):
    cfg1 = _build_config(
        output_root=tmp_path / "run1",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    cfg2 = _build_config(
        output_root=tmp_path / "run2",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
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


def test_compare_backtests_accepts_replayed_runs(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    signal_store_path,
    catalog_path,
):
    cfg1 = _build_config(
        output_root=tmp_path / "run1",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    cfg2 = _build_config(
        output_root=tmp_path / "run2",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )

    r1 = run_backtest(cfg1)
    r2 = run_backtest(cfg2)

    result = compare_backtest_runs(r1.output_dir, r2.output_dir)
    assert result.ok, result.differences


def test_compare_backtests_cli_reports_drift(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    signal_store_path,
    catalog_path,
    capsys,
):
    cfg1 = _build_config(
        output_root=tmp_path / "run1",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    cfg2 = _build_config(
        output_root=tmp_path / "run2",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )

    r1 = run_backtest(cfg1)
    r2 = run_backtest(cfg2)
    manifest_path = r2.output_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["totals"]["fills"] += 1
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    rc = compare_main([str(r1.output_dir), str(r2.output_dir)])

    assert rc == 1
    assert "run_manifest.json totals differs" in capsys.readouterr().out


def test_sidecar_schema_validation_rejects_missing_column(tmp_path):
    path = tmp_path / "bad.parquet"
    pd.DataFrame({"other": ["x"]}).to_parquet(path, engine="pyarrow", index=False)

    with pytest.raises(SidecarSchemaError, match="missing required column"):
        validate_sidecar(path, pa.schema([pa.field("required", pa.string())]))


def test_cli_entrypoint_runs_catalog_backtest(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path, capsys
):
    output_root = tmp_path / "cli-backtests"
    rc = main(
        [
            "--output-root",
            str(output_root),
            "--catalog-path",
            str(catalog_path),
            "--instrument-id",
            btcusdt_instrument.id.value,
            "--bar-type",
            str(bar_type),
            "--signal-store-path",
            str(signal_store_path),
            "--signal-source",
            "freqai_v1",
            "--signal-model-version",
            "2026-05-14",
            "--trade-size",
            "0.001",
            "--starting-balance",
            "100000",
            "--machine-id",
            "pytest",
        ]
    )

    assert rc == 0
    output_dir = Path(capsys.readouterr().out.strip())
    assert output_dir.parent == output_root
    assert (output_dir / "run_manifest.json").exists()


def test_cli_entrypoint_accepts_source_policy(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path, capsys
):
    output_root = tmp_path / "cli-policy-backtests"
    rc = main(
        [
            "--output-root",
            str(output_root),
            "--catalog-path",
            str(catalog_path),
            "--instrument-id",
            btcusdt_instrument.id.value,
            "--bar-type",
            str(bar_type),
            "--signal-store-path",
            str(signal_store_path),
            "--signal-source",
            "freqai_v1",
            "--signal-model-version",
            "2026-05-14",
            "--trade-size",
            "0.001",
            "--starting-balance",
            "100000",
            "--machine-id",
            "pytest",
            "--policy-position-pct-multiplier",
            "0.2",
            "--policy-dry-run",
        ]
    )

    assert rc == 0
    output_dir = Path(capsys.readouterr().out.strip())
    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["strategies"][0]["params"]["policies"] == [
        {
            "source": "freqai_v1",
            "model_version": "2026-05-14",
            "position_pct_multiplier": 0.2,
            "min_confidence_override": None,
            "dry_run": True,
        }
    ]
    assert manifest["totals"]["orders"] == 0
    assert manifest["totals"]["fills"] == 0


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


# ----- ADR-006 dry-run + policy integration -----------------------------


def test_dry_run_policy_writes_lineage_but_no_orders(
    tmp_path, btcusdt_instrument, bar_type, signals, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        policies={("freqai_v1", "2026-05-14"): SourcePolicy(dry_run=True)},
    )
    result = run_backtest(config)

    # No order or fill was submitted, yet every signal is still in lineage.
    assert result.manifest.totals.fills == 0
    assert result.manifest.totals.orders == 0
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert sorted(lineage["signal_id"].tolist()) == sorted(s.signal_id for s in signals)
    # No order_ids / fill_ids should be populated for dry-run decisions.
    for col in ("order_ids", "fill_ids"):
        assert (lineage[col] == "").all(), (
            f"{col} expected empty under dry-run, got {lineage[col].tolist()}"
        )

    # Manifest carries the policy back out for ADR-004 §2.4 replay diffing.
    policies = result.manifest.strategies[0].params["policies"]
    assert policies == [
        {
            "source": "freqai_v1",
            "model_version": "2026-05-14",
            "position_pct_multiplier": 1.0,
            "min_confidence_override": None,
            "dry_run": True,
        }
    ]


def test_dry_run_replay_is_bit_for_bit_identical(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    policies = {("freqai_v1", "2026-05-14"): SourcePolicy(dry_run=True)}
    cfg1 = _build_config(
        output_root=tmp_path / "run1",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        policies=policies,
    )
    cfg2 = _build_config(
        output_root=tmp_path / "run2",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        policies=policies,
    )
    r1 = run_backtest(cfg1)
    r2 = run_backtest(cfg2)

    assert filecmp.cmp(
        r1.output_dir / "fills.parquet",
        r2.output_dir / "fills.parquet",
        shallow=False,
    )
    assert filecmp.cmp(
        r1.output_dir / "signal_lineage.parquet",
        r2.output_dir / "signal_lineage.parquet",
        shallow=False,
    )
    assert r1.manifest.totals == r2.manifest.totals
    assert (
        r1.manifest.strategies[0].params["policies"]
        == r2.manifest.strategies[0].params["policies"]
    )


def test_multiplier_policy_still_produces_orders(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    # multiplier=0.5 halves the target but still emits live orders.
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        policies={("freqai_v1", "2026-05-14"): SourcePolicy(position_pct_multiplier=0.5)},
    )
    result = run_backtest(config)
    assert result.manifest.totals.fills > 0
    # Manifest preserves the policy multiplier for replay.
    pol = result.manifest.strategies[0].params["policies"][0]
    assert pol["position_pct_multiplier"] == 0.5
    assert pol["dry_run"] is False


def test_empty_policies_omitted_or_empty_list(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(config)
    policies = result.manifest.strategies[0].params.get("policies", [])
    assert policies == []

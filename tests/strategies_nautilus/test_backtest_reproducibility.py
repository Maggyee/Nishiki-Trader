"""End-to-end smoke + reproducibility tests for `backtest_runner.run_backtest`.

Two synthetic backtests with identical inputs must produce:
- bit-for-bit identical `fills.parquet` (ADR-004 §2.4)
- equal `stats_pnls` and `stats_returns` in the manifest
- identical row counts in `orders / positions / signal_lineage`

`run_id`, `started_at`, `finished_at`, and `elapsed_seconds` are explicitly
excluded by ADR-004 §2.4.
"""

from __future__ import annotations

import dataclasses
import filecmp
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pyarrow as pa
import pytest
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
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
    _build_arg_parser,
    _config_from_args,
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
    account_type: AccountType = AccountType.MARGIN,
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
        account_type=account_type,
    )


def test_cash_account_backtest_records_spot_execution_assumptions(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "cash-backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        account_type=AccountType.CASH,
    )
    result = run_backtest(config)

    params = result.manifest.strategies[0].params
    assert params["account_type"] == "CASH"
    assert params["oms_type"] == "NETTING"
    # The fixture's final sell signal must not short spot and halt the engine.
    assert result.manifest.totals.iterations == 10


def test_two_same_bar_spot_sells_close_once(
    tmp_path, btcusdt_instrument, bar_type, catalog_path, make_payload
):
    store = SignalStore(tmp_path / "double-sell.db")
    for signal_id, minute, side in (("open", 2, "buy"), ("sell-a", 5, "sell"), ("sell-b", 5, "sell")):
        store.write(
            SignalEvent.model_validate(
                make_payload(
                    signal_id=signal_id,
                    ts_event=BASE_TS_NS + minute * ONE_MIN_NS,
                    side=side,
                    ttl_seconds=900,
                )
            )
        )
    config = _build_config(
        output_root=tmp_path / "double-sell",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=tmp_path / "double-sell.db",
        account_type=AccountType.CASH,
    )
    result = run_backtest(config)

    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet").set_index("signal_id")
    assert lineage.loc["sell-a", "order_ids"] != ""
    assert lineage.loc["sell-b", "reason"] == "suppressed_after_same_bar_order_submission"
    orders = pd.read_parquet(result.output_dir / "orders.parquet")
    assert len(orders) == 2  # one buy, one close; no second close to be rejected


@pytest.mark.parametrize(
    ("account_type", "sell_decision"),
    [(AccountType.CASH, "target_flat"), (AccountType.MARGIN, "target_short")],
)
def test_sell_signal_closes_on_spot_and_shorts_on_margin(
    tmp_path, btcusdt_instrument, bar_type, catalog_path, make_payload, account_type, sell_decision
):
    store = SignalStore(tmp_path / "buy-sell.db")
    for signal_id, minute, side in (("open", 2, "buy"), ("sell", 5, "sell")):
        store.write(
            SignalEvent.model_validate(
                make_payload(
                    signal_id=signal_id,
                    ts_event=BASE_TS_NS + minute * ONE_MIN_NS,
                    side=side,
                    ttl_seconds=900,
                )
            )
        )
    config = _build_config(
        output_root=tmp_path / f"sell-{account_type.name}",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=tmp_path / "buy-sell.db",
        account_type=account_type,
    )
    result = run_backtest(config)

    assert result.manifest.totals.iterations == 10
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet").set_index("signal_id")
    assert lineage.loc["sell", "decision"] == sell_decision
    sides = pd.read_parquet(result.output_dir / "fills.parquet")["order_side"].astype(str)
    if account_type == AccountType.CASH:
        assert lineage.loc["sell", "reason"] == "spot_cash_account_sell_as_flat"
        assert list(sides) == ["BUY", "SELL"]  # the long is closed, nothing is shorted
    else:
        assert lineage.loc["sell", "order_ids"] != ""  # margin still opens the short


def test_trade_notional_sizes_each_order_from_the_latest_close(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "notional-backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(dataclasses.replace(config, trade_notional=Decimal("1000")))

    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    # The buy signal is decided on the bar that closes at 50,300; notional
    # sizing rounds down so the order never exceeds the requested value.
    expected = btcusdt_instrument.make_qty(Decimal("1000") / Decimal("50300"), round_down=True)
    assert Decimal(str(fills.iloc[0]["last_qty"])) == expected.as_decimal()
    assert result.manifest.strategies[0].params["trade_notional"] == "1000"


def test_trade_notional_never_spends_more_than_the_cash_balance(
    tmp_path, btcusdt_instrument, bar_type, catalog_path, make_payload
):
    store = SignalStore(tmp_path / "buy-flat.db")
    for signal_id, minute, side in (("cash-buy", 2, "buy"), ("cash-flat", 5, "flat")):
        store.write(
            SignalEvent.model_validate(
                make_payload(
                    signal_id=signal_id,
                    ts_event=BASE_TS_NS + minute * ONE_MIN_NS,
                    side=side,
                    ttl_seconds=900,
                )
            )
        )
    config = _build_config(
        output_root=tmp_path / "notional-cash",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=tmp_path / "buy-flat.db",
        account_type=AccountType.CASH,
    )
    result = run_backtest(
        dataclasses.replace(
            config, starting_balance=Money(1_000, USDT), trade_notional=Decimal("1000")
        )
    )

    assert result.manifest.totals.iterations == 10
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    buy = fills.iloc[0]
    cost = Decimal(str(buy["last_qty"])) * Decimal(str(buy["last_px"]).split()[0])
    assert cost * (1 + btcusdt_instrument.taker_fee) <= Decimal("1000")
    assert len(fills) == 2  # bought within the balance, then closed by the flat signal


def test_trade_notional_below_one_lot_submits_no_order(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "notional-tiny",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )
    result = run_backtest(dataclasses.replace(config, trade_notional=Decimal("0.01")))

    assert result.manifest.totals.iterations == 10
    assert pd.read_parquet(result.output_dir / "fills.parquet").empty


def test_repeated_buy_while_long_stays_a_no_op_before_sizing(
    tmp_path, btcusdt_instrument, bar_type, catalog_path, make_payload
):
    # A second source whose policy shrinks orders below one lot re-sends a buy
    # while the book is already long: it must stay a no-op, not reach make_qty.
    store = SignalStore(tmp_path / "two-sources.db")
    for signal_id, minute, source in (("open", 2, "freqai_v1"), ("repeat", 3, "freqai_tiny")):
        store.write(
            SignalEvent.model_validate(
                make_payload(
                    signal_id=signal_id,
                    ts_event=BASE_TS_NS + minute * ONE_MIN_NS,
                    source=source,
                    ttl_seconds=900,
                )
            )
        )
    config = _build_config(
        output_root=tmp_path / "repeat-buy",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=tmp_path / "two-sources.db",
    )
    baseline = dataclasses.replace(
        config.baseline_config,
        auth=Authorization(
            allowed_sources=frozenset({"freqai_v1", "freqai_tiny"}),
            allowed_model_versions=frozenset({"2026-05-14"}),
            policies={
                ("freqai_tiny", "2026-05-14"): SourcePolicy(position_pct_multiplier=0.0001)
            },
        ),
    )
    result = run_backtest(dataclasses.replace(config, baseline_config=baseline, signal_filter={}))

    assert result.manifest.totals.iterations == 10
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    assert (fills["order_side"].astype(str) == "BUY").sum() == 1
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet").set_index("signal_id")
    assert lineage.loc["repeat", "order_ids"] == ""


@pytest.mark.parametrize(
    ("sizing", "error"),
    [
        ([], SystemExit),
        (["--trade-size", "0.001", "--trade-notional", "1000"], SystemExit),
        (["--trade-notional", "0"], ValueError),
    ],
)
def test_cli_requires_exactly_one_positive_sizing_mode(sizing, error):
    argv = [
        "--instrument-id",
        "BTCUSDT.BINANCE",
        "--bar-type",
        "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
        "--signal-source",
        "freqai_v1",
        "--signal-model-version",
        "2026-05-14",
        "--starting-balance",
        "10000",
        *sizing,
    ]
    with pytest.raises(error):
        _config_from_args(_build_arg_parser().parse_args(argv))


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


def test_runner_skips_same_source_signal_for_different_instrument(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    signals,
    signal_store_path,
    catalog_path,
    make_payload,
):
    cross_asset = SignalEvent.model_validate(
        make_payload(
            signal_id="freqai_v1:ETHUSDT:BINANCE:cross-asset",
            symbol="ETHUSDT",
            ts_event=BASE_TS_NS + ONE_MIN_NS,
            side="buy",
        )
    )
    SignalStore(signal_store_path).write(cross_asset)
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
    )

    result = run_backtest(config)

    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    mismatch = lineage.loc[lineage["signal_id"] == cross_asset.signal_id].iloc[0]
    assert mismatch["decision"] == "skip"
    assert mismatch["reason"] == "instrument_mismatch:ETHUSDT.BINANCE!=BTCUSDT.BINANCE"
    orders = pd.read_parquet(result.output_dir / "orders.parquet")
    assert cross_asset.signal_id not in set(orders["signal_id"])


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


def test_nautilus_wrapper_suppresses_same_bar_order_intents(
    btcusdt_instrument, bar_type, make_payload, monkeypatch
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
    signals = [
        SignalEvent.model_validate(
            make_payload(
                signal_id="same-bar-buy-1",
                ts_event=BASE_TS_NS + ONE_MIN_NS,
                side="buy",
            )
        ),
        SignalEvent.model_validate(
            make_payload(
                signal_id="same-bar-buy-2",
                ts_event=BASE_TS_NS + ONE_MIN_NS,
                side="buy",
            )
        ),
    ]
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
    monkeypatch.setattr(strategy, "_current_equity", lambda: None)
    applied_signal_ids: list[str] = []

    def fake_apply_intent(intent):
        applied_signal_ids.append(intent.signal_id)
        return [f"order-{len(applied_signal_ids)}"]

    monkeypatch.setattr(strategy, "_apply_intent", fake_apply_intent)

    strategy.on_bar(SimpleNamespace(ts_event=BASE_TS_NS + ONE_MIN_NS))

    assert applied_signal_ids == ["same-bar-buy-1"]
    assert [row.signal_id for row in strategy.lineage] == [
        "same-bar-buy-1",
        "same-bar-buy-2",
    ]
    assert strategy.lineage[0].client_order_ids == ["order-1"]
    assert strategy.lineage[1].client_order_ids == []
    assert strategy.lineage[1].reason == "suppressed_after_same_bar_order_submission"


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
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    assert set(fills["quantity"].round(7)) == {0.0005}
    # Manifest preserves the policy multiplier for replay.
    pol = result.manifest.strategies[0].params["policies"][0]
    assert pol["position_pct_multiplier"] == 0.5
    assert pol["dry_run"] is False


def test_zero_multiplier_policy_submits_no_orders(
    tmp_path, btcusdt_instrument, bar_type, signal_store_path, catalog_path
):
    config = _build_config(
        output_root=tmp_path / "backtests",
        catalog_path=catalog_path,
        instrument_id=btcusdt_instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        policies={
            ("freqai_v1", "2026-05-14"): SourcePolicy(
                position_pct_multiplier=0.0
            )
        },
    )

    result = run_backtest(config)

    assert result.manifest.totals.orders == 0
    assert result.manifest.totals.fills == 0


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


def _fraction_backtest(
    tmp_path,
    instrument,
    bar_type,
    make_payload,
    *,
    prices=(50_000, 50_000, 100_000, 100_000),
    times=None,
    events=(("entry", 0, "buy"),),
    fraction=Decimal("0.4"),
    weekday=6,
    policies=None,
):
    """Small synthetic CASH catalog spanning a weekly boundary."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    index = pd.DatetimeIndex(
        times
        or [
            "2026-01-01T00:00:00Z",
            "2026-01-04T23:59:00Z",
            "2026-01-05T00:00:00Z",
            "2026-01-05T00:01:00Z",
        ]
    )
    frame = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": 100.0},
        index=index,
    )
    catalog_path = tmp_path / "catalog"
    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    catalog.write_data([instrument])
    catalog.write_data(BarDataWrangler(bar_type, instrument).process(frame))
    store_path = tmp_path / "signals.db"
    store = SignalStore(store_path)
    for signal_id, row, side, *source in events:
        store.write(
            SignalEvent.model_validate(
                make_payload(
                    signal_id=signal_id,
                    ts_event=index[row].value,
                    side=side,
                    source=source[0] if source else "freqai_v1",
                )
            )
        )
    config = _build_config(
        output_root=tmp_path / "runs",
        catalog_path=catalog_path,
        instrument_id=instrument.id.value,
        bar_type=bar_type,
        signal_store_path=store_path,
        account_type=AccountType.CASH,
        policies=policies,
    )
    if policies:
        config.baseline_config = dataclasses.replace(
            config.baseline_config,
            auth=dataclasses.replace(
                config.baseline_config.auth,
                allowed_sources=config.baseline_config.auth.allowed_sources
                | frozenset(source for source, _ in policies),
            ),
        )
    return run_backtest(
        dataclasses.replace(
        config,
        starting_balance=Money(10_000, USDT),
        signal_filter={},
        target_equity_fraction=fraction,
            rebalance_weekday=weekday,
        )
    )


@pytest.mark.parametrize(("fraction", "multiplier"), [("1", 1.0), ("0.4", 1.0), ("0.4", 0.5)])
def test_equity_fraction_entry_reserves_cash_fees_and_scales_policy(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
    fraction,
    multiplier,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        fraction=Decimal(fraction),
        weekday=None,
        events=(("entry", 0, "buy"), ("repeat", 1, "buy"), ("close", 3, "sell")),
        policies={("freqai_v1", "2026-05-14"): SourcePolicy(position_pct_multiplier=multiplier)},
    )
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    desired = Decimal(fraction) * Decimal(str(multiplier)) * Decimal(10000) / Decimal(50000)
    affordable = Decimal(10000) / (Decimal(50000) * (1 + btcusdt_instrument.taker_fee))
    expected = btcusdt_instrument.make_qty(min(desired, affordable), round_down=True).as_decimal()
    assert Decimal(str(fills.iloc[0]["last_qty"])) == expected
    assert len(fills) == 2  # repeated buy is idempotent; spot sell closes
    assert expected * Decimal(50000) * (1 + btcusdt_instrument.taker_fee) <= Decimal(10000)
    assert result.manifest.totals.iterations == 4
    assert result.manifest.strategies[0].params["target_equity_fraction"] == fraction


@pytest.mark.parametrize(("boundary_price", "side"), [(100_000, "SELL"), (25_000, "BUY")])
def test_weekly_equity_rebalance_trades_only_the_difference_and_writes_lineage(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
    boundary_price,
    side,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        prices=(50_000, 50_000, boundary_price, boundary_price * 2),
    )
    orders = pd.read_parquet(result.output_dir / "orders.parquet")
    fills = pd.read_parquet(result.output_dir / "fills.parquet")
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    rebalance = lineage[lineage["decision"] == "rebalance"]
    assert len(rebalance) == 1  # Monday's following minute is not a second boundary.
    record = rebalance.iloc[0]
    assert record["signal_id"] == "rebalance:2026-01-05T00:00:00+00:00"
    assert record["source"] == "freqai_v1"
    assert record["model_version"] == "2026-05-14"
    rebalance_orders = orders[orders["signal_id"] == record["signal_id"]]
    assert len(rebalance_orders) == 1
    order = rebalance_orders.iloc[0]
    assert order["side"] == side
    assert bool(order["is_reduce_only"]) == (side == "SELL")
    assert record["order_ids"] == order["client_order_id"]
    assert record["signal_id"] in str(order["tags"])
    assert record["fill_ids"]
    bought = Decimal(str(fills.iloc[0]["last_qty"]))
    cash = Decimal(10000) - bought * Decimal(50000) * (1 + btcusdt_instrument.taker_fee)
    equity = cash + bought * Decimal(boundary_price)
    desired = btcusdt_instrument.make_qty(
        Decimal("0.4") * equity / Decimal(boundary_price),
        round_down=True,
    ).as_decimal()
    assert Decimal(str(order["quantity"])) == abs(desired - bought)
    params = result.manifest.strategies[0].params
    assert params["rebalance_weekday"] == 6
    assert params["trade_notional"] is None


def test_rebalance_uses_the_latest_policy_multiplier(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
):
    policy = SourcePolicy(position_pct_multiplier=0.5)
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        events=(("entry", 0, "buy"), ("repeat", 1, "buy", "freqai_half")),
        policies={("freqai_half", "2026-05-14"): policy},
    )
    orders = pd.read_parquet(result.output_dir / "orders.parquet")
    rebalanced = orders[orders["signal_id"].str.startswith("rebalance:")].iloc[0]
    # Repeated buy leaves .08 BTC in place; weekly sizing uses the new half policy.
    assert rebalanced["quantity"] == pytest.approx(0.08 - 0.027992)
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet").set_index("signal_id")
    assert lineage.loc["repeat", "order_ids"] == ""
    assert lineage.loc[rebalanced["signal_id"], "source"] == "freqai_half"


def test_rebalance_boundary_is_the_end_of_the_selected_utc_weekday(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        weekday=0,
        times=[
            "2026-01-01T00:00:00Z",
            "2026-01-05T23:59:00Z",
            "2026-01-06T00:00:00Z",
            "2026-01-06T00:01:00Z",
        ],
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage[lineage["decision"] == "rebalance"]["signal_id"].tolist() == [
        "rebalance:2026-01-06T00:00:00+00:00"
    ]


@pytest.mark.parametrize("events", [(), (("entry", 0, "buy"), ("close", 1, "flat"))])
def test_rebalance_consumes_flat_boundaries_without_orders(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
    events,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        events=events,
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert not (lineage["decision"] == "rebalance").any()


def test_signal_order_on_boundary_suppresses_rebalance_and_consumes_boundary(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        events=(("entry", 0, "buy"), ("close", 2, "flat"), ("reentry", 3, "buy")),
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert not (lineage["decision"] == "rebalance").any()
    assert lineage.set_index("signal_id").loc["close", "order_ids"]


@pytest.mark.parametrize("fraction", [Decimal("0.4"), Decimal("0.000000001")])
def test_fraction_rebalance_skips_tiny_difference_or_tiny_entry(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
    fraction,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        prices=(50_000, 50_000, 50_000, 50_000),
        fraction=fraction,
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert not (lineage["decision"] == "rebalance").any()
    if fraction < Decimal("0.000001"):
        assert result.manifest.totals.orders == 0


def test_fraction_dry_run_cannot_submit_rebalance_orders(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        policies={("freqai_v1", "2026-05-14"): SourcePolicy(dry_run=True)},
    )
    assert result.manifest.totals.orders == 0


def test_equity_fraction_replay_is_reproducible(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
):
    runs = [
        _fraction_backtest(tmp_path / name, btcusdt_instrument, bar_type, make_payload)
        for name in ("first", "second")
    ]
    for filename in ("fills.parquet", "signal_lineage.parquet"):
        assert filecmp.cmp(
            runs[0].output_dir / filename, runs[1].output_dir / filename, shallow=False
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"target_equity_fraction": Decimal("0")},
        {"target_equity_fraction": Decimal("-0.1")},
        {"target_equity_fraction": Decimal("1.01")},
        {"target_equity_fraction": Decimal("NaN")},
        {"target_equity_fraction": Decimal("Infinity")},
        {"target_equity_fraction": Decimal("0.4"), "trade_notional": Decimal("100")},
        {"rebalance_weekday": 6},
        {"target_equity_fraction": Decimal("0.4"), "rebalance_weekday": -1},
        {"target_equity_fraction": Decimal("0.4"), "rebalance_weekday": 7},
        {"target_equity_fraction": Decimal("0.4"), "rebalance_weekday": 2.5},
    ],
)
def test_equity_fraction_params_validate(btcusdt_instrument, bar_type, config, changes):
    baseline = BaselineStrategyConfig(venue="BINANCE", auth=config.auth)
    with pytest.raises(ValueError):
        BaselineNautilusStrategyParams(
            instrument_id=btcusdt_instrument.id,
            bar_type=bar_type,
            baseline_config=baseline,
            trade_size=Decimal("0.001"),
            equity_currency=USDT,
            **changes,
        )


@pytest.mark.parametrize(
    ("sizing", "error"),
    [
        (["--target-equity-fraction", "0"], ValueError),
        (["--target-equity-fraction", "1.1"], ValueError),
        (["--target-equity-fraction", "NaN"], ValueError),
        (["--target-equity-fraction", ".4", "--trade-notional", "1000"], SystemExit),
        (["--target-equity-fraction", ".4", "--trade-size", ".001"], SystemExit),
        (["--trade-size", ".001", "--rebalance-weekday", "6"], ValueError),
        (["--target-equity-fraction", ".4", "--rebalance-weekday", "7"], ValueError),
        (["--target-equity-fraction", ".4", "--rebalance-weekday", "-1"], ValueError),
    ],
)
def test_equity_fraction_cli_validate(sizing, error):
    argv = [
        "--instrument-id",
        "BTCUSDT.BINANCE",
        "--bar-type",
        "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
        "--signal-source",
        "freqai_v1",
        "--signal-model-version",
        "2026-05-14",
        "--starting-balance",
        "10000",
        *sizing,
    ]
    with pytest.raises(error):
        _config_from_args(_build_arg_parser().parse_args(argv))


def test_equity_fraction_cli_config():
    args = _build_arg_parser().parse_args(
        [
            "--instrument-id",
            "BTCUSDT.BINANCE",
            "--bar-type",
            "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
            "--signal-source",
            "freqai_v1",
            "--signal-model-version",
            "2026-05-14",
            "--starting-balance",
            "10000",
            "--target-equity-fraction",
            ".4",
            "--rebalance-weekday",
            "6",
            "--account-type",
            "cash",
        ]
    )
    config = _config_from_args(args)
    assert config.target_equity_fraction == Decimal(".4")
    assert config.rebalance_weekday == 6
    assert config.trade_size == 0
    assert config.trade_notional is None


@pytest.mark.parametrize(("price", "expected_rebalances"), [(25_000, 0), (100_000, 1)])
def test_weekly_kill_switch_blocks_buys_and_allows_reductions(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
    monkeypatch,
    price,
    expected_rebalances,
):
    update = BaselineNautilusStrategy._update_daily_risk_state
    boundary_ns = pd.Timestamp("2026-01-05T00:00:00Z").value

    def with_loss(strategy, now_ns):
        update(strategy, now_ns)
        if now_ns >= boundary_ns:
            strategy._baseline.on_account_update(equity_open=10000.0, equity_now=9000.0)

    monkeypatch.setattr(BaselineNautilusStrategy, "_update_daily_risk_state", with_loss)
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        prices=(50_000, 50_000, price, price),
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert (lineage["decision"] == "rebalance").sum() == expected_rebalances


def test_new_dry_run_signal_while_long_suppresses_weekly_rebalance(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        events=(("entry", 0, "buy"), ("dry", 1, "buy", "freqai_dry")),
        policies={("freqai_dry", "2026-05-14"): SourcePolicy(dry_run=True)},
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert not (lineage["decision"] == "rebalance").any()
    assert lineage.set_index("signal_id").loc["dry", "order_ids"] == ""


@pytest.mark.parametrize(
    ("times", "expected_boundary"),
    [
        (
            [
                "2026-01-05T00:00:00Z",
                "2026-01-05T00:01:00Z",
                "2026-01-12T00:00:00Z",
                "2026-01-12T00:01:00Z",
            ],
            "2026-01-12T00:00:00+00:00",
        ),
        (
            [
                "2026-01-01T00:00:00Z",
                "2026-01-04T23:59:00Z",
                "2026-01-19T12:00:00Z",
                "2026-01-19T12:01:00Z",
            ],
            "2026-01-19T00:00:00+00:00",
        ),
    ],
)
def test_weekly_schedule_starts_at_first_bar_and_consumes_latest_missed_boundary(
    tmp_path,
    btcusdt_instrument,
    bar_type,
    make_payload,
    times,
    expected_boundary,
):
    result = _fraction_backtest(
        tmp_path,
        btcusdt_instrument,
        bar_type,
        make_payload,
        times=times,
        prices=(50_000, 50_000, 100_000, 100_000),
    )
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert lineage[lineage["decision"] == "rebalance"]["signal_id"].tolist() == [
        f"rebalance:{expected_boundary}"
    ]


@pytest.mark.parametrize("account_type", [None, AccountType.CASH, AccountType.MARGIN])
def test_fraction_sizing_equity_uses_total_balances_and_handles_missing_accounts(
    btcusdt_instrument,
    bar_type,
    config,
    monkeypatch,
    account_type,
):
    instrument = btcusdt_instrument
    account = (
        None
        if account_type is None
        else SimpleNamespace(
            type=account_type,
            balance_total=lambda currency: Money(
                5000 if currency == USDT else 0.1,
                currency,
            ),
        )
    )
    monkeypatch.setattr(
        BaselineNautilusStrategy,
        "portfolio",
        SimpleNamespace(account=lambda venue: account),
    )
    strategy = BaselineNautilusStrategy(
        BaselineNautilusStrategyParams(
            instrument_id=instrument.id,
            bar_type=bar_type,
            baseline_config=BaselineStrategyConfig(venue="BINANCE", auth=config.auth),
            trade_size=Decimal(0),
            equity_currency=USDT,
            target_equity_fraction=Decimal(".4"),
        )
    )
    strategy._last_close = Decimal(50000)
    monkeypatch.setattr(strategy, "_current_equity", lambda: 12345.0)
    expected = {
        None: Decimal(0),
        AccountType.CASH: Decimal(10000),
        AccountType.MARGIN: Decimal(12345),
    }
    assert strategy._sizing_equity(instrument) == expected[account_type]

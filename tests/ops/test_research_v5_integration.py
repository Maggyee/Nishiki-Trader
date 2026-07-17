from __future__ import annotations

import filecmp
import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import pandas as pd
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization
from apps.ops.alpha_review import build_alpha_review
from apps.ops.multi_asset_review import build_multi_asset_review
from apps.ops.research_v5_review import EXPECTED_FOLDS, build_research_v5_review
from apps.ops.research_v5_snapshot import (
    HttpResponse,
    build_requests,
    collect_snapshot,
)
from apps.strategies_freqtrade.research.binance_mechanism_signals import (
    STRATEGY_IDENTITIES,
    generate_curve_carry_signals,
    load_normalized_rows,
)
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig
from apps.strategies_nautilus.runners.backtest_runner import (
    BacktestRunnerConfig,
    run_backtest,
)


def _zip_csv(name: str, text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)
    return output.getvalue()


def _curve_fetch(asset: str, data_day: date, *, positive: bool):
    bodies: dict[str, bytes] = {}
    start_ms = int(datetime.combine(data_day, datetime.min.time(), UTC).timestamp() * 1000)
    for spec in build_requests("delivery_curve", asset, data_day):
        if spec.role == "index_price":
            close = 100.0
        elif positive and spec.role == "front_contract":
            close = 101.0
        elif positive:
            close = 104.0
        else:
            close = 99.0
        row = [
            start_ms,
            close,
            close + 1.0,
            close - 1.0,
            close,
            1.0,
            start_ms + 86_400_000 - 1,
            1.0,
            1,
            1.0,
            1.0,
            0,
        ]
        body = _zip_csv(
            spec.filename.removesuffix(".zip") + ".csv",
            ",".join(map(str, row)) + "\n",
        )
        digest = hashlib.sha256(body).hexdigest()
        bodies[spec.url] = body
        bodies[f"{spec.url}.CHECKSUM"] = f"{digest}  {spec.filename}\n".encode()

    def fetch(url: str) -> HttpResponse:
        return HttpResponse(
            body=bodies[url],
            status=200,
            final_url=url,
            headers={"etag": "synthetic-v5-integration"},
        )

    return fetch


def _instrument(symbol: str):
    if symbol == "BTCUSDT":
        return TestInstrumentProvider.btcusdt_binance()
    return TestInstrumentProvider.ethusdt_binance()


def _catalog(
    root: Path,
    *,
    symbol: str,
    start: date,
    end: date,
) -> tuple[Path, object, BarType, Decimal]:
    instrument = _instrument(symbol)
    bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
    first_close = Decimal("50000") if symbol == "BTCUSDT" else Decimal("4000")
    increment = Decimal(str(float(instrument.size_increment)))
    trade_size = ((Decimal("50") / first_close) / increment).to_integral_value(
        rounding=ROUND_FLOOR
    ) * increment
    timestamps = pd.date_range(
        pd.Timestamp(start - timedelta(days=1), tz="UTC") + pd.Timedelta(hours=23, minutes=59),
        pd.Timestamp(end + timedelta(days=1), tz="UTC") + pd.Timedelta(hours=23, minutes=59),
        freq="1D",
    )
    prices = [float(first_close)] * len(timestamps)
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": [price + 1.0 for price in prices],
            "low": [price - 1.0 for price in prices],
            "close": prices,
            "volume": 10.0,
        },
        index=timestamps,
    )
    frame.index.name = "timestamp"
    catalog_path = root / "catalog" / symbol
    catalog_path.mkdir(parents=True)
    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    catalog.write_data([instrument])
    catalog.write_data(BarDataWrangler(bar_type, instrument).process(frame))
    return catalog_path, instrument, bar_type, trade_size


def _asset_alpha_review(
    root: Path,
    *,
    symbol: str,
    start: date,
    end: date,
) -> Path:
    normalized_root = root / "snapshots" / "normalized"
    for offset, positive in ((-1, True), (1, True), (3, False)):
        data_day = start + timedelta(days=offset)
        collect_snapshot(
            "delivery_curve",
            symbol,
            data_day,
            raw_root=root / "snapshots" / "raw",
            normalized_root=normalized_root,
            fetch=_curve_fetch(symbol, data_day, positive=positive),
            now=datetime(2026, 7, 17, 12, tzinfo=UTC),
        )
    factors = load_normalized_rows(normalized_root, "curve_carry", symbol)
    events = generate_curve_carry_signals(
        factors,
        asset=symbol,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    assert [event.side for event in events] == ["buy", "flat", "buy", "flat"]
    signal_db = root / f"{symbol}-signals.db"
    written, duplicates = SignalStore(signal_db).write_many(events)
    assert (written, duplicates) == (4, 0)

    catalog_path, instrument, bar_type, trade_size = _catalog(
        root,
        symbol=symbol,
        start=start,
        end=end,
    )
    source, model_version = STRATEGY_IDENTITIES["curve_carry"]
    config = BacktestRunnerConfig(
        output_root=root / "backtests" / symbol,
        catalog_path=catalog_path,
        instrument_id=instrument.id.value,
        bar_type=bar_type,
        signal_store_path=signal_db,
        baseline_config=BaselineStrategyConfig(
            venue="BINANCE",
            auth=Authorization(
                allowed_sources=frozenset({source}),
                allowed_model_versions=frozenset({model_version}),
            ),
            min_confidence=0.5,
            max_position_pct=0.05,
            daily_drawdown_stop_pct=0.05,
        ),
        trade_size=trade_size,
        starting_balance=Money(100_000, USDT),
        base_currency=USDT,
        signal_filter={"source": source, "model_version": model_version},
        machine_id="pytest-v5-integration",
        git_commit="0" * 40,
        git_dirty=False,
        account_type=AccountType.CASH,
        oms_type=OmsType.NETTING,
    )
    first = run_backtest(config)
    second = run_backtest(config)
    assert filecmp.cmp(
        first.output_dir / "fills.parquet",
        second.output_dir / "fills.parquet",
        shallow=False,
    )
    alpha = build_alpha_review(
        [("curve_carry", first.output_dir), ("curve_carry", second.output_dir)],
        blind_start=start.isoformat(),
        blind_end=end.isoformat(),
        trade_size=float(trade_size),
    )
    alpha_path = root / f"alpha-{symbol}.json"
    alpha_path.write_text(
        json.dumps(alpha, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return alpha_path


def test_v5_raw_to_review_pipeline_is_reproducible(tmp_path: Path) -> None:
    fold_specs = []
    for fold_name, (start_text, end_text) in EXPECTED_FOLDS["curve_fast_track"].items():
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
        fold_root = tmp_path / fold_name
        asset_reviews = [
            (
                symbol,
                _asset_alpha_review(
                    fold_root / symbol,
                    symbol=symbol,
                    start=start,
                    end=end,
                ),
            )
            for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        multi = build_multi_asset_review(fold_name, asset_reviews)
        assert multi["candidates"][0]["exclusivity"]["maximum_concurrent_assets"] == 2
        assert multi["candidates"][0]["notional_audit"]["within_limit"] is True
        multi_path = fold_root / "multi-asset-review.json"
        multi_path.write_text(
            json.dumps(multi, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        fold_specs.append(("curve_carry", fold_name, multi_path))

    report = build_research_v5_review(
        "curve_fast_track",
        fold_specs,
        as_of=date(2026, 7, 17),
    )

    assert report["schema_version"] == "research.v5.review.v1"
    assert report["recommendation"] == "stop_before_testnet_resume"
    assert report["boundaries"]["starts_nautilus"] is False
    assert report["candidates"][0]["gates"]["reproducible"] is True

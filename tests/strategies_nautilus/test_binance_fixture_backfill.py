from __future__ import annotations

import json
import zipfile
from pathlib import Path

from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from apps.bridge.store import SignalStore
from apps.ops.backfill_bars import main


def _write_sample_binance_zip(path: Path) -> None:
    rows = [
        "1704067200000,42000.00,42100.00,41900.00,42050.00,12.0,1704067259999,0,0,0,0,0",
        "1704067260000,42050.00,42200.00,42000.00,42150.00,10.5,1704067319999,0,0,0,0,0",
        "1704067320000,42150.00,42300.00,42100.00,42250.00,11.1,1704067379999,0,0,0,0,0",
        "1704067380000,42250.00,42400.00,42200.00,42350.00,13.4,1704067439999,0,0,0,0,0",
    ]
    with zipfile.ZipFile(path, mode="w") as zf:
        zf.writestr("BTCUSDT-1m-2024-01-01.csv", "\n".join(rows) + "\n")


def _write_microsecond_binance_zip(path: Path) -> None:
    rows = [
        "1735689600000000,93000.00,93100.00,92900.00,93050.00,12.0,1735689659999999,0,0,0,0,0",
        "1735689660000000,93050.00,93200.00,93000.00,93150.00,10.5,1735689719999999,0,0,0,0,0",
    ]
    with zipfile.ZipFile(path, mode="w") as zf:
        zf.writestr("BTCUSDT-1m-2025-01-01.csv", "\n".join(rows) + "\n")


def test_backfill_bars_cli_imports_zip_to_catalog_and_demo_signals(
    tmp_path: Path,
    capsys,
) -> None:
    raw_path = tmp_path / "BTCUSDT-1m-2024-01-01.zip"
    catalog_path = tmp_path / "catalog"
    signal_store_path = tmp_path / "signals.db"
    _write_sample_binance_zip(raw_path)

    rc = main(
        [
            "--raw-path",
            str(raw_path),
            "--catalog-path",
            str(catalog_path),
            "--signal-store-path",
            str(signal_store_path),
            "--seed-demo-signals",
        ]
    )

    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["instrument_id"] == "BTCUSDT.BINANCE"
    assert result["bar_type"] == "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"
    assert result["bars_written"] == 4
    assert result["demo_signals_written"] == 3

    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    instruments = catalog.instruments(instrument_ids=["BTCUSDT.BINANCE"])
    bars = catalog.bars(bar_types=[result["bar_type"]])
    assert [instrument.id.value for instrument in instruments] == ["BTCUSDT.BINANCE"]
    assert len(bars) == 4

    signals = SignalStore(signal_store_path).replay(
        source="manual_research",
        model_version="binance-fixture-v1",
    )
    assert [signal.side for signal in signals] == ["buy", "flat", "sell"]


def test_backfill_detects_2025_microsecond_spot_timestamps(tmp_path: Path, capsys) -> None:
    raw_path = tmp_path / "BTCUSDT-1m-2025-01-01.zip"
    catalog_path = tmp_path / "catalog"
    _write_microsecond_binance_zip(raw_path)

    assert main(["--raw-path", str(raw_path), "--catalog-path", str(catalog_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    bars = ParquetDataCatalog(str(catalog_path.resolve())).bars(
        bar_types=[result["bar_type"]]
    )

    assert len(bars) == 2
    assert int(bars[0].ts_event) == 1_735_689_600_000_000_000
    assert int(bars[1].ts_event) == 1_735_689_660_000_000_000

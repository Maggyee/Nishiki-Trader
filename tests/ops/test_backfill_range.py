from __future__ import annotations

import pytest

from apps.ops import backfill_bars


def test_run_backfill_range_is_inclusive_and_aggregates(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_run_backfill(**kwargs):
        calls.append(kwargs["date"])
        day = len(calls)
        return backfill_bars.BackfillResult(
            catalog_path=str(kwargs["catalog_path"]),
            raw_path=f"raw-{kwargs['date']}.zip",
            instrument_id="BTCUSDT.BINANCE",
            bar_type="BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
            bars_written=1440,
            first_bar_ts_ns=day * 100,
            last_bar_ts_ns=day * 100 + 99,
        )

    monkeypatch.setattr(backfill_bars, "run_backfill", fake_run_backfill)
    result = backfill_bars.run_backfill_range(
        symbol="btcusdt",
        interval="1m",
        start_date="2024-02-28",
        end_date="2024-03-01",
        raw_output_dir=tmp_path / "raw",
        catalog_path=tmp_path / "catalog",
    )

    assert calls == ["2024-02-28", "2024-02-29", "2024-03-01"]
    assert result.days_requested == 3
    assert result.days_imported == 3
    assert result.bars_written == 4320
    assert result.first_bar_ts_ns == 100
    assert result.last_bar_ts_ns == 399


def test_run_backfill_range_monthly_downloads_complete_months(monkeypatch, tmp_path):
    downloads: list[str] = []
    imports: list[str] = []

    def fake_download_monthly_klines(**kwargs):
        downloads.append(kwargs["month"])
        return tmp_path / f"{kwargs['symbol']}-{kwargs['interval']}-{kwargs['month']}.zip"

    def fake_run_backfill(**kwargs):
        imports.append(kwargs["raw_path"].name)
        month = len(imports)
        return backfill_bars.BackfillResult(
            catalog_path=str(kwargs["catalog_path"]),
            raw_path=str(kwargs["raw_path"]),
            instrument_id="ETHUSDT.BINANCE",
            bar_type="ETHUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
            bars_written=44_640 if month == 1 else 41_760,
            first_bar_ts_ns=month * 100,
            last_bar_ts_ns=month * 100 + 99,
        )

    monkeypatch.setattr(backfill_bars, "download_monthly_klines", fake_download_monthly_klines)
    monkeypatch.setattr(backfill_bars, "run_backfill", fake_run_backfill)
    result = backfill_bars.run_backfill_range(
        symbol="ethusdt",
        interval="1m",
        start_date="2024-01-01",
        end_date="2024-02-29",
        raw_output_dir=tmp_path / "raw",
        catalog_path=tmp_path / "catalog",
        archive_period="monthly",
    )

    assert downloads == ["2024-01", "2024-02"]
    assert imports == ["ETHUSDT-1m-2024-01.zip", "ETHUSDT-1m-2024-02.zip"]
    assert result.days_requested == 60
    assert result.days_imported == 60
    assert result.bars_written == 86_400
    assert result.first_bar_ts_ns == 100
    assert result.last_bar_ts_ns == 299
    assert len(result.raw_paths) == 2


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2024-01-02", "2024-01-31"),
        ("2024-01-01", "2024-02-28"),
    ],
)
def test_monthly_range_requires_complete_calendar_months(start, end, tmp_path):
    with pytest.raises(ValueError, match="complete calendar months"):
        backfill_bars.run_backfill_range(
            symbol="SOLUSDT",
            interval="1m",
            start_date=start,
            end_date=end,
            raw_output_dir=tmp_path / "raw",
            catalog_path=tmp_path / "catalog",
            archive_period="monthly",
        )


@pytest.mark.parametrize(
    ("symbol", "base_currency", "size_precision"),
    [
        ("BTCUSDT", "BTC", 6),
        ("ETHUSDT", "ETH", 5),
        ("SOLUSDT", "SOL", 3),
        ("BNBUSDT", "BNB", 3),
        ("XRPUSDT", "XRP", 1),
        ("ADAUSDT", "ADA", 1),
    ],
)
def test_binance_spot_instrument_supports_locked_universe(
    symbol, base_currency, size_precision
):
    instrument = backfill_bars._binance_spot_instrument(
        symbol=symbol,
        venue_name="BINANCE",
    )

    assert instrument.id.value == f"{symbol}.BINANCE"
    assert instrument.base_currency.code == base_currency
    assert instrument.size_precision == size_precision


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2024-02-30", "2024-03-01", "start_date"),
        ("2024-03-02", "2024-03-01", "before"),
    ],
)
def test_run_backfill_range_rejects_invalid_dates(start, end, message, tmp_path):
    with pytest.raises(ValueError, match=message):
        backfill_bars.run_backfill_range(
            symbol="BTCUSDT",
            interval="1m",
            start_date=start,
            end_date=end,
            raw_output_dir=tmp_path / "raw",
            catalog_path=tmp_path / "catalog",
        )


def test_range_cli_requires_both_dates(capsys):
    with pytest.raises(SystemExit) as exc:
        backfill_bars.main(["--download", "--start-date", "2024-01-01"])
    assert exc.value.code == 2
    assert "provide both" in capsys.readouterr().err

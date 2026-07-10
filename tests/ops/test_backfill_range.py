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

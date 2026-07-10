from __future__ import annotations

import pandas as pd

from apps.ops import daily_archive_audit


def test_daily_archive_audit_accepts_complete_aligned_data(monkeypatch, tmp_path) -> None:
    symbols = ("BNBUSDT", "XRPUSDT", "ADAUSDT")
    index = pd.date_range("2023-01-01", periods=2, freq="1D", tz="UTC")

    def fake_loader(_directory, _symbol, _frequency, *, source_interval):
        assert source_interval == "1d"
        return pd.DataFrame(
            {
                "open": [1.0, 2.0],
                "close": [2.0, 3.0],
                "quote_volume": [100.0, 200.0],
            },
            index=index,
        )

    monkeypatch.setattr(daily_archive_audit, "load_spot_aggregates", fake_loader)

    result = daily_archive_audit.build_daily_archive_audit(
        {symbol: tmp_path for symbol in symbols},
        expected_symbols=symbols,
        start_date="2023-01-01",
        end_date="2023-01-02",
    )

    assert result["aligned"] is True
    assert result["passed"] is True

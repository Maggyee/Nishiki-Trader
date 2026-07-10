from __future__ import annotations

import numpy as np
import pandas as pd

from apps.ops import feature_audit
from apps.strategies_freqtrade.research.multi_asset_rotation_signals import UNIVERSE


def test_feature_audit_accepts_complete_finite_aligned_inputs(monkeypatch, tmp_path) -> None:
    days = pd.date_range("2024-01-01", periods=2, freq="1D", tz="UTC")
    funding_index = pd.date_range("2024-01-01", periods=6, freq="8h", tz="UTC")

    def fake_spot(_directory, _symbol, _frequency):
        return pd.DataFrame(
            {
                "close": [100.0, 101.0],
                "quote_volume": [1000.0, 1100.0],
                "taker_buy_quote": [510.0, 550.0],
            },
            index=days,
        )

    def fake_funding(_directory, _symbol):
        return pd.Series(np.linspace(-0.0001, 0.0001, 6), index=funding_index)

    monkeypatch.setattr(feature_audit, "load_spot_aggregates", fake_spot)
    monkeypatch.setattr(feature_audit, "load_funding_archives", fake_funding)

    result = feature_audit.build_feature_audit(
        {symbol: tmp_path for symbol in UNIVERSE},
        {symbol: tmp_path for symbol in UNIVERSE},
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert result["alignment"]["spot_daily_aligned"] is True
    assert result["passed"] is True


def test_feature_audit_rejects_missing_funding_day(monkeypatch, tmp_path) -> None:
    days = pd.date_range("2024-01-01", periods=2, freq="1D", tz="UTC")

    monkeypatch.setattr(
        feature_audit,
        "load_spot_aggregates",
        lambda *_args: pd.DataFrame(
            {
                "close": [100.0, 101.0],
                "quote_volume": [1000.0, 1100.0],
                "taker_buy_quote": [510.0, 550.0],
            },
            index=days,
        ),
    )
    monkeypatch.setattr(
        feature_audit,
        "load_funding_archives",
        lambda *_args: pd.Series([0.0], index=days[:1]),
    )

    result = feature_audit.build_feature_audit(
        {symbol: tmp_path for symbol in UNIVERSE},
        {symbol: tmp_path for symbol in UNIVERSE},
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert result["passed"] is False
    assert "funding_days=1!=expected=2" in result["instruments"][0]["blockers"]


def test_feature_audit_allows_subminute_funding_timestamp_jitter(monkeypatch, tmp_path) -> None:
    days = pd.date_range("2024-01-01", periods=2, freq="1D", tz="UTC")
    funding_index = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-01T00:00:00Z"),
            pd.Timestamp("2024-01-01T08:00:13Z"),
            pd.Timestamp("2024-01-01T16:00:13Z"),
            pd.Timestamp("2024-01-02T00:00:13Z"),
            pd.Timestamp("2024-01-02T08:00:13Z"),
            pd.Timestamp("2024-01-02T16:00:13Z"),
        ]
    )
    monkeypatch.setattr(
        feature_audit,
        "load_spot_aggregates",
        lambda *_args: pd.DataFrame(
            {
                "close": [100.0, 101.0],
                "quote_volume": [1000.0, 1100.0],
                "taker_buy_quote": [510.0, 550.0],
            },
            index=days,
        ),
    )
    monkeypatch.setattr(
        feature_audit,
        "load_funding_archives",
        lambda *_args: pd.Series(np.zeros(6), index=funding_index),
    )

    result = feature_audit.build_feature_audit(
        {symbol: tmp_path for symbol in UNIVERSE},
        {symbol: tmp_path for symbol in UNIVERSE},
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert result["instruments"][0]["maximum_funding_gap_hours"] > 8.0
    assert result["passed"] is True

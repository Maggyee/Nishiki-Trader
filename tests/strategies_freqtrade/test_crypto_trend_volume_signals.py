from __future__ import annotations

import pandas as pd

from apps.strategies_freqtrade.research.crypto_trend_volume_signals import (
    generate_crypto_trend_volume_signals,
)


def test_generate_crypto_trend_volume_signals() -> None:
    data = [
        {
            "ts_event": 1577923200000000000,
            "available_at": "2020-01-02T00:00:00Z",
            "observation_date": "2020-01-01",
            "vintage_id": "test_vintage",
            "snapshot_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "index_value": 1.0,
        },
        {
            "ts_event": 1578009600000000000,
            "available_at": "2020-01-03T00:00:00Z",
            "observation_date": "2020-01-02",
            "vintage_id": "test_vintage",
            "snapshot_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "index_value": -1.0,
        },
    ]
    df = pd.DataFrame(data)
    df["ts_event_dt"] = pd.to_datetime(df["ts_event"], unit="ns", utc=True)
    df = df.set_index("ts_event_dt")

    events = generate_crypto_trend_volume_signals(
        df,
        candidate="btc_macd_vol_confirmed",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    assert len(events) == 2
    assert events[0].side == "buy"
    assert events[1].side == "flat"

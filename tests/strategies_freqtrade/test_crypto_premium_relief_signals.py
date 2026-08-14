from __future__ import annotations

import pandas as pd

from apps.strategies_freqtrade.research.crypto_premium_relief_signals import (
    generate_premium_relief_signals,
)


def test_generate_premium_relief_signals() -> None:
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

    events = generate_premium_relief_signals(
        df,
        candidate="btc_prem_diff5_negative",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    assert len(events) == 2
    assert events[0].side == "buy"
    assert events[1].side == "flat"

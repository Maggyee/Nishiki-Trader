from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.equity_vol_relief_signals import (
    audit_factor_frame,
    generate_equity_vol_relief_signals,
)


def _make_dummy_frame(n: int = 15) -> pd.DataFrame:
    rows = []
    base_date = pd.Timestamp("2020-01-01", tz="UTC")
    dummy_sha = "sha256:" + "0" * 64
    for i in range(n):
        obs = base_date + pd.Timedelta(days=i)
        avail = obs + pd.Timedelta(days=1)
        val = 30.0 - (i % 4) * 2.0
        rows.append(
            {
                "ts_event": avail,
                "available_at": avail.isoformat(),
                "observation_date": obs.date().isoformat(),
                "vintage_id": "test_vintage",
                "snapshot_sha256": dummy_sha,
                "index_value": val,
            }
        )
    df = pd.DataFrame.from_records(rows)
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    return df.set_index("ts_event")


def test_audit_factor_frame_valid() -> None:
    df = _make_dummy_frame()
    audited = audit_factor_frame(df)
    assert len(audited) == 15
    assert "index_value" in audited.columns


def test_generate_equity_vol_relief_signals_emits_buy_and_flat() -> None:
    df = _make_dummy_frame(25)
    events = generate_equity_vol_relief_signals(
        df,
        candidate="vxn_relief",
        start_date="2020-01-01",
        end_date="2020-01-20",
    )
    assert len(events) > 0
    assert all(e.side in {"buy", "flat"} for e in events)
    assert all(e.source == "rule_cboe_vxn_relief_v1" for e in events)


def test_generate_equity_vol_relief_signals_rejects_unknown_candidate() -> None:
    df = _make_dummy_frame()
    with pytest.raises(ValueError, match="unsupported candidate"):
        generate_equity_vol_relief_signals(df, candidate="unknown_cand")

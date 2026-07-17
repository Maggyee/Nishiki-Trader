from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research.binance_mechanism_signals import (
    BvolReliefParams,
    CurveCarryParams,
    candidate_fingerprint,
    generate_bvol_relief_signals,
    generate_curve_carry_signals,
)

SHA = "sha256:" + "a" * 64
RAW = json.dumps({"sample.zip": "sha256:" + "b" * 64}, sort_keys=True)


def _common(days: pd.DatetimeIndex, asset: str = "BTCUSDT") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset": asset,
            "data_date": days.strftime("%Y-%m-%d"),
            "retrieved_at": "2026-07-17T10:00:00Z",
            "vintage_id": [f"v-{day:%Y%m%d}" for day in days],
            "snapshot_sha256": SHA,
            "raw_file_hashes": RAW,
        }
    )


def _curve_frame() -> pd.DataFrame:
    days = pd.date_range("2021-08-01", periods=4, freq="1D", tz="UTC")
    frame = _common(days)
    frame["available_at"] = days + pd.Timedelta(days=1)
    frame["index_close"] = 100.0
    frame["front_futures_close"] = [99.0, 101.0, 101.0, 99.0]
    frame["next_futures_close"] = [99.0, 104.0, 102.0, 99.0]
    frame["front_days_to_expiry"] = [53.0, 52.0, 51.0, 50.0]
    frame["next_days_to_expiry"] = [151.0, 150.0, 149.0, 148.0]
    frame["front_contract"] = "BTCUSDT_210924"
    frame["next_contract"] = "BTCUSDT_211231"
    frame["front_expiry"] = "2021-09-24T08:00:00Z"
    frame["next_expiry"] = "2021-12-31T08:00:00Z"
    return frame


def _bvol_frame(values: list[float]) -> pd.DataFrame:
    days = pd.date_range("2023-08-01", periods=len(values), freq="1D", tz="UTC")
    frame = _common(days)
    frame["available_at"] = days + pd.Timedelta(days=2)
    frame["bvol_index"] = values
    return frame


def test_curve_carry_uses_strict_positive_steep_rule_and_state_deduplication() -> None:
    events = generate_curve_carry_signals(_curve_frame(), asset="BTCUSDT")

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.side in {"buy", "flat"} for event in events)
    assert events[0].source == "rule_binance_curve_carry_v1"
    assert events[0].metadata["contracts"]["front"] == "BTCUSDT_210924"
    assert events[0].metadata["factor"]["front_annualized_basis"] > 0
    assert events[0].features_hash == candidate_fingerprint("curve_carry")["features_hash"]


def test_curve_missing_day_forces_flat_without_forward_fill() -> None:
    frame = _curve_frame().drop(index=2).reset_index(drop=True)
    events = generate_curve_carry_signals(frame, asset="BTCUSDT")

    assert [event.side for event in events] == ["buy", "flat"]
    assert events[-1].metadata["quality_status"] == "missing_no_forward_fill"


def test_bvol_uses_five_valid_observations_strict_negative_and_missing_flat() -> None:
    values = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 95.0, 101.0]
    events = generate_bvol_relief_signals(_bvol_frame(values), asset="BTCUSDT")

    assert [event.side for event in events] == ["buy", "flat"]
    assert events[0].metadata["factor"]["bvol_change"] == -5.0
    assert events[0].ts_event == pd.Timestamp("2023-08-08T00:00:00Z").value

    missing = _bvol_frame(values).drop(index=6).reset_index(drop=True)
    missing_events = generate_bvol_relief_signals(missing, asset="BTCUSDT")
    assert [event.side for event in missing_events] == ["buy", "flat"]
    assert missing_events[-1].metadata["quality_status"] == "missing_no_forward_fill"


def test_bvol_rejects_duplicate_nonfinite_and_publication_lookahead() -> None:
    frame = _bvol_frame([100, 99, 98, 97, 96, 95])
    duplicate = pd.concat([frame, frame.iloc[[-1]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        generate_bvol_relief_signals(duplicate, asset="BTCUSDT")

    invalid = frame.copy()
    invalid["bvol_index"] = invalid["bvol_index"].astype(float)
    invalid.loc[2, "bvol_index"] = np.inf
    with pytest.raises(ValueError, match="NaN or Infinity"):
        generate_bvol_relief_signals(invalid, asset="BTCUSDT")

    lookahead = frame.copy()
    lookahead.loc[2, "available_at"] = "2023-08-04T12:00:00Z"
    with pytest.raises(ValueError, match="two-day lag"):
        generate_bvol_relief_signals(lookahead, asset="BTCUSDT")


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (CurveCarryParams, {"minimum_curve_slope": -0.01}),
        (CurveCarryParams, {"expiry_hour_utc": 0}),
        (BvolReliefParams, {"change_observations": 4}),
        (BvolReliefParams, {"historical_publication_lag_days": 1}),
    ],
)
def test_v5_parameters_cannot_be_tuned(factory, kwargs) -> None:
    with pytest.raises(ValueError):
        factory(**kwargs)

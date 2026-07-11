from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research.macro_native_mechanism_signals import (
    EquityVolReliefParams,
    MinerHashrateRecoveryParams,
    UsdWeaknessImpulseParams,
    generate_equity_vol_relief_signals,
    generate_miner_hashrate_recovery_signals,
    generate_usd_weakness_impulse_signals,
)

SNAPSHOT = "sha256:" + "c" * 64


def _base_frame(periods: int = 50) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=periods, freq="1D", tz="UTC")
    return pd.DataFrame(
        {
            "available_at": index - pd.Timedelta(hours=1),
            "vintage_id": [f"vintage-{day:%Y%m%d}" for day in index],
            "snapshot_sha256": [SNAPSHOT] * periods,
        },
        index=index,
    )


def test_hashrate_recovery_emits_state_changes_and_rejects_nonpositive() -> None:
    periods = 40
    frame = _base_frame(periods)
    values = np.full(periods, 100.0)
    values[20:] = 120.0
    values[30:] = 80.0
    frame["hashrate_eh_s"] = values

    events = generate_miner_hashrate_recovery_signals(frame)

    assert events
    assert events[0].side == "buy"
    assert events[0].source == "rule_miner_hashrate_recovery_v1"
    assert events[0].model_version == "hashrate7-30-positive-1d-v1"
    assert events[0].metadata["point_in_time"] is True
    assert "hashrate_spread" in events[0].metadata["inputs"]
    assert all(event.side in {"buy", "flat"} for event in events)

    invalid = frame.copy()
    invalid.loc[invalid.index[0], "hashrate_eh_s"] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        generate_miner_hashrate_recovery_signals(invalid)


def test_usd_weakness_uses_negative_return_only() -> None:
    periods = 30
    frame = _base_frame(periods)
    closes = np.linspace(100.0, 110.0, periods)
    closes[21:] = np.linspace(110.0, 95.0, periods - 21)
    frame["dxy_close"] = closes

    events = generate_usd_weakness_impulse_signals(frame)

    assert events
    assert events[0].side == "buy"
    assert events[0].source == "rule_usd_weakness_v1"
    assert events[0].model_version == "dxy20d-negative-1d-v1"
    assert events[0].metadata["inputs"]["dxy_return_20d"] < 0.0
    assert all(event.side in {"buy", "flat"} for event in events)


def test_equity_vol_relief_is_causal_and_deterministic() -> None:
    periods = 20
    frame = _base_frame(periods)
    closes = np.linspace(30.0, 20.0, periods)
    closes[12:] = np.linspace(20.0, 35.0, periods - 12)
    frame["vix_close"] = closes

    first = generate_equity_vol_relief_signals(frame, start_date="2020-01-08")
    second = generate_equity_vol_relief_signals(frame, start_date="2020-01-08")

    assert first
    assert [event.model_dump_json() for event in first] == [
        event.model_dump_json() for event in second
    ]
    assert all(event.side in {"buy", "flat"} for event in first)
    assert first[0].source == "rule_equity_vol_relief_v1"
    assert first[0].model_version == "vix5d-negative-1d-v1"

    cutoff = frame.index[10]
    changed = frame.copy()
    changed.loc[changed.index > cutoff, "vix_close"] = 50.0
    mutated = generate_equity_vol_relief_signals(changed, start_date="2020-01-08")
    assert [event.model_dump() for event in first if event.ts_event <= cutoff.value] == [
        event.model_dump() for event in mutated if event.ts_event <= cutoff.value
    ]


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (MinerHashrateRecoveryParams, {"short_hashrate_days": 6}),
        (UsdWeaknessImpulseParams, {"maximum_dxy_return": -0.01}),
        (EquityVolReliefParams, {"vix_change_days": 4}),
        (EquityVolReliefParams, {"confidence": 0.8}),
    ],
)
def test_pre_registered_parameters_cannot_be_tuned(factory, kwargs) -> None:
    with pytest.raises(ValueError):
        factory(**kwargs)

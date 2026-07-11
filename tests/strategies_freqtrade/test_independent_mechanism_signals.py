from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    FuturesBasisCurveParams,
    OptionRiskPremiumParams,
    StablecoinLiquidityParams,
    audit_point_in_time_frame,
    generate_futures_basis_curve_signals,
    generate_option_risk_premium_signals,
    generate_stablecoin_liquidity_signals,
)

SNAPSHOT = "sha256:" + "a" * 64
SPEC = "sha256:" + "b" * 64


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


def _option_frame(values: list[float]) -> pd.DataFrame:
    frame = _base_frame(len(values))
    expected = np.asarray(values, dtype=float)
    frame["expected_excess_return_30d"] = expected
    frame["intercept_contribution"] = expected * 0.10
    frame["variance_contribution"] = expected * 0.20
    frame["higher_moment_contribution"] = expected * 0.40
    frame["vol_of_vol_contribution"] = expected * 0.30
    frame["replication_spec_hash"] = SPEC
    return frame


def test_point_in_time_audit_rejects_lookahead_gap_duplicate_and_nan() -> None:
    frame = _base_frame(4)
    frame["factor"] = [1.0, 2.0, 3.0, 4.0]

    lookahead = frame.copy()
    lookahead.loc[lookahead.index[2], "available_at"] = lookahead.index[2] + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="lookahead"):
        audit_point_in_time_frame(lookahead, required_numeric={"factor"})

    with pytest.raises(ValueError, match="every daily"):
        audit_point_in_time_frame(frame.drop(frame.index[1]), required_numeric={"factor"})

    duplicate = pd.concat([frame, frame.iloc[[-1]]])
    with pytest.raises(ValueError, match="unique"):
        audit_point_in_time_frame(duplicate, required_numeric={"factor"})

    invalid = frame.copy()
    invalid.loc[invalid.index[0], "factor"] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        audit_point_in_time_frame(invalid, required_numeric={"factor"})


def test_option_candidate_emits_state_changes_and_auditable_decomposition() -> None:
    events = generate_option_risk_premium_signals(_option_frame([-0.01, 0.02, 0.03, 0.0, -0.01]))

    assert [event.side for event in events] == ["buy", "flat"]
    assert events[0].source == "rule_option_risk_premium_v1"
    assert events[0].model_version == "structural-rn-excessret30d-sign-v1"
    assert events[0].metadata["inputs"]["higher_moment_contribution"] == 0.008
    assert events[0].metadata["point_in_time"] is True
    assert events[0].features_hash == events[1].features_hash

    invalid = _option_frame([0.01, 0.02])
    invalid.loc[invalid.index[0], "variance_contribution"] += 0.001
    with pytest.raises(ValueError, match="decomposition"):
        generate_option_risk_premium_signals(invalid)


def test_basis_candidate_uses_fixed_expiry_curve_and_never_shorts() -> None:
    frame = _base_frame(4)
    frame["spot_price"] = 100.0
    frame["front_days_to_expiry"] = 30.0
    frame["next_days_to_expiry"] = 90.0
    frame["front_futures_price"] = [99.0, 101.0, 101.0, 99.0]
    frame["next_futures_price"] = [99.0, 104.0, 102.0, 99.0]

    events = generate_futures_basis_curve_signals(frame)

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.side in {"buy", "flat"} for event in events)
    assert events[0].metadata["inputs"]["front_annualized_basis"] > 0.0
    assert events[0].metadata["inputs"]["curve_slope"] >= 0.0

    invalid = frame.copy()
    invalid["next_days_to_expiry"] = invalid["front_days_to_expiry"]
    with pytest.raises(ValueError, match="front < next"):
        generate_futures_basis_curve_signals(invalid)


def test_stablecoin_candidate_is_causal_and_future_mutation_does_not_change_past() -> None:
    periods = 70
    frame = _base_frame(periods)
    frame["stablecoin_supply_total"] = np.linspace(100.0, 170.0, periods)
    frame["stablecoin_transfer_volume"] = np.linspace(10.0, 30.0, periods)

    original = generate_stablecoin_liquidity_signals(frame)
    cutoff = frame.index[55]
    changed = frame.copy()
    changed.loc[changed.index > cutoff, "stablecoin_supply_total"] = 1.0
    changed.loc[changed.index > cutoff, "stablecoin_transfer_volume"] = 1.0
    mutated = generate_stablecoin_liquidity_signals(changed)

    assert original
    assert original[0].side == "buy"
    assert all(event.side in {"buy", "flat"} for event in original)
    assert [event.model_dump() for event in original if event.ts_event <= cutoff.value] == [
        event.model_dump() for event in mutated if event.ts_event <= cutoff.value
    ]


def test_generators_are_deterministic_and_window_does_not_emit_pre_window_transition() -> None:
    frame = _option_frame([0.02, 0.02, -0.01, 0.02])

    first = generate_option_risk_premium_signals(frame, start_date="2020-01-02")
    second = generate_option_risk_premium_signals(frame, start_date="2020-01-02")

    assert [event.model_dump_json() for event in first] == [
        event.model_dump_json() for event in second
    ]
    assert [event.side for event in first] == ["buy", "flat", "buy"]


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (OptionRiskPremiumParams, {"expected_excess_return_floor": 0.01}),
        (FuturesBasisCurveParams, {"minimum_curve_slope": -0.01}),
        (StablecoinLiquidityParams, {"supply_change_days": 29}),
        (StablecoinLiquidityParams, {"confidence": 0.8}),
    ],
)
def test_pre_registered_parameters_cannot_be_tuned(factory, kwargs) -> None:
    with pytest.raises(ValueError):
        factory(**kwargs)

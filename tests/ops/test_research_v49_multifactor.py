"""Offline tests for Research Protocol v49 (no factor snapshots, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.ops.research_protocol_v49 import (
    FACTOR_SOURCES,
    GATES_V2,
    WINDOWS,
    contract_sha256,
    validate_contract,
)
from apps.ops.research_v49_multifactor import (
    _fit_ridge,
    _predict_ridge,
    apply_gates,
    bootstrap_p_value,
    build_features,
    build_label,
    build_panel,
    evaluate_states,
    run_walkforward,
)


def _daily_index(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="D", tz="UTC")


def test_contract_is_valid_and_fingerprint_is_stable() -> None:
    assert validate_contract() == []
    assert contract_sha256() == contract_sha256()
    assert len(FACTOR_SOURCES) == 17
    assert WINDOWS["development_oos"][1] < WINDOWS["confirmation"][0]
    assert GATES_V2["confirmation"]["bootstrap_p_value_max"] == 0.10


def test_ridge_recovers_linear_relationship() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(size=(500, 3))
    true_coef = np.array([0.5, -0.25, 0.0])
    y = x @ true_coef + 0.1 + rng.normal(scale=0.01, size=500)
    coef = _fit_ridge(x, y, alpha=1.0)
    predictions = _predict_ridge(coef, x)
    assert np.corrcoef(predictions, y)[0, 1] > 0.99
    assert coef[-1] == pytest.approx(0.1, abs=0.02)  # unpenalized intercept


def test_build_panel_respects_availability_and_ffill_limit() -> None:
    dates = _daily_index("2020-01-01", "2020-01-31")
    closes = pd.Series(100.0, index=dates)
    stamps = pd.DatetimeIndex(
        [pd.Timestamp("2020-01-05 12:00", tz="UTC"), pd.Timestamp("2020-01-20 12:00", tz="UTC")]
    )
    factor = pd.Series([1.0, 2.0], index=stamps, name="f")
    panel = build_panel(closes, {"f": factor})
    # not yet available before its stamp
    assert np.isnan(panel.loc[pd.Timestamp("2020-01-04", tz="UTC"), "f"])
    # available on the stamp's panel day and forward-filled within 7 days
    assert panel.loc[pd.Timestamp("2020-01-05", tz="UTC"), "f"] == 1.0
    assert panel.loc[pd.Timestamp("2020-01-11", tz="UTC"), "f"] == 1.0
    # stale beyond the 7-day forward-fill limit
    assert np.isnan(panel.loc[pd.Timestamp("2020-01-15", tz="UTC"), "f"])
    assert panel.loc[pd.Timestamp("2020-01-20", tz="UTC"), "f"] == 2.0


def _synthetic_inputs(seed: int = 5) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    dates = _daily_index("2020-01-01", "2021-12-31")
    rng = np.random.default_rng(seed)
    closes = pd.Series(10_000 + np.cumsum(rng.normal(0, 25, len(dates))), index=dates).clip(1000)
    panel = pd.DataFrame(
        {f"f{i}": rng.normal(size=len(dates)).cumsum() for i in range(17)}, index=dates
    )
    features = build_features(closes, panel)
    label = build_label(closes)
    return closes, features, label


def test_walkforward_predictions_do_not_use_future_labels() -> None:
    closes, features, label = _synthetic_inputs()
    preds = run_walkforward(
        features, label, alpha=100.0, predict_start="2020-07-01", predict_end="2020-09-30"
    )
    # corrupt labels inside the prediction window; earlier predictions must not move
    label_corrupt = label.copy()
    corrupt_mask = label_corrupt.index >= pd.Timestamp("2020-08-01", tz="UTC")
    label_corrupt.loc[corrupt_mask] = label_corrupt.loc[corrupt_mask] + 1.0
    preds_corrupt = run_walkforward(
        features, label_corrupt, alpha=100.0, predict_start="2020-07-01", predict_end="2020-09-30"
    )
    july = preds.index < pd.Timestamp("2020-08-01", tz="UTC")
    august = (preds.index >= pd.Timestamp("2020-08-01", tz="UTC")) & (
        preds.index < pd.Timestamp("2020-09-01", tz="UTC")
    )
    assert np.allclose(preds[july], preds_corrupt[july])
    # July+August labels feed September's fit, so September must move; August
    # predictions were fitted on data through July only and must not.
    assert np.allclose(preds[august], preds_corrupt[august])
    assert not np.allclose(preds[~(july | august)], preds_corrupt[~(july | august)])


def test_walkforward_refuses_insufficient_training_history() -> None:
    closes, features, label = _synthetic_inputs()
    with pytest.raises(ValueError, match="insufficient training months"):
        run_walkforward(
            features, label, alpha=10.0, predict_start="2020-03-01", predict_end="2020-03-31"
        )


def test_evaluate_states_and_gates_round_trip() -> None:
    dates = _daily_index("2022-01-01", "2022-12-31")
    closes = pd.Series(np.linspace(10_000, 12_000, len(dates)), index=dates)
    states = np.zeros(len(dates), dtype=bool)
    states[10:100] = True
    states[150:260] = True
    candidate = evaluate_states(closes, states)
    assert candidate["closed_positions"] == 2
    assert 0.0 < candidate["time_in_market_fraction"] < 1.0
    assert candidate["mean_holding_days"] == pytest.approx(100.0, rel=0.05)
    gates = apply_gates("confirmation", candidate, bh_pnl=2.0, p_value=0.5)
    assert gates["checks"]["bootstrap_p"] is False
    assert gates["checks"]["activity_floor"] is False  # 2 positions < 60
    assert gates["pass_gates"] is False


def test_bootstrap_p_value_is_deterministic_and_bounded() -> None:
    dates = _daily_index("2022-01-01", "2022-06-30")
    rng = np.random.default_rng(3)
    closes = pd.Series(10_000 + np.cumsum(rng.normal(0, 20, len(dates))), index=dates).clip(1000)
    candidate = {
        "base_net_pnl": 0.5,
        "time_in_market_fraction": 0.5,
        "mean_holding_days": 5.0,
    }
    p1 = bootstrap_p_value(closes, candidate, n_trials=300, seed=7)
    p2 = bootstrap_p_value(closes, candidate, n_trials=300, seed=7)
    assert p1 == p2
    assert 0.0 < p1 <= 1.0
    # an absurdly high candidate PnL should be nearly impossible under the null
    lucky = dict(candidate, base_net_pnl=1e9)
    assert bootstrap_p_value(closes, lucky, n_trials=300, seed=7) == pytest.approx(1 / 301)

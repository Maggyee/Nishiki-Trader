"""Synthetic flow thresholds, calendar holds and causality checks for v55."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research import flow_imbalance


def _frames(
    shares: list[float], close: list[float] | None = None, oi: list[float] | None = None
) -> dict[str, dict[str, pd.DataFrame]]:
    index = pd.date_range("2024-01-01", periods=len(shares), tz="UTC")
    prices = pd.DataFrame(
        {
            "close": close if close is not None else 100.0,
            "volume": 100.0,
            "taker_buy_volume": np.array(shares) * 100.0,
        },
        index=index,
    )
    frames = {flow_imbalance.PRICE_DATASET: {"BTCUSDT": prices}}
    if oi is not None:
        frames["um_metrics_daily"] = {"BTCUSDT": pd.DataFrame({"open_interest": oi}, index=index)}
    return frames


def _taker(frames: dict, **params) -> pd.DataFrame:
    return flow_imbalance.target_weights(
        frames, "taker_continuation", {"baseline_days": 3, "z_threshold": 1.0} | params
    )


def _squeeze(frames: dict, **params) -> pd.DataFrame:
    return flow_imbalance.target_weights(
        frames, "oi_squeeze", {"lookback_days": 3, "oi_change_min": 0.05, "hold_days": 3} | params
    )


@pytest.mark.parametrize(("share", "expected"), [(0.9, 1.0), (0.1, -1.0), (0.5, 0.0)])
def test_taker_thresholds_use_previous_rows_only(share: float, expected: float) -> None:
    # Prior mean=.5, sample std=.1. Including today's extreme changes the decision.
    frames = _frames([0.4, 0.5, 0.6, share])
    weights = _taker(frames, z_threshold=2.0)
    assert flow_imbalance.PRICE_DATASET == "um_klines_1d"
    assert weights["BTCUSDT"].tolist() == [0.0, 0.0, 0.0, expected]
    assert weights["BTCUSDT"].dtype == float
    assert str(weights.index.tz) == "UTC"


@pytest.mark.parametrize("share", [0.25, 0.75])
def test_taker_threshold_equality_is_flat_and_std_is_sample(share: float) -> None:
    # The previous three shares have mean=.5 and sample std=.25 exactly.
    weights = _taker(_frames([0.25, 0.5, 0.75, share]))
    assert weights.iloc[-1, 0] == 0.0


def test_taker_is_daily_without_holding() -> None:
    weights = _taker(_frames([0.4, 0.5, 0.6, 0.9, 0.1, 0.5]))
    assert weights["BTCUSDT"].tolist() == [0.0, 0.0, 0.0, 1.0, -1.0, 0.0]


def test_frozen_taker_baseline_requires_ninety_prior_rows() -> None:
    weights = _taker(_frames([0.25, 0.75] * 45 + [1.0]), baseline_days=90)
    assert (weights.iloc[:90] == 0.0).all().all()
    assert weights.iloc[90, 0] == 1.0


def test_taker_zero_std_and_missing_share_are_flat() -> None:
    assert (_taker(_frames([0.5] * 5 + [0.9])) == 0.0).all().all()
    frames = _frames([0.4, 0.5, 0.6, 0.9, 0.1, 0.9, 0.1])
    prices = frames[flow_imbalance.PRICE_DATASET]["BTCUSDT"]
    prices.iloc[3, prices.columns.get_loc("volume")] = 0.0
    weights = _taker(frames)
    assert (weights == 0.0).all().all()
    assert not weights.isna().any().any()


def test_taker_missing_calendar_day_still_uses_previous_observed_rows() -> None:
    frames = _frames([0.4, 0.5, 0.0, 0.6, 0.9])
    prices = frames[flow_imbalance.PRICE_DATASET]["BTCUSDT"]
    frames[flow_imbalance.PRICE_DATASET]["BTCUSDT"] = prices.drop(prices.index[2])
    weights = _taker(frames)
    assert weights["BTCUSDT"].tolist() == [0.0, 0.0, 0.0, 1.0]


def test_squeeze_holds_ignore_triggers_then_allow_immediate_reentry() -> None:
    frames = _frames(
        [0.5] * 11,
        close=[100, 100, 100, 90, 110, 120, 110, 130, 130, 100, 130],
        oi=[100, 100, 100, 110, 120, 130, 130, 140, 150, 150, 140],
    )
    weights = _squeeze(frames)
    # Long day 3; opposite triggers on days 4/5 must neither reverse nor extend it.
    # Short day 6; long on day 9 after that hold expires, and no trigger on day 10.
    assert weights["BTCUSDT"].tolist() == [0.0] * 3 + [1.0] * 3 + [-1.0] * 3 + [1.0] * 2
    assert (weights.abs().sum(axis=1) <= 1.0).all()


def test_squeeze_expires_without_another_trigger() -> None:
    frames = _frames(
        [0.5] * 8,
        close=[100, 100, 100, 90, 100, 100, 90, 100],
        oi=[100, 100, 100, 110, 100, 100, 110, 100],
    )
    assert _squeeze(frames)["BTCUSDT"].tolist() == [0.0] * 3 + [1.0] * 3 + [0.0] * 2


@pytest.mark.parametrize("close", [[100, 100, 100, 100], [100, 100, 100, 90]])
def test_squeeze_requires_strict_oi_increase_and_nonzero_price_move(close: list[float]) -> None:
    # 25% is exactly representable, so equality exercises the strict boundary.
    frames = _frames([0.5] * 4, close=close, oi=[100, 100, 100, 125])
    assert (_squeeze(frames, oi_change_min=0.25) == 0.0).all().all()
    if close[-1] == 100:
        assert (_squeeze(frames) == 0.0).all().all()


@pytest.mark.parametrize("dataset", ["um_klines_1d", "um_metrics_daily"])
def test_squeeze_missing_endpoint_cannot_use_previous_observation(dataset: str) -> None:
    frames = _frames(
        [0.5] * 6,
        close=[100, 100, 100, 90, 90, 90],
        oi=[100, 100, 100, 100, 120, 120],
    )
    original = frames[dataset]["BTCUSDT"]
    frames[dataset]["BTCUSDT"] = original.drop(original.index[1])
    weights = _squeeze(frames)
    assert weights.iloc[:5, 0].tolist() == [0.0] * 5
    assert weights.iloc[5, 0] == 1.0


def test_squeeze_missing_day_still_consumes_one_day_of_hold() -> None:
    frames = _frames(
        [0.5] * 8,
        close=[100, 100, 100, 90, 110, 120, 110, 130],
        oi=[100, 100, 100, 110, 120, 130, 130, 140],
    )
    index = frames[flow_imbalance.PRICE_DATASET]["BTCUSDT"].index
    for symbols in frames.values():
        symbols["BTCUSDT"] = symbols["BTCUSDT"].drop(index[4])
    weights = _squeeze(frames)
    pd.testing.assert_index_equal(weights.index, index)
    assert weights["BTCUSDT"].tolist() == [0.0] * 3 + [1.0] * 3 + [-1.0] * 2


@pytest.mark.parametrize("candidate", ["taker_continuation", "oi_squeeze"])
def test_future_changes_and_truncation_cannot_change_past_targets(candidate: str) -> None:
    rng = np.random.default_rng(55)
    frames = _frames(
        rng.uniform(0.1, 0.9, 80).tolist(),
        close=(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 80)))).tolist(),
        oi=(100 * np.exp(np.cumsum(rng.normal(0, 0.1, 80)))).tolist(),
    )
    original = {
        dataset: {s: f.copy(deep=True) for s, f in symbols.items()}
        for dataset, symbols in frames.items()
    }
    run = _taker if candidate == "taker_continuation" else _squeeze
    weights = run(frames)
    cutoff = weights.index[43]
    changed = {
        dataset: {s: f.copy(deep=True) for s, f in symbols.items()}
        for dataset, symbols in frames.items()
    }
    for symbols in changed.values():
        frame = symbols["BTCUSDT"]
        frame.loc[frame.index > cutoff, :] *= np.arange(2.0, 38.0)[:, None]
        if "taker_buy_volume" in frame:
            frame.loc[frame.index > cutoff, "taker_buy_volume"] = 0.0
    pd.testing.assert_frame_equal(weights.loc[:cutoff], run(changed).loc[:cutoff])
    truncated = {
        dataset: {s: f.loc[:cutoff] for s, f in symbols.items()}
        for dataset, symbols in frames.items()
    }
    pd.testing.assert_frame_equal(weights.loc[:cutoff], run(truncated))
    for dataset, symbols in frames.items():
        for symbol, frame in symbols.items():
            pd.testing.assert_frame_equal(frame, original[dataset][symbol])


@pytest.mark.parametrize("candidate", ["taker_continuation", "oi_squeeze"])
def test_empty_history_is_flat(candidate: str) -> None:
    frames = _frames([], close=[], oi=[])
    run = _taker if candidate == "taker_continuation" else _squeeze
    weights = run(frames)
    assert weights.empty
    assert weights["BTCUSDT"].dtype == float
    assert str(weights.index.tz) == "UTC"


def test_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError, match="Unknown candidate"):
        flow_imbalance.target_weights({}, "unknown", {})

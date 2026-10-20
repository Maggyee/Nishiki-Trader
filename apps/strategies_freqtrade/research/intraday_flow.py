"""Minute targets for the frozen v60 cascade and v61 laggard rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_DATASET: str = "spot_klines_1m"


def target_weights(
    frames: dict[str, dict[str, pd.DataFrame]], candidate: str, params: dict
) -> pd.DataFrame:
    """Decide at each minute's close, using data available by that close."""
    if candidate == "laggard_catchup":
        return _laggard_catchup(frames[PRICE_DATASET], params)
    if candidate != "cascade_rebound":
        raise ValueError(f"Unknown candidate: {candidate}")

    held = {
        symbol: _symbol_weights(prices, frames["um_metrics_5m"].get(symbol), params)
        for symbol, prices in frames[PRICE_DATASET].items()
    }
    if not held:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
    weights = pd.DataFrame(held).sort_index().fillna(0.0)
    scale = (1.0 / weights.abs().sum(axis=1)).clip(upper=1.0).fillna(1.0)
    return weights.mul(scale, axis=0)


def _oi_asof(oi: pd.Series, times: pd.DatetimeIndex, staleness: pd.Timedelta) -> np.ndarray:
    # Reindex fills absent timestamps, preserving a missing value at the last
    # actual observation rather than falling back to an earlier valid value.
    values = oi.reindex(times, method="ffill", tolerance=staleness).to_numpy(dtype=float)
    return np.where(values > 0.0, values, np.nan)


def _symbol_weights(prices: pd.DataFrame, metrics: pd.DataFrame | None, params: dict) -> pd.Series:
    if prices.empty:
        return pd.Series(index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
    grid = pd.date_range(prices.index.min(), prices.index.max(), freq="min", tz="UTC")
    weight = np.zeros(len(grid))
    if metrics is None or metrics.empty:
        return pd.Series(weight, index=grid)

    close = prices["close"].reindex(grid)
    r60 = (close / close.shift(params["return_window_minutes"]) - 1.0).to_numpy()
    oi = metrics["open_interest"].sort_index()
    decision_times = grid + pd.Timedelta(minutes=1)
    staleness = pd.Timedelta(minutes=params["oi_max_staleness_minutes"])
    current = _oi_asof(oi, decision_times, staleness)
    previous = _oi_asof(
        oi, decision_times - pd.Timedelta(minutes=params["oi_window_minutes"]), staleness
    )
    doi60 = current / previous - 1.0

    days = pd.date_range(grid[0].normalize(), grid[-1].normalize(), freq="D")
    starts = grid.searchsorted(days)
    ends = np.r_[starts[1:], len(grid)]
    lefts = grid.searchsorted(days - pd.Timedelta(days=params["baseline_days"]))
    required = params["min_baseline_fraction"] * params["baseline_days"] * 1440
    trigger = np.zeros(len(grid), dtype=bool)
    for left, start, end in zip(lefts, starts, ends, strict=True):
        past_r = r60[left:start]
        past_r = past_r[np.isfinite(past_r)]
        past_oi = doi60[left:start]
        past_oi = past_oi[np.isfinite(past_oi)]
        if not len(past_r) or not len(past_oi) or min(len(past_r), len(past_oi)) < required:
            continue
        r_threshold = np.quantile(past_r, params["quantile"], method="linear")
        oi_threshold = np.quantile(past_oi, params["quantile"], method="linear")
        trigger[start:end] = (
            np.isfinite(r60[start:end])
            & np.isfinite(doi60[start:end])
            & (r60[start:end] <= r_threshold)
            & (doi60[start:end] <= oi_threshold)
        )

    next_free = 0
    for row in np.flatnonzero(trigger):
        if row >= next_free:
            next_free = row + params["hold_minutes"]
            weight[row:next_free] = params["weight_per_symbol"]
    return pd.Series(weight, index=grid)


def _laggard_catchup(prices: dict[str, pd.DataFrame], params: dict) -> pd.DataFrame:
    btc = prices["BTCUSDT"]
    columns = list(prices)
    if btc.empty:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"), columns=columns, dtype=float)
    grid = pd.date_range(btc.index.min(), btc.index.max(), freq="min", tz="UTC")
    returns = {}
    for symbol, frame in prices.items():
        close = frame["close"].reindex(grid)
        returns[symbol] = (close / close.shift(params["return_window_minutes"]) - 1.0).to_numpy()

    btc_returns = returns["BTCUSDT"]
    days = pd.date_range(grid[0].normalize(), grid[-1].normalize(), freq="D")
    starts = grid.searchsorted(days)
    ends = np.r_[starts[1:], len(grid)]
    lefts = grid.searchsorted(days - pd.Timedelta(days=params["baseline_days"]))
    required = params["min_baseline_fraction"] * params["baseline_days"] * 1440
    trigger = np.zeros(len(grid), dtype=bool)
    for left, start, end in zip(lefts, starts, ends, strict=True):
        past = btc_returns[left:start]
        past = past[np.isfinite(past)]
        if not len(past) or len(past) < required:
            continue
        threshold = np.quantile(past, params["quantile"], method="linear")
        trigger[start:end] = np.isfinite(btc_returns[start:end]) & (
            btc_returns[start:end] >= threshold
        )

    # Stable sorting of alphabetically ordered symbols resolves equal returns.
    symbols = sorted(symbol for symbol in prices if symbol != "BTCUSDT")
    leg_columns = np.array([columns.index(symbol) for symbol in symbols], dtype=int)
    weight = np.zeros((len(grid), len(columns)))
    next_free = 0
    for row in np.flatnonzero(trigger):
        if row < next_free:
            continue
        values = np.array([returns[symbol][row] for symbol in symbols])
        finite = np.flatnonzero(np.isfinite(values))
        if len(finite) < params["min_universe"]:
            continue
        chosen = finite[np.argsort(values[finite], kind="stable")[: params["legs"]]]
        next_free = row + params["hold_minutes"]
        weight[row:next_free, leg_columns[chosen]] = params["gross_weight"] / params["legs"]
    return pd.DataFrame(weight, index=grid, columns=columns)

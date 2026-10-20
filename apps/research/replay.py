"""Deterministic constant-notional replay of target weights.

Row ``t`` of the weights is decided after bar ``t``'s close and earns bar
``t+1``'s return by default. The book starts flat before the window, pays costs
on every weight change (charged on the bar the new position starts) and is
closed at the window's last close.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


def window_arrays(
    weights: pd.DataFrame,
    closes: pd.DataFrame,
    start: str,
    end: str,
    funding: pd.DataFrame | None = None,
    *,
    bar: str = "1D",
    lag: int = 0,
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Bars in the window, held weights (bars x assets) and bar returns.

    Settlements belong to the bar ending at or after their timestamp; longs
    pay positive funding and shorts receive it.
    """
    if lag < 0:
        raise ValueError("execution lag must be nonnegative")
    closes = closes[weights.columns].sort_index()
    calendar = pd.date_range(closes.index.min(), closes.index.max(), freq=bar, tz="UTC")
    filled = closes.reindex(calendar).ffill()
    returns = filled.pct_change(fill_method=None).fillna(0.0)
    if funding is not None:
        keys = (funding.index - pd.Timedelta(milliseconds=1)).floor(bar)
        bucketed = funding.groupby(keys).sum()
        returns = returns - bucketed.reindex(index=calendar, columns=weights.columns).fillna(0.0)
    decided = weights.reindex(calendar).ffill().fillna(0.0)
    held = decided.shift(1 + lag).fillna(0.0)
    days = calendar[
        (calendar >= pd.Timestamp(start, tz="UTC"))
        & (calendar < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1))
    ]
    if len(days) == 0:
        raise ValueError(f"no data in window {start}..{end}")
    return days, held.loc[days].to_numpy(), returns.loc[days].to_numpy()


def bar_pnl(held: np.ndarray, returns: np.ndarray, notional: float, cost: float) -> np.ndarray:
    """Net bar PnL (USDT); cost is a fraction per unit of traded weight."""
    previous = np.vstack([np.zeros((1, held.shape[1])), held[:-1]])
    traded = np.abs(held - previous)
    traded[-1] += np.abs(held[-1])  # close the book at the window's last close
    return notional * ((held * returns).sum(axis=1) - cost * traded.sum(axis=1))


def _episodes(held: np.ndarray, returns: np.ndarray, notional: float, cost: float) -> list[float]:
    """Base-cost PnL of each same-sign holding run per asset.

    Exit costs go to the closing run and entry costs to the new one, so the
    runs sum exactly to the replay's base PnL.
    """
    pnls: list[float] = []
    for asset in range(held.shape[1]):
        weight = np.ascontiguousarray(held[:, asset])
        if not len(weight):
            continue
        signs = np.sign(weight)
        starts = np.flatnonzero((weight != 0.0) & (signs != np.r_[0.0, signs[:-1]]))
        ends = np.flatnonzero((weight != 0.0) & (signs != np.r_[signs[1:], 0.0])) + 1
        terms = np.empty((len(weight), 2))
        terms[:, 0] = -cost * np.abs(weight - np.r_[0.0, weight[:-1]]) * notional
        terms[starts, 0] = -cost * np.abs(weight[starts]) * notional
        terms[:, 1] = notional * weight * returns[:, asset]
        for start, end in zip(starts, ends, strict=True):
            # Accumulate in the original cost-then-return order, without a
            # Python loop per bar, to preserve daily replay rounding exactly.
            pnl = np.add.accumulate(terms[start:end].ravel())[-1]
            pnls.append(float(pnl - cost * abs(weight[end - 1]) * notional))
    return pnls


def run(
    weights: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    start: str,
    end: str,
    notional: float,
    costs_bps: dict[str, float],
    funding: pd.DataFrame | None = None,
    bar: str = "1D",
    lag: int = 0,
) -> dict[str, object]:
    """Replay one candidate over one window and return the gate inputs."""
    days, held, returns = window_arrays(weights, closes, start, end, funding, bar=bar, lag=lag)
    base_cost = costs_bps["base"] / 1e4
    base = bar_pnl(held, returns, notional, base_cost)
    stress = bar_pnl(held, returns, notional, costs_bps["stress"] / 1e4)
    gross = bar_pnl(held, returns, notional, 0.0)
    long_only = bar_pnl(np.clip(held, 0.0, None), returns, notional, base_cost)
    series = pd.Series(base, index=days)
    monthly = series.groupby(days.tz_localize(None).to_period("M")).sum()
    yearly = series.groupby(days.year).sum()
    episodes = _episodes(held, returns, notional, base_cost)
    equity = np.cumsum(base)
    drawdown = float((np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:] - equity).max())
    benchmark = float(notional * (held.mean(axis=0) * returns.sum(axis=0)).sum())
    return {
        "bars": len(days),
        "days": int(days.normalize().nunique()),
        "active_days": int(days[np.abs(held).sum(axis=1) > 0].normalize().nunique()),
        "gross_net_pnl": float(gross.sum()),
        "base_net_pnl": float(base.sum()),
        "stress_net_pnl": float(stress.sum()),
        "base_return_pct": float(100 * base.sum() / notional),
        "positive_months": int((monthly > 0).sum()),
        "months_total": int(len(monthly)),
        "positive_years": int((yearly > 0).sum()),
        "years_total": int(len(yearly)),
        "closed_positions": len(episodes),
        "leave_best_base_net_pnl": float(base.sum() - max(episodes, default=0.0)),
        "benchmark_pnl": benchmark,
        "time_in_market": float((np.abs(held).sum(axis=1) > 0).mean()),
        "gross_exposure_mean": float(np.abs(held).sum(axis=1).mean()),
        "net_exposure_mean": float(held.sum(axis=1).mean()),
        "max_drawdown_usdt": drawdown,
        "max_drawdown_pct": float(100 * drawdown / notional),
        "long_only_leg_base_net_pnl": float(long_only.sum()),
        "base_pnl_sha256": hashlib.sha256(np.round(base, 8).tobytes()).hexdigest(),
    }

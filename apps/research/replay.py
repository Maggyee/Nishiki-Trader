"""Deterministic constant-notional replay of target weights.

Row ``t`` of the weights is decided after day ``t``'s close and earns day
``t+1``'s return. The book starts flat the day before the window, pays costs
on every weight change (charged on the day the new position starts) and is
closed at the window's last close.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


def window_arrays(
    weights: pd.DataFrame, closes: pd.DataFrame, start: str, end: str
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Days in the window, held weights (days x assets) and daily returns."""
    closes = closes[weights.columns].sort_index()
    calendar = pd.date_range(closes.index.min(), closes.index.max(), freq="D", tz="UTC")
    filled = closes.reindex(calendar).ffill()
    returns = filled.pct_change(fill_method=None).fillna(0.0)
    decided = weights.reindex(calendar).ffill().fillna(0.0)
    held = decided.shift(1).fillna(0.0)  # weight decided at t-1 earns day t
    days = calendar[
        (calendar >= pd.Timestamp(start, tz="UTC")) & (calendar <= pd.Timestamp(end, tz="UTC"))
    ]
    if len(days) == 0:
        raise ValueError(f"no data in window {start}..{end}")
    return days, held.loc[days].to_numpy(), returns.loc[days].to_numpy()


def daily_pnl(held: np.ndarray, returns: np.ndarray, notional: float, cost: float) -> np.ndarray:
    """Net daily PnL (USDT) for held weights; cost is a fraction per unit of traded weight."""
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
        current: float | None = None
        previous = 0.0
        for day in range(held.shape[0]):
            weight = float(held[day, asset])
            if np.sign(weight) != np.sign(previous):
                if current is not None:
                    pnls.append(current - cost * abs(previous) * notional)
                current = -cost * abs(weight) * notional if weight != 0 else None
            elif current is not None:
                current -= cost * abs(weight - previous) * notional
            if current is not None:
                current += notional * weight * float(returns[day, asset])
            previous = weight
        if current is not None:
            pnls.append(current - cost * abs(previous) * notional)
    return pnls


def run(
    weights: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    start: str,
    end: str,
    notional: float,
    costs_bps: dict[str, float],
) -> dict[str, object]:
    """Replay one candidate over one window and return the gate inputs."""
    days, held, returns = window_arrays(weights, closes, start, end)
    base_cost = costs_bps["base"] / 1e4
    base = daily_pnl(held, returns, notional, base_cost)
    stress = daily_pnl(held, returns, notional, costs_bps["stress"] / 1e4)
    gross = daily_pnl(held, returns, notional, 0.0)
    long_only = daily_pnl(np.clip(held, 0.0, None), returns, notional, base_cost)
    series = pd.Series(base, index=days)
    monthly = series.groupby(days.tz_localize(None).to_period("M")).sum()
    yearly = series.groupby(days.year).sum()
    episodes = _episodes(held, returns, notional, base_cost)
    equity = np.cumsum(base)
    drawdown = float((np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:] - equity).max())
    benchmark = float(notional * (held.mean(axis=0) * returns.sum(axis=0)).sum())
    return {
        "days": len(days),
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
        "daily_base_pnl_sha256": hashlib.sha256(np.round(base, 8).tobytes()).hexdigest(),
    }

"""Timing null and ADR-014 Gates v2 for research replays."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def shift_null(
    held: np.ndarray,
    returns: np.ndarray,
    days: pd.DatetimeIndex,
    *,
    observed_base: float,
    notional: float,
    cost: float,
    trials: int,
    seed: int,
    shift_unit: int = 1,
) -> dict[str, float]:
    """Circularly shift each asset's held weights against its returns.

    Exposure, turnover, holding cadence and long/short mix are preserved; only
    the timing is destroyed. Returns the p-value of the observed base PnL and
    the null's median count of positive months (ADR-014 §11).
    """
    rng = np.random.default_rng(seed)
    n_rows, n_assets = held.shape
    if shift_unit < 1 or n_rows // shift_unit < 2:
        raise ValueError("null requires at least two shift units")
    month_codes = days.tz_localize(None).to_period("M").asi8
    month_starts = np.flatnonzero(np.r_[True, np.diff(month_codes) != 0])
    totals = np.empty(trials)
    positive_months = np.empty(trials)
    # Contiguous asset series avoid strided reads in every Monte Carlo trial.
    asset_weights = np.ascontiguousarray(held.T)
    asset_returns = np.ascontiguousarray(returns.T)
    traded = np.empty(n_rows)
    for trial in range(trials):
        shifts = rng.integers(1, n_rows // shift_unit, size=n_assets) * shift_unit
        months = np.zeros(len(month_starts))
        for asset, shift in enumerate(shifts):
            shifted = np.roll(asset_weights[asset], shift)
            np.subtract(shifted[1:], shifted[:-1], out=traded[1:])
            traded[0] = shifted[0]
            np.abs(traded, out=traded)
            traded[-1] += abs(shifted[-1])
            pnl = shifted * asset_returns[asset]
            np.multiply(traded, cost, out=traded)
            pnl -= traded
            pnl *= notional
            months += np.add.reduceat(pnl, month_starts)
        totals[trial] = months.sum()
        positive_months[trial] = (months > 0).sum()
    exceed = int((totals >= observed_base).sum())
    return {
        "trials": trials,
        "seed": seed,
        "p_value": (1 + exceed) / (trials + 1),
        "null_base_mean": float(totals.mean()),
        "null_base_p90": float(np.quantile(totals, 0.9)),
        "null_months_positive_median": float(np.median(positive_months)),
    }


def apply_gates(gates: dict[str, object], result: dict, null: dict[str, float]) -> dict:
    """Evaluate a replay against the contract's frozen gates."""
    # Contracts write 2/3 as 0.6667; the tolerance keeps 2 of 3 years a pass.
    years_needed = math.ceil(
        float(gates["positive_years_fraction_at_least"]) * result["years_total"] - 1e-3
    )
    checks = {
        "base_net_pnl_positive": result["base_net_pnl"] > gates["base_net_pnl_gt"],
        "stress_net_pnl_positive": result["stress_net_pnl"] > gates["stress_net_pnl_gt"],
        "years_breadth": result["positive_years"] >= years_needed,
        "months_breadth": result["positive_months"] > null["null_months_positive_median"],
        "activity_floor": result["closed_positions"] >= gates["closed_positions_at_least"],
        "leave_best_positive": result["leave_best_base_net_pnl"]
        > gates["leave_best_base_net_pnl_gt"],
        "benchmark_relative": (
            not gates["benchmark_relative"] or result["base_net_pnl"] > result["benchmark_pnl"]
        ),
        "null_p_value": null["p_value"] <= gates["p_value_max"],
    }
    if "active_days_at_least" in gates:
        checks["active_days_floor"] = result["active_days"] >= gates["active_days_at_least"]
    return {
        "checks": checks,
        "years_needed": years_needed,
        "months_threshold": null["null_months_positive_median"],
        "pass": all(checks.values()),
    }

"""Timing null and ADR-014 Gates v2 for research replays."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from apps.research.replay import daily_pnl


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
) -> dict[str, float]:
    """Circularly shift each asset's held weights against its returns.

    Exposure, turnover, holding cadence and long/short mix are preserved; only
    the timing is destroyed. Returns the p-value of the observed base PnL and
    the null's median count of positive months (ADR-014 §11).
    """
    rng = np.random.default_rng(seed)
    n_days, n_assets = held.shape
    month_codes = days.tz_localize(None).to_period("M").asi8
    month_starts = np.flatnonzero(np.r_[True, np.diff(month_codes) != 0])
    totals = np.empty(trials)
    positive_months = np.empty(trials)
    rows = np.arange(n_days)[:, None]
    for trial in range(trials):
        shifts = rng.integers(1, n_days, size=n_assets)
        shifted = held[(rows - shifts[None, :]) % n_days, np.arange(n_assets)]
        pnl = daily_pnl(shifted, returns, notional, cost)
        totals[trial] = pnl.sum()
        positive_months[trial] = (np.add.reduceat(pnl, month_starts) > 0).sum()
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
    return {
        "checks": checks,
        "years_needed": years_needed,
        "months_threshold": null["null_months_positive_median"],
        "pass": all(checks.values()),
    }

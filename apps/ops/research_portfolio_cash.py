"""Cash bounds from retained fills only; no orders, sizing or execution model."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from apps.ops.research_portfolio_evidence import COSTS, END, START


def event_cash_bounds(
    fills: dict[str, pd.DataFrame], weights: dict[str, float], capital: float
) -> dict:
    """Consume already hash/identity-audited fills; bound unknown cross-sleeve ties.

    Independent replay timestamps cannot establish actual inter-strategy order.
    Sell-first gives the lowest cash requirement; buy-first gives the highest
    within each recorded timestamp. Neither adds or changes a fill.
    """
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("positive finite planning capital required")
    if (
        not fills
        or set(fills) != set(weights)
        or any(not math.isfinite(w) or w <= 0 for w in weights.values())
    ):
        raise ValueError("positive weights required for the exact audited cohort")
    frames = []
    for protocol, frame in fills.items():
        if (
            frame.empty
            or frame["fill_id"].duplicated().any()
            or not frame["side"].isin(["BUY", "SELL"]).all()
        ):
            raise ValueError("empty, duplicate or invalid cash evidence")
        timestamps = pd.to_numeric(frame["ts_event"], errors="raise")
        quantity = pd.to_numeric(frame["quantity"], errors="raise")
        price = pd.to_numeric(frame["price"], errors="raise")
        if (
            not np.isfinite(timestamps).all()
            or (timestamps % 1 != 0).any()
            or not timestamps.between(START.value, END.value - 1).all()
            or not np.isfinite(quantity).all()
            or not np.isfinite(price).all()
            or (quantity <= 0).any()
            or (price <= 0).any()
        ):
            raise ValueError("invalid historical cash inputs")
        notionals = quantity * price * weights[protocol]
        if not np.isfinite(notionals).all():
            raise ValueError("nonfinite weighted notional")
        frames.append(
            pd.DataFrame(
                {
                    "buy": notionals.where(frame["side"] == "BUY", 0).to_numpy(),
                    "sell": notionals.where(frame["side"] == "SELL", 0).to_numpy(),
                },
                index=timestamps.to_numpy(dtype="int64"),
            )
        )
    groups = pd.concat(frames).groupby(level=0, sort=True).sum()
    scenarios = {}
    for scenario, bps in COSTS.items():
        buys = groups["buy"] * (1 + bps / 10000)
        sells = groups["sell"] * (1 - bps / 10000)
        closing_cash = (sells - buys).cumsum()
        opening_cash = closing_cash.shift(1, fill_value=0)
        sell_first_required = max(0.0, -float(closing_cash.min()))
        buy_first_required = max(0.0, -float((opening_cash - buys).min()))
        scenarios[scenario] = {
            "required_initial_cash_sell_before_buy_usdt": sell_first_required,
            "required_initial_cash_buy_before_sell_usdt": buy_first_required,
            "cash_headroom_sell_before_buy_usdt": capital - sell_first_required,
            "cash_headroom_buy_before_sell_usdt": capital - buy_first_required,
            "covers_sell_before_buy_bound": capital >= sell_first_required,
            "covers_buy_before_sell_bound": capital >= buy_first_required,
            "final_cash_change_usdt": float(closing_cash.iloc[-1]),
        }
    return {
        "planned_capital_usdt": capital,
        "recorded_fills": sum(len(frame) for frame in fills.values()),
        "distinct_execution_timestamps": len(groups),
        "mixed_buy_sell_timestamp_count": int(((groups["buy"] > 0) & (groups["sell"] > 0)).sum()),
        "diagnostic_weights_not_source_policy": weights,
        "scenarios": scenarios,
        "order_reservations_modeled": False,
        "intraday_equity_drawdown_measured": False,
        "actual_execution_order_known": False,
        "new_fills_created": False,
    }

"""ADR-019 historical admission of beta allocations against buy-and-hold.

    uv run python -m apps.research.beta

Equity compounds from a starting balance. Target weights are fractions of equity,
decided at a day's close and traded at that close; coin units are held between
rebalances, so weights drift. The book is closed at the last close.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from apps.research import data
from apps.strategies_freqtrade.research import trend_vol

START, END = "2020-01-01", "2025-12-31"
EQUITY = 10_000.0
COSTS_BPS = {"base": 12.0, "stress": 20.0}
TEN_COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
             "LTCUSDT", "LINKUSDT", "TRXUSDT", "ETCUSDT", "XLMUSDT"]  # fmt: skip
V54_PARAMS = {
    "lookbacks_days": [20, 60, 120],
    "vol_window_days": 30,
    "rebalance_weekday": 6,
    "max_gross_exposure": 1.0,
}
OUT_PATH = Path("docs/research/results/beta-2026-10.json")


def simulate(
    weights: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    cost: float,
    equity: float = EQUITY,
    start: str = START,
    end: str = END,
) -> dict[str, object]:
    """Daily equity of a long/flat book that trades only when its target changes."""
    first, last = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    days = pd.date_range(first, last, freq="D")
    raw = closes[weights.columns].reindex(days)
    if raw.isna().any().any():
        raise ValueError(f"closes must cover every symbol on every day {start}..{end}")
    px = raw.to_numpy()
    target = weights.reindex(days).ffill().fillna(0.0).to_numpy()
    if (target < 0).any() or (target.sum(axis=1) > 1 + 1e-9).any():
        raise ValueError("beta weights must be long/flat with gross <= 1")
    units = np.zeros(px.shape[1])
    cash = equity
    curve = np.empty(len(days))
    previous = None
    trades = 0
    for row in range(len(days)):
        prices = px[row]
        value = cash + units @ prices
        wanted = target[row]
        if previous is None or not np.array_equal(wanted, previous):
            # Size from equity net of this rebalance's fees so cash never goes
            # negative; the fixed point converges in a few steps for small costs.
            fee = 0.0
            for _ in range(5):
                new_units = wanted * (value - fee) / prices
                traded = np.abs(new_units - units) @ prices
                fee = cost * traded
            cash = value - new_units @ prices - fee
            trades += int((np.abs(new_units - units) * prices > 1e-9).sum())
            units, previous = new_units, wanted
        curve[row] = cash + units @ prices
    curve[-1] -= cost * (units @ px[-1])  # close the book
    return {
        "equity": pd.Series(curve, index=days),
        "trades": trades,
        "time_in_market": float((target.sum(axis=1) > 0).mean()),
    }


def metrics(equity: pd.Series, start_equity: float = EQUITY) -> dict[str, object]:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    final = float(equity.iloc[-1])
    peak = np.maximum.accumulate(np.r_[start_equity, equity.to_numpy()])[1:]
    max_dd = float((1 - equity.to_numpy() / peak).max())
    cagr = (final / start_equity) ** (1 / years) - 1
    year_end = equity.groupby(equity.index.year).last()
    starts = np.r_[start_equity, year_end.to_numpy()[:-1]]
    yearly = {
        int(y): float(v / s - 1) for y, v, s in zip(year_end.index, year_end, starts, strict=True)
    }
    return {
        "final_equity": final,
        "cagr": float(cagr),
        "max_drawdown": max_dd,
        "cagr_over_max_drawdown": float(cagr / max_dd) if max_dd > 0 else None,
        "yearly_return": yearly,
    }


def admit(candidate: dict, benchmark: dict, stress_final: float) -> dict[str, object]:
    """ADR-019 §3 criteria, fixed before evaluation."""
    checks = {
        "drawdown_at_most_two_thirds": candidate["max_drawdown"]
        <= 2 / 3 * benchmark["max_drawdown"],
        "cagr_over_drawdown_at_least_benchmark": (candidate["cagr_over_max_drawdown"] or 0)
        >= benchmark["cagr_over_max_drawdown"],
        "loss_2022_at_most_half": candidate["yearly_return"][2022]
        >= 0.5 * min(benchmark["yearly_return"][2022], 0.0),
        "cagr_at_least_half": candidate["cagr"] >= 0.5 * benchmark["cagr"],
        "stress_total_return_positive": stress_final > EQUITY,
    }
    return {"checks": checks, "admitted": all(checks.values())}


def candidates(frames: dict[str, dict[str, pd.DataFrame]]) -> dict[str, tuple]:
    """Name -> (weights, benchmark universe), as fixed in ADR-019 §3."""
    b1 = trend_vol.target_weights(frames, "tsmom_vol", V54_PARAMS).clip(lower=0.0)
    pair = {data_set: {s: f for s, f in syms.items() if s in ("BTCUSDT", "ETHUSDT")}
            for data_set, syms in frames.items()}  # fmt: skip
    b2 = trend_vol.target_weights(pair, "sma_filter", {"sma_days": 200, "weight_per_symbol": 0.5})
    return {
        "B1_v54_long_flat": (b1, TEN_COINS),
        "B2_btc_eth_sma200": (b2, ["BTCUSDT", "ETHUSDT"]),
    }


def evaluate(frames: dict[str, dict[str, pd.DataFrame]]) -> dict[str, object]:
    closes = pd.DataFrame({s: f["close"] for s, f in frames[trend_vol.PRICE_DATASET].items()})
    report: dict[str, object] = {}
    for name, (weights, universe) in candidates(frames).items():
        start_row = closes.index[closes.index >= pd.Timestamp(START, tz="UTC")][0]
        hold = pd.DataFrame(1.0 / len(universe), index=[start_row], columns=universe)
        bench = simulate(hold, closes, cost=COSTS_BPS["base"] / 1e4)
        base = simulate(weights[universe], closes, cost=COSTS_BPS["base"] / 1e4)
        stress = simulate(weights[universe], closes, cost=COSTS_BPS["stress"] / 1e4)
        bench_m, base_m = metrics(bench["equity"]), metrics(base["equity"])
        report[name] = {
            "universe": universe,
            "candidate": base_m
            | {"trades": base["trades"], "time_in_market": base["time_in_market"]},
            "candidate_stress_final_equity": float(stress["equity"].iloc[-1]),
            "benchmark_buy_and_hold": bench_m,
            "admission": admit(base_m, bench_m, float(stress["equity"].iloc[-1])),
        }
    return report


def main() -> int:
    frames = data.load_frames([trend_vol.PRICE_DATASET], TEN_COINS)
    report = {
        "schema_version": "research.beta.v1",
        "adr": "019",
        "window": [START, END],
        "start_equity_usdt": EQUITY,
        "costs_bps_per_unit_traded": COSTS_BPS,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidates": evaluate(frames),
    }
    if OUT_PATH.exists():
        raise FileExistsError(f"{OUT_PATH} exists; results are immutable")
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    for name, item in report["candidates"].items():
        c, b = item["candidate"], item["benchmark_buy_and_hold"]
        failed = [k for k, ok in item["admission"]["checks"].items() if not ok]
        print(
            f"{name}: {'ADMITTED' if item['admission']['admitted'] else 'NOT ADMITTED'} "
            f"final {c['final_equity']:.0f} vs {b['final_equity']:.0f}, "
            f"CAGR {c['cagr']:.1%} vs {b['cagr']:.1%}, maxDD {c['max_drawdown']:.1%} vs "
            f"{b['max_drawdown']:.1%}, 2022 {c['yearly_return'][2022]:.1%} vs "
            f"{b['yearly_return'][2022]:.1%}, failed={failed or '-'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

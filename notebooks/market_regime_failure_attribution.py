"""Reproduce the 2024-2025 BTCUSDT trend-regime failure attribution.

This is a passive research script. It reads the local Parquet catalog and two
ADR-004 backtest bundles, then writes a strict JSON diagnostic artifact. It
does not read credentials, write SignalEvent, start NautilusTrader, or mutate
SourcePolicy.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.breakout_rule_signals import (
    resample_ohlcv_15m,
)
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    _load_bars_from_catalog,
)

DEFAULT_BAR_TYPE = "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"
TRADE_SIZE = 0.001


def _finite_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [_json_safe(child) for child in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return _finite_or_none(value)
    return value


def _monthly_market_metrics(group: pd.DataFrame) -> dict[str, Any]:
    opening = float(group["open"].iloc[0])
    closing = float(group["close"].iloc[-1])
    log_steps = np.log(group["close"] / group["close"].shift(1))
    log_steps.iloc[0] = math.log(float(group["close"].iloc[0]) / opening)
    absolute_path = float(log_steps.abs().sum())
    close_path = pd.concat(
        [pd.Series([opening]), group["close"].reset_index(drop=True)],
        ignore_index=True,
    )
    drawdown = close_path / close_path.cummax() - 1.0
    month_return = closing / opening - 1.0
    efficiency = abs(float(log_steps.sum())) / absolute_path if absolute_path else 0.0
    realized_vol = float(log_steps.std(ddof=1) * math.sqrt(365.0))
    if abs(month_return) >= 0.05 and efficiency >= 0.30:
        regime = "directional_up" if month_return > 0 else "directional_down"
    else:
        regime = "mixed"
    return {
        "open": opening,
        "close": closing,
        "return_pct": month_return * 100.0,
        "realized_vol_ann_pct": realized_vol * 100.0,
        "trend_efficiency": efficiency,
        "max_drawdown_pct": float(drawdown.min()) * 100.0,
        "range_pct": (float(group["high"].max()) / float(group["low"].min()) - 1.0)
        * 100.0,
        "up_day_share": float((log_steps > 0).mean()),
        "diagnostic_regime": regime,
    }


def _hourly_state(bars: pd.DataFrame) -> pd.DataFrame:
    hourly = resample_ohlcv_15m(bars.drop(columns=["ts"]), timeframe_minutes=60).copy()
    hourly["ts"] = pd.to_datetime(hourly["ts_event"], unit="ns", utc=True)
    close = hourly["close"].astype(float)
    hourly["fast"] = close.ewm(span=24, adjust=False).mean()
    hourly["slow"] = close.ewm(span=96, adjust=False).mean()
    hourly["momentum24"] = close.pct_change(24)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            hourly["high"] - hourly["low"],
            (hourly["high"] - previous_close).abs(),
            (hourly["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    hourly["atr14"] = true_range.rolling(14, min_periods=14).mean()
    hourly["spread_atr"] = (hourly["fast"] - hourly["slow"]) / hourly["atr14"]
    hourly["distance_slow_atr"] = (close - hourly["slow"]) / hourly["atr14"]
    return hourly.set_index("ts").sort_index()


def _position_detail(
    bundle_dir: Path,
    *,
    minute: pd.DataFrame,
    hourly: pd.DataFrame,
) -> pd.DataFrame:
    positions = pd.read_parquet(bundle_dir / "positions.parquet")
    rows: list[dict[str, Any]] = []
    for position in positions.itertuples(index=False):
        opened = pd.Timestamp(int(position.opened_ts), unit="ns", tz="UTC")
        closed = pd.Timestamp(int(position.closed_ts), unit="ns", tz="UTC")
        entry_price = float(position.avg_px_open)
        exit_price = float(position.avg_px_close)
        segment = minute.loc[opened:closed]
        entry_state = hourly.loc[:opened].iloc[-1]
        exit_state = hourly.loc[:closed].iloc[-1]
        notional_sum = TRADE_SIZE * (entry_price + exit_price)
        gross_pnl = TRADE_SIZE * (exit_price - entry_price)
        base_cost = notional_sum * 0.0012
        stress_cost = notional_sum * 0.0015
        mfe_pnl = TRADE_SIZE * (float(segment["high"].max()) - entry_price)
        mae_pnl = TRADE_SIZE * (float(segment["low"].min()) - entry_price)

        fast_below = bool(exit_state["fast"] < exit_state["slow"])
        price_below = bool(
            exit_state["close"] < exit_state["slow"] - 0.5 * exit_state["atr14"]
        )
        if fast_below and price_below:
            exit_cause = "both"
        elif fast_below:
            exit_cause = "ema_cross"
        elif price_below:
            exit_cause = "price_buffer"
        else:
            exit_cause = "end_or_unclassified"

        follow_through: dict[str, float | None] = {}
        for hours in (24, 48):
            target = opened + pd.Timedelta(hours=hours)
            if target > minute.index.max():
                follow_through[f"return_{hours}h_pct"] = None
            else:
                index = minute.index.get_indexer([target], method="pad")[0]
                follow_through[f"return_{hours}h_pct"] = (
                    (float(minute.iloc[index]["close"]) / entry_price - 1.0) * 100.0
                    if index >= 0
                    else None
                )

        rows.append(
            {
                "opened": opened.isoformat(),
                "closed": closed.isoformat(),
                "opened_month": opened.strftime("%Y-%m"),
                "closed_month": closed.strftime("%Y-%m"),
                "duration_hours": (closed - opened).total_seconds() / 3600.0,
                "entry_px": entry_price,
                "exit_px": exit_price,
                "gross_pnl": gross_pnl,
                "recorded_net_pnl": float(position.realized_pnl),
                "base_pnl": gross_pnl - base_cost,
                "stress_pnl": gross_pnl - stress_cost,
                "base_cost": base_cost,
                "stress_cost": stress_cost,
                "mfe_pnl": mfe_pnl,
                "mae_pnl": mae_pnl,
                "giveback_from_mfe": mfe_pnl - gross_pnl,
                "captured_mfe_ratio": gross_pnl / mfe_pnl if mfe_pnl > 0 else None,
                "mfe_cleared_base_cost": bool(mfe_pnl > base_cost),
                "entry_momentum24_pct": _finite_or_none(entry_state["momentum24"] * 100),
                "entry_spread_atr": _finite_or_none(entry_state["spread_atr"]),
                "entry_distance_slow_atr": _finite_or_none(
                    entry_state["distance_slow_atr"]
                ),
                "exit_cause": exit_cause,
                **follow_through,
            }
        )
    return pd.DataFrame(rows)


def _position_summary(detail: pd.DataFrame) -> dict[str, Any]:
    losers = detail[detail["gross_pnl"] <= 0]
    by_exit = {
        cause: {
            "positions": len(group),
            "gross_pnl": float(group["gross_pnl"].sum()),
            "base_pnl": float(group["base_pnl"].sum()),
            "win_rate": float((group["gross_pnl"] > 0).mean()),
        }
        for cause, group in detail.groupby("exit_cause")
    }
    by_month = {
        month: {
            "positions": len(group),
            "gross_pnl": float(group["gross_pnl"].sum()),
            "base_pnl": float(group["base_pnl"].sum()),
            "wins": int((group["gross_pnl"] > 0).sum()),
        }
        for month, group in detail.groupby("closed_month")
    }
    ranked = detail.sort_values("gross_pnl")
    rank_columns = [
        "opened",
        "closed",
        "gross_pnl",
        "base_pnl",
        "mfe_pnl",
        "giveback_from_mfe",
        "duration_hours",
        "exit_cause",
    ]
    captured = detail.loc[detail["mfe_pnl"] > 0, "captured_mfe_ratio"]
    return {
        "positions": len(detail),
        "gross_pnl": float(detail["gross_pnl"].sum()),
        "base_pnl": float(detail["base_pnl"].sum()),
        "stress_pnl": float(detail["stress_pnl"].sum()),
        "modeled_base_cost": float(detail["base_cost"].sum()),
        "modeled_stress_cost": float(detail["stress_cost"].sum()),
        "win_rate_gross": float((detail["gross_pnl"] > 0).mean()),
        "win_rate_base": float((detail["base_pnl"] > 0).mean()),
        "avg_gross_pnl": float(detail["gross_pnl"].mean()),
        "avg_base_pnl": float(detail["base_pnl"].mean()),
        "median_gross_pnl": float(detail["gross_pnl"].median()),
        "median_duration_hours": float(detail["duration_hours"].median()),
        "mean_duration_hours": float(detail["duration_hours"].mean()),
        "exposure_hours": float(detail["duration_hours"].sum()),
        "mean_mfe_pnl": float(detail["mfe_pnl"].mean()),
        "mean_mae_pnl": float(detail["mae_pnl"].mean()),
        "mean_giveback_from_mfe": float(detail["giveback_from_mfe"].mean()),
        "median_captured_mfe_ratio": _finite_or_none(captured.median()),
        "losers_with_positive_mfe": int((losers["mfe_pnl"] > 0).sum()),
        "losers_that_cleared_base_cost_intratrade": int(
            losers["mfe_cleared_base_cost"].sum()
        ),
        "positions_never_clearing_base_cost": int(
            (~detail["mfe_cleared_base_cost"]).sum()
        ),
        "mean_entry_momentum24_pct": float(detail["entry_momentum24_pct"].mean()),
        "mean_entry_spread_atr": float(detail["entry_spread_atr"].mean()),
        "mean_entry_distance_slow_atr": float(
            detail["entry_distance_slow_atr"].mean()
        ),
        "mean_return_24h_pct": float(detail["return_24h_pct"].mean()),
        "mean_return_48h_pct": float(detail["return_48h_pct"].mean()),
        "exit_causes": by_exit,
        "monthly": by_month,
        "top_winners": ranked.tail(3)[rank_columns].to_dict("records"),
        "top_losers": ranked.head(3)[rank_columns].to_dict("records"),
    }


def build_review(
    *,
    catalog_path: Path,
    bar_type: str,
    development_bundle: Path,
    blind_bundle: Path,
) -> dict[str, Any]:
    bars = _load_bars_from_catalog(catalog_path, bar_type).copy()
    bars["ts"] = pd.to_datetime(bars["ts_event"], unit="ns", utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        bars[column] = bars[column].astype(float)
    minute = bars.set_index("ts").sort_index()
    daily = (
        minute.resample("1D")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna()
    )
    monthly = {
        month: _monthly_market_metrics(group)
        for month, group in daily.groupby(daily.index.strftime("%Y-%m"))
    }
    hourly = _hourly_state(bars)

    bundles = {
        "development_2024_08_12": development_bundle,
        "blind_2025_08_12": blind_bundle,
    }
    position_detail = {
        label: _position_detail(bundle, minute=minute, hourly=hourly)
        for label, bundle in bundles.items()
    }
    position_summary = {
        label: _position_summary(detail) for label, detail in position_detail.items()
    }

    windows: dict[str, dict[str, Any]] = {}
    for label, (start, end) in {
        "development_2024_08_12": ("2024-08", "2024-12"),
        "blind_2025_08_12": ("2025-08", "2025-12"),
    }.items():
        months = [month for month in monthly if start <= month <= end]
        windows[label] = {
            "market_return_pct": (
                monthly[months[-1]]["close"] / monthly[months[0]]["open"] - 1.0
            )
            * 100.0,
            "months": months,
            "directional_up_months": sum(
                monthly[month]["diagnostic_regime"] == "directional_up"
                for month in months
            ),
            "directional_down_months": sum(
                monthly[month]["diagnostic_regime"] == "directional_down"
                for month in months
            ),
            "mixed_months": sum(
                monthly[month]["diagnostic_regime"] == "mixed" for month in months
            ),
            "mean_trend_efficiency": float(
                np.mean([monthly[month]["trend_efficiency"] for month in months])
            ),
            "mean_realized_vol_ann_pct": float(
                np.mean([monthly[month]["realized_vol_ann_pct"] for month in months])
            ),
        }

    return _json_safe(
        {
            "schema_version": "market.failure_attribution.v1",
            "scope": {
                "catalog_path": str(catalog_path),
                "bar_type": bar_type,
                "bars": len(bars),
                "start": minute.index.min().isoformat(),
                "end": minute.index.max().isoformat(),
                "development_bundle": str(development_bundle),
                "blind_bundle": str(blind_bundle),
                "method_notes": {
                    "monthly_return": "first 1m open to last 1m close",
                    "realized_vol": "daily log-return standard deviation annualized by sqrt(365)",
                    "trend_efficiency": "absolute cumulative daily log return divided by sum of absolute daily log returns",
                    "diagnostic_regime": "directional when abs(month return)>=5% and efficiency>=0.30; descriptive only",
                    "position_gross": "0.001 * (exit fill - entry fill)",
                    "base_cost": "12 bps per fill notional (10 fee + 2 slippage)",
                    "mfe_mae": "intratrade 1m high/low relative to entry fill",
                },
            },
            "monthly_market": monthly,
            "window_market": windows,
            "position_summary": position_summary,
            "position_detail": {
                label: detail.to_dict("records") for label, detail in position_detail.items()
            },
            "boundaries": {
                "diagnostic_only": True,
                "writes_signal_event": False,
                "mutates_source_policy": False,
                "loads_credentials": False,
                "starts_nautilus": False,
                "resumes_testnet": False,
            },
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog-path", type=Path, default=Path("data/catalog"))
    parser.add_argument("--bar-type", default=DEFAULT_BAR_TYPE)
    parser.add_argument(
        "--development-bundle",
        type=Path,
        default=Path("data/backtests/20260710-053017Z-8c63508d"),
    )
    parser.add_argument(
        "--blind-bundle",
        type=Path,
        default=Path("data/backtests/20260710-053944Z-1a2d2376"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/market-regime-failure-attribution-2024-2025.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    review = build_review(
        catalog_path=args.catalog_path,
        bar_type=args.bar_type,
        development_bundle=args.development_bundle,
        blind_bundle=args.blind_bundle,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review, indent=2, allow_nan=False) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

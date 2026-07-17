"""Combine strict single-asset alpha reviews into one passive portfolio review."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from apps.ops.alpha_review import SCENARIOS

SCHEMA_VERSION = "multi_asset.review.v1"
SOURCE_UNIVERSES = {
    "rule_alt_diversified_momentum_v1": {"BNBUSDT", "XRPUSDT", "ADAUSDT"},
    "rule_alt_low_vol_rotation_v1": {"BNBUSDT", "XRPUSDT", "ADAUSDT"},
    "rule_flow_exhaustion_v1": {"BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "rule_funding_crowding_rotation_v1": {"BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "rule_taker_flow_rotation_v1": {"BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "rule_xs_momentum_rotation_v1": {"BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "rule_market_breadth_v1": {"BTCUSDT"},
    "rule_relative_value_rotation_v1": {"BTCUSDT", "ETHUSDT"},
    "rule_binance_curve_carry_v1": {"BTCUSDT", "ETHUSDT"},
    "rule_binance_bvol_relief_v1": {"BTCUSDT", "ETHUSDT"},
}
SOURCE_MAX_CONCURRENT_ASSETS = {
    "rule_alt_diversified_momentum_v1": 3,
    "rule_binance_curve_carry_v1": 2,
    "rule_binance_bvol_relief_v1": 2,
}
V5_SOURCES = {
    "rule_binance_curve_carry_v1",
    "rule_binance_bvol_relief_v1",
}


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)


def _load_review(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )
    if not isinstance(payload, dict) or payload.get("schema_version") != "alpha.review.v1":
        raise ValueError(f"{path} is not alpha.review.v1")
    _assert_finite(payload)
    return payload


def _candidate(report: dict[str, Any], path: Path) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in report.get("candidates", [])
        if candidate.get("is_research_candidate")
    ]
    if len(candidates) != 1:
        raise ValueError(f"{path} must contain exactly one research candidate")
    return candidates[0]


def _sum_metrics(candidates: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    fields = (
        "recorded_pnl",
        "recorded_commission",
        "modeled_fee",
        "modeled_slippage",
        "net_pnl",
    )
    return {
        scenario["name"]: {
            field: sum(
                float(candidate["scenario_metrics"][scenario["name"]][field])
                for candidate in candidates
            )
            for field in fields
        }
        for scenario in SCENARIOS
    }


def _monthly_metrics(
    candidates: list[dict[str, Any]], expected_months: list[str]
) -> list[dict[str, Any]]:
    by_candidate = []
    for candidate in candidates:
        rows = {row["month"]: row for row in candidate["monthly_metrics"]}
        if list(rows) != expected_months:
            raise ValueError("asset review has missing, duplicate, or out-of-order months")
        by_candidate.append(rows)
    fields = (
        "recorded_pnl",
        "recorded_commission",
        "modeled_fee",
        "modeled_slippage",
        "net_pnl",
    )
    return [
        {
            "month": month,
            "scenarios": {
                scenario["name"]: {
                    field: sum(
                        float(rows[month]["scenarios"][scenario["name"]][field])
                        for rows in by_candidate
                    )
                    for field in fields
                }
                for scenario in SCENARIOS
            },
        }
        for month in expected_months
    ]


def _audit_exclusivity(
    assets: list[tuple[str, Path, dict[str, Any]]],
    *,
    source: str,
    model_version: str,
    maximum_allowed_assets: int,
) -> dict[str, Any]:
    events: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for symbol, _path, candidate in assets:
        runs = candidate.get("bundle_runs")
        if not isinstance(runs, list) or not runs:
            raise ValueError(f"{symbol} review is missing bundle_runs")
        lineage_path = Path(str(runs[0])) / "signal_lineage.parquet"
        lineage = pd.read_parquet(lineage_path)
        required = {"source", "model_version", "ts_event", "decision"}
        if not required <= set(lineage.columns):
            raise ValueError(f"{lineage_path} is missing required lineage columns")
        selected = lineage.loc[
            (lineage["source"].astype(str) == source)
            & (lineage["model_version"].astype(str) == model_version)
            & lineage["decision"].astype(str).isin({"target_flat", "target_long"})
        ]
        for row in selected.to_dict("records"):
            ts_event = int(row["ts_event"])
            events[ts_event].append((symbol, str(row["decision"])))

    held: set[str] = set()
    overlaps: list[dict[str, Any]] = []
    limit_violations: list[dict[str, Any]] = []
    maximum_observed = 0
    for ts_event, rows in sorted(events.items()):
        for symbol, decision in rows:
            if decision == "target_flat":
                held.discard(symbol)
        for symbol, decision in rows:
            if decision == "target_long":
                held.add(symbol)
        maximum_observed = max(maximum_observed, len(held))
        if len(held) > 1:
            overlaps.append({"ts_event": ts_event, "held_assets": sorted(held)})
        if len(held) > maximum_allowed_assets:
            limit_violations.append(
                {"ts_event": ts_event, "held_assets": sorted(held)}
            )
    return {
        "event_timestamps": len(events),
        "maximum_concurrent_assets": maximum_observed,
        "maximum_allowed_assets": maximum_allowed_assets,
        "overlap_count": len(overlaps),
        "first_overlaps": overlaps[:10],
        "limit_violation_count": len(limit_violations),
        "first_limit_violations": limit_violations[:10],
        "exclusive": maximum_observed <= 1,
        "within_limit": not limit_violations,
    }


def _risk_metrics(rows: list[dict[str, Any]], scenario: str) -> dict[str, Any]:
    equities = [100_000.0]
    equities.extend(float(row["scenarios"][scenario]["equity"]) for row in rows)
    peak = equities[0]
    maximum_drawdown = 0.0
    for equity in equities:
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity - peak)
    net_pnl = equities[-1] - equities[0]
    ratio = net_pnl / abs(maximum_drawdown) if maximum_drawdown < 0.0 else None
    return {
        "net_pnl": net_pnl,
        "max_drawdown_usdt": maximum_drawdown,
        "max_drawdown_pct": maximum_drawdown / 100_000.0,
        "net_pnl_to_abs_max_drawdown": ratio,
    }


def _v5_asset_curve(
    symbol: str,
    report: dict[str, Any],
    candidate: dict[str, Any],
    *,
    start: str,
    end: str,
) -> dict[str, Any]:
    from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

    from apps.strategies_nautilus.result_schema import BacktestManifest
    from apps.strategies_nautilus.runners.backtest_runner import validate_sidecar_bundle

    bundle = Path(str(candidate["bundle_runs"][0]))
    validate_sidecar_bundle(bundle)
    manifest_raw = json.loads(
        (bundle / "run_manifest.json").read_text(),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )
    manifest = BacktestManifest.model_validate(manifest_raw)
    if manifest.git_dirty:
        raise ValueError(f"{symbol} v5 bundle is git-dirty")
    catalog = ParquetDataCatalog(str(Path(manifest.data_catalog.path).resolve()))
    instrument_id = manifest.data_catalog.instruments[0].id
    bar_type = manifest.data_catalog.instruments[0].bars
    instruments = catalog.instruments(instrument_ids=[instrument_id])
    if len(instruments) != 1:
        raise ValueError(f"{symbol} catalog must contain exactly one instrument")
    start_ns = int(pd.Timestamp(start, tz="UTC").value)
    end_exclusive = int((pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).value)
    bars = sorted(
        catalog.bars(bar_types=[bar_type], start=start_ns, end=end_exclusive - 1),
        key=lambda bar: int(bar.ts_event),
    )
    if not bars:
        raise ValueError(f"{symbol} catalog has no bars in the fold")
    close_frame = pd.DataFrame(
        {
            "ts": [int(bar.ts_event) for bar in bars],
            "close": [float(bar.close) for bar in bars],
        }
    )
    close_frame["date"] = pd.to_datetime(close_frame["ts"], unit="ns", utc=True).dt.date
    daily_close = close_frame.groupby("date", sort=True)["close"].last()
    expected_days = pd.date_range(start, end, freq="1D").date
    if list(daily_close.index) != list(expected_days):
        raise ValueError(f"{symbol} v5 catalog has an incomplete daily execution window")

    increment = Decimal(str(float(instruments[0].size_increment)))
    first_close = Decimal(str(float(daily_close.iloc[0])))
    expected_size = ((Decimal("50") / first_close) / increment).to_integral_value(
        rounding=ROUND_FLOOR
    ) * increment
    actual_size = Decimal(str(report["inputs"].get("trade_size")))
    if actual_size != expected_size:
        raise ValueError(
            f"{symbol} trade_size={actual_size} differs from frozen fold size {expected_size}"
        )
    initial_notional = float(expected_size * first_close)
    if initial_notional > 50.0:
        raise ValueError(f"{symbol} initial target notional exceeds 50 USDT")

    fills = pd.read_parquet(bundle / "fills.parquet").copy()
    required = {"ts_event", "side", "quantity", "price", "commission"}
    if not required <= set(fills.columns):
        raise ValueError(f"{symbol} fills are missing required columns")
    for column in ("ts_event", "quantity", "price", "commission"):
        fills[column] = pd.to_numeric(fills[column], errors="coerce")
        if fills[column].isna().any() or not fills[column].map(math.isfinite).all():
            raise ValueError(f"{symbol} fills.{column} contains a non-finite value")
    fills = fills.loc[
        (fills["ts_event"] >= start_ns) & (fills["ts_event"] < end_exclusive)
    ].sort_values("ts_event", kind="mergesort")
    fill_rows = fills.to_dict("records")
    fill_index = 0
    quantity = 0.0
    cash = 0.0
    costs = {scenario["name"]: 0.0 for scenario in SCENARIOS}
    daily: list[dict[str, Any]] = []
    for day, close in daily_close.items():
        boundary = int((pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=1)).value)
        while fill_index < len(fill_rows) and int(fill_rows[fill_index]["ts_event"]) < boundary:
            fill = fill_rows[fill_index]
            side = str(fill["side"]).upper()
            if "BUY" in side:
                signed = abs(float(fill["quantity"]))
            elif "SELL" in side:
                signed = -abs(float(fill["quantity"]))
            else:
                raise ValueError(f"{symbol} fill has unsupported side {fill['side']!r}")
            notional = abs(float(fill["quantity"]) * float(fill["price"]))
            quantity += signed
            cash -= signed * float(fill["price"])
            for scenario in SCENARIOS:
                costs[scenario["name"]] += notional * (
                    float(scenario["fee_bps"]) + float(scenario["slippage_bps"])
                ) / 10_000.0
            fill_index += 1
        gross_pnl = cash + quantity * float(close)
        daily.append(
            {
                "date": day.isoformat(),
                "close": float(close),
                "scenarios": {
                    scenario["name"]: {
                        "net_pnl": gross_pnl - costs[scenario["name"]],
                    }
                    for scenario in SCENARIOS
                },
            }
        )

    benchmark: list[dict[str, Any]] = []
    entry_notional = float(expected_size * first_close)
    last_notional = float(expected_size) * float(daily_close.iloc[-1])
    for index, (day, close) in enumerate(daily_close.items()):
        gross = float(expected_size) * (float(close) - float(first_close))
        benchmark.append(
            {
                "date": day.isoformat(),
                "scenarios": {
                    scenario["name"]: {
                        "net_pnl": gross
                        - entry_notional
                        * (float(scenario["fee_bps"]) + float(scenario["slippage_bps"]))
                        / 10_000.0
                        - (
                            last_notional
                            * (
                                float(scenario["fee_bps"])
                                + float(scenario["slippage_bps"])
                            )
                            / 10_000.0
                            if index == len(daily_close) - 1
                            else 0.0
                        )
                    }
                    for scenario in SCENARIOS
                },
            }
        )
    return {
        "symbol": symbol,
        "trade_size": float(expected_size),
        "size_increment": float(increment),
        "fold_first_close": float(first_close),
        "initial_target_notional_usdt": initial_notional,
        "daily": daily,
        "benchmark_daily": benchmark,
        "scenario_metrics": candidate["scenario_metrics"],
    }


def _v5_portfolio_evidence(
    assets: list[tuple[str, Path, dict[str, Any], dict[str, Any]]],
    *,
    start: str,
    end: str,
) -> dict[str, Any]:
    curves = [
        _v5_asset_curve(symbol, report, candidate, start=start, end=end)
        for symbol, _path, report, candidate in assets
    ]
    initial_total = sum(float(curve["initial_target_notional_usdt"]) for curve in curves)
    if initial_total > 100.0:
        raise ValueError("v5 combined initial target notional exceeds 100 USDT")
    dates = [row["date"] for row in curves[0]["daily"]]
    if any([row["date"] for row in curve["daily"]] != dates for curve in curves[1:]):
        raise ValueError("v5 asset daily curves do not share the same dates")
    daily = []
    benchmark_daily = []
    for index, day in enumerate(dates):
        daily.append(
            {
                "date": day,
                "scenarios": {
                    scenario["name"]: {
                        "net_pnl": sum(
                            float(curve["daily"][index]["scenarios"][scenario["name"]]["net_pnl"])
                            for curve in curves
                        ),
                        "equity": 100_000.0
                        + sum(
                            float(curve["daily"][index]["scenarios"][scenario["name"]]["net_pnl"])
                            for curve in curves
                        ),
                    }
                    for scenario in SCENARIOS
                },
            }
        )
        benchmark_daily.append(
            {
                "date": day,
                "scenarios": {
                    scenario["name"]: {
                        "net_pnl": sum(
                            float(curve["benchmark_daily"][index]["scenarios"][scenario["name"]]["net_pnl"])
                            for curve in curves
                        ),
                        "equity": 100_000.0
                        + sum(
                            float(curve["benchmark_daily"][index]["scenarios"][scenario["name"]]["net_pnl"])
                            for curve in curves
                        ),
                    }
                    for scenario in SCENARIOS
                },
            }
        )
    return {
        "notional_audit": {
            "per_asset_target_usdt": 50.0,
            "maximum_total_initial_target_usdt": 100.0,
            "assets": [
                {
                    key: curve[key]
                    for key in (
                        "symbol",
                        "trade_size",
                        "size_increment",
                        "fold_first_close",
                        "initial_target_notional_usdt",
                    )
                }
                for curve in curves
            ],
            "total_initial_target_notional_usdt": initial_total,
            "within_limit": initial_total <= 100.0,
        },
        "asset_cost_results": {
            curve["symbol"]: curve["scenario_metrics"] for curve in curves
        },
        "daily_portfolio_equity": daily,
        "risk_metrics": {
            scenario["name"]: _risk_metrics(daily, scenario["name"])
            for scenario in SCENARIOS
        },
        "benchmark": {
            "identity": "equal_weight_buy_and_hold_same_size_v1",
            "daily_portfolio_equity": benchmark_daily,
            "risk_metrics": {
                scenario["name"]: _risk_metrics(benchmark_daily, scenario["name"])
                for scenario in SCENARIOS
            },
        },
    }


def build_multi_asset_review(
    label: str,
    asset_specs: list[tuple[str, Path]],
) -> dict[str, Any]:
    if not label.strip():
        raise ValueError("label must be non-empty")
    if not asset_specs:
        raise ValueError("provide at least one SYMBOL=alpha_review.json asset")
    symbols = [symbol.upper() for symbol, _path in asset_specs]
    if len(set(symbols)) != len(symbols):
        raise ValueError("asset symbols must be unique")

    assets: list[tuple[str, Path, dict[str, Any], dict[str, Any]]] = []
    for (_raw_symbol, path), symbol in zip(asset_specs, symbols, strict=True):
        report = _load_review(path)
        assets.append((symbol, path, report, _candidate(report, path)))
    sources = {asset[3]["source"] for asset in assets}
    models = {asset[3]["model_version"] for asset in assets}
    windows = {
        (asset[2]["inputs"]["blind_start"], asset[2]["inputs"]["blind_end"])
        for asset in assets
    }
    if len(sources) != 1 or len(models) != 1 or len(windows) != 1:
        raise ValueError("asset reviews have inconsistent source, model, or window")
    source = str(next(iter(sources)))
    model_version = str(next(iter(models)))
    expected_universe = SOURCE_UNIVERSES.get(source)
    if expected_universe is None or set(symbols) != expected_universe:
        raise ValueError(f"{source} requires asset universe {sorted(expected_universe or [])}")

    expected_months = list(assets[0][2]["inputs"].get("expected_months", []))
    if len(expected_months) != 5 or len(set(expected_months)) != 5:
        raise ValueError("portfolio window must contain five complete expected months")
    candidates = [asset[3] for asset in assets]
    scenario_metrics = _sum_metrics(candidates)
    monthly_metrics = _monthly_metrics(candidates, expected_months)
    best_position = max(float(candidate["best_position_base_net_pnl"]) for candidate in candidates)
    base_without_best = float(scenario_metrics["base"]["net_pnl"]) - best_position
    blockers = sorted(
        {
            f"{symbol}:{blocker}"
            for symbol, _path, _report, candidate in assets
            for blocker in candidate.get("blockers", [])
        }
    )
    reproducible = all(candidate.get("reproducible") is True for candidate in candidates)
    if not reproducible:
        blockers.append("portfolio_asset_reproducibility_failed")
    maximum_allowed_assets = SOURCE_MAX_CONCURRENT_ASSETS.get(source, 1)
    exclusivity = _audit_exclusivity(
        [(symbol, path, candidate) for symbol, path, _report, candidate in assets],
        source=source,
        model_version=model_version,
        maximum_allowed_assets=maximum_allowed_assets,
    )
    if not exclusivity["within_limit"]:
        blockers.append(
            "portfolio_asset_overlap"
            if maximum_allowed_assets == 1
            else "portfolio_concurrency_limit_exceeded"
        )

    portfolio_candidate = {
        "label": label,
        "source": source,
        "model_version": model_version,
        "is_research_candidate": True,
        "assets": [
            {
                "symbol": symbol,
                "review_path": str(path),
                "bundle_runs": candidate["bundle_runs"],
                "trade_size": report["inputs"].get("trade_size"),
            }
            for symbol, path, report, candidate in assets
        ],
        "scenario_metrics": scenario_metrics,
        "monthly_metrics": monthly_metrics,
        "fills": sum(int(candidate["fills"]) for candidate in candidates),
        "closed_positions": sum(int(candidate["closed_positions"]) for candidate in candidates),
        "short_positions": sum(int(candidate["short_positions"]) for candidate in candidates),
        "best_position_base_net_pnl": best_position,
        "base_net_without_best_position": base_without_best,
        "reproducible": reproducible,
        "exclusivity": exclusivity,
        "blockers": sorted(set(blockers)),
    }
    v5_evidence: dict[str, Any] = {}
    if source in V5_SOURCES:
        start, end = next(iter(windows))
        v5_evidence = _v5_portfolio_evidence(assets, start=start, end=end)
        portfolio_candidate.update(v5_evidence)
    _assert_finite(portfolio_candidate)
    start, end = next(iter(windows))
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "blind_start": start,
            "blind_end": end,
            "expected_months": expected_months,
            "asset_reviews": [
                {"symbol": symbol, "path": str(path)} for symbol, path in asset_specs
            ],
        },
        "cost_scenarios": list(SCENARIOS),
        "candidates": [portfolio_candidate],
        "monthly_metrics": {label: monthly_metrics},
        **v5_evidence,
        "gates": {
            "spot_long_flat_only": portfolio_candidate["short_positions"] == 0,
            "assets_reproducible": reproducible,
            "portfolio_exclusive": exclusivity["exclusive"],
            "portfolio_concurrency_within_limit": exclusivity["within_limit"],
            "portfolio_initial_notional_within_limit": (
                v5_evidence.get("notional_audit", {}).get("within_limit", True)
            ),
            "evidence_clean": not blockers,
        },
        "recommendation": "portfolio_fold_ready" if not blockers else "reject_portfolio_evidence",
        "boundaries": {
            "diagnostic_only": True,
            "writes_signal_event": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "starts_nautilus": False,
            "resumes_testnet": False,
        },
    }


def _parse_asset(value: str) -> tuple[str, Path]:
    symbol, separator, path = value.partition("=")
    if not separator or not symbol.strip() or not path.strip():
        raise argparse.ArgumentTypeError("asset must be SYMBOL=alpha_review.json")
    return symbol.strip().upper(), Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--asset", action="append", type=_parse_asset, default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(
        json.dumps(
            build_multi_asset_review(args.label, args.asset),
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

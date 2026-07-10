"""Passive cost-sensitive alpha review for ADR-004/ADR-007 bundles.

The reader never starts NautilusTrader, writes signals, loads credentials, or
changes SourcePolicy. It recalculates recorded results under fixed per-fill
fee/slippage scenarios and fails closed on malformed evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from apps.strategies_nautilus.result_schema import BacktestManifest
from apps.strategies_nautilus.runners.backtest_runner import validate_sidecar_bundle

SCHEMA_VERSION = "alpha.review.v1"
ELIGIBLE_SOURCES = frozenset(
    {
        "freqai_linear_walkforward_v1",
        "rule_breakout_v1",
        "rule_dual_momentum_v1",
        "rule_mean_reversion_v1",
        "rule_pullback_regime_v1",
        "rule_market_breadth_v1",
        "rule_relative_value_rotation_v1",
        "rule_trend_regime_v1",
        "rule_vol_squeeze_v1",
        "rule_volume_breakout_v1",
        "rule_xs_momentum_rotation_v1",
    }
)
CURRENT_SOURCE = "freqai_linear_v1"
SCENARIOS = (
    {"name": "gross", "fee_bps": 0.0, "slippage_bps": 0.0},
    {"name": "base", "fee_bps": 10.0, "slippage_bps": 2.0},
    {"name": "stress", "fee_bps": 10.0, "slippage_bps": 5.0},
)
SIDECARS = (
    "orders.parquet",
    "fills.parquet",
    "positions.parquet",
    "account_balances.parquet",
    "signal_lineage.parquet",
)


def build_alpha_review(
    candidate_specs: list[tuple[str, Path]],
    *,
    blind_start: str,
    blind_end: str,
    catalog_path: Path | None = None,
    bar_type: str | None = None,
    trade_size: float = 0.001,
) -> dict[str, Any]:
    start_ns, end_exclusive_ns, months = _blind_window(blind_start, blind_end)
    grouped: dict[str, list[Path]] = defaultdict(list)
    for label, path in candidate_specs:
        if not label.strip():
            raise ValueError("candidate label must be non-empty")
        grouped[label].append(path)
    if not grouped:
        raise ValueError("provide at least one --candidate label=run_dir")

    candidates: list[dict[str, Any]] = []
    input_rows: list[dict[str, Any]] = []
    for label, paths in grouped.items():
        runs = [
            _analyze_bundle(
                path,
                start_ns=start_ns,
                end_exclusive_ns=end_exclusive_ns,
                months=months,
            )
            for path in paths
        ]
        primary = dict(runs[0])
        reproducible = _runs_reproducible(runs)
        source = primary["source"]
        is_research_candidate = source in ELIGIBLE_SOURCES
        blockers = list(primary["blockers"])
        if is_research_candidate and len(runs) < 2:
            blockers.append("reproducibility_run_missing")
        elif is_research_candidate and not reproducible:
            blockers.append("reproducibility_mismatch")

        base_net = float(primary["scenario_metrics"]["base"]["net_pnl"])
        stress_net = float(primary["scenario_metrics"]["stress"]["net_pnl"])
        positive_months = sum(
            1
            for month in primary["monthly_metrics"]
            if float(month["scenarios"]["base"]["net_pnl"]) > 0.0
        )
        positions = int(primary["closed_positions"])
        base_without_best = float(primary["base_net_without_best_position"])
        gates = {
            "base_net_positive": base_net > 0.0,
            "stress_net_positive": stress_net > 0.0,
            "base_net_without_best_position": base_without_best,
            "base_net_without_best_position_positive": base_without_best > 0.0,
            "base_positive_months": positive_months,
            "base_positive_months_required": 4,
            "closed_positions": positions,
            "closed_positions_required": 30,
            "spot_long_flat_only": int(primary["short_positions"]) == 0,
            "evidence_clean": not blockers,
            "reproducible": reproducible if is_research_candidate else None,
        }
        passed = bool(
            is_research_candidate
            and gates["base_net_positive"]
            and gates["stress_net_positive"]
            and gates["base_net_without_best_position_positive"]
            and positive_months >= 4
            and positions >= 30
            and gates["spot_long_flat_only"]
            and not blockers
            and reproducible
        )
        if source == CURRENT_SOURCE and base_net < 0.0:
            recommendation = "demote_to_paper_simulated_recommended"
        elif passed:
            recommendation = "eligible_for_paper_shadow_review"
        elif (
            is_research_candidate
            and base_net > 0.0
            and stress_net > 0.0
            and positions < 30
        ):
            recommendation = "insufficient_evidence"
        else:
            recommendation = "stop_before_testnet_resume"

        primary.update(
            {
                "label": label,
                "bundle_runs": [run["bundle_dir"] for run in runs],
                "run_count": len(runs),
                "is_research_candidate": is_research_candidate,
                "reproducible": reproducible,
                "blockers": sorted(set(blockers)),
                "gates": gates,
                "passed": passed,
                "recommendation": recommendation,
            }
        )
        candidates.append(primary)
        input_rows.extend(
            {
                "label": label,
                "bundle_dir": run["bundle_dir"],
                "run_id": run["run_id"],
                "manifest_sha256": run["manifest_sha256"],
                "fills_sha256": run["fills_sha256"],
            }
            for run in runs
        )

    if catalog_path is not None:
        if bar_type is None:
            raise ValueError("--bar-type is required with --catalog-path")
        candidates.append(
            _buy_and_hold_benchmark(
                catalog_path=catalog_path,
                bar_type=bar_type,
                trade_size=trade_size,
                start_ns=start_ns,
                end_exclusive_ns=end_exclusive_ns,
                months=months,
            )
        )

    passed = [candidate for candidate in candidates if candidate.get("passed")]
    insufficient = [
        candidate
        for candidate in candidates
        if candidate.get("recommendation") == "insufficient_evidence"
    ]
    recommendation = (
        "eligible_for_paper_shadow_review"
        if passed
        else "insufficient_evidence"
        if insufficient
        else "stop_before_testnet_resume"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "blind_start": blind_start,
            "blind_end": blind_end,
            "expected_months": months,
            "bundles": input_rows,
            "catalog_path": str(catalog_path) if catalog_path else None,
            "bar_type": bar_type,
            "trade_size": trade_size,
        },
        "cost_scenarios": list(SCENARIOS),
        "candidates": candidates,
        "monthly_metrics": {
            candidate["label"]: candidate["monthly_metrics"] for candidate in candidates
        },
        "gates": {
            "eligible_candidate_count": sum(
                1 for candidate in candidates if candidate.get("is_research_candidate")
            ),
            "passed_candidate_count": len(passed),
            "positive_months_required": 4,
            "closed_positions_required": 30,
            "base_and_stress_must_be_positive": True,
            "base_without_best_position_must_be_positive": True,
        },
        "recommendation": recommendation,
        "boundaries": {
            "places_orders": False,
            "starts_nautilus": False,
            "writes_signal_event": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "authorizes_live_trading": False,
            "resumes_testnet_continuity": False,
        },
    }


def _analyze_bundle(
    bundle_dir: Path,
    *,
    start_ns: int,
    end_exclusive_ns: int,
    months: list[str],
) -> dict[str, Any]:
    manifest_path = bundle_dir / "run_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    payload = _strict_json_loads(manifest_bytes)
    if not isinstance(payload, dict):
        raise ValueError(f"{manifest_path} top-level JSON must be an object")
    manifest = BacktestManifest.model_validate(payload)
    if manifest.kind not in {"backtest", "paper"}:
        raise ValueError(f"{bundle_dir} kind={manifest.kind!r} is not backtest/paper")
    validate_sidecar_bundle(bundle_dir)
    fills = pd.read_parquet(bundle_dir / "fills.parquet")
    positions = pd.read_parquet(bundle_dir / "positions.parquet")
    lineage = pd.read_parquet(bundle_dir / "signal_lineage.parquet")

    blockers: list[str] = []
    if manifest.git_dirty:
        blockers.append("git_dirty")
    start = int(pd.Timestamp(manifest.backtest_start).value)
    end = int(pd.Timestamp(manifest.backtest_end).value)
    if start > start_ns or end < end_exclusive_ns - 60_000_000_000:
        blockers.append("blind_window_not_fully_covered")
    expected_rows = (end_exclusive_ns - start_ns) // 60_000_000_000
    catalog_rows = int(manifest.data_catalog.instruments[0].rows)
    if (
        start == start_ns
        and end >= end_exclusive_ns - 60_000_000_000
        and catalog_rows != expected_rows
    ):
        blockers.append(f"catalog_rows={catalog_rows}!=expected={expected_rows}")

    fill_ts = _finite_numeric(fills, "ts_event", blockers, integer=True)
    fill_qty = _finite_numeric(fills, "quantity", blockers)
    fill_price = _finite_numeric(fills, "price", blockers)
    fill_commission = _finite_numeric(fills, "commission", blockers)
    fill_mask = (fill_ts >= start_ns) & (fill_ts < end_exclusive_ns)
    fills_window = fills.loc[fill_mask].copy()
    fills_window["_ts"] = fill_ts.loc[fill_mask].astype("int64")
    fills_window["_notional"] = (
        fill_qty.loc[fill_mask].abs() * fill_price.loc[fill_mask].abs()
    )
    fills_window["_commission"] = fill_commission.loc[fill_mask]
    if (fills_window["_notional"] <= 0.0).any():
        blockers.append("non_positive_fill_notional")

    position_ts = _finite_numeric(positions, "closed_ts", blockers, integer=True)
    position_pnl = _finite_numeric(positions, "realized_pnl", blockers)
    position_mask = (position_ts >= start_ns) & (position_ts < end_exclusive_ns)
    positions_window = positions.loc[position_mask].copy()
    positions_window["_ts"] = position_ts.loc[position_mask].astype("int64")
    positions_window["_pnl"] = position_pnl.loc[position_mask]
    _ensure_concentration_columns(positions_window, fills)
    fills_for_positions = fills.copy()
    fills_for_positions["_order_id"] = fills["order_id"].astype(str)
    fills_for_positions["_notional"] = fill_qty.abs() * fill_price.abs()
    fills_for_positions["_commission"] = fill_commission
    positions_window["_position_id"] = positions_window["position_id"].astype(str)
    if positions_window["_position_id"].duplicated().any():
        blockers.append("duplicate_position_id")
    position_base_net: list[float] = []
    concentration_columns = [
        "_position_id",
        "_pnl",
        "opening_order_id",
        "closing_order_id",
    ]
    for position in positions_window[concentration_columns].to_dict("records"):
        order_ids = {
            str(position["opening_order_id"]),
            str(position["closing_order_id"]),
        }
        position_fills = fills_for_positions.loc[
            fills_for_positions["_order_id"].isin(order_ids)
        ]
        if position_fills.empty:
            blockers.append(f"position_without_fills:{position['_position_id']}")
            continue
        position_base_net.append(
            float(position["_pnl"])
            + float(position_fills["_commission"].sum())
            - float(position_fills["_notional"].sum()) * 12.0 / 10_000.0
        )
    best_position_base_net = max(position_base_net) if position_base_net else 0.0
    base_net_without_best_position = (
        float(sum(position_base_net)) - best_position_base_net
    )
    short_positions = int(
        positions_window.get("side", pd.Series(dtype="string"))
        .astype(str)
        .str.upper()
        .str.contains("SHORT")
        .sum()
    )

    lineage_ids = set(lineage.get("signal_id", pd.Series(dtype="string")).astype(str))
    fill_ids = fills_window.get("signal_id", pd.Series(dtype="string")).astype(str)
    nonblank_fill_ids = fill_ids.loc[fill_ids.str.len() > 0]
    invalid_fill_lineage = int(
        sum(signal_id not in lineage_ids for signal_id in nonblank_fill_ids)
    )
    blank_fill_mask = fill_ids.str.len() == 0
    system_exit_fills = int(blank_fill_mask.sum())
    if system_exit_fills:
        blank_fill_times = fills_window.loc[blank_fill_mask, "_ts"]
        if (blank_fill_times < end_exclusive_ns - 60_000_000_000).any():
            invalid_fill_lineage += int(
                (blank_fill_times < end_exclusive_ns - 60_000_000_000).sum()
            )
    if invalid_fill_lineage:
        blockers.append(f"invalid_fill_lineage={invalid_fill_lineage}")
    reasons = lineage.get("reason", pd.Series(dtype="string")).astype(str)
    if reasons.str.contains("kill_switch", case=False, regex=False).any():
        blockers.append("kill_switch_lineage")
    if reasons.str.contains("data_gap", case=False, regex=False).any():
        blockers.append("data_gap_lineage")
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    if _safe_int(runtime.get("data_gap_count"), 0) > 0:
        blockers.append("runtime_data_gap")

    scenario_metrics: dict[str, dict[str, float]] = {}
    monthly_metrics = [
        {"month": month, "scenarios": {scenario["name"]: {} for scenario in SCENARIOS}}
        for month in months
    ]
    recorded_pnl = float(positions_window["_pnl"].sum())
    recorded_commission = float(fills_window["_commission"].sum())
    total_notional = float(fills_window["_notional"].sum())
    for scenario in SCENARIOS:
        fee = total_notional * float(scenario["fee_bps"]) / 10_000.0
        slippage = total_notional * float(scenario["slippage_bps"]) / 10_000.0
        scenario_metrics[str(scenario["name"])] = {
            "recorded_pnl": recorded_pnl,
            "recorded_commission": recorded_commission,
            "modeled_fee": fee,
            "modeled_slippage": slippage,
            "net_pnl": recorded_pnl + recorded_commission - fee - slippage,
        }

    for row in monthly_metrics:
        month = row["month"]
        month_start = pd.Timestamp(f"{month}-01", tz="UTC")
        month_end = month_start + pd.offsets.MonthBegin(1)
        position_month = positions_window.loc[
            (positions_window["_ts"] >= int(month_start.value))
            & (positions_window["_ts"] < int(month_end.value))
        ]
        fill_month = fills_window.loc[
            (fills_window["_ts"] >= int(month_start.value))
            & (fills_window["_ts"] < int(month_end.value))
        ]
        gross = float(position_month["_pnl"].sum())
        commission = float(fill_month["_commission"].sum())
        notional = float(fill_month["_notional"].sum())
        for scenario in SCENARIOS:
            fee = notional * float(scenario["fee_bps"]) / 10_000.0
            slippage = notional * float(scenario["slippage_bps"]) / 10_000.0
            row["scenarios"][str(scenario["name"])] = {
                "recorded_pnl": gross,
                "recorded_commission": commission,
                "modeled_fee": fee,
                "modeled_slippage": slippage,
                "net_pnl": gross + commission - fee - slippage,
            }

    source = _source_from_manifest(manifest)
    model_version = _model_from_manifest(manifest)
    fills_sha = _sha256_file(bundle_dir / "fills.parquet")
    return {
        "bundle_dir": str(bundle_dir),
        "run_id": manifest.run_id,
        "kind": manifest.kind,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fills_sha256": fills_sha,
        "source": source,
        "model_version": model_version,
        "backtest_start": manifest.backtest_start,
        "backtest_end": manifest.backtest_end,
        "catalog_rows": catalog_rows,
        "fills": len(fills_window),
        "closed_positions": len(positions_window),
        "short_positions": short_positions,
        "invalid_fill_lineage": invalid_fill_lineage,
        "system_exit_fills": system_exit_fills,
        "best_position_base_net_pnl": best_position_base_net,
        "base_net_without_best_position": base_net_without_best_position,
        "scenario_metrics": scenario_metrics,
        "monthly_metrics": monthly_metrics,
        "blockers": sorted(set(blockers)),
    }


def _ensure_concentration_columns(
    positions_window: pd.DataFrame,
    fills: pd.DataFrame,
) -> None:
    """Require order linkage, except absent extras on a validated empty sidecar."""
    required = {"position_id", "opening_order_id", "closing_order_id"}
    missing = required - set(positions_window.columns)
    if missing and positions_window.empty:
        for column in missing:
            positions_window[column] = pd.Series(dtype="string")
        missing = set()
    if missing or "order_id" not in fills:
        absent = sorted(missing | ({"order_id"} - set(fills.columns)))
        raise ValueError(f"required column missing: {', '.join(absent)}")


def _buy_and_hold_benchmark(
    *,
    catalog_path: Path,
    bar_type: str,
    trade_size: float,
    start_ns: int,
    end_exclusive_ns: int,
    months: list[str],
) -> dict[str, Any]:
    from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    bars = catalog.bars(bar_types=[bar_type], start=start_ns, end=end_exclusive_ns - 1)
    bars = sorted(bars, key=lambda bar: int(bar.ts_event))
    if not bars:
        raise ValueError("buy-and-hold benchmark found no catalog bars")
    expected = (end_exclusive_ns - start_ns) // 60_000_000_000
    blockers = [] if len(bars) == expected else [f"catalog_rows={len(bars)}!=expected={expected}"]
    first_price = float(bars[0].close)
    last_price = float(bars[-1].close)
    entry_notional = abs(trade_size * first_price)
    exit_notional = abs(trade_size * last_price)
    total_notional = entry_notional + exit_notional
    gross = trade_size * (last_price - first_price)
    scenarios: dict[str, dict[str, float]] = {}
    for scenario in SCENARIOS:
        fee = total_notional * float(scenario["fee_bps"]) / 10_000.0
        slippage = total_notional * float(scenario["slippage_bps"]) / 10_000.0
        scenarios[str(scenario["name"])] = {
            "recorded_pnl": gross,
            "recorded_commission": 0.0,
            "modeled_fee": fee,
            "modeled_slippage": slippage,
            "net_pnl": gross - fee - slippage,
        }

    frame = pd.DataFrame(
        {
            "ts": [int(bar.ts_event) for bar in bars],
            "close": [float(bar.close) for bar in bars],
        }
    )
    monthly: list[dict[str, Any]] = []
    previous = first_price
    for index, month in enumerate(months):
        month_start = pd.Timestamp(f"{month}-01", tz="UTC")
        month_end = month_start + pd.offsets.MonthBegin(1)
        month_frame = frame.loc[
            (frame["ts"] >= int(month_start.value))
            & (frame["ts"] < int(month_end.value))
        ]
        month_close = float(month_frame["close"].iloc[-1])
        pnl = trade_size * (month_close - previous)
        month_notional = (entry_notional if index == 0 else 0.0) + (
            exit_notional if index == len(months) - 1 else 0.0
        )
        row = {"month": month, "scenarios": {}}
        for scenario in SCENARIOS:
            fee = month_notional * float(scenario["fee_bps"]) / 10_000.0
            slippage = month_notional * float(scenario["slippage_bps"]) / 10_000.0
            row["scenarios"][str(scenario["name"])] = {
                "recorded_pnl": pnl,
                "recorded_commission": 0.0,
                "modeled_fee": fee,
                "modeled_slippage": slippage,
                "net_pnl": pnl - fee - slippage,
            }
        monthly.append(row)
        previous = month_close
    return {
        "label": "buy_and_hold",
        "bundle_dir": None,
        "bundle_runs": [],
        "run_count": 0,
        "kind": "benchmark",
        "source": "benchmark_buy_and_hold",
        "model_version": "same-size-spot-v1",
        "catalog_rows": len(bars),
        "fills": 2,
        "closed_positions": 1,
        "short_positions": 0,
        "scenario_metrics": scenarios,
        "monthly_metrics": monthly,
        "blockers": blockers,
        "is_research_candidate": False,
        "reproducible": None,
        "gates": {},
        "passed": False,
        "recommendation": "reference_only",
    }


def _runs_reproducible(runs: list[dict[str, Any]]) -> bool:
    if len(runs) < 2:
        return False
    reference = _reproducibility_fingerprint(runs[0])
    return all(_reproducibility_fingerprint(run) == reference for run in runs[1:])


def _reproducibility_fingerprint(run: dict[str, Any]) -> str:
    stable = {
        "source": run["source"],
        "model_version": run["model_version"],
        "catalog_rows": run["catalog_rows"],
        "fills_sha256": run["fills_sha256"],
        "closed_positions": run["closed_positions"],
        "short_positions": run["short_positions"],
        "scenario_metrics": run["scenario_metrics"],
        "monthly_metrics": run["monthly_metrics"],
        "best_position_base_net_pnl": run["best_position_base_net_pnl"],
        "base_net_without_best_position": run["base_net_without_best_position"],
        "blockers": run["blockers"],
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _blind_window(start: str, end: str) -> tuple[int, int, list[str]]:
    start_ts = pd.Timestamp(start, tz="UTC")
    end_date = pd.Timestamp(end, tz="UTC")
    if end_date < start_ts:
        raise ValueError("blind_end must not be before blind_start")
    end_exclusive = end_date + pd.Timedelta(days=1)
    if start_ts.day != 1 or end_date != (end_date + pd.offsets.MonthEnd(0)).normalize():
        raise ValueError("blind window must cover complete calendar months")
    months = [str(period) for period in pd.period_range(start_ts.tz_localize(None), end_date.tz_localize(None), freq="M")]
    if len(months) != 5:
        raise ValueError(f"blind window must contain exactly 5 months, got {len(months)}")
    return int(start_ts.value), int(end_exclusive.value), months


def _finite_numeric(
    frame: pd.DataFrame,
    column: str,
    blockers: list[str],
    *,
    integer: bool = False,
) -> pd.Series:
    if column not in frame:
        raise ValueError(f"required column missing: {column}")
    values = pd.to_numeric(frame[column], errors="coerce")
    invalid = values.isna() | ~values.map(math.isfinite)
    if invalid.any():
        blockers.append(f"invalid_numeric:{column}={int(invalid.sum())}")
        values = values.fillna(0)
    return values.astype("int64" if integer else "float64")


def _source_from_manifest(manifest: BacktestManifest) -> str | None:
    value = manifest.signal_source.filter.get("source")
    return str(value) if isinstance(value, str) and value else None


def _model_from_manifest(manifest: BacktestManifest) -> str | None:
    value = manifest.signal_source.filter.get("model_version")
    return str(value) if isinstance(value, str) and value else None


def _strict_json_loads(raw: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cost-Sensitive Alpha Review",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Blind window: `{report['inputs']['blind_start']}` through `{report['inputs']['blind_end']}`",
        f"- Recommendation: `{report['recommendation']}`",
        "- Passive boundary: no orders, credentials, policy mutation, or testnet continuity",
        "",
        "## Candidates",
        "",
        "| label | source / model | base net | base w/o best | stress net | positive months | positions | short | reproducible | recommendation | blockers |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for candidate in report["candidates"]:
        base = candidate["scenario_metrics"]["base"]["net_pnl"]
        base_without_best = candidate.get("base_net_without_best_position", 0.0)
        stress = candidate["scenario_metrics"]["stress"]["net_pnl"]
        positive = sum(
            1
            for month in candidate["monthly_metrics"]
            if month["scenarios"]["base"]["net_pnl"] > 0
        )
        lines.append(
            f"| `{candidate['label']}` | `{candidate['source']} / {candidate['model_version']}` "
            f"| {base:.8f} | {base_without_best:.8f} | {stress:.8f} | {positive}/5 "
            f"| {candidate['closed_positions']} | {candidate['short_positions']} "
            f"| {candidate.get('reproducible')} | `{candidate['recommendation']}` "
            f"| {', '.join(candidate.get('blockers') or []) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def _parse_candidate(value: str) -> tuple[str, Path]:
    label, separator, path = value.partition("=")
    if not separator or not label.strip() or not path.strip():
        raise argparse.ArgumentTypeError("candidate must be label=run_dir")
    return label.strip(), Path(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--candidate", action="append", type=_parse_candidate, default=[])
    parser.add_argument("--blind-start", required=True, help="First day of first month")
    parser.add_argument("--blind-end", required=True, help="Last day of fifth month")
    parser.add_argument("--catalog-path", type=Path)
    parser.add_argument("--bar-type")
    parser.add_argument("--trade-size", type=float, default=0.001)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--markdown", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_alpha_review(
            args.candidate,
            blind_start=args.blind_start,
            blind_end=args.blind_end,
            catalog_path=args.catalog_path,
            bar_type=args.bar_type,
            trade_size=args.trade_size,
        )
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        else:
            print(render_markdown(report), end="")
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0


__all__ = [
    "CURRENT_SOURCE",
    "ELIGIBLE_SOURCES",
    "SCENARIOS",
    "SCHEMA_VERSION",
    "build_alpha_review",
    "main",
    "render_markdown",
]


if __name__ == "__main__":
    raise SystemExit(main())

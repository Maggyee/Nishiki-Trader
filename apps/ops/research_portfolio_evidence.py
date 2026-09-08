"""Read-only accounting of hash-verified historical Nautilus fills, never execution.

Method: docs/progress/portfolio-evidence-study-2026-09-08.md. Only already-opened
2023–2025 confirmation evidence; output is diagnostic and cannot grant promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from apps.ops.research_portfolio_monitor import CANDIDATE_SPECS

START = pd.Timestamp("2023-01-01", tz="UTC")
END = pd.Timestamp("2026-01-01", tz="UTC")
SIZE = 0.001
COSTS = {"gross": 0.0, "base": 12.0, "stress": 15.0}


def verified_bytes(path: Path, expected: str) -> bytes:
    if not isinstance(expected, str) or len(expected.removeprefix("sha256:")) != 64:
        raise ValueError("missing recorded SHA256")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"SHA256 mismatch: {path}")
    return raw


def load_benchmark(root: Path) -> tuple[pd.Series, dict]:
    qualification = root / "docs/progress/phase-2-research-v49-provider-qualification.json"
    evidence_raw = qualification.read_bytes()
    evidence = json.loads(evidence_raw)["closes"]
    raw = verified_bytes(root / evidence["path"], evidence["sha256"])
    frame = pd.read_csv(io.BytesIO(raw))
    dates = pd.to_datetime(frame["date"], utc=True, errors="raise")
    prices = pd.to_numeric(frame["close"], errors="raise")
    if (
        dates.duplicated().any()
        or not dates.is_monotonic_increasing
        or not np.isfinite(prices).all()
        or (prices <= 0).any()
    ):
        raise ValueError("invalid benchmark prices or dates")
    if dates.max() >= END:
        raise ValueError("benchmark file extends beyond authorized historical window")
    series = pd.Series(prices.to_numpy(), index=pd.DatetimeIndex(dates))
    grid = pd.date_range(START - pd.Timedelta(days=1), END - pd.Timedelta(days=1), freq="D")
    series = series.reindex(grid)
    if series.isna().any():
        raise ValueError("benchmark daily coverage incomplete; no forward fill permitted")
    return series, {
        "path": evidence["path"],
        "sha256": evidence["sha256"],
        "qualification_sha256": hashlib.sha256(evidence_raw).hexdigest(),
        "window_start_mark": str(grid[0].date()),
        "rows": len(series),
    }


def audit_fills(frame: pd.DataFrame, identity: dict) -> pd.DataFrame:
    required = {"fill_id", "ts_event", "side", "quantity", "price", "signal_id", "instrument_id"}
    if not required.issubset(frame) or frame.empty:
        raise ValueError("missing fill columns or empty fill evidence")
    fills = frame.copy()
    for key in ("ts_event", "quantity", "price"):
        fills[key] = pd.to_numeric(fills[key], errors="raise")
        if not np.isfinite(fills[key]).all():
            raise ValueError("nonfinite fill value")
    if (fills["ts_event"] % 1 != 0).any() or not fills["ts_event"].is_monotonic_increasing:
        raise ValueError("fill timestamps must be ordered integer nanoseconds")
    if not fills["ts_event"].between(START.value, END.value - 1).all():
        raise ValueError("fill outside authorized confirmation window")
    if fills["fill_id"].duplicated().any() or not fills["side"].isin(["BUY", "SELL"]).all():
        raise ValueError("duplicate fill identity or invalid side")
    if not np.allclose(fills["quantity"], SIZE, rtol=0, atol=1e-12) or (fills["price"] <= 0).any():
        raise ValueError("expected positive fixed-size BTC fills")
    if not fills["instrument_id"].eq("BTCUSDT.BINANCE").all():
        raise ValueError("unexpected fill instrument")
    prefix = identity["source"] + ":" + identity["model_version"] + ":BTCUSDT:BINANCE:"
    ids = fills["signal_id"].astype(str)
    identified = ids.str.startswith(prefix)
    # BaselineNautilusStrategy.on_stop closes the remaining position without
    # a signal tag. Only the final SELL at the exact retained backtest end is
    # allowed this exception; all other missing/mismatched lineage fails closed.
    terminal = (
        ids.eq("")
        & fills["side"].eq("SELL")
        & fills["ts_event"].eq((END - pd.Timedelta(hours=1)).value)
    )
    terminal &= np.arange(len(fills)) == len(fills) - 1
    if not (identified | terminal).all():
        raise ValueError("fill signal lineage identity mismatch")
    fills["terminal_close_without_signal"] = terminal
    fills["signed_qty"] = fills["quantity"].where(fills["side"] == "BUY", -fills["quantity"])
    position = fills["signed_qty"].cumsum()
    if (
        (position < -1e-12).any()
        or (position > SIZE + 1e-12).any()
        or abs(position.iloc[-1]) > 1e-12
    ):
        raise ValueError("unexpected short, multiple-sized or unclosed position")
    return fills


def account_fills(fills: pd.DataFrame, closes: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Linear cash accounting of recorded fills; no synthetic trades or sizing."""
    grid = closes.index[1:]
    days = pd.to_datetime(fills["ts_event"], unit="ns", utc=True).dt.normalize()
    deltas = pd.DataFrame(
        {
            "qty": fills["signed_qty"].to_numpy(),
            "cash": (-fills["signed_qty"] * fills["price"]).to_numpy(),
            "notional": (fills["quantity"] * fills["price"]).to_numpy(),
        },
        index=days,
    )
    cumulative = deltas.groupby(level=0).sum().reindex(grid, fill_value=0).cumsum()
    curves = pd.DataFrame(index=grid)
    curves["qty"] = cumulative["qty"]
    gross = cumulative["cash"] + cumulative["qty"] * closes.iloc[1:]
    for scenario, bps in COSTS.items():
        curves[scenario] = gross - cumulative["notional"] * bps / 10000
    # Exact elapsed-time exposure, including the initial flat interval.
    stamps = np.r_[START.value, fills["ts_event"].to_numpy(dtype="int64"), END.value]
    quantities = np.r_[0.0, fills["signed_qty"].cumsum().to_numpy()]
    fraction = float(np.sum(np.diff(stamps) / (END.value - START.value) * quantities) / SIZE)
    bh_gross = SIZE * float(closes.iloc[-1] - closes.iloc[0])
    bh_notional = SIZE * float(closes.iloc[-1] + closes.iloc[0])
    benchmarks = {s: bh_gross - bh_notional * bps / 10000 for s, bps in COSTS.items()}
    metrics = {
        "fills": len(fills),
        "time_in_market_fraction": fraction,
        "terminal_close_without_signal_count": int(fills["terminal_close_without_signal"].sum()),
        "net_pnl_usdt": {s: float(curves[s].iloc[-1]) for s in COSTS},
        "daily_marked_max_drawdown_usdt": {s: drawdown(curves[s]) for s in COSTS},
        "buy_and_hold_usdt": benchmarks,
        "exposure_matched_buy_and_hold_usdt": {
            s: value * fraction for s, value in benchmarks.items()
        },
        "excess_over_exposure_matched_usdt": {
            s: float(curves[s].iloc[-1]) - value * fraction for s, value in benchmarks.items()
        },
        "account_return_pct": None,
        "actual_account_leverage": None,
    }
    return curves, metrics


def drawdown(curve: pd.Series) -> float:
    values = np.r_[0.0, curve.to_numpy()]
    return float(np.max(np.maximum.accumulate(values) - values))


def load_candidate(root: Path, spec: dict, closes: pd.Series) -> tuple[pd.DataFrame, dict]:
    path = root / f"docs/progress/phase-2-research-{spec['protocol']}-confirmation-results.json"
    result_raw = path.read_bytes()
    result = json.loads(result_raw)
    candidate = result.get("candidate")
    candidate = candidate if isinstance(candidate, dict) else result
    for field in ("source", "model_version"):
        if candidate[field] != spec[field]:
            raise ValueError("committed result identity mismatch")
    refs = candidate.get("bundle_runs", [])
    if not refs or not all(key in refs[0] for key in ("path", "manifest_sha256", "fills_sha256")):
        raise ValueError("committed result lacks manifest-and-fills hash references")
    # Use the original primary run, never select on returns or file availability.
    ref = refs[0]
    bundle = root / ref["path"]
    manifest = json.loads(verified_bytes(bundle / "run_manifest.json", ref["manifest_sha256"]))
    if manifest["kind"] != "backtest" or manifest["git_dirty"] is not False:
        raise ValueError("not a clean historical Nautilus backtest")
    if not manifest.get("nautilus_version"):
        raise ValueError("execution provenance missing")
    if pd.Timestamp(manifest["backtest_start"]) != START or pd.Timestamp(
        manifest["backtest_end"]
    ) != END - pd.Timedelta(hours=1):
        raise ValueError("backtest window does not match the fixed study")
    filters = manifest["signal_source"]["filter"]
    if any(filters[k] != spec[k] for k in ("source", "model_version")):
        raise ValueError("manifest source identity mismatch")
    fills_raw = verified_bytes(bundle / "fills.parquet", ref["fills_sha256"])
    fills = audit_fills(pd.read_parquet(io.BytesIO(fills_raw)), spec)
    curves, metrics = account_fills(fills, closes)
    for scenario in ("base", "stress"):
        if not math.isclose(
            metrics["net_pnl_usdt"][scenario],
            candidate[f"{scenario}_net_pnl"],
            abs_tol=1e-7,
            rel_tol=1e-9,
        ):
            raise ValueError(f"{scenario} cash accounting does not reconcile with committed PnL")
    execution_path = fills[["ts_event", "side", "quantity", "price"]].to_json(
        orient="records", double_precision=15
    )
    metrics.update(
        protocol=spec["protocol"],
        source=spec["source"],
        model_version=spec["model_version"],
        evidence={**ref, "confirmation_result_sha256": hashlib.sha256(result_raw).hexdigest()},
        execution_path_sha256=hashlib.sha256(execution_path.encode()).hexdigest(),
    )
    return curves, metrics


def basket_metrics(curves: dict[str, pd.DataFrame], weights: dict[str, float]) -> dict:
    aggregate = sum(curves[p][list(COSTS)] * weight for p, weight in weights.items())
    quantity = sum(curves[p]["qty"] * weight for p, weight in weights.items())
    leave_one_out = {}
    for p, weight in weights.items():
        without = aggregate["base"] - weight * curves[p]["base"]
        leave_one_out[p] = {
            "base_pnl_contribution_usdt": float(weight * curves[p]["base"].iloc[-1]),
            "base_max_drawdown_without_usdt": drawdown(without),
            "base_drawdown_increase_usdt": drawdown(aggregate["base"]) - drawdown(without),
        }
    return {
        "diagnostic_weights_not_source_policy": weights,
        "net_pnl_usdt": {s: float(aggregate[s].iloc[-1]) for s in COSTS},
        "daily_marked_max_drawdown_usdt": {s: drawdown(aggregate[s]) for s in COSTS},
        "max_daily_marked_btc_quantity": float(quantity.max()),
        "leave_one_out": leave_one_out,
        "account_return_pct": None,
        "actual_account_leverage": None,
    }


def build_report(root: Path) -> dict:
    closes, benchmark = load_benchmark(root)
    included, excluded, curves = [], [], {}
    for spec in CANDIDATE_SPECS:
        try:
            curve, metrics = load_candidate(root, spec, closes)
            curves[spec["protocol"]] = curve
            included.append(metrics)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            excluded.append({"protocol": spec["protocol"], "reason": f"{type(exc).__name__}:{exc}"})
    clusters = {}
    for entry in included:
        clusters.setdefault(entry["execution_path_sha256"], []).append(entry["protocol"])
    duplicate_groups = [members for members in clusters.values() if len(members) > 1]
    correlations, overlaps = {}, {}
    for left in curves:
        correlations[left], overlaps[left] = {}, {}
        for right in curves:
            a, b = curves[left]["base"].diff(), curves[right]["base"].diff()
            a.iloc[0], b.iloc[0] = curves[left]["base"].iloc[0], curves[right]["base"].iloc[0]
            value = float(a.corr(b)) if a.nunique() > 1 and b.nunique() > 1 else None
            correlations[left][right] = value
            qa, qb = curves[left]["qty"] > 1e-12, curves[right]["qty"] > 1e-12
            union = int((qa | qb).sum())
            overlaps[left][right] = float((qa & qb).sum()) / union if union else None
    return {
        "schema_version": "research.portfolio_evidence.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "docs/progress/portfolio-evidence-study-2026-09-08.md",
        "window": {
            "start": str(START.date()),
            "end_inclusive": "2025-12-31",
            "daily_samples": len(closes) - 1,
        },
        "accounting": {
            "original_sleeve_btc_quantity": SIZE,
            "cost_bps_per_fill": COSTS,
            "costs_replace_recorded_commissions": True,
            "mark_frequency": "daily UTC close",
        },
        "cohort_status": "complete" if not excluded else "partial" if included else "blocked",
        "requested_candidates": len(CANDIDATE_SPECS),
        "verified_candidates": len(included),
        "benchmark": benchmark,
        "candidates": included,
        "excluded": excluded,
        "duplicate_execution_groups": duplicate_groups,
        "daily_pnl_correlation": correlations,
        "daily_holding_jaccard_overlap": overlaps,
        "raw_fixed_quantity_basket": basket_metrics(curves, dict.fromkeys(curves, 1.0))
        if curves
        else None,
        "duplicate_normalized_diagnostic": basket_metrics(
            curves, {p: 1 / len(group) for group in clusters.values() for p in group}
        )
        if curves
        else None,
        "limitations": [
            "partial cohort cannot establish ten-candidate portfolio performance"
            if excluded
            else "retrospective diagnostics only",
            "verified account equity unavailable; leverage and percentage return are not inferred",
            "daily marks do not measure intraday drawdown",
            "exposure matching does not establish statistical significance or match volatility",
            "no portfolio allocation or promotion is authorized",
        ],
        "boundaries": {
            "reads_retained_evidence_only": True,
            "writes_signals": False,
            "creates_fills": False,
            "changes_source_policy": False,
            "opens_future_blind": False,
            "touches_live_path": False,
        },
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Retained-fill portfolio evaluation — 2026-09-08",
        "",
        f"Cohort: **{report['cohort_status']}**, {report['verified_candidates']}/{report['requested_candidates']} candidates verified.",
        "2023–2025, 0.001 BTC per original sleeve, 12/15 bps per-fill base/stress costs.",
        "Not a new backtest, actual account return, optimized portfolio or promotion decision.",
        "",
        "| Candidate | Base PnL | Stress PnL | Holding fraction | Base exposure-matched B&H | Base excess | Daily base drawdown |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in report["candidates"]:
        lines.append(
            f"| {c['protocol']} | {c['net_pnl_usdt']['base']:.2f} | {c['net_pnl_usdt']['stress']:.2f} | "
            f"{c['time_in_market_fraction']:.1%} | {c['exposure_matched_buy_and_hold_usdt']['base']:.2f} | "
            f"{c['excess_over_exposure_matched_usdt']['base']:.2f} | {c['daily_marked_max_drawdown_usdt']['base']:.2f} |"
        )
    lines += [
        "",
        "All monetary values are USDT, not percentage returns.",
        "",
        "## Duplicate exposure",
        "",
        f"Exact execution-path groups: {report['duplicate_execution_groups']}.",
        "Weights in the JSON are diagnostic accounting weights, not authorized position sizing.",
        "",
        "## Basket diagnostics",
        "",
    ]
    for key in ("raw_fixed_quantity_basket", "duplicate_normalized_diagnostic"):
        basket = report[key]
        if basket:
            lines.append(
                f"- {key}: base {basket['net_pnl_usdt']['base']:.2f}, stress {basket['net_pnl_usdt']['stress']:.2f}, "
                f"daily base drawdown {basket['daily_marked_max_drawdown_usdt']['base']:.2f} USDT."
            )
    lines += [
        "",
        "## Dependence and marginal contribution",
        "",
        "The JSON records full daily PnL correlation and daily holding Jaccard matrices.",
        "The following leave-one-out figures use the raw fixed-quantity basket; removing a sleeve also removes its exposure.",
        "",
        "| Candidate | Base PnL contribution | Base drawdown without sleeve | Drawdown increase from sleeve |",
        "| --- | ---: | ---: | ---: |",
    ]
    basket = report["raw_fixed_quantity_basket"]
    if basket:
        for protocol, row in basket["leave_one_out"].items():
            lines.append(
                f"| {protocol} | {row['base_pnl_contribution_usdt']:.2f} | "
                f"{row['base_max_drawdown_without_usdt']:.2f} | {row['base_drawdown_increase_usdt']:.2f} |"
            )
    lines += ["", "## Excluded evidence", ""]
    lines += [f"- {r['protocol']}: {r['reason']}" for r in report["excluded"]]
    lines += ["", "## Limitations", ""] + [f"- {s}" for s in report["limitations"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args(argv)
    if (
        args.output_json.exists()
        or args.output_md.exists()
        or args.output_json.resolve() == args.output_md.resolve()
    ):
        parser.error("output files must be distinct new paths; reports are immutable")
    report = build_report(args.repo_root.resolve())
    with args.output_json.open("x") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    with args.output_md.open("x") as handle:
        handle.write(render_markdown(report))
    print(
        f"{report['cohort_status']}: {report['verified_candidates']}/{report['requested_candidates']} verified candidates"
    )
    return 0 if report["cohort_status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())

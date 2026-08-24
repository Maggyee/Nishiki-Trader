"""Multi-candidate forward shadow signal portfolio monitor and correlation analyzer."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore

SCHEMA_VERSION = "research.portfolio_shadow_monitor.v1"
DEFAULT_OUTPUT_JSON = Path("docs/progress/phase-2-research-portfolio-shadow-status.json")
DEFAULT_OUTPUT_MD = Path("docs/progress/phase-2-research-portfolio-shadow-report.md")

CANDIDATE_SPECS: list[dict[str, Any]] = [
    {
        "protocol": "v8",
        "name": "Cboe GVZ Gold Volatility Relief",
        "category": "Commodity / Gold Vol",
        "source": "rule_gold_vol_relief_v1",
        "model_version": "cboe-gvz5obs-negative-1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v8-paper-shadow-status.json"),
        "db_path": Path("data/research-v8-forward/signals.db"),
        "crontab_schedule": "weekdays at 02:30 UTC",
    },
    {
        "protocol": "v16",
        "name": "U.S. Treasury 10Y Volatility Relief",
        "category": "Fixed Income / Duration",
        "source": "rule_us_treasury_volatility_relief_v2",
        "model_version": "treasury-nominal10-absdiff5-20-negative-lag2d-v1",
        "status_path": Path("docs/progress/phase-2-research-v16-paper-shadow-status.json"),
        "db_path": Path("data/research-v16-forward/signals.db"),
        "crontab_schedule": "weekdays at 12:30 UTC",
    },
    {
        "protocol": "v18",
        "name": "Cboe VXN Nasdaq Volatility OHLC Relief",
        "category": "Equity Tech Volatility",
        "source": "rule_nasdaq_vol_relief_v2",
        "model_version": "cboe-vxn-ohlc5obs-negative-1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v18-paper-shadow-status.json"),
        "db_path": Path("data/research-v18-forward/signals.db"),
        "crontab_schedule": "weekdays at 03:30 UTC",
    },
    {
        "protocol": "v22",
        "name": "Cboe COR1M 1-Month Implied Correlation Relief",
        "category": "Option Surface / Correlation",
        "source": "rule_cboe_implied_correlation_relief_v1",
        "model_version": "cboe-cor1m-diff5-negative-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v22-paper-shadow-status.json"),
        "db_path": Path("data/research-v22-forward/signals.db"),
        "crontab_schedule": "weekdays at 04:30 UTC",
    },
    {
        "protocol": "v34",
        "name": "Cboe FVX 5-Year Treasury Yield Relief",
        "category": "Fixed Income / Yield",
        "source": "rule_cboe_fvx_relief_v1",
        "model_version": "cboe-fvx-diff5-negative-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v34-paper-shadow-status.json"),
        "db_path": Path("data/research-v34-forward/signals.db"),
        "crontab_schedule": "weekdays at 02:45 UTC",
    },
    {
        "protocol": "v36",
        "name": "Cboe VPN Option Strategy Relief",
        "category": "Option Strategy / Variance",
        "source": "rule_cboe_vpn_relief_v1",
        "model_version": "cboe-vpn-diff5-negative-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v36-paper-shadow-status.json"),
        "db_path": Path("data/research-v36-forward/signals.db"),
        "crontab_schedule": "weekdays at 03:00 UTC",
    },
    {
        "protocol": "v40",
        "name": "Cboe VXN Cross-Asset Equity Implied Vol Relief",
        "category": "Equity Tech Volatility",
        "source": "rule_cboe_vxn_relief_v1",
        "model_version": "cboe-vxn-diff5-negative-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v40-paper-shadow-status.json"),
        "db_path": Path("data/research-v40/shadow/signals.db"),
        "crontab_schedule": "weekdays at 03:15 UTC (7d complete)",
    },
    {
        "protocol": "v42",
        "name": "Cboe VIX6M Term Structure Volatility Relief",
        "category": "Volatility Term Structure",
        "source": "rule_cboe_vix6m_relief_v1",
        "model_version": "cboe-vix6m-diff5-negative-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v42-paper-shadow-status.json"),
        "db_path": Path("data/research-v42/shadow/signals.db"),
        "crontab_schedule": "weekdays at 03:45 UTC (7d complete)",
    },
    {
        "protocol": "v46",
        "name": "Binance BTC Perpetual Premium Index Delta Relief",
        "category": "Crypto Perpetual Derivatives",
        "source": "rule_crypto_prem_relief_v1",
        "model_version": "crypto-btc-prem-diff5-negative-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v46-paper-shadow-status.json"),
        "db_path": Path("data/research-v46/shadow/signals.db"),
        "crontab_schedule": "daily at 04:00 UTC (8r complete)",
    },
    {
        "protocol": "v48",
        "name": "Binance BTC Perpetual Basis MA10 Relief",
        "category": "Crypto Spot-Perp Basis",
        "source": "rule_crypto_basis_relief_v1",
        "model_version": "crypto-btc-basis-below-ma10-lag1d-v1",
        "status_path": Path("docs/progress/phase-2-research-v48-paper-shadow-status.json"),
        "db_path": Path("data/research-v48/shadow/signals.db"),
        "crontab_schedule": "daily at 04:15 UTC (7r complete)",
    },
]


def load_candidate_data(
    repo_root: Path, specs: list[dict[str, Any]] = CANDIDATE_SPECS
) -> list[dict[str, Any]]:
    candidates = []
    for spec in specs:
        status_file = repo_root / spec["status_path"]
        db_file = repo_root / spec["db_path"]
        status_data: dict[str, Any] = {}
        if status_file.exists():
            try:
                status_data = json.loads(status_file.read_text())
            except Exception:
                status_data = {}

        signals: list[dict[str, Any]] = []
        if db_file.exists():
            try:
                store = SignalStore(db_file)
                for event in store.replay(
                    source=spec["source"], model_version=spec["model_version"]
                ):
                    dt = datetime.fromtimestamp(event.ts_event / 1e9, tz=UTC)
                    signals.append(
                        {
                            "signal_id": event.signal_id,
                            "ts_event": event.ts_event,
                            "dt_utc": dt.isoformat(),
                            "date_utc": dt.date().isoformat(),
                            "side": event.side,
                            "score": event.score,
                            "confidence": event.confidence,
                        }
                    )
            except Exception:
                pass

        buy_count = sum(1 for s in signals if s["side"].upper() == "BUY")
        flat_count = sum(1 for s in signals if s["side"].upper() in {"FLAT", "SELL"})

        # Extract qualified days across all protocol formats
        qualified_days = 0
        journal_dir = db_file.parent / "journal"
        if not journal_dir.exists() and (db_file.parent.parent / "journal").exists():
            journal_dir = db_file.parent.parent / "journal"

        if journal_dir.exists():
            for jf in journal_dir.glob("*.json"):
                try:
                    jd = json.loads(jf.read_text())
                    if jd.get("qualified_day"):
                        qualified_days += 1
                except Exception:
                    pass
        elif "qualified_runs" in status_data:
            qualified_days = int(status_data["qualified_runs"])
        elif "total_days_collected" in status_data:
            qualified_days = int(status_data["total_days_collected"])
        elif "total_runs_collected" in status_data:
            qualified_days = int(status_data["total_runs_collected"])
        elif "qualified_day_count" in status_data:
            qualified_days = int(status_data["qualified_day_count"])
        elif "forward_gate" in status_data and "qualified_day_count" in status_data["forward_gate"]:
            qualified_days = int(status_data["forward_gate"]["qualified_day_count"])

        gate_days = status_data.get("gate", {}).get("days", 7)
        if "target_runs" in status_data:
            gate_days = int(status_data["target_runs"])
        elif "forward_gate" in status_data:
            gate_days = status_data["forward_gate"].get("required_days", 7)

        threshold_met = (qualified_days >= gate_days) or status_data.get("threshold_met", False)
        if "forward_gate" in status_data:
            threshold_met = threshold_met or status_data["forward_gate"].get("threshold_met", False)
        if spec["protocol"] in {"v40", "v42", "v46", "v48"} and qualified_days >= gate_days:
            threshold_met = True

        candidates.append(
            {
                "protocol": spec["protocol"],
                "name": spec["name"],
                "category": spec["category"],
                "source": spec["source"],
                "model_version": spec["model_version"],
                "status_path": str(spec["status_path"]),
                "db_path": str(spec["db_path"]),
                "crontab_schedule": spec["crontab_schedule"],
                "stage": status_data.get("stage", "paper_shadow"),
                "policy": status_data.get(
                    "policy",
                    {
                        "dry_run": True,
                        "position_pct_multiplier": 0.2,
                        "min_confidence_override": None,
                    },
                ),
                "qualified_days": qualified_days,
                "gate_days": gate_days,
                "threshold_met": threshold_met,
                "review_eligible": threshold_met and not status_data.get("anomaly_blockers", []),
                "anomaly_blockers": status_data.get("anomaly_blockers", []),
                "signals_count": len(signals),
                "buy_count": buy_count,
                "flat_count": flat_count,
                "signals": signals,
            }
        )
    return candidates


def compute_portfolio_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    # Build a daily aligned signal panel
    strategy_series: dict[str, pd.Series] = {}
    for cand in candidates:
        proto = cand["protocol"]
        sigs = cand["signals"]
        if not sigs:
            continue
        df = pd.DataFrame(sigs)
        df["dt"] = pd.to_datetime(df["dt_utc"], utc=True)
        df["date"] = df["dt"].dt.date
        # Daily exposure: 1.0 for BUY, 0.0 for FLAT/SELL (last signal of the day)
        daily = (
            df.sort_values("dt")
            .groupby("date")
            .last()["side"]
            .apply(lambda side: 1.0 if str(side).upper() == "BUY" else 0.0)
        )
        strategy_series[proto] = daily

    if not strategy_series:
        return {
            "candidate_count": len(candidates),
            "active_series_count": 0,
            "correlation_matrix": {},
            "overlap_matrix": {},
            "portfolio_exposure_stats": {},
        }

    panel = pd.DataFrame(strategy_series).sort_index().fillna(0.0)
    # Pairwise Pearson Correlation
    corr_df = panel.corr().round(4).fillna(0.0)
    corr_dict = {col: corr_df[col].to_dict() for col in corr_df.columns}

    # Pairwise Overlap Rate (% of common days both active)
    overlap_dict: dict[str, dict[str, float]] = {}
    for c1 in panel.columns:
        overlap_dict[c1] = {}
        for c2 in panel.columns:
            both = (panel[c1] > 0) & (panel[c2] > 0)
            total = (panel[c1] > 0) | (panel[c2] > 0)
            if total.sum() == 0:
                overlap_dict[c1][c2] = 0.0
            else:
                overlap_dict[c1][c2] = round(float(both.sum() / total.sum()), 4)

    # Portfolio simultaneous exposure (assuming 0.20 weight per active candidate)
    concurrent_active = panel.sum(axis=1)
    combined_exposure = concurrent_active * 0.20

    active_counts_hist = {
        int(k): int(v) for k, v in concurrent_active.value_counts().sort_index().items()
    }

    # Average off-diagonal correlation
    n = len(corr_df)
    off_diag = []
    for i in range(n):
        for j in range(i + 1, n):
            val = corr_df.iloc[i, j]
            if not math.isnan(val):
                off_diag.append(val)
    avg_off_diag_corr = float(np.mean(off_diag)) if off_diag else 0.0

    return {
        "candidate_count": len(candidates),
        "active_series_count": len(strategy_series),
        "total_days_observed": len(panel),
        "first_observed_date": str(panel.index[0]) if len(panel) > 0 else None,
        "last_observed_date": str(panel.index[-1]) if len(panel) > 0 else None,
        "avg_cross_correlation": round(avg_off_diag_corr, 4),
        "correlation_matrix": corr_dict,
        "overlap_matrix": overlap_dict,
        "portfolio_exposure_stats": {
            "max_concurrent_active_strategies": int(concurrent_active.max())
            if len(concurrent_active) > 0
            else 0,
            "mean_concurrent_active_strategies": round(float(concurrent_active.mean()), 2)
            if len(concurrent_active) > 0
            else 0.0,
            "max_aggregate_leverage_multiplier": round(float(combined_exposure.max()), 2)
            if len(combined_exposure) > 0
            else 0.0,
            "mean_aggregate_leverage_multiplier": round(float(combined_exposure.mean()), 2)
            if len(combined_exposure) > 0
            else 0.0,
            "active_strategy_count_distribution": active_counts_hist,
        },
    }


def generate_portfolio_markdown_report(
    candidates: list[dict[str, Any]], metrics: dict[str, Any]
) -> str:
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Phase 5 Multi-Candidate Forward Paper-Shadow Portfolio Report",
        "",
        f"- **Generated at**: {now_utc}",
        f"- **Total Candidates Tracked**: {len(candidates)}",
        f"- **Active Shadow Data Streams**: {metrics.get('active_series_count', 0)}",
        f"- **Overall Average Correlation**: {metrics.get('avg_cross_correlation', 0.0):.4f}",
        "",
        "## 1. Candidate Roster & Progress",
        "",
        "| Protocol | Strategy / Model | Category | Gate Progress | Signals (Buy / Flat) | Shadow Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for c in candidates:
        gate_str = f"{c['qualified_days']} / {c['gate_days']}d"
        if c["threshold_met"]:
            gate_str += " (Gate Met)"
        sig_str = f"{c['signals_count']} ({c['buy_count']}B / {c['flat_count']}F)"
        lines.append(
            f"| **{c['protocol'].upper()}** | `{c['model_version']}` | {c['category']} | {gate_str} | {sig_str} | `{c['stage']}` |"
        )

    lines.extend(
        [
            "",
            "## 2. Cross-Strategy Correlation Matrix (Daily Signal Panel)",
            "",
        ]
    )

    corr_matrix = metrics.get("correlation_matrix", {})
    if corr_matrix:
        protocols = sorted(corr_matrix.keys())
        header = "| Protocol | " + " | ".join(p.upper() for p in protocols) + " |"
        separator = "| :--- | " + " | ".join(":---:" for _ in protocols) + " |"
        lines.append(header)
        lines.append(separator)
        for p1 in protocols:
            row_vals = [f"{corr_matrix[p1].get(p2, 0.0):+.2f}" for p2 in protocols]
            lines.append(f"| **{p1.upper()}** | " + " | ".join(row_vals) + " |")

    lines.extend(
        [
            "",
            "## 3. Joint Multi-Strategy Exposure Profile",
            "",
            f"- **Observation Window**: {metrics.get('first_observed_date', 'N/A')} to {metrics.get('last_observed_date', 'N/A')} ({metrics.get('total_days_observed', 0)} UTC days)",
            f"- **Max Concurrent Active Relief Signals**: {metrics.get('portfolio_exposure_stats', {}).get('max_concurrent_active_strategies', 0)} strategies",
            f"- **Mean Active Relief Signals**: {metrics.get('portfolio_exposure_stats', {}).get('mean_concurrent_active_strategies', 0.0)} strategies",
            f"- **Max Combined Sizing Multiplier**: {metrics.get('portfolio_exposure_stats', {}).get('max_aggregate_leverage_multiplier', 0.0)}x (assuming 0.20x per candidate)",
            f"- **Mean Combined Sizing Multiplier**: {metrics.get('portfolio_exposure_stats', {}).get('mean_aggregate_leverage_multiplier', 0.0)}x",
            "",
            "### Concurrent Active Signals Distribution (Days)",
            "",
        ]
    )

    hist = metrics.get("portfolio_exposure_stats", {}).get(
        "active_strategy_count_distribution", {}
    )
    if hist:
        lines.append("| Active Strategies Count | Frequency (Days) | Percentage |")
        lines.append("| :---: | :---: | :---: |")
        total_d = metrics.get("total_days_observed", 1) or 1
        for k, v in sorted(hist.items()):
            pct = v / total_d * 100
            lines.append(f"| **{k}** | {v} | {pct:.1f}% |")

    lines.extend(
        [
            "",
            "## 4. Phase 5 Governance Boundaries",
            "",
            "- All strategies remain strictly under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`.",
            "- Live trading and testnet execution remain strictly blocked by the Phase 6 gate.",
            "- The 2026-09..2027-01 future blind dataset remains sealed and unopened.",
            "",
        ]
    )

    return "\n".join(lines)


def run_monitor(
    repo_root: Path = Path.cwd(),
    output_json_path: Path | None = DEFAULT_OUTPUT_JSON,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    candidates = load_candidate_data(repo_root)
    metrics = compute_portfolio_metrics(candidates)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "candidates": [
            {k: v for k, v in c.items() if k != "signals"} for c in candidates
        ],
        "metrics": metrics,
        "boundaries": {
            "dry_run": True,
            "live_trading_blocked": True,
            "phase_6_gate_closed": True,
            "future_blind_sealed": True,
        },
    }

    if output_json_path is not None:
        target = (repo_root / output_json_path) if not output_json_path.is_absolute() else output_json_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    if output_md_path is not None:
        md_text = generate_portfolio_markdown_report(candidates, metrics)
        target_md = (repo_root / output_md_path) if not output_md_path.is_absolute() else output_md_path
        target_md.parent.mkdir(parents=True, exist_ok=True)
        target_md.write_text(md_text + "\n")

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown to stdout")
    args = parser.parse_args(argv)

    payload = run_monitor(
        repo_root=args.repo_root.resolve(),
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )

    if args.markdown:
        candidates = load_candidate_data(args.repo_root.resolve())
        print(generate_portfolio_markdown_report(candidates, payload["metrics"]))
    elif args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"Portfolio monitor complete: {len(payload['candidates'])} candidates audited."
        )
        print(f"JSON status saved to: {args.output_json}")
        print(f"Markdown report saved to: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Multi-candidate forward shadow signal portfolio monitor and correlation analyzer."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.ops.research_shadow_runtime import atomic_json

SCHEMA_VERSION = "research.portfolio_shadow_monitor.v2"
DEFAULT_OUTPUT_JSON = Path("data/research-portfolio/status.json")
DEFAULT_OUTPUT_MD = Path("data/research-portfolio/report.md")

CANDIDATE_SPECS: list[dict[str, Any]] = [
    {
        "protocol": "v8",
        "name": "Cboe GVZ Gold Volatility Relief",
        "category": "Commodity / Gold Vol",
        "status_path": Path("docs/progress/phase-2-research-v8-paper-shadow-status.json"),
        "db_path": Path("data/research-v8-forward/signals.db"),
        "crontab_schedule": "weekdays at 02:30 UTC",
    },
    {
        "protocol": "v16",
        "name": "U.S. Treasury 10Y Volatility Relief",
        "category": "Fixed Income / Duration",
        "status_path": Path("docs/progress/phase-2-research-v16-paper-shadow-status.json"),
        "db_path": Path("data/research-v16-forward/signals.db"),
        "crontab_schedule": "weekdays at 12:30 UTC",
    },
    {
        "protocol": "v18",
        "name": "Cboe VXN Nasdaq Volatility OHLC Relief",
        "category": "Equity Tech Volatility",
        "status_path": Path("docs/progress/phase-2-research-v18-paper-shadow-status.json"),
        "db_path": Path("data/research-v18-forward/signals.db"),
        "crontab_schedule": "weekdays at 03:30 UTC",
    },
    {
        "protocol": "v22",
        "name": "Cboe COR1M 1-Month Implied Correlation Relief",
        "category": "Option Surface / Correlation",
        "status_path": Path("docs/progress/phase-2-research-v22-paper-shadow-status.json"),
        "db_path": Path("data/research-v22-forward/signals.db"),
        "crontab_schedule": "weekdays at 04:30 UTC",
    },
    {
        "protocol": "v34",
        "name": "Cboe FVX 5-Year Treasury Yield Relief",
        "category": "Fixed Income / Yield",
        "status_path": Path("docs/progress/phase-2-research-v34-paper-shadow-status.json"),
        "db_path": Path("data/research-v34-forward/signals.db"),
        "crontab_schedule": "weekdays at 02:45 UTC",
    },
    {
        "protocol": "v36",
        "name": "Cboe VPN Option Strategy Expansion",
        "category": "Option Strategy / Variance",
        "status_path": Path("docs/progress/phase-2-research-v36-paper-shadow-status.json"),
        "db_path": Path("data/research-v36-forward/signals.db"),
        "crontab_schedule": "weekdays at 03:00 UTC",
    },
    {
        "protocol": "v40",
        "name": "Cboe VXN Cross-Asset Equity Implied Vol Relief",
        "category": "Equity Tech Volatility",
        "status_path": Path("docs/progress/phase-2-research-v40-paper-shadow-status.json"),
        "db_path": Path("data/research-v40/shadow/signals.db"),
        "crontab_schedule": "weekdays at 03:15 UTC",
    },
    {
        "protocol": "v42",
        "name": "Cboe VIX6M Term Structure Volatility Relief",
        "category": "Volatility Term Structure",
        "status_path": Path("docs/progress/phase-2-research-v42-paper-shadow-status.json"),
        "db_path": Path("data/research-v42/shadow/signals.db"),
        "crontab_schedule": "weekdays at 03:45 UTC",
    },
    {
        "protocol": "v46",
        "name": "Binance BTC Perpetual Premium Index Delta Relief",
        "category": "Crypto Perpetual Derivatives",
        "status_path": Path("docs/progress/phase-2-research-v46-paper-shadow-status.json"),
        "db_path": Path("data/research-v46/shadow/signals.db"),
        "crontab_schedule": "daily at 04:00 UTC",
    },
    {
        "protocol": "v48",
        "name": "Binance BTC Perpetual Basis MA10 Relief",
        "category": "Crypto Spot-Perp Basis",
        "status_path": Path("docs/progress/phase-2-research-v48-paper-shadow-status.json"),
        "db_path": Path("data/research-v48/shadow/signals.db"),
        "crontab_schedule": "daily at 04:15 UTC",
    },
]


def contract_identity(protocol: str) -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    path = root / f"docs/progress/phase-2-research-{protocol}-paper-shadow.json"
    contract = json.loads(path.read_text())
    identities = [entry for entry in (contract, contract.get("candidate"), contract.get("strategy"))
                  if isinstance(entry, dict) and "source" in entry and "model_version" in entry]
    pairs = {(entry["source"], entry["model_version"]) for entry in identities}
    if len(pairs) != 1:
        raise ValueError(f"missing or conflicting frozen identity: {protocol}")
    source, model = pairs.pop()
    return {"source": source, "model_version": model}


for _spec in CANDIDATE_SPECS:
    _spec.update(contract_identity(_spec["protocol"]))


def load_candidate_data(
    repo_root: Path, specs: list[dict[str, Any]] = CANDIDATE_SPECS,
    *, now: datetime | None = None,
) -> list[dict[str, Any]]:
    observed_at = now or datetime.now(UTC)
    candidates = []
    for spec in specs:
        db_file = repo_root / spec["db_path"]
        status_file = db_file.parent / "status.json"
        blockers: list[str] = []
        status_data: dict[str, Any] = {}
        if not status_file.exists():
            status_file = repo_root / spec["status_path"]
            blockers.append("runtime_status_missing")
        if status_file.exists():
            try:
                status_data = json.loads(status_file.read_text())
                if not isinstance(status_data, dict):
                    raise ValueError("status must be an object")
            except (OSError, ValueError):
                blockers.append("status_unreadable")
                status_data = {}
        else:
            blockers.append("status_missing")

        updated_at = status_data.get("updated_at") or status_data.get("last_run_at") or status_data.get("evaluated_at")
        try:
            timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age = (observed_at - timestamp).total_seconds()
            if age < 0 or age > 4 * 86400:
                blockers.append("status_stale_or_future")
        except (AttributeError, ValueError, TypeError):
            blockers.append("status_timestamp_invalid")
        reported_blockers = status_data.get("anomaly_blockers", [])
        if isinstance(reported_blockers, list) and all(isinstance(b, str) for b in reported_blockers):
            blockers.extend(reported_blockers)
        else:
            blockers.append("status_blockers_invalid")
        if "health" in status_data and status_data["health"] != "HEALTHY":
            blockers.append("collector_unhealthy")
        for field in ("source", "model_version"):
            if field in status_data and status_data[field] != spec[field]:
                blockers.append(f"status_{field}_mismatch")

        signals: list[dict[str, Any]] = []
        if db_file.exists():
            try:
                with closing(sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                    rows = conn.execute(
                        "SELECT raw_json FROM signals WHERE source=? AND model_version=? ORDER BY ts_event, signal_id",
                        (spec["source"], spec["model_version"]),
                    ).fetchall()
                for row in rows:
                    event = SignalEvent.model_validate_json(row[0])
                    if event.source != spec["source"] or event.model_version != spec["model_version"]:
                        raise ValueError("stored signal identity mismatch")
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
            except (OSError, ValueError, sqlite3.Error):
                signals = []
                blockers.append("signal_database_unreadable")
        else:
            blockers.append("signal_database_missing")

        buy_count = sum(1 for s in signals if s["side"].upper() == "BUY")
        flat_count = sum(1 for s in signals if s["side"].upper() in {"FLAT", "SELL"})

        gate = status_data.get("forward_gate", status_data.get("gate", {}))
        if not isinstance(gate, dict):
            blockers.append("gate_invalid")
            gate = {}
        qualified_days = status_data.get("qualified_day_count", gate.get("qualified_day_count", 0))
        gate_days = gate.get("required_days", gate.get("days", 7))
        if type(qualified_days) is not int or qualified_days < 0:
            blockers.append("qualified_days_invalid")
            qualified_days = 0
        if type(gate_days) is not int or gate_days < 1:
            blockers.append("gate_days_invalid")
            gate_days = 7
        if "qualified_day_count" not in status_data and "qualified_day_count" not in gate:
            blockers.append("legacy_run_count_not_qualified_days")
        threshold_met = status_data.get("threshold_met", gate.get("threshold_met")) is True
        declared_eligible = status_data.get("review_eligible", gate.get("review_eligible")) is True
        policy = status_data.get("policy", {})
        if not isinstance(policy, dict) or policy.get("dry_run") is not True:
            blockers.append("shadow_policy_unverified")
            policy = {}

        candidates.append(
            {
                "protocol": spec["protocol"],
                "name": spec["name"],
                "category": spec["category"],
                "source": spec["source"],
                "model_version": spec["model_version"],
                "status_path": str(status_file),
                "updated_at": updated_at,
                "last_observation_date": status_data.get("last_observation_date"),
                "last_qualified_at": status_data.get("last_qualified_at"),
                "db_path": str(spec["db_path"]),
                "crontab_schedule": spec["crontab_schedule"],
                "stage": status_data.get("stage", "paper_shadow"),
                "policy": policy,
                "qualified_days": qualified_days,
                "gate_days": gate_days,
                "threshold_met": threshold_met,
                "review_eligible": threshold_met and declared_eligible and not blockers,
                "anomaly_blockers": sorted(set(blockers)),
                "signals_count": len(signals),
                "buy_count": buy_count,
                "flat_count": flat_count,
                "signals": signals,
            }
        )
    return candidates


def compute_portfolio_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Sparse signal-arrival diagnostics, NOT holdings, returns or leverage.

    A signal is not a fill. Missing events do not establish a flat position, and
    holding state cannot be inferred across TTL/risk rejection/collector gaps.
    """
    series = {}
    for candidate in candidates:
        if not candidate["signals"]:
            continue
        frame = pd.DataFrame(candidate["signals"])
        frame["day"] = pd.to_datetime(frame["dt_utc"], utc=True).dt.normalize()
        daily = frame.sort_values("dt_utc").groupby("day").last()["side"]
        series[candidate["protocol"]] = daily.map(
            lambda side: 1.0 if str(side).upper() == "BUY" else 0.0)
    metrics = {
        "candidate_count": len(candidates), "active_series_count": len(series),
        "metric_semantics": "last_signal_direction_on_joint_observed_days_only",
        "missing_days_are_flat": False, "holding_state_inferred": False,
        "correlation_matrix": {}, "overlap_matrix": {}, "pairwise_sample_days": {},
        "portfolio_exposure_stats": {},
        "portfolio_evaluation": {
            "status": "unavailable", "actual_leverage": None,
            "net_return": None, "drawdown": None, "cost_adjusted_alpha": None,
            "blockers": ["verified_nautilus_fills_and_account_equity_not_attached"],
            "future_blind_evaluated": False,
        },
        "shared_mechanism_warnings": [
            "v18 and v40 both use VXN; identities are not independent alpha sources",
            "all ten shadow candidates target BTC long/flat; category labels do not diversify assets",
        ],
        "avg_cross_correlation": None,
    }
    if not series:
        return metrics
    panel = pd.DataFrame(series).sort_index()
    panel = panel.reindex(pd.date_range(panel.index.min(), panel.index.max(), freq="D"))
    corr, overlaps, samples = {}, {}, {}
    values = []
    for left in panel:
        corr[left], overlaps[left], samples[left] = {}, {}, {}
        for right in panel:
            valid = panel[left].notna() & panel[right].notna()
            a, b = panel.loc[valid, left], panel.loc[valid, right]
            count = len(a)
            samples[left][right] = count
            coefficient = float(a.corr(b)) if count >= 2 and a.nunique() > 1 and b.nunique() > 1 else None
            corr[left][right] = round(coefficient, 4) if coefficient is not None else None
            union = int(((a > 0) | (b > 0)).sum())
            overlaps[left][right] = round(float(((a > 0) & (b > 0)).sum()) / union, 4) if union else None
            if left < right and coefficient is not None:
                values.append(coefficient)
    metrics.update(
        total_days_observed=len(panel), first_observed_date=str(panel.index[0].date()),
        last_observed_date=str(panel.index[-1].date()),
        observed_signal_days={key: int(panel[key].notna().sum()) for key in panel},
        missing_signal_days={key: int(panel[key].isna().sum()) for key in panel},
        correlation_matrix=corr, overlap_matrix=overlaps, pairwise_sample_days=samples,
        avg_cross_correlation=round(sum(values) / len(values), 4) if values else None,
    )
    return metrics


def generate_portfolio_markdown_report(
    candidates: list[dict[str, Any]], metrics: dict[str, Any]
) -> str:
    lines = [
        "# Phase 5 Multi-Candidate Forward Paper-Shadow Portfolio Report", "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        "- Signal arrival diagnostics only; no holdings, leverage or alpha inferred.",
        "- Missing days and undefined correlations remain unknown, never zero.", "",
        "## 1. Candidate Roster & Progress", "",
        "| Protocol | Qualified days | Latest observation | Last qualified | Review eligible | Blockers |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in candidates:
        blockers = "; ".join(c["anomaly_blockers"]).replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {c['protocol']} | {c['qualified_days']}/{c['gate_days']} | "
            f"{c['last_observation_date'] or 'unknown'} | {c['last_qualified_at'] or 'unknown'} | "
            f"{c['review_eligible']} | {blockers or 'none'} |")
    lines += ["", "## 2. Cross-Strategy Correlation Matrix", "",
              "Last signal direction, conditioned on joint signal-arrival days; not return correlation.",
              "Each cell is correlation / paired days. Sparse samples are not diversification evidence.", ""]
    corr = metrics["correlation_matrix"]
    if corr:
        protocols = list(corr)
        lines += ["| Protocol | " + " | ".join(protocols) + " |",
                  "| --- | " + " | ".join("---" for _ in protocols) + " |"]
        for left in protocols:
            cells = []
            for right in protocols:
                value = corr[left][right]
                label = f"{value:+.2f}" if value is not None else "unknown"
                cells.append(f"{label} / {metrics['pairwise_sample_days'][left][right]}")
            lines.append(f"| {left} | " + " | ".join(cells) + " |")
    lines += ["", "## 3. Portfolio Evaluation Gaps", "",
              "- Actual exposure, net return, drawdown and cost-adjusted alpha are unavailable.",
              "- Attach verified Nautilus fills and account equity for already-opened historical windows.",
              "- Compare against BTC buy-and-hold with matched capital/exposure and base/stress costs.",
              "- V18/V40 share VXN; all ten candidates are BTC long/flat, not ten independent assets.",
              "", "## 4. Governance Boundaries", "",
              "- No promotion or source-policy change. Testnet/live remain blocked.",
              "- Future-blind PnL remains sealed; forward collection is observation-only.", ""]
    return "\n".join(lines)
def run_monitor(
    repo_root: Path | None = None,
    output_json_path: Path | None = DEFAULT_OUTPUT_JSON,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    if repo_root is None:
        repo_root = Path.cwd()
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
        atomic_json(target, payload)

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

"""Frozen offline engineering cohort, not a research identity or promotion.

Revalidates the original evidence; missing inputs never shrink the plan or
silently substitute another strategy. No signals, orders, or network calls.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from apps.ops import research_portfolio_evidence as evidence
from apps.strategies_nautilus.portfolio_preflight import Limits

PLAN_ID = "portfolio-engineering-v1-20260909"
ANCHOR_PATH = "docs/progress/portfolio-evidence-review-2026-09-08.json"
ANCHOR_SHA256 = "0a0a6b034298919a292ba7b388d1fb686a41137ccf3dcf01f836f34c8deb336f"
VERIFIED = ("v16", "v18", "v22", "v34", "v36", "v40")
SLEEVES = ("v16", "v18", "v22", "v34", "v36")
EXCLUDED = ("v8", "v42", "v46", "v48")


def preflight_limits() -> Limits:
    """Offline acceptance parameters only; not a SourcePolicy conversion."""
    return Limits(
        SLEEVES, Decimal("0.001"), Decimal("0.005"), Decimal("50"), Decimal("250"), 60_000_000_000
    )


def validate_cohort(anchor: dict, current: dict) -> None:
    """Exact membership and provenance, not a new performance gate."""
    for report in (anchor, current):
        rows = report["candidates"]
        if len(rows) != len(VERIFIED) or {r["protocol"] for r in rows} != set(VERIFIED):
            raise ValueError("verified cohort changed; no automatic substitution")
        if {r["protocol"] for r in report["excluded"]} != set(EXCLUDED):
            raise ValueError("excluded cohort changed; separate review required")
    original = {r["protocol"]: r for r in anchor["candidates"]}
    fresh = {r["protocol"]: r for r in current["candidates"]}
    for protocol in VERIFIED:
        for key in ("source", "model_version", "evidence", "execution_path_sha256"):
            if original[protocol][key] != fresh[protocol][key]:
                raise ValueError(f"{protocol}: pinned {key} changed")
    paths = {p: fresh[p]["execution_path_sha256"] for p in VERIFIED}
    if paths["v18"] != paths["v40"] or len({paths[p] for p in SLEEVES}) != 5:
        raise ValueError("duplicate-path assumption changed")


def build_plan(root: Path) -> dict:
    anchor = json.loads(evidence.verified_bytes(root / ANCHOR_PATH, ANCHOR_SHA256))
    current = evidence.build_report(root)  # reopens only authorized 2023–2025 evidence
    validate_cohort(anchor, current)
    return {
        "schema_version": "portfolio.execution_plan.v1",
        "plan_id": PLAN_ID,
        "status": "offline_engineering_only",
        "evidence_anchor": {"path": ANCHOR_PATH, "sha256": ANCHOR_SHA256},
        "verified_evidence_cohort": list(VERIFIED),
        "sleeves": [
            {k: r[k] for k in ("protocol", "source", "model_version", "evidence")}
            | {"max_quantity_btc": "0.001"}
            for r in current["candidates"]
            if r["protocol"] in SLEEVES
        ],
        "observation_only": {"v40": "same retained execution path as v18; no fallback"},
        "excluded": current["excluded"],
        "selection_rule": "verified lineage only; earliest protocol represents exact duplicate",
        "instrument_id": "BTCUSDT.BINANCE",
        "direction": "spot_long_flat",
        "capital_usdt": "500",
        "daily_loss_usdt": "50",
        "peak_drawdown_limit_usdt": "250",
        "drawdown_definition": "peak equity minus current equity; fixed 50% of initial 500",
        "daily_definition": "UTC day-open marked equity minus current equity; no transfers",
        "max_quantity_btc": "0.005",
        "snapshot_max_age_seconds": 60,
        "preflight_order_scope": "bounded LIMIT only; effective filters, quote fees required",
        "sizing": "fixed 0.001 BTC per sleeve; no compounding, leverage or auto-resizing",
        "netting": "separate sleeve attribution; flat reduces own sleeve only; no cross-netting",
        "admission": "one atomic batch; reserve buys before crediting any unfilled sells",
        "unfilled_policy": "no replacement until terminal acknowledgement and reconciliation",
        "risk_action": "latch entry block; no automatic reset; allow reconciled owned reductions",
        "signal_boundary": "SignalEvent v1 -> Nautilus Strategy -> risk -> execution",
        "runtime_risk_change_authorized": False,
        "promotion_allowed": False,
        "blockers": [
            "forward integrity and portfolio-level alpha review remain incomplete",
            "Nautilus multi-sleeve integration and restart/reservation acceptance pending",
            "account equity, effective venue filters and fee currency not verified",
            "50 USDT planning daily loss differs from existing 5% runtime ADR; reconcile before wiring",
            "intraday risk and emergency actions not validated by historical daily marks",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.repo_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0  # evidence lock valid, NOT authorization to execute


if __name__ == "__main__":
    raise SystemExit(main())

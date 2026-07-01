"""Passive Phase 6 live-readiness gate.

This module is intentionally read-only. It does not load exchange
credentials, start NautilusTrader, mutate SourcePolicy, or authorize live
trading by itself.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apps.strategies_nautilus.runners.promotion_review_artifact import (
    evaluate_live_canary_promotion_review,
)
from apps.strategies_nautilus.runners.report_testnet_bundle import (
    load_testnet_continuity_summary,
)

DEFAULT_PROJECT_STATUS_PATH = Path("docs/project-status.md")
DEFAULT_LIVE_RISK_ADR_PATH = Path("docs/decisions/013-phase6-live-risk-gate.md")
SCHEMA_VERSION = "phase6.live_readiness.v1"
MIN_LIVE_CANARY_CAPITAL_USDT = 100.0
MAX_LIVE_CANARY_CAPITAL_USDT = 500.0

_STATUS_RE = re.compile(
    r"^- \*\*(?:Status|状态)\*\*[:：]\s*(?P<value>.+)$",
    re.MULTILINE,
)
_STRICT_STREAK_RE = re.compile(
    r"(?:current_qualified_streak_days\s*=\s*|strict streak remains\s+)"
    r"(?P<value>\d+/\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


@dataclass(frozen=True)
class LiveReadinessReport:
    schema_version: str
    generated_at_ns: int
    source: str | None
    model_version: str | None
    readiness_gate_met: bool
    live_trading_allowed: bool
    recommendation: str
    blockers: list[str]
    checks: list[ReadinessCheck]
    project_status: dict[str, Any]
    live_risk_adr: dict[str, Any]
    git: dict[str, Any]
    continuity_summary: dict[str, Any] | None
    capital_plan: dict[str, Any]
    market_scope: dict[str, Any]
    boundaries: dict[str, bool]


def build_live_readiness_report(
    *,
    project_status_path: Path = DEFAULT_PROJECT_STATUS_PATH,
    live_risk_adr_path: Path = DEFAULT_LIVE_RISK_ADR_PATH,
    continuity_bundle_dirs: list[Path] | None = None,
    source: str | None = None,
    model_version: str | None = None,
    live_promotion_review_path: Path | None = None,
    starting_capital_usdt: float | None = None,
    market_type: str = "spot",
    margin_enabled: bool = False,
    max_leverage: float = 1.0,
    min_clean_hours_per_day: float = 6.0,
    required_consecutive_days: int = 14,
    repo_root: Path = Path("."),
    git_state: GitState | None = None,
    generated_at_ns: int | None = None,
) -> LiveReadinessReport:
    generated_ns = time.time_ns() if generated_at_ns is None else generated_at_ns
    checks: list[ReadinessCheck] = []
    blockers: list[str] = []

    project_status = _project_status_gate(project_status_path)
    checks.append(
        _check(
            "project_status_live_block",
            "ok" if project_status["live_trading_blocked"] else "blocked",
            (
                "Project status keeps live trading blocked."
                if project_status["live_trading_blocked"]
                else "Project status no longer explicitly blocks live trading."
            ),
        )
    )
    if not project_status["live_trading_blocked"]:
        blockers.append("project_status_live_trading_not_blocked")

    state = git_state or _git_state(repo_root)
    git = {
        "commit": state.commit,
        "dirty": state.dirty,
        "repo_root": str(repo_root),
    }
    checks.append(
        _check(
            "git_clean",
            "ok" if not state.dirty else "blocked",
            (
                f"Git tree is clean at {state.commit}."
                if not state.dirty
                else "Live-readiness evidence must be generated from a clean git tree."
            ),
        )
    )
    if state.dirty:
        blockers.append("git_dirty")

    live_risk_adr = _live_risk_adr_gate(live_risk_adr_path)
    if live_risk_adr["accepted"]:
        checks.append(
            _check(
                "live_risk_adr",
                "ok",
                f"{live_risk_adr_path} is accepted.",
            )
        )
    else:
        blockers.append("live_risk_adr_not_accepted")
        detail = (
            f"{live_risk_adr_path} status is {live_risk_adr['status']!r}."
            if live_risk_adr["exists"]
            else f"{live_risk_adr_path} does not exist."
        )
        checks.append(_check("live_risk_adr", "blocked", detail))

    continuity_summary = None
    bundle_dirs = continuity_bundle_dirs or []
    if bundle_dirs:
        summary = load_testnet_continuity_summary(
            bundle_dirs,
            min_clean_hours_per_day=min_clean_hours_per_day,
            required_consecutive_days=required_consecutive_days,
        )
        continuity_summary = _to_jsonable_dict(summary)
        if bool(continuity_summary.get("required_gate_met")):
            checks.append(
                _check(
                    "testnet_continuity",
                    "ok",
                    (
                        "Testnet continuity gate met: "
                        f"{continuity_summary.get('current_qualified_streak_days')}/"
                        f"{continuity_summary.get('required_consecutive_days')}"
                    ),
                )
            )
        else:
            continuity_blockers = [
                str(item) for item in continuity_summary.get("blockers", [])
            ]
            blockers.extend(
                f"testnet_continuity:{item}" for item in continuity_blockers
            )
            checks.append(
                _check(
                    "testnet_continuity",
                    "blocked",
                    ", ".join(continuity_blockers)
                    or "Continuity summary did not meet the required gate.",
                )
            )
    else:
        blockers.append("testnet_continuity_evidence_missing")
        checks.append(
            _check(
                "testnet_continuity",
                "blocked",
                "No completed testnet bundle directories were supplied.",
            )
        )

    capital_plan = _capital_plan_gate(starting_capital_usdt)
    checks.append(
        _check(
            "capital_ladder",
            "ok" if capital_plan["within_live_canary_range"] else "blocked",
            capital_plan["detail"],
        )
    )
    if not capital_plan["within_live_canary_range"]:
        blockers.append(capital_plan["blocker"])

    market_scope = _market_scope_gate(
        market_type=market_type,
        margin_enabled=margin_enabled,
        max_leverage=max_leverage,
    )
    checks.append(
        _check(
            "market_scope",
            "ok" if market_scope["spot_only_no_margin_no_leverage"] else "blocked",
            market_scope["detail"],
        )
    )
    blockers.extend(str(item) for item in market_scope["blockers"])

    if not source:
        blockers.append("source_not_declared")
        checks.append(
            _check(
                "source_model",
                "blocked",
                "Source must be explicitly declared for live readiness review.",
            )
        )
    elif not model_version:
        blockers.append("model_version_not_declared")
        checks.append(
            _check(
                "source_model",
                "blocked",
                "Model version must be explicitly declared for live readiness review.",
            )
        )
    else:
        promotion_gate = _promotion_review_gate(
            live_promotion_review_path,
            source=source,
            model_version=model_version,
        )
        if promotion_gate["accepted"]:
            checks.append(
                _check(
                    "source_model",
                    "ok",
                    f"{source} / {model_version} has a signed live-canary promotion review.",
                )
            )
        else:
            blockers.append(str(promotion_gate["blocker"]))
            checks.append(
                _check(
                    "source_model",
                    "blocked",
                    str(promotion_gate["detail"]),
                )
            )

    blockers = sorted(dict.fromkeys(blockers))
    readiness_gate_met = not blockers
    return LiveReadinessReport(
        schema_version=SCHEMA_VERSION,
        generated_at_ns=generated_ns,
        source=source,
        model_version=model_version,
        readiness_gate_met=readiness_gate_met,
        live_trading_allowed=False,
        recommendation=(
            "ready_for_manual_live_go_no_go_review"
            if readiness_gate_met
            else "remain_blocked_before_phase6_live_canary"
        ),
        blockers=blockers,
        checks=checks,
        project_status=project_status,
        live_risk_adr=live_risk_adr,
        git=git,
        continuity_summary=continuity_summary,
        capital_plan=capital_plan,
        market_scope=market_scope,
        boundaries={
            "starts_runtime": False,
            "loads_exchange_credentials": False,
            "mutates_source_policy": False,
            "writes_signal_event": False,
            "places_orders": False,
            "authorizes_live_trading": False,
        },
    )


def render_markdown_report(report: LiveReadinessReport) -> str:
    blockers = ", ".join(report.blockers) if report.blockers else "none"
    lines = [
        "# Phase 6 Live Readiness",
        "",
        f"- schema_version: `{report.schema_version}`",
        f"- source_model: `{report.source or 'unknown'} / {report.model_version or 'unknown'}`",
        f"- readiness_gate_met: {str(report.readiness_gate_met).lower()}",
        f"- live_trading_allowed: {str(report.live_trading_allowed).lower()}",
        f"- recommendation: `{report.recommendation}`",
        f"- blockers: {blockers}",
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for check in report.checks:
        lines.append(
            "| "
            f"{_markdown_cell(check.name)} | "
            f"{_markdown_cell(check.status)} | "
            f"{_markdown_cell(check.detail)} |"
        )
    return "\n".join(lines)


def _project_status_gate(path: Path) -> dict[str, Any]:
    exists = path.exists()
    text = path.read_text(encoding="utf-8") if exists else ""
    lowered = text.lower()
    return {
        "path": str(path),
        "exists": exists,
        "live_trading_blocked": (
            "no live trading" in lowered
            or "live trading still blocked" in lowered
            or ("实盘交易" in text and "blocked" in lowered)
        ),
        "strict_continuity": _strict_streak(text),
    }


def _live_risk_adr_gate(path: Path) -> dict[str, Any]:
    exists = path.exists()
    text = path.read_text(encoding="utf-8") if exists else ""
    status = _adr_status(text)
    return {
        "path": str(path),
        "exists": exists,
        "status": status,
        "accepted": status.lower().startswith("accepted"),
    }


def _capital_plan_gate(starting_capital_usdt: float | None) -> dict[str, Any]:
    if starting_capital_usdt is None:
        return {
            "starting_capital_usdt": None,
            "min_live_canary_capital_usdt": MIN_LIVE_CANARY_CAPITAL_USDT,
            "max_live_canary_capital_usdt": MAX_LIVE_CANARY_CAPITAL_USDT,
            "within_live_canary_range": False,
            "blocker": "starting_capital_not_declared",
            "detail": "Starting capital must be explicitly declared.",
        }
    within_range = (
        MIN_LIVE_CANARY_CAPITAL_USDT
        <= starting_capital_usdt
        <= MAX_LIVE_CANARY_CAPITAL_USDT
    )
    return {
        "starting_capital_usdt": starting_capital_usdt,
        "min_live_canary_capital_usdt": MIN_LIVE_CANARY_CAPITAL_USDT,
        "max_live_canary_capital_usdt": MAX_LIVE_CANARY_CAPITAL_USDT,
        "within_live_canary_range": within_range,
        "blocker": (
            "starting_capital_outside_live_canary_range"
            if not within_range
            else ""
        ),
        "detail": (
            "Starting capital is within ADR-001 live-canary range."
            if within_range
            else "Starting capital must be between 100 and 500 USDT."
        ),
    }


def _market_scope_gate(
    *,
    market_type: str,
    margin_enabled: bool,
    max_leverage: float,
) -> dict[str, Any]:
    normalized_market_type = market_type.strip().lower()
    blockers: list[str] = []
    if normalized_market_type != "spot":
        blockers.append("market_type_must_be_spot")
    if margin_enabled:
        blockers.append("margin_must_be_disabled")
    if max_leverage != 1.0:
        blockers.append("leverage_must_be_one")
    accepted = not blockers
    return {
        "market_type": normalized_market_type,
        "margin_enabled": margin_enabled,
        "max_leverage": max_leverage,
        "spot_only_no_margin_no_leverage": accepted,
        "blockers": blockers,
        "detail": (
            "Market scope is Binance Spot only, no margin, no leverage."
            if accepted
            else "Phase 6 live canary requires spot-only, no margin, and max_leverage=1.0."
        ),
    }


def _promotion_review_gate(
    path: Path | None,
    *,
    source: str,
    model_version: str,
) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "accepted": False,
            "blocker": "live_canary_promotion_review_required",
            "detail": "A signed live-canary promotion_review artifact is required.",
        }
    if not path.exists():
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_canary_promotion_review_not_found",
            "detail": f"{path} does not exist.",
        }
    gate = evaluate_live_canary_promotion_review(
        path,
        source=source,
        model_version=model_version,
    )
    if gate["accepted"]:
        return gate
    return {
        **gate,
        "accepted": False,
        "blocker": "live_canary_promotion_review_invalid",
    }


def _adr_status(text: str) -> str:
    match = _STATUS_RE.search(text)
    if not match:
        return "missing"
    return match.group("value").strip()


def _strict_streak(text: str) -> str | None:
    match = _STRICT_STREAK_RE.search(text)
    return match.group("value") if match else None


def _git_state(repo_root: Path) -> GitState:
    commit = _git_output(["git", "rev-parse", "HEAD"], repo_root)
    status = _git_output(["git", "status", "--porcelain"], repo_root)
    return GitState(commit=commit, dirty=bool(status.strip()))


def _git_output(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _check(name: str, status: str, detail: str) -> ReadinessCheck:
    return ReadinessCheck(name=name, status=status, detail=detail)


def _to_jsonable_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise TypeError(f"cannot convert {type(value).__name__} to dict")


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit a passive Phase 6 live-readiness gate report.",
    )
    parser.add_argument(
        "--project-status-path",
        type=Path,
        default=DEFAULT_PROJECT_STATUS_PATH,
    )
    parser.add_argument(
        "--live-risk-adr-path",
        type=Path,
        default=DEFAULT_LIVE_RISK_ADR_PATH,
    )
    parser.add_argument(
        "--continuity-bundle",
        dest="continuity_bundles",
        type=Path,
        action="append",
        default=[],
        help="Completed testnet bundle directory to include in continuity review.",
    )
    parser.add_argument("--source")
    parser.add_argument("--model-version")
    parser.add_argument("--live-promotion-review-path", type=Path)
    parser.add_argument("--starting-capital-usdt", type=float)
    parser.add_argument("--market-type", default="spot")
    parser.add_argument("--margin-enabled", action="store_true")
    parser.add_argument("--max-leverage", type=float, default=1.0)
    parser.add_argument("--min-clean-hours-per-day", type=float, default=6.0)
    parser.add_argument("--required-consecutive-days", type=int, default=14)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    report = build_live_readiness_report(
        project_status_path=args.project_status_path,
        live_risk_adr_path=args.live_risk_adr_path,
        continuity_bundle_dirs=list(args.continuity_bundles),
        source=args.source,
        model_version=args.model_version,
        live_promotion_review_path=args.live_promotion_review_path,
        starting_capital_usdt=args.starting_capital_usdt,
        market_type=args.market_type,
        margin_enabled=bool(args.margin_enabled),
        max_leverage=float(args.max_leverage),
        min_clean_hours_per_day=args.min_clean_hours_per_day,
        required_consecutive_days=args.required_consecutive_days,
        repo_root=args.repo_root,
    )
    if args.markdown:
        print(render_markdown_report(report))
    else:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

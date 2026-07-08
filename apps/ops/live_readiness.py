"""Passive Phase 6 live-readiness gate.

This module is intentionally read-only. It does not load exchange
credentials, start NautilusTrader, mutate SourcePolicy, or authorize live
trading by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import operator
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
REQUIRED_TESTNET_CONTINUITY_DAYS = 14

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
    generated_at_ns: int | None
    source: str | None
    model_version: str | None
    readiness_gate_met: bool
    live_trading_allowed: bool
    recommendation: str
    blockers: list[str]
    checks: list[ReadinessCheck]
    project_status: dict[str, Any]
    live_risk_adr: dict[str, Any]
    live_promotion_review: dict[str, Any] | None
    git: dict[str, Any]
    continuity_summary: dict[str, Any] | None
    continuity_artifacts: list[dict[str, Any]]
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
    generated_ns = (
        time.time_ns()
        if generated_at_ns is None
        else _timestamp_ns_or_none(generated_at_ns)
    )
    generated_at_ns_invalid = generated_at_ns is not None and generated_ns is None
    source_text = _text_or_none(source)
    model_version_text = _text_or_none(model_version)
    checks: list[ReadinessCheck] = []
    blockers: list[str] = []
    promotion_gate: dict[str, Any] | None = None

    if generated_at_ns_invalid:
        blockers.append("generated_at_ns_invalid")
        checks.append(
            _check(
                "generated_at_ns",
                "blocked",
                "generated_at_ns must be a non-negative integer nanosecond timestamp.",
            )
        )

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
    if project_status.get("decode_error"):
        blockers.append("project_status_invalid_utf8")
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
    continuity_artifacts = _continuity_artifacts(bundle_dirs)
    continuity_config = _continuity_config_gate(
        min_clean_hours_per_day=min_clean_hours_per_day,
        required_consecutive_days=required_consecutive_days,
    )
    checks.append(
        _check(
            "testnet_continuity_config",
            "ok" if continuity_config["accepted"] else "blocked",
            str(continuity_config["detail"]),
        )
    )
    blockers.extend(str(item) for item in continuity_config["blockers"])
    if bundle_dirs and continuity_config["accepted"]:
        continuity_artifact_hashes_present = all(
            bool(artifact.get("sha256")) for artifact in continuity_artifacts
        )
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
            checks.append(
                _check(
                    "testnet_continuity_artifacts",
                    "ok" if continuity_artifact_hashes_present else "blocked",
                    (
                        "Continuity bundle manifest fingerprints are recorded."
                        if continuity_artifact_hashes_present
                        else "Every continuity bundle must expose a run_manifest.json fingerprint."
                    ),
                )
            )
            if not continuity_artifact_hashes_present:
                blockers.append("testnet_continuity_artifact_fingerprint_missing")
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
    elif bundle_dirs:
        checks.append(
            _check(
                "testnet_continuity",
                "blocked",
                "Continuity summary was not loaded because continuity review parameters are invalid.",
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

    source_declared = source_text is not None
    model_version_declared = model_version_text is not None
    if not source_declared:
        blockers.append("source_not_declared")
        checks.append(
            _check(
                "source_model",
                "blocked",
                "Source must be explicitly declared for live readiness review.",
            )
        )
    elif not model_version_declared:
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
            source=source_text,
            model_version=model_version_text,
        )
        if promotion_gate["accepted"]:
            checks.append(
                _check(
                    "source_model",
                    "ok",
                    f"{source_text} / {model_version_text} has a signed live-canary promotion review.",
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
        source=source_text,
        model_version=model_version_text,
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
        live_promotion_review=promotion_gate,
        git=git,
        continuity_summary=continuity_summary,
        continuity_artifacts=continuity_artifacts,
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
    raw = path.read_bytes() if exists else b""
    artifact_sha256 = hashlib.sha256(raw).hexdigest() if exists else None
    text, decode_error = _decode_utf8(raw) if exists else ("", None)
    lowered = text.lower()
    return {
        "path": str(path),
        "exists": exists,
        "sha256": artifact_sha256,
        "decode_error": decode_error,
        "live_trading_blocked": (
            decode_error is None
            and (
                "no live trading" in lowered
                or "live trading still blocked" in lowered
                or ("实盘交易" in text and "blocked" in lowered)
            )
        ),
        "strict_continuity": _strict_streak(text),
    }


def _live_risk_adr_gate(path: Path) -> dict[str, Any]:
    exists = path.exists()
    raw = path.read_bytes() if exists else b""
    artifact_sha256 = hashlib.sha256(raw).hexdigest() if exists else None
    text, decode_error = _decode_utf8(raw) if exists else ("", None)
    status = _adr_status(text)
    return {
        "path": str(path),
        "exists": exists,
        "sha256": artifact_sha256,
        "decode_error": decode_error,
        "status": "invalid_utf8" if decode_error else status,
        "accepted": decode_error is None and status.lower().startswith("accepted"),
    }


def _decode_utf8(raw: bytes) -> tuple[str, str | None]:
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return "", str(exc)


def _continuity_artifacts(bundle_dirs: list[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for bundle_dir in bundle_dirs:
        manifest_path = bundle_dir / "run_manifest.json"
        exists = manifest_path.exists()
        raw = manifest_path.read_bytes() if exists else b""
        artifacts.append(
            {
                "bundle_dir": str(bundle_dir),
                "manifest_path": str(manifest_path),
                "exists": exists,
                "sha256": hashlib.sha256(raw).hexdigest() if exists else None,
            }
        )
    return artifacts


def _continuity_config_gate(
    *,
    min_clean_hours_per_day: float,
    required_consecutive_days: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    details: list[str] = []

    clean_hours = _finite_float(min_clean_hours_per_day)
    if clean_hours is None or clean_hours <= 0:
        blockers.append("testnet_continuity_min_clean_hours_invalid")
        details.append("min_clean_hours_per_day must be finite and > 0.")

    required_days = _int_or_none(required_consecutive_days)
    if required_days is None or required_days <= 0:
        blockers.append("testnet_continuity_required_days_invalid")
        details.append("required_consecutive_days must be a positive integer.")
    elif required_days < REQUIRED_TESTNET_CONTINUITY_DAYS:
        blockers.append("testnet_continuity_required_days_below_phase6_minimum")
        details.append(
            "required_consecutive_days must be at least 14 for Phase 6 live readiness."
        )

    accepted = not blockers
    return {
        "accepted": accepted,
        "blockers": blockers,
        "detail": (
            "Continuity review parameters preserve the 14-day Phase 6 minimum."
            if accepted
            else " ".join(details)
        ),
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
    capital = _finite_float(starting_capital_usdt)
    if capital is None:
        return {
            "starting_capital_usdt": None,
            "min_live_canary_capital_usdt": MIN_LIVE_CANARY_CAPITAL_USDT,
            "max_live_canary_capital_usdt": MAX_LIVE_CANARY_CAPITAL_USDT,
            "within_live_canary_range": False,
            "blocker": "starting_capital_not_finite",
            "detail": "Starting capital must be a finite USDT amount.",
        }
    within_range = (
        MIN_LIVE_CANARY_CAPITAL_USDT
        <= capital
        <= MAX_LIVE_CANARY_CAPITAL_USDT
    )
    return {
        "starting_capital_usdt": capital,
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
    market_type: Any,
    margin_enabled: Any,
    max_leverage: float,
) -> dict[str, Any]:
    market_type_text = _text_or_none(market_type)
    normalized_market_type = market_type_text.lower() if market_type_text else None
    margin_enabled_flag = _bool_or_none(margin_enabled)
    blockers: list[str] = []
    leverage = _finite_float(max_leverage)
    if normalized_market_type is None:
        blockers.append("market_type_must_be_text")
    elif normalized_market_type != "spot":
        blockers.append("market_type_must_be_spot")
    if margin_enabled_flag is None:
        blockers.append("margin_enabled_must_be_boolean")
    elif margin_enabled_flag:
        blockers.append("margin_must_be_disabled")
    if leverage is None:
        blockers.append("leverage_must_be_finite")
    elif leverage != 1.0:
        blockers.append("leverage_must_be_one")
    accepted = not blockers
    return {
        "market_type": normalized_market_type,
        "margin_enabled": margin_enabled_flag,
        "max_leverage": leverage,
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


def _text_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _has_text(value: Any) -> bool:
    return _text_or_none(value) is not None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return candidate if math.isfinite(candidate) else None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return operator.index(value)
    except TypeError:
        return None


def _timestamp_ns_or_none(value: Any) -> int | None:
    timestamp_ns = _int_or_none(value)
    return timestamp_ns if timestamp_ns is not None and timestamp_ns >= 0 else None


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
        print(json.dumps(asdict(report), allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

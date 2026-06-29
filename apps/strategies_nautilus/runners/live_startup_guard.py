"""Passive Phase 6 live startup guard.

This module is the preflight contract for a future live runner. It validates
operator intent, local evidence paths, git cleanliness, capital sizing, and
SourcePolicy caps before any live credentials could be loaded.

It intentionally does not read credential values, instantiate NautilusTrader,
connect to Binance, mutate SourcePolicy, write SignalEvent rows, or place
orders.
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

MODE_LIVE = "live"
KIND_LIVE = "live"
DATA_MODE_EXCHANGE_WS = "exchange_ws"
ORDER_MODE_EXCHANGE_LIVE = "exchange_live"
SCHEMA_VERSION = "phase6.live_startup_guard.v1"
READINESS_SCHEMA_VERSION = "phase6.live_readiness.v1"
DEFAULT_LIVE_RISK_ADR_PATH = Path("docs/decisions/013-phase6-live-risk-gate.md")
DEFAULT_FIRST_LIVE_DAY_RUNBOOK_PATH = Path("docs/runbook-first-live-day.md")
REQUIRED_LIVE_CREDENTIAL_ENV_NAMES = (
    "BINANCE_LIVE_API_KEY",
    "BINANCE_LIVE_API_SECRET",
)
MIN_LIVE_CANARY_CAPITAL_USDT = 100.0
MAX_LIVE_CANARY_CAPITAL_USDT = 500.0
LIVE_CANARY_MAX_MULTIPLIER = 0.1
EXIT_OK = 0
EXIT_STARTUP_VALIDATION = 2

_STATUS_RE = re.compile(
    r"^- \*\*(?:Status|状态)\*\*[:：]\s*(?P<value>.+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


@dataclass(frozen=True)
class LiveStartupSettings:
    mode: str
    kind: str
    allow_live_credentials: bool
    source: str
    model_version: str
    policy_dry_run: bool
    policy_position_pct_multiplier: float
    starting_capital_usdt: float
    live_readiness_report_path: Path
    live_promotion_review_path: Path
    first_live_day_runbook_path: Path
    live_risk_adr_path: Path = DEFAULT_LIVE_RISK_ADR_PATH
    repo_root: Path = Path(".")
    operator: str = "nishiki"
    credential_env_names: tuple[str, ...] = REQUIRED_LIVE_CREDENTIAL_ENV_NAMES


@dataclass(frozen=True)
class StartupGuardCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class LiveStartupGuardReport:
    schema_version: str
    generated_at_ns: int
    mode: str
    kind: str
    runtime_mode: str
    runtime_data_mode: str
    runtime_order_mode: str
    source: str
    model_version: str
    startup_allowed: bool
    live_trading_authorized: bool
    recommendation: str
    blockers: list[str]
    checks: list[StartupGuardCheck]
    git: dict[str, Any]
    evidence: dict[str, Any]
    capital_plan: dict[str, Any]
    source_policy: dict[str, Any]
    credential_boundary: dict[str, Any]
    boundaries: dict[str, bool]


def build_live_startup_guard_report(
    settings: LiveStartupSettings,
    *,
    git_state: GitState | None = None,
    generated_at_ns: int | None = None,
) -> LiveStartupGuardReport:
    """Build a structured live startup preflight report."""

    generated_ns = time.time_ns() if generated_at_ns is None else generated_at_ns
    checks: list[StartupGuardCheck] = []
    blockers: list[str] = []

    _check_mode_kind(settings, checks, blockers)
    _check_operator_intent(settings, checks, blockers)
    credential_boundary = _credential_boundary(settings, checks, blockers)

    state = git_state or _git_state(settings.repo_root)
    checks.append(
        _check(
            "git_clean",
            "ok" if not state.dirty else "blocked",
            (
                f"Git tree is clean at {state.commit}."
                if not state.dirty
                else "Live startup requires a clean git worktree."
            ),
        )
    )
    if state.dirty:
        blockers.append("git_dirty")

    capital_plan = _capital_plan(settings.starting_capital_usdt)
    checks.append(
        _check(
            "capital_ladder",
            "ok" if capital_plan["within_live_canary_range"] else "blocked",
            capital_plan["detail"],
        )
    )
    if not capital_plan["within_live_canary_range"]:
        blockers.append(str(capital_plan["blocker"]))

    source_policy = _source_policy_gate(settings)
    checks.append(
        _check(
            "source_policy",
            "ok" if source_policy["within_live_canary_bounds"] else "blocked",
            source_policy["detail"],
        )
    )
    blockers.extend(str(item) for item in source_policy["blockers"])

    evidence: dict[str, Any] = {}
    adr_gate = _live_risk_adr_gate(settings.live_risk_adr_path)
    evidence["live_risk_adr"] = adr_gate
    checks.append(
        _check(
            "live_risk_adr",
            "ok" if adr_gate["accepted"] else "blocked",
            (
                f"{settings.live_risk_adr_path} is accepted."
                if adr_gate["accepted"]
                else f"{settings.live_risk_adr_path} status is {adr_gate['status']!r}."
            ),
        )
    )
    if not adr_gate["accepted"]:
        blockers.append("live_risk_adr_not_accepted")

    readiness_gate = _live_readiness_report_gate(settings)
    evidence["live_readiness_report"] = readiness_gate
    checks.append(
        _check(
            "live_readiness_report",
            "ok" if readiness_gate["accepted"] else "blocked",
            str(readiness_gate["detail"]),
        )
    )
    if not readiness_gate["accepted"]:
        blockers.append(str(readiness_gate["blocker"]))

    promotion_gate = _promotion_review_gate(settings)
    evidence["live_promotion_review"] = promotion_gate
    checks.append(
        _check(
            "live_promotion_review",
            "ok" if promotion_gate["accepted"] else "blocked",
            str(promotion_gate["detail"]),
        )
    )
    if not promotion_gate["accepted"]:
        blockers.append(str(promotion_gate["blocker"]))

    runbook_gate = _first_live_day_runbook_gate(settings.first_live_day_runbook_path)
    evidence["first_live_day_runbook"] = runbook_gate
    checks.append(
        _check(
            "first_live_day_runbook",
            "ok" if runbook_gate["accepted"] else "blocked",
            str(runbook_gate["detail"]),
        )
    )
    if not runbook_gate["accepted"]:
        blockers.append(str(runbook_gate["blocker"]))

    blockers = sorted(dict.fromkeys(blockers))
    startup_allowed = not blockers
    return LiveStartupGuardReport(
        schema_version=SCHEMA_VERSION,
        generated_at_ns=generated_ns,
        mode=settings.mode,
        kind=settings.kind,
        runtime_mode=MODE_LIVE,
        runtime_data_mode=DATA_MODE_EXCHANGE_WS,
        runtime_order_mode=ORDER_MODE_EXCHANGE_LIVE,
        source=settings.source,
        model_version=settings.model_version,
        startup_allowed=startup_allowed,
        live_trading_authorized=False,
        recommendation=(
            "startup_preflight_passed_for_future_live_runner"
            if startup_allowed
            else "refuse_live_startup"
        ),
        blockers=blockers,
        checks=checks,
        git={"commit": state.commit, "dirty": state.dirty},
        evidence=evidence,
        capital_plan=capital_plan,
        source_policy=source_policy,
        credential_boundary=credential_boundary,
        boundaries={
            "starts_runtime": False,
            "loads_exchange_credentials": False,
            "reads_exchange_credential_values": False,
            "builds_nautilus_node": False,
            "connects_exchange": False,
            "mutates_source_policy": False,
            "writes_signal_event": False,
            "places_orders": False,
            "authorizes_live_trading": False,
        },
    )


def render_markdown_report(report: LiveStartupGuardReport) -> str:
    blockers = ", ".join(report.blockers) if report.blockers else "none"
    lines = [
        "# Phase 6 Live Startup Guard",
        "",
        f"- schema_version: `{report.schema_version}`",
        f"- source_model: `{report.source} / {report.model_version}`",
        f"- startup_allowed: {str(report.startup_allowed).lower()}",
        f"- live_trading_authorized: {str(report.live_trading_authorized).lower()}",
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


def _check_mode_kind(
    settings: LiveStartupSettings,
    checks: list[StartupGuardCheck],
    blockers: list[str],
) -> None:
    if settings.mode == MODE_LIVE and settings.kind == KIND_LIVE:
        checks.append(_check("mode_kind", "ok", "--mode live and --kind live set."))
        return
    checks.append(
        _check(
            "mode_kind",
            "blocked",
            f"--mode live and --kind live are required; got {settings.mode!r}/{settings.kind!r}.",
        )
    )
    blockers.append("mode_kind_not_live")


def _check_operator_intent(
    settings: LiveStartupSettings,
    checks: list[StartupGuardCheck],
    blockers: list[str],
) -> None:
    if not settings.source:
        blockers.append("source_not_declared")
    if not settings.model_version:
        blockers.append("model_version_not_declared")
    if settings.allow_live_credentials:
        checks.append(
            _check(
                "operator_intent",
                "ok",
                "--allow-live-credentials set; credential values still not read.",
            )
        )
        return
    checks.append(
        _check(
            "operator_intent",
            "blocked",
            "--allow-live-credentials is required before a live runner may load credentials.",
        )
    )
    blockers.append("allow_live_credentials_required")


def _credential_boundary(
    settings: LiveStartupSettings,
    checks: list[StartupGuardCheck],
    blockers: list[str],
) -> dict[str, Any]:
    env_names = tuple(settings.credential_env_names)
    missing = [
        name for name in REQUIRED_LIVE_CREDENTIAL_ENV_NAMES if name not in env_names
    ]
    accepted = not missing
    checks.append(
        _check(
            "credential_boundary",
            "ok" if accepted else "blocked",
            (
                "Credential env names are declared; values are not inspected."
                if accepted
                else "Missing required live credential env names: "
                + ", ".join(missing)
            ),
        )
    )
    if missing:
        blockers.append("credential_env_names_missing")
    return {
        "credential_env_names": list(env_names),
        "required_credential_env_names": list(REQUIRED_LIVE_CREDENTIAL_ENV_NAMES),
        "values_inspected": False,
        "key_prefix_recorded": False,
    }


def _capital_plan(starting_capital_usdt: float) -> dict[str, Any]:
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


def _source_policy_gate(settings: LiveStartupSettings) -> dict[str, Any]:
    blockers: list[str] = []
    if settings.policy_dry_run:
        blockers.append("policy_must_not_be_dry_run_for_live_canary")
    if not 0.0 <= settings.policy_position_pct_multiplier <= LIVE_CANARY_MAX_MULTIPLIER:
        blockers.append("policy_multiplier_outside_live_canary_bounds")
    return {
        "dry_run": settings.policy_dry_run,
        "position_pct_multiplier": settings.policy_position_pct_multiplier,
        "max_live_canary_multiplier": LIVE_CANARY_MAX_MULTIPLIER,
        "within_live_canary_bounds": not blockers,
        "blockers": blockers,
        "detail": (
            "SourcePolicy is within live-canary bounds."
            if not blockers
            else "SourcePolicy must be dry_run=False and position_pct_multiplier <= 0.1."
        ),
    }


def _live_risk_adr_gate(path: Path) -> dict[str, Any]:
    exists = path.exists()
    text = path.read_text(encoding="utf-8") if exists else ""
    status = _document_status(text)
    return {
        "path": str(path),
        "exists": exists,
        "status": status,
        "accepted": status.lower().startswith("accepted"),
    }


def _live_readiness_report_gate(settings: LiveStartupSettings) -> dict[str, Any]:
    path = settings.live_readiness_report_path
    if not path.exists():
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_readiness_report_not_found",
            "detail": f"{path} does not exist.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_readiness_report_invalid_json",
            "detail": f"{path} is not valid JSON: {exc}",
        }

    problems: list[str] = []
    if payload.get("schema_version") != READINESS_SCHEMA_VERSION:
        problems.append("schema_version")
    if payload.get("source") != settings.source:
        problems.append("source")
    if payload.get("model_version") != settings.model_version:
        problems.append("model_version")
    if payload.get("readiness_gate_met") is not True:
        problems.append("readiness_gate_met")
    if payload.get("live_trading_allowed") is not False:
        problems.append("live_trading_allowed_must_remain_false")
    if payload.get("blockers"):
        problems.append("blockers_must_be_empty")
    continuity = payload.get("continuity_summary") or {}
    if continuity.get("required_gate_met") is not True:
        problems.append("testnet_continuity")
    capital_plan = payload.get("capital_plan") or {}
    if capital_plan.get("within_live_canary_range") is not True:
        problems.append("capital_plan")
    report_capital = capital_plan.get("starting_capital_usdt")
    try:
        report_capital_float = float(report_capital)
    except (TypeError, ValueError):
        report_capital_float = None
    if report_capital_float != settings.starting_capital_usdt:
        problems.append("starting_capital_usdt")
    live_risk_adr = payload.get("live_risk_adr") or {}
    if live_risk_adr.get("accepted") is not True:
        problems.append("live_risk_adr")
    if problems:
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_readiness_report_gate_not_met",
            "detail": "Live readiness report failed checks: " + ", ".join(problems),
            "problems": problems,
        }
    return {
        "path": str(path),
        "accepted": True,
        "blocker": "",
        "detail": f"{path} proves the passive live-readiness gate.",
    }


def _promotion_review_gate(settings: LiveStartupSettings) -> dict[str, Any]:
    path = settings.live_promotion_review_path
    if not path.exists():
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_promotion_review_not_found",
            "detail": f"{path} does not exist.",
        }
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    checks = {
        "decision_allowed": (
            "decision_allowed: **yes**" in lowered
            or "decision_allowed=true" in lowered
            or "decision_allowed: true" in lowered
        ),
        "source": settings.source in text,
        "model_version": settings.model_version in text,
        "current_stage": "current_stage" in lowered and "testnet_canary" in lowered,
        "target_stage": "target_stage" in lowered and "live_canary" in lowered,
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_promotion_review_invalid",
            "detail": "Promotion review failed checks: " + ", ".join(missing),
            "missing": missing,
        }
    return {
        "path": str(path),
        "accepted": True,
        "blocker": "",
        "detail": f"{path} contains a signed testnet_canary -> live_canary review.",
    }


def _first_live_day_runbook_gate(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "first_live_day_runbook_not_found",
            "detail": f"{path} does not exist.",
        }
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    status = _document_status(text)
    missing_sections = [
        label
        for label, tokens in {
            "credential_key_prefix_audit": ("credential", "key-prefix"),
            "emergency_flatten": ("emergency flatten",),
            "manual_exchange_fallback": ("manual exchange fallback",),
            "first_hour_observation": ("first-hour",),
            "post_run_retro": ("post-run retro",),
        }.items()
        if not all(token in lowered for token in tokens)
    ]
    if not status.lower().startswith("accepted"):
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "first_live_day_runbook_not_accepted",
            "detail": f"{path} status is {status!r}.",
            "missing_sections": missing_sections,
            "status": status,
        }
    if missing_sections:
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "first_live_day_runbook_incomplete",
            "detail": "Runbook missing required sections: "
            + ", ".join(missing_sections),
            "missing_sections": missing_sections,
            "status": status,
        }
    return {
        "path": str(path),
        "accepted": True,
        "blocker": "",
        "detail": f"{path} is accepted and includes first-live-day safety sections.",
        "missing_sections": [],
        "status": status,
    }


def _document_status(text: str) -> str:
    match = _STATUS_RE.search(text)
    if not match:
        return "missing"
    return match.group("value").strip()


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


def _check(name: str, status: str, detail: str) -> StartupGuardCheck:
    return StartupGuardCheck(name=name, status=status, detail=detail)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the passive Phase 6 live startup preflight gate.",
    )
    parser.add_argument("--mode", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--allow-live-credentials", action="store_true")
    parser.add_argument("--source", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--policy-dry-run", action="store_true")
    parser.add_argument("--policy-position-pct-multiplier", type=float, required=True)
    parser.add_argument("--starting-capital-usdt", type=float, required=True)
    parser.add_argument("--live-readiness-report-path", type=Path, required=True)
    parser.add_argument("--live-promotion-review-path", type=Path, required=True)
    parser.add_argument(
        "--first-live-day-runbook-path",
        type=Path,
        default=DEFAULT_FIRST_LIVE_DAY_RUNBOOK_PATH,
    )
    parser.add_argument(
        "--live-risk-adr-path",
        type=Path,
        default=DEFAULT_LIVE_RISK_ADR_PATH,
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--operator", default="nishiki")
    parser.add_argument(
        "--credential-env-name",
        dest="credential_env_names",
        action="append",
        default=None,
        help="Declare live credential env var names without reading their values.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    git_state: GitState | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = LiveStartupSettings(
        mode=args.mode,
        kind=args.kind,
        allow_live_credentials=bool(args.allow_live_credentials),
        source=args.source,
        model_version=args.model_version,
        policy_dry_run=bool(args.policy_dry_run),
        policy_position_pct_multiplier=float(args.policy_position_pct_multiplier),
        starting_capital_usdt=float(args.starting_capital_usdt),
        live_readiness_report_path=args.live_readiness_report_path,
        live_promotion_review_path=args.live_promotion_review_path,
        first_live_day_runbook_path=args.first_live_day_runbook_path,
        live_risk_adr_path=args.live_risk_adr_path,
        repo_root=args.repo_root,
        operator=args.operator,
        credential_env_names=tuple(
            args.credential_env_names or REQUIRED_LIVE_CREDENTIAL_ENV_NAMES
        ),
    )
    report = build_live_startup_guard_report(settings, git_state=git_state)
    if args.markdown:
        print(render_markdown_report(report))
    else:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return EXIT_OK if report.startup_allowed else EXIT_STARTUP_VALIDATION


if __name__ == "__main__":
    raise SystemExit(main())

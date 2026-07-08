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
import hashlib
import json
import math
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apps.strategies_nautilus.runners.promotion_review_artifact import (
    evaluate_live_canary_promotion_review,
    promotion_review_sha256,
)

MODE_LIVE = "live"
KIND_LIVE = "live"
DATA_MODE_EXCHANGE_WS = "exchange_ws"
ORDER_MODE_EXCHANGE_LIVE = "exchange_live"
SCHEMA_VERSION = "phase6.live_startup_guard.v1"
READINESS_SCHEMA_VERSION = "phase6.live_readiness.v1"
DEFAULT_PROJECT_STATUS_PATH = Path("docs/project-status.md")
DEFAULT_LIVE_RISK_ADR_PATH = Path("docs/decisions/013-phase6-live-risk-gate.md")
DEFAULT_FIRST_LIVE_DAY_RUNBOOK_PATH = Path("docs/runbook-first-live-day.md")
DEFAULT_MAX_READINESS_REPORT_AGE_SECONDS = 24 * 60 * 60
REQUIRED_LIVE_CREDENTIAL_ENV_NAMES = (
    "BINANCE_LIVE_API_KEY",
    "BINANCE_LIVE_API_SECRET",
)
MIN_LIVE_CANARY_CAPITAL_USDT = 100.0
MAX_LIVE_CANARY_CAPITAL_USDT = 500.0
LIVE_CANARY_MAX_MULTIPLIER = 0.1
REQUIRED_TESTNET_CONTINUITY_DAYS = 14
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
    project_status_path: Path = DEFAULT_PROJECT_STATUS_PATH
    live_risk_adr_path: Path = DEFAULT_LIVE_RISK_ADR_PATH
    repo_root: Path = Path(".")
    operator: str = "nishiki"
    credential_env_names: tuple[str, ...] = REQUIRED_LIVE_CREDENTIAL_ENV_NAMES
    market_type: str = "spot"
    margin_enabled: bool = False
    max_leverage: float = 1.0
    max_readiness_report_age_seconds: float = DEFAULT_MAX_READINESS_REPORT_AGE_SECONDS


@dataclass(frozen=True)
class StartupGuardCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class LiveStartupGuardReport:
    schema_version: str
    generated_at_ns: int | None
    mode: str | None
    kind: str | None
    runtime_mode: str
    runtime_data_mode: str
    runtime_order_mode: str
    source: str | None
    model_version: str | None
    startup_allowed: bool
    live_trading_authorized: bool
    recommendation: str
    blockers: list[str]
    checks: list[StartupGuardCheck]
    git: dict[str, Any]
    evidence: dict[str, Any]
    capital_plan: dict[str, Any]
    market_scope: dict[str, Any]
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

    generated_ns = (
        time.time_ns()
        if generated_at_ns is None
        else _timestamp_ns_or_none(generated_at_ns)
    )
    generated_at_ns_invalid = generated_at_ns is not None and generated_ns is None
    guard_generated_ns = generated_ns if generated_ns is not None else time.time_ns()
    checks: list[StartupGuardCheck] = []
    blockers: list[str] = []

    if generated_at_ns_invalid:
        blockers.append("generated_at_ns_invalid")
        checks.append(
            _check(
                "generated_at_ns",
                "blocked",
                "generated_at_ns must be a non-negative integer nanosecond timestamp.",
            )
        )

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

    market_scope = _market_scope_gate(settings)
    checks.append(
        _check(
            "market_scope",
            "ok" if market_scope["spot_only_no_margin_no_leverage"] else "blocked",
            market_scope["detail"],
        )
    )
    blockers.extend(str(item) for item in market_scope["blockers"])

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

    readiness_gate = _live_readiness_report_gate(
        settings,
        git_state=state,
        generated_at_ns=guard_generated_ns,
    )
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
        mode=_text_or_none(settings.mode),
        kind=_text_or_none(settings.kind),
        runtime_mode=MODE_LIVE,
        runtime_data_mode=DATA_MODE_EXCHANGE_WS,
        runtime_order_mode=ORDER_MODE_EXCHANGE_LIVE,
        source=_text_or_none(settings.source),
        model_version=_text_or_none(settings.model_version),
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
        market_scope=market_scope,
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
    source_model = (
        f"{report.source or 'unknown'} / {report.model_version or 'unknown'}"
    )
    lines = [
        "# Phase 6 Live Startup Guard",
        "",
        f"- schema_version: `{report.schema_version}`",
        f"- source_model: `{source_model}`",
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
    if not _has_text(settings.source):
        blockers.append("source_not_declared")
    if not _has_text(settings.model_version):
        blockers.append("model_version_not_declared")
    allow_live_credentials = _bool_or_none(settings.allow_live_credentials)
    if allow_live_credentials is True:
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
    blockers.append(
        "allow_live_credentials_must_be_boolean"
        if allow_live_credentials is None
        else "allow_live_credentials_required"
    )


def _credential_boundary(
    settings: LiveStartupSettings,
    checks: list[StartupGuardCheck],
    blockers: list[str],
) -> dict[str, Any]:
    env_names, invalid_count, unknown_count = _credential_env_names(
        settings.credential_env_names
    )
    missing = [
        name for name in REQUIRED_LIVE_CREDENTIAL_ENV_NAMES if name not in env_names
    ]
    accepted = not missing and invalid_count == 0 and unknown_count == 0
    checks.append(
        _check(
            "credential_boundary",
            "ok" if accepted else "blocked",
            (
                "Credential env names are declared; values are not inspected."
                if accepted
                else _credential_boundary_detail(
                    missing=missing,
                    invalid_count=invalid_count,
                    unknown_count=unknown_count,
                )
            ),
        )
    )
    if missing:
        blockers.append("credential_env_names_missing")
    if invalid_count:
        blockers.append("credential_env_names_invalid")
    if unknown_count:
        blockers.append("credential_env_names_unknown")
    return {
        "credential_env_names": list(env_names),
        "required_credential_env_names": list(REQUIRED_LIVE_CREDENTIAL_ENV_NAMES),
        "invalid_credential_env_name_count": invalid_count,
        "unknown_credential_env_name_count": unknown_count,
        "values_inspected": False,
        "key_prefix_recorded": False,
    }


def _capital_plan(starting_capital_usdt: float) -> dict[str, Any]:
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


def _source_policy_gate(settings: LiveStartupSettings) -> dict[str, Any]:
    blockers: list[str] = []
    multiplier = _finite_float(settings.policy_position_pct_multiplier)
    dry_run = _bool_or_none(settings.policy_dry_run)
    if dry_run is None:
        blockers.append("policy_dry_run_must_be_boolean")
    elif dry_run:
        blockers.append("policy_must_not_be_dry_run_for_live_canary")
    if multiplier is None:
        blockers.append("policy_multiplier_must_be_finite")
    elif not 0.0 <= multiplier <= LIVE_CANARY_MAX_MULTIPLIER:
        blockers.append("policy_multiplier_outside_live_canary_bounds")
    return {
        "dry_run": dry_run,
        "position_pct_multiplier": multiplier,
        "max_live_canary_multiplier": LIVE_CANARY_MAX_MULTIPLIER,
        "within_live_canary_bounds": not blockers,
        "blockers": blockers,
        "detail": (
            "SourcePolicy is within live-canary bounds."
            if not blockers
            else "SourcePolicy must be dry_run=False with a finite position_pct_multiplier <= 0.1."
        ),
    }


def _market_scope_gate(settings: LiveStartupSettings) -> dict[str, Any]:
    market_type_text = _text_or_none(settings.market_type)
    normalized_market_type = market_type_text.lower() if market_type_text else None
    margin_enabled = _bool_or_none(settings.margin_enabled)
    blockers: list[str] = []
    leverage = _finite_float(settings.max_leverage)
    if normalized_market_type is None:
        blockers.append("market_type_must_be_text")
    elif normalized_market_type != "spot":
        blockers.append("market_type_must_be_spot")
    if margin_enabled is None:
        blockers.append("margin_enabled_must_be_boolean")
    elif margin_enabled:
        blockers.append("margin_must_be_disabled")
    if leverage is None:
        blockers.append("leverage_must_be_finite")
    elif leverage != 1.0:
        blockers.append("leverage_must_be_one")
    accepted = not blockers
    return {
        "market_type": normalized_market_type,
        "margin_enabled": margin_enabled,
        "max_leverage": leverage,
        "spot_only_no_margin_no_leverage": accepted,
        "blockers": blockers,
        "detail": (
            "Market scope is Binance Spot only, no margin, no leverage."
            if accepted
            else "Phase 6 live canary requires spot-only, no margin, and max_leverage=1.0."
        ),
    }


def _live_risk_adr_gate(path: Path) -> dict[str, Any]:
    exists = path.exists()
    raw = path.read_bytes() if exists else b""
    artifact_sha256 = hashlib.sha256(raw).hexdigest() if exists else None
    text, decode_error = _decode_utf8(raw) if exists else ("", None)
    status = _document_status(text)
    return {
        "path": str(path),
        "exists": exists,
        "sha256": artifact_sha256,
        "decode_error": decode_error,
        "status": "invalid_utf8" if decode_error else status,
        "accepted": decode_error is None and status.lower().startswith("accepted"),
    }


def _live_readiness_report_gate(
    settings: LiveStartupSettings,
    *,
    git_state: GitState,
    generated_at_ns: int,
) -> dict[str, Any]:
    path = settings.live_readiness_report_path
    if not path.exists():
        return {
            "path": str(path),
            "sha256": None,
            "readiness_git": None,
            "expected_git_commit": git_state.commit,
            "expected_git_dirty": False,
            "expected_project_status_sha256": _file_sha256_or_none(
                settings.project_status_path
            ),
            "expected_project_status_path": str(settings.project_status_path),
            "accepted": False,
            "blocker": "live_readiness_report_not_found",
            "detail": f"{path} does not exist.",
        }
    raw = path.read_bytes()
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_non_standard_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "readiness_git": None,
            "expected_git_commit": git_state.commit,
            "expected_git_dirty": False,
            "expected_project_status_sha256": _file_sha256_or_none(
                settings.project_status_path
            ),
            "expected_project_status_path": str(settings.project_status_path),
            "accepted": False,
            "blocker": "live_readiness_report_invalid_json",
            "detail": f"{path} is not valid JSON: {exc}",
        }
    if not isinstance(payload, dict):
        expected_project_status_sha256 = _file_sha256_or_none(
            settings.project_status_path
        )
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "readiness_git": None,
            "expected_git_commit": git_state.commit,
            "expected_git_dirty": False,
            "expected_project_status_sha256": expected_project_status_sha256,
            "expected_project_status_path": str(settings.project_status_path),
            "accepted": False,
            "blocker": "live_readiness_report_gate_not_met",
            "detail": "Live readiness report failed checks: readiness_report_object",
            "problems": ["readiness_report_object"],
        }

    problems: list[str] = []
    freshness = _readiness_report_freshness(
        payload.get("generated_at_ns"),
        guard_generated_at_ns=generated_at_ns,
        max_age_seconds=settings.max_readiness_report_age_seconds,
    )
    problems.extend(str(item) for item in freshness["problems"])
    if payload.get("schema_version") != READINESS_SCHEMA_VERSION:
        problems.append("schema_version")
    settings_source = _text_or_none(settings.source)
    settings_model_version = _text_or_none(settings.model_version)
    if payload.get("source") != settings_source:
        problems.append("source")
    if payload.get("model_version") != settings_model_version:
        problems.append("model_version")
    if payload.get("readiness_gate_met") is not True:
        problems.append("readiness_gate_met")
    if payload.get("live_trading_allowed") is not False:
        problems.append("live_trading_allowed_must_remain_false")
    if payload.get("blockers"):
        problems.append("blockers_must_be_empty")
    report_git = _optional_dict(
        payload.get("git"),
        problem="readiness_git",
        problems=problems,
    )
    if report_git.get("dirty") is not False:
        problems.append("readiness_git_dirty")
    if report_git.get("commit") != git_state.commit:
        problems.append("readiness_git_commit")
    project_status = _optional_dict(
        payload.get("project_status"),
        problem="project_status",
        problems=problems,
    )
    expected_project_status_sha256 = _file_sha256_or_none(settings.project_status_path)
    project_status_sha256 = project_status.get("sha256")
    if (
        not project_status_sha256
        or expected_project_status_sha256 is None
        or project_status_sha256 != expected_project_status_sha256
    ):
        problems.append("project_status_sha256")
    continuity = _optional_dict(
        payload.get("continuity_summary"),
        problem="continuity_summary",
        problems=problems,
    )
    if continuity.get("required_gate_met") is not True:
        problems.append("testnet_continuity")
    problems.extend(_continuity_summary_problems(continuity))
    continuity_artifacts = payload.get("continuity_artifacts")
    continuity_artifact_problems = []
    if continuity.get("required_gate_met") is True:
        continuity_artifact_problems = _continuity_artifact_problems(
            continuity_artifacts,
            repo_root=settings.repo_root,
        )
        if continuity_artifact_problems:
            problems.append("testnet_continuity_artifacts")
    capital_plan = _optional_dict(
        payload.get("capital_plan"),
        problem="capital_plan",
        problems=problems,
    )
    if capital_plan.get("within_live_canary_range") is not True:
        problems.append("capital_plan")
    report_capital = capital_plan.get("starting_capital_usdt")
    try:
        report_capital_float = float(report_capital)
    except (TypeError, ValueError):
        report_capital_float = None
    if report_capital_float != settings.starting_capital_usdt:
        problems.append("starting_capital_usdt")
    market_scope = _optional_dict(
        payload.get("market_scope"),
        problem="market_scope",
        problems=problems,
    )
    if market_scope.get("spot_only_no_margin_no_leverage") is not True:
        problems.append("market_scope")
    settings_market_type = _text_or_none(settings.market_type)
    normalized_settings_market_type = (
        settings_market_type.lower() if settings_market_type else None
    )
    if market_scope.get("market_type") != normalized_settings_market_type:
        problems.append("market_type")
    settings_margin_enabled = _bool_or_none(settings.margin_enabled)
    if market_scope.get("margin_enabled") is not settings_margin_enabled:
        problems.append("margin_enabled")
    try:
        report_max_leverage = float(market_scope.get("max_leverage"))
    except (TypeError, ValueError):
        report_max_leverage = None
    if report_max_leverage != settings.max_leverage:
        problems.append("max_leverage")
    boundaries = _optional_dict(
        payload.get("boundaries"),
        problem="readiness_boundaries",
        problems=problems,
    )
    opened_boundaries = [
        key
        for key in (
            "starts_runtime",
            "loads_exchange_credentials",
            "mutates_source_policy",
            "writes_signal_event",
            "places_orders",
            "authorizes_live_trading",
        )
        if boundaries.get(key) is not False
    ]
    if opened_boundaries:
        problems.append("readiness_boundaries")
    live_risk_adr = _optional_dict(
        payload.get("live_risk_adr"),
        problem="live_risk_adr",
        problems=problems,
    )
    expected_live_risk_adr_sha256 = _file_sha256_or_none(settings.live_risk_adr_path)
    if live_risk_adr.get("accepted") is not True:
        problems.append("live_risk_adr")
    if (
        expected_live_risk_adr_sha256 is None
        or live_risk_adr.get("sha256") != expected_live_risk_adr_sha256
    ):
        problems.append("live_risk_adr_sha256")
    live_promotion_review = _optional_dict(
        payload.get("live_promotion_review"),
        problem="live_promotion_review",
        problems=problems,
    )
    expected_promotion_review_sha256 = _promotion_review_sha256_or_none(
        settings.live_promotion_review_path
    )
    if live_promotion_review.get("accepted") is not True:
        problems.append("live_promotion_review")
    if (
        expected_promotion_review_sha256 is None
        or live_promotion_review.get("sha256") != expected_promotion_review_sha256
    ):
        problems.append("live_promotion_review_sha256")
    problems = list(dict.fromkeys(problems))
    if problems:
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "readiness_git": report_git,
            "expected_git_commit": git_state.commit,
            "expected_git_dirty": False,
            "expected_project_status_sha256": expected_project_status_sha256,
            "expected_project_status_path": str(settings.project_status_path),
            "accepted": False,
            "blocker": "live_readiness_report_gate_not_met",
            "detail": "Live readiness report failed checks: " + ", ".join(problems),
            "problems": problems,
            "opened_boundaries": opened_boundaries,
            "freshness": freshness,
            "project_status": project_status,
            "continuity_artifacts": continuity_artifacts,
            "continuity_artifact_problems": continuity_artifact_problems,
            "live_risk_adr": live_risk_adr,
            "expected_live_risk_adr_sha256": expected_live_risk_adr_sha256,
            "live_promotion_review": live_promotion_review,
            "expected_live_promotion_review_sha256": expected_promotion_review_sha256,
        }
    return {
        "path": str(path),
        "sha256": artifact_sha256,
        "readiness_git": report_git,
        "expected_git_commit": git_state.commit,
        "expected_git_dirty": False,
        "expected_project_status_sha256": expected_project_status_sha256,
        "expected_project_status_path": str(settings.project_status_path),
        "accepted": True,
        "blocker": "",
        "detail": f"{path} proves the passive live-readiness gate and is fresh.",
        "freshness": freshness,
        "project_status": project_status,
        "continuity_artifacts": continuity_artifacts,
        "continuity_artifact_problems": continuity_artifact_problems,
        "live_risk_adr": live_risk_adr,
        "expected_live_risk_adr_sha256": expected_live_risk_adr_sha256,
        "live_promotion_review": live_promotion_review,
        "expected_live_promotion_review_sha256": expected_promotion_review_sha256,
    }


def _readiness_report_freshness(
    report_generated_at_ns: Any,
    *,
    guard_generated_at_ns: int,
    max_age_seconds: float,
) -> dict[str, Any]:
    problems: list[str] = []
    report_generated_ns: int | None
    if isinstance(report_generated_at_ns, bool):
        report_generated_ns = None
    else:
        try:
            report_generated_ns = _finite_int(report_generated_at_ns)
        except (TypeError, ValueError, OverflowError):
            report_generated_ns = None
    if report_generated_ns is None:
        problems.append("readiness_generated_at_ns")
        age_seconds = None
    else:
        age_seconds = (guard_generated_at_ns - report_generated_ns) / 1_000_000_000
    max_age_seconds_finite = _finite_float(max_age_seconds)
    if max_age_seconds_finite is None or max_age_seconds_finite <= 0:
        problems.append("max_readiness_report_age_seconds")
    elif age_seconds is not None:
        if age_seconds < 0:
            problems.append("readiness_generated_in_future")
        elif age_seconds > max_age_seconds_finite:
            problems.append("readiness_report_stale")
    return {
        "report_generated_at_ns": report_generated_ns,
        "guard_generated_at_ns": guard_generated_at_ns,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds_finite,
        "fresh": not problems,
        "problems": problems,
    }


def _continuity_summary_problems(continuity: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    required_days = _int_or_none(continuity.get("required_consecutive_days"))
    current_streak = _int_or_none(continuity.get("current_qualified_streak_days"))
    if required_days is None or required_days < REQUIRED_TESTNET_CONTINUITY_DAYS:
        problems.append("testnet_continuity_required_days")
    required_streak = max(required_days or 0, REQUIRED_TESTNET_CONTINUITY_DAYS)
    if current_streak is None or current_streak < required_streak:
        problems.append("testnet_continuity_current_streak")

    kill_switch_alerts = _int_or_none(continuity.get("kill_switch_alerts"))
    if kill_switch_alerts != 0:
        problems.append("testnet_continuity_kill_switch_alerts")

    emergency_flatten_alerts = _int_or_none(
        continuity.get("emergency_flatten_completed_alerts")
    )
    if emergency_flatten_alerts != 0:
        problems.append("testnet_continuity_emergency_flatten_alerts")

    restart_drift_days = continuity.get("restart_drift_days")
    if not isinstance(restart_drift_days, list) or restart_drift_days:
        problems.append("testnet_continuity_restart_drift_days")

    blockers = continuity.get("blockers")
    if blockers not in (None, []):
        problems.append("testnet_continuity_blockers")
    return problems


def _promotion_review_gate(settings: LiveStartupSettings) -> dict[str, Any]:
    path = settings.live_promotion_review_path
    if not path.exists():
        return {
            "path": str(path),
            "accepted": False,
            "blocker": "live_promotion_review_not_found",
            "detail": f"{path} does not exist.",
        }
    gate = evaluate_live_canary_promotion_review(
        path,
        source=_text_or_none(settings.source),
        model_version=_text_or_none(settings.model_version),
    )
    if not gate["accepted"]:
        return {
            **gate,
            "accepted": False,
            "blocker": "live_promotion_review_invalid",
        }
    return {
        **gate,
        "accepted": True,
        "blocker": "",
    }


def _promotion_review_sha256_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return promotion_review_sha256(path)
    except OSError:
        return None


def _continuity_artifact_problems(value: Any, *, repo_root: Path) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["continuity_artifacts_missing"]

    problems: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            problems.append("continuity_artifact_invalid")
            continue
        recorded_sha256 = item.get("sha256")
        if not isinstance(recorded_sha256, str) or not recorded_sha256:
            problems.append("continuity_artifact_sha256")
        if item.get("exists") is not True:
            problems.append("continuity_artifact_exists")

        manifest_path_raw = item.get("manifest_path")
        if not isinstance(manifest_path_raw, str) or not manifest_path_raw.strip():
            problems.append("continuity_artifact_manifest_path")
            continue
        manifest_path = Path(manifest_path_raw)
        if not manifest_path.is_absolute():
            manifest_path = repo_root / manifest_path
        actual_sha256 = _file_sha256_or_none(manifest_path)
        if actual_sha256 is None:
            problems.append("continuity_artifact_manifest_not_found")
        elif recorded_sha256 and actual_sha256 != recorded_sha256:
            problems.append("continuity_artifact_sha256_mismatch")

    return sorted(dict.fromkeys(problems))


def _file_sha256_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _optional_dict(
    value: Any,
    *,
    problem: str,
    problems: list[str],
) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    problems.append(problem)
    return {}


def _reject_non_standard_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _timestamp_ns_or_none(value: Any) -> int | None:
    timestamp_ns = _int_or_none(value)
    return timestamp_ns if timestamp_ns is not None and timestamp_ns >= 0 else None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return candidate if math.isfinite(candidate) else None


def _finite_int(value: Any) -> int:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("not finite")
    return int(value)


def _decode_utf8(raw: bytes) -> tuple[str, str | None]:
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return "", str(exc)


def _first_live_day_runbook_gate(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "sha256": None,
            "accepted": False,
            "blocker": "first_live_day_runbook_not_found",
            "detail": f"{path} does not exist.",
        }
    raw = path.read_bytes()
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    text, decode_error = _decode_utf8(raw)
    if decode_error:
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "accepted": False,
            "blocker": "first_live_day_runbook_invalid_utf8",
            "detail": f"{path} is not valid UTF-8: {decode_error}",
            "missing_sections": [],
            "status": "invalid_utf8",
            "decode_error": decode_error,
        }
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
            "sha256": artifact_sha256,
            "accepted": False,
            "blocker": "first_live_day_runbook_not_accepted",
            "detail": f"{path} status is {status!r}.",
            "missing_sections": missing_sections,
            "status": status,
        }
    if missing_sections:
        return {
            "path": str(path),
            "sha256": artifact_sha256,
            "accepted": False,
            "blocker": "first_live_day_runbook_incomplete",
            "detail": "Runbook missing required sections: "
            + ", ".join(missing_sections),
            "missing_sections": missing_sections,
            "status": status,
        }
    return {
        "path": str(path),
        "sha256": artifact_sha256,
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


def _text_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _has_text(value: Any) -> bool:
    return _text_or_none(value) is not None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _credential_env_names(value: Any) -> tuple[tuple[str, ...], int, int]:
    if isinstance(value, str | bytes):
        return (), 1, 0
    try:
        raw_names = tuple(value)
    except TypeError:
        return (), 1, 0

    allowed = set(REQUIRED_LIVE_CREDENTIAL_ENV_NAMES)
    env_names: list[str] = []
    invalid_count = 0
    unknown_count = 0
    for item in raw_names:
        name = _text_or_none(item)
        if name is None:
            invalid_count += 1
            continue
        if name not in allowed:
            unknown_count += 1
            continue
        if name not in env_names:
            env_names.append(name)
    return tuple(env_names), invalid_count, unknown_count


def _credential_boundary_detail(
    *,
    missing: list[str],
    invalid_count: int,
    unknown_count: int,
) -> str:
    details: list[str] = []
    if missing:
        details.append(
            "missing required live credential env names: " + ", ".join(missing)
        )
    if invalid_count:
        details.append(f"{invalid_count} credential env name value(s) were not text")
    if unknown_count:
        details.append(
            f"{unknown_count} unknown credential env name(s) were supplied but not echoed"
        )
    return "; ".join(details)


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
    parser.add_argument("--market-type", default="spot")
    parser.add_argument("--margin-enabled", action="store_true")
    parser.add_argument("--max-leverage", type=float, default=1.0)
    parser.add_argument(
        "--max-readiness-report-age-seconds",
        type=float,
        default=DEFAULT_MAX_READINESS_REPORT_AGE_SECONDS,
        help=(
            "Maximum accepted age for the saved phase6.live_readiness.v1 report "
            "before live startup must refuse."
        ),
    )
    parser.add_argument("--live-readiness-report-path", type=Path, required=True)
    parser.add_argument("--live-promotion-review-path", type=Path, required=True)
    parser.add_argument(
        "--first-live-day-runbook-path",
        type=Path,
        default=DEFAULT_FIRST_LIVE_DAY_RUNBOOK_PATH,
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
        project_status_path=args.project_status_path,
        live_risk_adr_path=args.live_risk_adr_path,
        repo_root=args.repo_root,
        operator=args.operator,
        credential_env_names=tuple(
            args.credential_env_names or REQUIRED_LIVE_CREDENTIAL_ENV_NAMES
        ),
        market_type=args.market_type,
        margin_enabled=bool(args.margin_enabled),
        max_leverage=float(args.max_leverage),
        max_readiness_report_age_seconds=float(args.max_readiness_report_age_seconds),
    )
    report = build_live_startup_guard_report(settings, git_state=git_state)
    if args.markdown:
        print(render_markdown_report(report))
    else:
        print(json.dumps(asdict(report), allow_nan=False, indent=2, sort_keys=True))
    return EXIT_OK if report.startup_allowed else EXIT_STARTUP_VALIDATION


if __name__ == "__main__":
    raise SystemExit(main())

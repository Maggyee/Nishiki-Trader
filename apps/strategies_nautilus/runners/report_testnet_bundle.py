"""Summarize an ADR-008 testnet canary bundle for retro evidence.

This reader is intentionally passive: it reads ``data/testnet/<run_id>``
artifacts and prints review evidence. It never loads exchange credentials,
starts a Nautilus runtime, or talks to Binance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.strategies_nautilus.runners.backtest_runner import validate_sidecar_bundle

SIDECAR_FILES = {
    "orders": "orders.parquet",
    "fills": "fills.parquet",
    "positions": "positions.parquet",
    "account_balances": "account_balances.parquet",
    "signal_lineage": "signal_lineage.parquet",
}

SIDECAR_RESULT_KEYS = {
    "orders": "orders_count",
    "fills": "fills_count",
    "positions": "positions_count",
    "account_balances": "account_rows",
    "signal_lineage": "lineage_rows",
}

KNOWN_ALERT_MSGS = (
    "restart_drift_detected",
    "ws_disconnected",
    "data_gap_exceeded_tolerance",
    "signal_lag_exceeded_threshold",
    "kill_switch_fired",
    "exchange_error_burst",
    "ws_reconnect_burst",
    "heartbeat_lost",
    "emergency_flatten_started",
    "emergency_flatten_completed",
)

MAX_TESTNET_EXCHANGE_ERRORS = 999
MAX_TESTNET_WS_RECONNECTS = 49
MAX_TESTNET_RESTART_SEQUENCE = 3


@dataclass(frozen=True)
class TestnetBundleReport:
    bundle_dir: str
    run_id: str
    manifest_sha256: str
    kind: str
    git_commit: str | None
    git_dirty: bool
    source: str | None
    model_version: str | None
    started_at: str | None
    finished_at: str | None
    elapsed_seconds: float | int | None
    shutdown_reason: str | None
    runtime: dict[str, Any]
    strategies_registered: int
    actors_registered: int
    enable_strategy_execution: bool
    write_live_sidecars: bool
    sidecar_success: bool | None
    sidecar_error: str | None
    sidecar_rows: dict[str, int]
    sidecar_mismatches: list[str]
    sidecar_schema_errors: list[str]
    heartbeat_count: int
    first_heartbeat_at: str | None
    last_heartbeat_at: str | None
    max_heartbeat_gap_seconds: float | None
    ws_disconnected_heartbeats: int
    max_ws_reconnect_count: int
    max_exchange_error_count: int
    heartbeat_open_orders_counts: dict[str, int]
    heartbeat_open_positions_counts: dict[str, int]
    alert_count: int
    alert_msg_counts: dict[str, int]
    alert_kind_counts: dict[str, int]
    alert_severity_counts: dict[str, int]
    malformed_heartbeat_lines: int
    malformed_alert_lines: int
    order_count: int
    fill_count: int
    position_count: int
    account_balance_rows: int
    lineage_rows: int
    first_signal_ts_event_ns: int | None
    last_signal_ts_event_ns: int | None
    decision_counts: dict[str, int]
    reason_counts: dict[str, int]
    lineage_rows_with_order_ids: int
    lineage_rows_with_fill_ids: int
    lineage_rows_with_position_id: int
    first_fill: dict[str, Any] | None
    last_fill: dict[str, Any] | None
    realized_pnl_total: float
    final_position_sides: dict[str, int]
    final_account_usdt: dict[str, float | int | str | None]
    clean_for_retro: bool
    review_blockers: list[str]
    recommendation: str


@dataclass(frozen=True)
class TestnetRunSummary:
    bundle_dir: str
    run_id: str
    date: str | None
    clean_for_retro: bool
    elapsed_seconds: float | int | None
    heartbeat_count: int
    max_heartbeat_gap_seconds: float | None
    alert_count: int
    order_count: int
    fill_count: int
    position_count: int
    account_balance_rows: int
    lineage_rows: int
    final_state: str
    realized_pnl_total: float
    review_blockers: list[str]


@dataclass(frozen=True)
class TestnetEvidenceSummary:
    bundle_dirs: list[str]
    run_count: int
    clean_run_count: int
    blocked_run_count: int
    clean_run_ids: list[str]
    blocked_run_ids: list[str]
    total_elapsed_seconds: float
    clean_elapsed_seconds: float
    total_heartbeats: int
    clean_heartbeats: int
    max_heartbeat_gap_seconds: float | None
    total_alerts: int
    clean_alerts: int
    alert_msg_counts: dict[str, int]
    total_orders: int
    total_fills: int
    total_positions: int
    total_account_balance_rows: int
    total_lineage_rows: int
    total_realized_pnl: float
    clean_orders: int
    clean_fills: int
    clean_positions: int
    clean_account_balance_rows: int
    clean_lineage_rows: int
    clean_realized_pnl: float
    final_flat_run_count: int
    review_blockers_by_run: dict[str, list[str]]
    per_run: list[TestnetRunSummary]
    recommendation: str


@dataclass(frozen=True)
class TestnetContinuityDay:
    date: str
    clean_elapsed_seconds: float
    total_elapsed_seconds: float
    clean_run_ids: list[str]
    blocked_run_ids: list[str]
    alert_count: int
    exchange_error_count: int
    ws_reconnect_count: int
    max_restart_sequence: int
    restart_drift_detected: bool
    kill_switch_alerts: int
    emergency_flatten_completed_alerts: int
    realized_pnl: float
    qualified: bool
    blockers: list[str]


@dataclass(frozen=True)
class TestnetContinuitySummary:
    bundle_dirs: list[str]
    min_clean_hours_per_day: float
    required_consecutive_days: int
    day_count: int
    qualified_day_count: int
    longest_qualified_streak_days: int
    current_qualified_streak_days: int
    required_gate_met: bool
    total_exchange_error_count: int
    total_ws_reconnect_count: int
    max_restart_sequence: int
    restart_drift_days: list[str]
    kill_switch_alerts: int
    emergency_flatten_completed_alerts: int
    blockers: list[str]
    days: list[TestnetContinuityDay]
    recommendation: str


def load_testnet_bundle_report(bundle_dir: Path) -> TestnetBundleReport:
    manifest_path = bundle_dir / "run_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
    kind = str(manifest_payload.get("kind") or "")
    if kind != "testnet":
        raise ValueError(f"{bundle_dir} is kind={kind!r}, expected 'testnet'")

    runtime = _dict_or_empty(manifest_payload.get("runtime"))
    sidecar_schema_errors = _sidecar_schema_errors(bundle_dir)
    sidecars = _read_sidecars(bundle_dir)
    sidecar_rows = {name: int(len(df)) for name, df in sidecars.items()}
    sidecar_mismatches = _sidecar_mismatches(runtime, sidecar_rows)

    heartbeats, malformed_heartbeats = _read_jsonl(bundle_dir / "logs" / "heartbeat.jsonl")
    alerts, malformed_alerts = _read_jsonl(bundle_dir / "logs" / "alerts.log")
    heartbeat_summary = _heartbeat_summary(heartbeats)

    fills = sidecars["fills"]
    positions = sidecars["positions"]
    account_balances = sidecars["account_balances"]
    lineage = sidecars["signal_lineage"]
    first_signal_ts_event_ns, last_signal_ts_event_ns = _signal_ts_event_bounds(lineage)

    source = _str_or_none(manifest_payload.get("source")) or _single_value(
        lineage,
        "source",
    )
    model_version = _str_or_none(manifest_payload.get("model_version")) or _single_value(
        lineage,
        "model_version",
    )
    sidecar_info = _dict_or_empty(runtime.get("sidecar"))
    sidecar_error = _str_or_none(sidecar_info.get("error"))
    review_blockers = _review_blockers(
        manifest_payload=manifest_payload,
        runtime=runtime,
        source=source,
        model_version=model_version,
        sidecar_rows=sidecar_rows,
        sidecar_mismatches=sidecar_mismatches,
        sidecar_schema_errors=sidecar_schema_errors,
        heartbeat_count=len(heartbeats),
        malformed_heartbeat_lines=malformed_heartbeats,
        alert_count=len(alerts),
        malformed_alert_lines=malformed_alerts,
        heartbeat_summary=heartbeat_summary,
        fills=fills,
        positions=positions,
        lineage=lineage,
    )

    return TestnetBundleReport(
        bundle_dir=str(bundle_dir),
        run_id=str(manifest_payload.get("run_id") or bundle_dir.name),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        kind=kind,
        git_commit=_str_or_none(manifest_payload.get("git_commit")),
        git_dirty=bool(manifest_payload.get("git_dirty")),
        source=source,
        model_version=model_version,
        started_at=_str_or_none(manifest_payload.get("started_at")),
        finished_at=_str_or_none(manifest_payload.get("finished_at")),
        elapsed_seconds=_number_or_none(manifest_payload.get("elapsed_seconds")),
        shutdown_reason=_str_or_none(runtime.get("shutdown_reason")),
        runtime=runtime,
        strategies_registered=_int_or_zero(runtime.get("strategies_registered")),
        actors_registered=_int_or_zero(runtime.get("actors_registered")),
        enable_strategy_execution=bool(runtime.get("enable_strategy_execution")),
        write_live_sidecars=bool(runtime.get("write_live_sidecars")),
        sidecar_success=_bool_or_none(sidecar_info.get("success")),
        sidecar_error=sidecar_error,
        sidecar_rows=sidecar_rows,
        sidecar_mismatches=sidecar_mismatches,
        sidecar_schema_errors=sidecar_schema_errors,
        heartbeat_count=len(heartbeats),
        first_heartbeat_at=heartbeat_summary["first_at"],
        last_heartbeat_at=heartbeat_summary["last_at"],
        max_heartbeat_gap_seconds=heartbeat_summary["max_gap_seconds"],
        ws_disconnected_heartbeats=heartbeat_summary["ws_disconnected"],
        max_ws_reconnect_count=heartbeat_summary["max_ws_reconnect_count"],
        max_exchange_error_count=heartbeat_summary["max_exchange_error_count"],
        heartbeat_open_orders_counts=heartbeat_summary["open_orders_counts"],
        heartbeat_open_positions_counts=heartbeat_summary["open_positions_counts"],
        alert_count=len(alerts),
        alert_msg_counts=_known_alert_counts(alerts),
        alert_kind_counts=_record_counts(alerts, "kind"),
        alert_severity_counts=_record_counts(alerts, "severity"),
        malformed_heartbeat_lines=malformed_heartbeats,
        malformed_alert_lines=malformed_alerts,
        order_count=sidecar_rows["orders"],
        fill_count=sidecar_rows["fills"],
        position_count=sidecar_rows["positions"],
        account_balance_rows=sidecar_rows["account_balances"],
        lineage_rows=sidecar_rows["signal_lineage"],
        first_signal_ts_event_ns=first_signal_ts_event_ns,
        last_signal_ts_event_ns=last_signal_ts_event_ns,
        decision_counts=_value_counts(lineage, "decision"),
        reason_counts=_value_counts(lineage, "reason"),
        lineage_rows_with_order_ids=_nonempty_count(lineage, "order_ids"),
        lineage_rows_with_fill_ids=_nonempty_count(lineage, "fill_ids"),
        lineage_rows_with_position_id=_nonempty_count(lineage, "position_id"),
        first_fill=_fill_summary(_first_row_by_ts(fills, "ts_event")),
        last_fill=_fill_summary(_last_row_by_ts(fills, "ts_event")),
        realized_pnl_total=_numeric_sum(positions, "realized_pnl"),
        final_position_sides=_value_counts(positions, "side"),
        final_account_usdt=_final_account_usdt(account_balances),
        clean_for_retro=not review_blockers,
        review_blockers=review_blockers,
        recommendation=(
            "ready_for_retro_evidence"
            if not review_blockers
            else "review_blockers_before_retro"
        ),
    )


def load_testnet_evidence_summary(
    bundle_dirs: list[Path],
) -> TestnetEvidenceSummary:
    reports = [load_testnet_bundle_report(bundle_dir) for bundle_dir in bundle_dirs]
    clean_reports = [report for report in reports if report.clean_for_retro]
    blocked_reports = [report for report in reports if not report.clean_for_retro]
    per_run = [_run_summary(report) for report in reports]
    return TestnetEvidenceSummary(
        bundle_dirs=[str(path) for path in bundle_dirs],
        run_count=len(reports),
        clean_run_count=len(clean_reports),
        blocked_run_count=len(blocked_reports),
        clean_run_ids=[report.run_id for report in clean_reports],
        blocked_run_ids=[report.run_id for report in blocked_reports],
        total_elapsed_seconds=_sum_elapsed_seconds(reports),
        clean_elapsed_seconds=_sum_elapsed_seconds(clean_reports),
        total_heartbeats=sum(report.heartbeat_count for report in reports),
        clean_heartbeats=sum(report.heartbeat_count for report in clean_reports),
        max_heartbeat_gap_seconds=_max_optional_float(
            report.max_heartbeat_gap_seconds for report in reports
        ),
        total_alerts=sum(report.alert_count for report in reports),
        clean_alerts=sum(report.alert_count for report in clean_reports),
        alert_msg_counts=_sum_count_dicts(
            report.alert_msg_counts for report in reports
        ),
        total_orders=sum(report.order_count for report in reports),
        total_fills=sum(report.fill_count for report in reports),
        total_positions=sum(report.position_count for report in reports),
        total_account_balance_rows=sum(
            report.account_balance_rows for report in reports
        ),
        total_lineage_rows=sum(report.lineage_rows for report in reports),
        total_realized_pnl=_sum_realized_pnl(reports),
        clean_orders=sum(report.order_count for report in clean_reports),
        clean_fills=sum(report.fill_count for report in clean_reports),
        clean_positions=sum(report.position_count for report in clean_reports),
        clean_account_balance_rows=sum(
            report.account_balance_rows for report in clean_reports
        ),
        clean_lineage_rows=sum(report.lineage_rows for report in clean_reports),
        clean_realized_pnl=_sum_realized_pnl(clean_reports),
        final_flat_run_count=sum(1 for report in reports if _is_final_flat(report)),
        review_blockers_by_run={
            report.run_id: report.review_blockers
            for report in reports
            if report.review_blockers
        },
        per_run=per_run,
        recommendation=(
            "ready_for_progress_evidence"
            if reports and not blocked_reports
            else "review_blocked_runs_before_progress_evidence"
        ),
    )


def load_testnet_continuity_summary(
    bundle_dirs: list[Path],
    *,
    min_clean_hours_per_day: float = 6.0,
    required_consecutive_days: int = 14,
) -> TestnetContinuitySummary:
    if min_clean_hours_per_day <= 0:
        raise ValueError("min_clean_hours_per_day must be positive")
    if required_consecutive_days <= 0:
        raise ValueError("required_consecutive_days must be positive")

    reports = [load_testnet_bundle_report(bundle_dir) for bundle_dir in bundle_dirs]
    reports_by_date: dict[str, list[TestnetBundleReport]] = {}
    for report in reports:
        report_date = _date_from_report(report)
        date_key = report_date or f"unknown:{report.run_id}"
        reports_by_date.setdefault(date_key, []).append(report)

    days = [
        _continuity_day(
            date_key,
            day_reports,
            min_clean_hours_per_day=min_clean_hours_per_day,
        )
        for date_key, day_reports in sorted(
            reports_by_date.items(),
            key=lambda item: _continuity_sort_key(item[0]),
        )
    ]
    longest_streak = _longest_qualified_streak(days)
    current_streak = _current_qualified_streak(days)
    total_exchange_errors = sum(day.exchange_error_count for day in days)
    total_ws_reconnects = sum(day.ws_reconnect_count for day in days)
    max_restart_sequence = max(
        (day.max_restart_sequence for day in days),
        default=0,
    )
    restart_drift_days = [
        day.date for day in days if day.restart_drift_detected
    ]
    kill_switch_alerts = sum(day.kill_switch_alerts for day in days)
    emergency_flatten_alerts = sum(
        day.emergency_flatten_completed_alerts for day in days
    )

    blockers = _continuity_summary_blockers(
        days=days,
        current_qualified_streak_days=current_streak,
        required_consecutive_days=required_consecutive_days,
        total_exchange_error_count=total_exchange_errors,
        total_ws_reconnect_count=total_ws_reconnects,
        max_restart_sequence=max_restart_sequence,
        restart_drift_days=restart_drift_days,
        kill_switch_alerts=kill_switch_alerts,
        emergency_flatten_completed_alerts=emergency_flatten_alerts,
    )
    return TestnetContinuitySummary(
        bundle_dirs=[str(path) for path in bundle_dirs],
        min_clean_hours_per_day=min_clean_hours_per_day,
        required_consecutive_days=required_consecutive_days,
        day_count=len(days),
        qualified_day_count=sum(1 for day in days if day.qualified),
        longest_qualified_streak_days=longest_streak,
        current_qualified_streak_days=current_streak,
        required_gate_met=not blockers,
        total_exchange_error_count=total_exchange_errors,
        total_ws_reconnect_count=total_ws_reconnects,
        max_restart_sequence=max_restart_sequence,
        restart_drift_days=restart_drift_days,
        kill_switch_alerts=kill_switch_alerts,
        emergency_flatten_completed_alerts=emergency_flatten_alerts,
        blockers=blockers,
        days=days,
        recommendation=(
            "ready_for_live_risk_adr_review"
            if not blockers
            else "continue_testnet_continuity"
        ),
    )


def render_text_report(report: TestnetBundleReport) -> str:
    blockers = ", ".join(report.review_blockers) if report.review_blockers else "none"
    return "\n".join(
        [
            f"testnet bundle: {report.bundle_dir}",
            f"run_id: {report.run_id}",
            f"manifest_sha256: {report.manifest_sha256}",
            f"source_model: {report.source or 'unknown'} / {report.model_version or 'unknown'}",
            (
                "runtime: "
                f"shutdown_reason={report.shutdown_reason or 'unknown'} "
                f"elapsed_seconds={report.elapsed_seconds} "
                f"git_dirty={report.git_dirty} "
                f"strategies={report.strategies_registered} "
                f"actors={report.actors_registered} "
                f"strategy_execution={report.enable_strategy_execution} "
                f"write_live_sidecars={report.write_live_sidecars}"
            ),
            (
                "heartbeats: "
                f"count={report.heartbeat_count} "
                f"first={report.first_heartbeat_at or 'none'} "
                f"last={report.last_heartbeat_at or 'none'} "
                f"max_gap_seconds={report.max_heartbeat_gap_seconds} "
                f"ws_disconnected={report.ws_disconnected_heartbeats} "
                f"max_ws_reconnect_count={report.max_ws_reconnect_count} "
                f"max_exchange_error_count={report.max_exchange_error_count}"
            ),
            (
                "alerts: "
                f"count={report.alert_count} "
                f"msgs={json.dumps(report.alert_msg_counts, sort_keys=True)}"
            ),
            (
                "sidecars: "
                f"orders={report.order_count} fills={report.fill_count} "
                f"positions={report.position_count} "
                f"account_balances={report.account_balance_rows} "
                f"lineage={report.lineage_rows} "
                f"first_signal_ts_event_ns={report.first_signal_ts_event_ns} "
                f"last_signal_ts_event_ns={report.last_signal_ts_event_ns} "
                f"mismatches={report.sidecar_mismatches or 'none'}"
            ),
            (
                "lineage: "
                f"decisions={json.dumps(report.decision_counts, sort_keys=True)} "
                f"with_order_ids={report.lineage_rows_with_order_ids} "
                f"with_fill_ids={report.lineage_rows_with_fill_ids} "
                f"with_position_id={report.lineage_rows_with_position_id}"
            ),
            (
                "fills: "
                f"first={json.dumps(report.first_fill, sort_keys=True)} "
                f"last={json.dumps(report.last_fill, sort_keys=True)}"
            ),
            (
                "positions: "
                f"sides={json.dumps(report.final_position_sides, sort_keys=True)} "
                f"realized_pnl_total={report.realized_pnl_total}"
            ),
            (
                "final_account_usdt: "
                f"{json.dumps(report.final_account_usdt, sort_keys=True)}"
            ),
            f"clean_for_retro: {report.clean_for_retro}",
            f"review_blockers: {blockers}",
            f"recommendation: {report.recommendation}",
        ]
    )


def render_summary_text(summary: TestnetEvidenceSummary) -> str:
    blocked = ", ".join(summary.blocked_run_ids) if summary.blocked_run_ids else "none"
    clean = ", ".join(summary.clean_run_ids) if summary.clean_run_ids else "none"
    return "\n".join(
        [
            "testnet evidence summary",
            f"run_count: {summary.run_count}",
            f"clean_run_count: {summary.clean_run_count}",
            f"blocked_run_count: {summary.blocked_run_count}",
            f"clean_run_ids: {clean}",
            f"blocked_run_ids: {blocked}",
            f"clean_elapsed_hours: {summary.clean_elapsed_seconds / 3600:.2f}",
            (
                "clean_totals: "
                f"orders={summary.clean_orders} fills={summary.clean_fills} "
                f"positions={summary.clean_positions} "
                f"heartbeats={summary.clean_heartbeats} "
                f"alerts={summary.clean_alerts} "
                f"realized_pnl={summary.clean_realized_pnl:.8g}"
            ),
            (
                "all_totals: "
                f"orders={summary.total_orders} fills={summary.total_fills} "
                f"positions={summary.total_positions} "
                f"heartbeats={summary.total_heartbeats} "
                f"alerts={summary.total_alerts} "
                f"realized_pnl={summary.total_realized_pnl:.8g}"
            ),
            (
                "alert_msg_counts: "
                f"{json.dumps(summary.alert_msg_counts, sort_keys=True)}"
            ),
            f"recommendation: {summary.recommendation}",
        ]
    )


def render_markdown_summary(summary: TestnetEvidenceSummary) -> str:
    lines = [
        "# Testnet Evidence Summary",
        "",
        (
            f"- clean_run_count: {summary.clean_run_count}/{summary.run_count}"
        ),
        f"- clean_elapsed_hours: {summary.clean_elapsed_seconds / 3600:.2f}",
        (
            "- clean_totals: "
            f"orders={summary.clean_orders} / fills={summary.clean_fills} / "
            f"positions={summary.clean_positions} / "
            f"heartbeats={summary.clean_heartbeats} / alerts={summary.clean_alerts}"
        ),
        f"- clean_realized_pnl: {summary.clean_realized_pnl:.8g} USDT",
        f"- recommendation: `{summary.recommendation}`",
        "",
        (
            "| run_id | date | clean | heartbeats | alerts | sidecars | "
            "final state | realized PnL | blockers |"
        ),
        "|---|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for run in summary.per_run:
        sidecars = (
            f"orders={run.order_count} / fills={run.fill_count} / "
            f"positions={run.position_count} / account={run.account_balance_rows} / "
            f"lineage={run.lineage_rows}"
        )
        blockers = ", ".join(run.review_blockers) if run.review_blockers else "none"
        lines.append(
            "| "
            f"`{run.run_id}` | "
            f"{run.date or 'unknown'} | "
            f"{str(run.clean_for_retro).lower()} | "
            f"{run.heartbeat_count} | "
            f"{run.alert_count} | "
            f"{sidecars} | "
            f"{run.final_state} | "
            f"{run.realized_pnl_total:.8g} | "
            f"{blockers} |"
        )
    return "\n".join(lines)


def render_continuity_text(summary: TestnetContinuitySummary) -> str:
    blockers = ", ".join(summary.blockers) if summary.blockers else "none"
    return "\n".join(
        [
            "testnet continuity summary",
            f"day_count: {summary.day_count}",
            f"qualified_day_count: {summary.qualified_day_count}",
            f"min_clean_hours_per_day: {summary.min_clean_hours_per_day:.2f}",
            f"required_consecutive_days: {summary.required_consecutive_days}",
            (
                "qualified_streaks: "
                f"current={summary.current_qualified_streak_days} "
                f"longest={summary.longest_qualified_streak_days}"
            ),
            (
                "adr_thresholds: "
                f"exchange_error_count={summary.total_exchange_error_count} "
                f"ws_reconnect_count={summary.total_ws_reconnect_count} "
                f"max_restart_sequence={summary.max_restart_sequence} "
                f"restart_drift_days={summary.restart_drift_days or 'none'} "
                f"kill_switch_alerts={summary.kill_switch_alerts} "
                "emergency_flatten_completed_alerts="
                f"{summary.emergency_flatten_completed_alerts}"
            ),
            f"required_gate_met: {summary.required_gate_met}",
            f"blockers: {blockers}",
            f"recommendation: {summary.recommendation}",
        ]
    )


def render_continuity_markdown(summary: TestnetContinuitySummary) -> str:
    blockers = ", ".join(summary.blockers) if summary.blockers else "none"
    lines = [
        "# Testnet Continuity Summary",
        "",
        (
            f"- qualified_day_count: "
            f"{summary.qualified_day_count}/{summary.day_count}"
        ),
        (
            f"- current_qualified_streak_days: "
            f"{summary.current_qualified_streak_days}/"
            f"{summary.required_consecutive_days}"
        ),
        f"- longest_qualified_streak_days: {summary.longest_qualified_streak_days}",
        f"- min_clean_hours_per_day: {summary.min_clean_hours_per_day:.2f}",
        (
            "- adr_thresholds: "
            f"exchange_errors={summary.total_exchange_error_count}/"
            f"{MAX_TESTNET_EXCHANGE_ERRORS + 1} max exclusive, "
            f"ws_reconnects={summary.total_ws_reconnect_count}/"
            f"{MAX_TESTNET_WS_RECONNECTS + 1} max exclusive, "
            f"restart_sequence={summary.max_restart_sequence}/"
            f"{MAX_TESTNET_RESTART_SEQUENCE} max"
        ),
        (
            "- alert_thresholds: "
            f"kill_switch={summary.kill_switch_alerts}, "
            "emergency_flatten_completed="
            f"{summary.emergency_flatten_completed_alerts}"
        ),
        f"- required_gate_met: {str(summary.required_gate_met).lower()}",
        f"- blockers: {blockers}",
        f"- recommendation: `{summary.recommendation}`",
        "",
        (
            "| date | qualified | clean hours | runs | alerts | exchange errors | "
            "ws reconnects | restart seq | realized PnL | blockers |"
        ),
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for day in summary.days:
        blockers = ", ".join(day.blockers) if day.blockers else "none"
        lines.append(
            "| "
            f"{day.date} | "
            f"{str(day.qualified).lower()} | "
            f"{day.clean_elapsed_seconds / 3600:.2f} | "
            f"{_continuity_run_ids_label(day)} | "
            f"{day.alert_count} | "
            f"{day.exchange_error_count} | "
            f"{day.ws_reconnect_count} | "
            f"{day.max_restart_sequence} | "
            f"{day.realized_pnl:.8g} | "
            f"{blockers} |"
        )
    return "\n".join(lines)


def _run_summary(report: TestnetBundleReport) -> TestnetRunSummary:
    return TestnetRunSummary(
        bundle_dir=report.bundle_dir,
        run_id=report.run_id,
        date=_date_from_report(report),
        clean_for_retro=report.clean_for_retro,
        elapsed_seconds=report.elapsed_seconds,
        heartbeat_count=report.heartbeat_count,
        max_heartbeat_gap_seconds=report.max_heartbeat_gap_seconds,
        alert_count=report.alert_count,
        order_count=report.order_count,
        fill_count=report.fill_count,
        position_count=report.position_count,
        account_balance_rows=report.account_balance_rows,
        lineage_rows=report.lineage_rows,
        final_state=_final_state_label(report),
        realized_pnl_total=report.realized_pnl_total,
        review_blockers=report.review_blockers,
    )


def _continuity_run_ids_label(day: TestnetContinuityDay) -> str:
    labels: list[str] = []
    if day.clean_run_ids:
        labels.append(
            "clean="
            + ", ".join(f"`{run_id}`" for run_id in day.clean_run_ids)
        )
    if day.blocked_run_ids:
        labels.append(
            "blocked="
            + ", ".join(f"`{run_id}`" for run_id in day.blocked_run_ids)
        )
    return "; ".join(labels) if labels else "none"


def _continuity_day(
    date_key: str,
    reports: list[TestnetBundleReport],
    *,
    min_clean_hours_per_day: float,
) -> TestnetContinuityDay:
    clean_reports = [report for report in reports if report.clean_for_retro]
    blocked_reports = [report for report in reports if not report.clean_for_retro]
    clean_elapsed_seconds = _sum_elapsed_seconds(clean_reports)
    total_elapsed_seconds = _sum_elapsed_seconds(reports)
    alert_count = sum(report.alert_count for report in reports)
    exchange_error_count = sum(_exchange_error_count(report) for report in reports)
    ws_reconnect_count = sum(_ws_reconnect_count(report) for report in reports)
    max_restart_sequence = max(
        (_restart_sequence(report) for report in reports),
        default=0,
    )
    restart_drift_detected = any(_restart_drift_detected(report) for report in reports)
    kill_switch_alerts = sum(
        report.alert_msg_counts.get("kill_switch_fired", 0) for report in reports
    )
    emergency_flatten_alerts = sum(
        report.alert_msg_counts.get("emergency_flatten_completed", 0)
        for report in reports
    )
    blockers = _continuity_day_blockers(
        date_key=date_key,
        clean_elapsed_seconds=clean_elapsed_seconds,
        min_clean_hours_per_day=min_clean_hours_per_day,
        blocked_reports=blocked_reports,
        alert_count=alert_count,
        restart_drift_detected=restart_drift_detected,
        kill_switch_alerts=kill_switch_alerts,
        emergency_flatten_completed_alerts=emergency_flatten_alerts,
    )
    return TestnetContinuityDay(
        date=date_key,
        clean_elapsed_seconds=clean_elapsed_seconds,
        total_elapsed_seconds=total_elapsed_seconds,
        clean_run_ids=[report.run_id for report in clean_reports],
        blocked_run_ids=[report.run_id for report in blocked_reports],
        alert_count=alert_count,
        exchange_error_count=exchange_error_count,
        ws_reconnect_count=ws_reconnect_count,
        max_restart_sequence=max_restart_sequence,
        restart_drift_detected=restart_drift_detected,
        kill_switch_alerts=kill_switch_alerts,
        emergency_flatten_completed_alerts=emergency_flatten_alerts,
        realized_pnl=_sum_realized_pnl(reports),
        qualified=not blockers,
        blockers=blockers,
    )


def _continuity_day_blockers(
    *,
    date_key: str,
    clean_elapsed_seconds: float,
    min_clean_hours_per_day: float,
    blocked_reports: list[TestnetBundleReport],
    alert_count: int,
    restart_drift_detected: bool,
    kill_switch_alerts: int,
    emergency_flatten_completed_alerts: int,
) -> list[str]:
    blockers: list[str] = []
    if _parse_date(date_key) is None:
        blockers.append("date_unknown")
    min_clean_seconds = min_clean_hours_per_day * 3600
    if clean_elapsed_seconds < min_clean_seconds:
        blockers.append(
            "clean_elapsed_hours="
            f"{clean_elapsed_seconds / 3600:.2f}<min={min_clean_hours_per_day:.2f}"
        )
    if blocked_reports:
        blockers.append(
            "blocked_runs="
            + ",".join(report.run_id for report in blocked_reports)
        )
    if alert_count:
        blockers.append(f"alerts={alert_count}")
    if restart_drift_detected:
        blockers.append("restart_drift_detected")
    if kill_switch_alerts:
        blockers.append(f"kill_switch_fired={kill_switch_alerts}")
    if emergency_flatten_completed_alerts:
        blockers.append(
            "emergency_flatten_completed="
            f"{emergency_flatten_completed_alerts}"
        )
    return blockers


def _continuity_summary_blockers(
    *,
    days: list[TestnetContinuityDay],
    current_qualified_streak_days: int,
    required_consecutive_days: int,
    total_exchange_error_count: int,
    total_ws_reconnect_count: int,
    max_restart_sequence: int,
    restart_drift_days: list[str],
    kill_switch_alerts: int,
    emergency_flatten_completed_alerts: int,
) -> list[str]:
    blockers: list[str] = []
    if any(_parse_date(day.date) is None for day in days):
        blockers.append("unknown_date_days_present")
    if current_qualified_streak_days < required_consecutive_days:
        blockers.append(
            "current_qualified_streak_days="
            f"{current_qualified_streak_days}<required={required_consecutive_days}"
        )
    if total_exchange_error_count > MAX_TESTNET_EXCHANGE_ERRORS:
        blockers.append(
            "exchange_error_count="
            f"{total_exchange_error_count}>{MAX_TESTNET_EXCHANGE_ERRORS}"
        )
    if total_ws_reconnect_count > MAX_TESTNET_WS_RECONNECTS:
        blockers.append(
            "ws_reconnect_count="
            f"{total_ws_reconnect_count}>{MAX_TESTNET_WS_RECONNECTS}"
        )
    if max_restart_sequence > MAX_TESTNET_RESTART_SEQUENCE:
        blockers.append(
            "max_restart_sequence="
            f"{max_restart_sequence}>{MAX_TESTNET_RESTART_SEQUENCE}"
        )
    if restart_drift_days:
        blockers.append("restart_drift_days=" + ",".join(restart_drift_days))
    if kill_switch_alerts:
        blockers.append(f"kill_switch_fired={kill_switch_alerts}")
    if emergency_flatten_completed_alerts:
        blockers.append(
            "emergency_flatten_completed="
            f"{emergency_flatten_completed_alerts}"
        )
    return blockers


def _longest_qualified_streak(days: list[TestnetContinuityDay]) -> int:
    longest = 0
    current = 0
    previous_date: date | None = None
    for day in days:
        parsed_date = _parse_date(day.date)
        if not day.qualified or parsed_date is None:
            current = 0
            previous_date = parsed_date
            continue
        if previous_date is not None and parsed_date == previous_date + timedelta(days=1):
            current += 1
        else:
            current = 1
        previous_date = parsed_date
        longest = max(longest, current)
    return longest


def _current_qualified_streak(days: list[TestnetContinuityDay]) -> int:
    valid_days = [day for day in days if _parse_date(day.date) is not None]
    if not valid_days or not valid_days[-1].qualified:
        return 0
    streak = 0
    expected_date: date | None = None
    for day in reversed(valid_days):
        parsed_date = _parse_date(day.date)
        if parsed_date is None or not day.qualified:
            break
        if expected_date is not None and parsed_date != expected_date:
            break
        streak += 1
        expected_date = parsed_date - timedelta(days=1)
    return streak


def _continuity_sort_key(date_key: str) -> tuple[int, int | str]:
    parsed = _parse_date(date_key)
    if parsed is None:
        return (0, date_key)
    return (1, parsed.toordinal())


def _exchange_error_count(report: TestnetBundleReport) -> int:
    return max(
        _int_or_zero(report.runtime.get("exchange_error_count")),
        report.max_exchange_error_count,
    )


def _ws_reconnect_count(report: TestnetBundleReport) -> int:
    return max(
        _int_or_zero(report.runtime.get("ws_reconnect_count")),
        report.max_ws_reconnect_count,
    )


def _restart_sequence(report: TestnetBundleReport) -> int:
    return _int_or_zero(report.runtime.get("restart_sequence"))


def _restart_drift_detected(report: TestnetBundleReport) -> bool:
    return bool(report.runtime.get("restart_drift_detected")) or bool(
        report.alert_msg_counts.get("restart_drift_detected", 0)
    )


def _date_from_report(report: TestnetBundleReport) -> str | None:
    if report.started_at and len(report.started_at) >= 10:
        return report.started_at[:10]
    if len(report.run_id) >= 8 and report.run_id[:8].isdigit():
        raw = report.run_id[:8]
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _final_state_label(report: TestnetBundleReport) -> str:
    if not report.final_position_sides:
        return "none"
    if set(report.final_position_sides) == {"FLAT"}:
        return "FLAT"
    return ", ".join(
        f"{side}:{count}" for side, count in sorted(report.final_position_sides.items())
    )


def _is_final_flat(report: TestnetBundleReport) -> bool:
    return bool(report.final_position_sides) and set(report.final_position_sides) == {
        "FLAT"
    }


def _sum_elapsed_seconds(reports: list[TestnetBundleReport]) -> float:
    return float(
        sum(
            report.elapsed_seconds
            for report in reports
            if isinstance(report.elapsed_seconds, int | float)
        )
    )


def _sum_realized_pnl(reports: list[TestnetBundleReport]) -> float:
    return float(sum(report.realized_pnl_total for report in reports))


def _max_optional_float(values: Any) -> float | None:
    floats = [float(value) for value in values if value is not None]
    return max(floats) if floats else None


def _sum_count_dicts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        for key, count in value.items():
            counts[str(key)] = counts.get(str(key), 0) + int(count)
    return dict(sorted(counts.items()))


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    records: list[dict[str, Any]] = []
    malformed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            records.append(payload)
        else:
            malformed += 1
    return records, malformed


def _sidecar_schema_errors(bundle_dir: Path) -> list[str]:
    try:
        validate_sidecar_bundle(bundle_dir)
    except Exception as exc:  # noqa: BLE001 - report all validation failures as evidence.
        return [str(exc)]
    return []


def _read_sidecars(bundle_dir: Path) -> dict[str, pd.DataFrame]:
    sidecars: dict[str, pd.DataFrame] = {}
    for name, filename in SIDECAR_FILES.items():
        path = bundle_dir / filename
        if path.exists():
            sidecars[name] = pd.read_parquet(path)
        else:
            sidecars[name] = pd.DataFrame()
    return sidecars


def _sidecar_mismatches(
    runtime: dict[str, Any],
    sidecar_rows: dict[str, int],
) -> list[str]:
    sidecar = _dict_or_empty(runtime.get("sidecar"))
    result = _dict_or_empty(sidecar.get("result"))
    mismatches: list[str] = []
    if bool(runtime.get("write_live_sidecars")) and not result:
        mismatches.append("sidecar_result_missing")
        return mismatches
    for name, result_key in SIDECAR_RESULT_KEYS.items():
        if result_key not in result:
            continue
        expected = _int_or_zero(result.get(result_key))
        actual = sidecar_rows.get(name, 0)
        if expected != actual:
            mismatches.append(
                f"sidecar_mismatch:{name} manifest={expected} actual={actual}"
            )
    return mismatches


def _heartbeat_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    parsed = [_parse_iso(record.get("ts")) for record in records]
    parsed = [value for value in parsed if value is not None]
    gaps = [
        (current - previous).total_seconds()
        for previous, current in zip(parsed, parsed[1:], strict=False)
    ]
    return {
        "first_at": _str_or_none(records[0].get("ts")) if records else None,
        "last_at": _str_or_none(records[-1].get("ts")) if records else None,
        "max_gap_seconds": round(max(gaps), 6) if gaps else None,
        "ws_disconnected": sum(
            1 for record in records if record.get("ws_connected") is False
        ),
        "max_ws_reconnect_count": _max_int(records, "ws_reconnect_count"),
        "max_exchange_error_count": _max_int(records, "exchange_error_count"),
        "open_orders_counts": _record_counts(records, "open_orders"),
        "open_positions_counts": _record_counts(records, "open_positions"),
    }


def _known_alert_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {msg: 0 for msg in KNOWN_ALERT_MSGS}
    for msg, count in _record_counts(records, "msg").items():
        counts[msg] = count
    return counts


def _record_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items()))


def _max_int(records: list[dict[str, Any]], key: str) -> int:
    values = [_int_or_none(record.get(key)) for record in records]
    ints = [value for value in values if value is not None]
    return max(ints) if ints else 0


def _value_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    counts = df[column].fillna("").astype(str).value_counts(sort=False).to_dict()
    return {str(key): int(value) for key, value in counts.items()}


def _signal_ts_event_bounds(lineage: pd.DataFrame) -> tuple[int | None, int | None]:
    if lineage.empty or "ts_event" not in lineage.columns:
        return None, None
    ts_events = pd.to_numeric(lineage["ts_event"], errors="coerce").dropna()
    if ts_events.empty:
        return None, None
    return int(ts_events.min()), int(ts_events.max())


def _single_value(df: pd.DataFrame, column: str) -> str | None:
    if df.empty or column not in df.columns:
        return None
    values = sorted(value for value in df[column].fillna("").astype(str).unique() if value)
    return values[0] if len(values) == 1 else None


def _nonempty_count(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df.columns:
        return 0
    return int(df[column].fillna("").astype(str).str.len().gt(0).sum())


def _numeric_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0.0).sum())


def _first_row_by_ts(df: pd.DataFrame, column: str) -> dict[str, Any] | None:
    if df.empty:
        return None
    ordered = df.sort_values(column, kind="stable") if column in df.columns else df
    return ordered.iloc[0].to_dict()


def _last_row_by_ts(df: pd.DataFrame, column: str) -> dict[str, Any] | None:
    if df.empty:
        return None
    ordered = df.sort_values(column, kind="stable") if column in df.columns else df
    return ordered.iloc[-1].to_dict()


def _fill_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = (
        "fill_id",
        "order_id",
        "client_order_id",
        "venue_order_id",
        "trade_id",
        "side",
        "quantity",
        "price",
        "currency",
        "ts_event",
        "signal_id",
    )
    return {key: _json_scalar(row.get(key)) for key in keys if key in row}


def _final_account_usdt(df: pd.DataFrame) -> dict[str, float | int | str | None]:
    if df.empty or "currency" not in df.columns:
        return {}
    usdt = df[df["currency"].fillna("").astype(str).eq("USDT")]
    if usdt.empty:
        return {}
    if "ts_event" in usdt.columns:
        usdt = usdt.sort_values("ts_event", kind="stable")
    row = usdt.iloc[-1].to_dict()
    return {
        key: _json_scalar(row.get(key))
        for key in ("ts_event", "venue", "account_id", "currency", "total", "free", "locked")
        if key in row
    }


def _review_blockers(
    *,
    manifest_payload: dict[str, Any],
    runtime: dict[str, Any],
    source: str | None,
    model_version: str | None,
    sidecar_rows: dict[str, int],
    sidecar_mismatches: list[str],
    sidecar_schema_errors: list[str],
    heartbeat_count: int,
    malformed_heartbeat_lines: int,
    alert_count: int,
    malformed_alert_lines: int,
    heartbeat_summary: dict[str, Any],
    fills: pd.DataFrame,
    positions: pd.DataFrame,
    lineage: pd.DataFrame,
) -> list[str]:
    blockers: list[str] = []
    if bool(manifest_payload.get("git_dirty")):
        blockers.append("git_dirty")
    if runtime.get("shutdown_reason") != "max_duration":
        blockers.append(f"shutdown_reason={runtime.get('shutdown_reason') or 'unknown'}")
    if not runtime.get("enable_strategy_execution"):
        blockers.append("strategy_execution_disabled")
    if not runtime.get("write_live_sidecars"):
        blockers.append("write_live_sidecars_disabled")
    if runtime.get("open_orders") != 0:
        blockers.append(f"open_orders={runtime.get('open_orders')}")
    sidecar = _dict_or_empty(runtime.get("sidecar"))
    positions_flat = _positions_are_flat(positions)
    sidecar_final_state_authoritative = (
        sidecar.get("success") is True
        and sidecar_rows["positions"] > 0
        and positions_flat
    )
    if runtime.get("open_positions") != 0 and not positions_flat:
        blockers.append(f"open_positions={runtime.get('open_positions')}")
    if (
        runtime.get("open_state_source") != "live_sidecars"
        and not sidecar_final_state_authoritative
    ):
        blockers.append("open_state_source_not_live_sidecars")
    if _int_or_zero(runtime.get("strategies_registered")) <= 0:
        blockers.append("no_strategies_registered")
    if source is None:
        blockers.append("source_unknown")
    if model_version is None:
        blockers.append("model_version_unknown")
    if sidecar.get("success") is not True:
        blockers.append("sidecar_write_not_successful")
    if sidecar.get("error"):
        blockers.append(f"sidecar_error={sidecar.get('error')}")
    blockers.extend(sidecar_schema_errors)
    blockers.extend(sidecar_mismatches)
    if heartbeat_count <= 0:
        blockers.append("no_heartbeats")
    if malformed_heartbeat_lines:
        blockers.append(f"malformed_heartbeat_lines={malformed_heartbeat_lines}")
    if alert_count:
        blockers.append(f"alerts={alert_count}")
    if malformed_alert_lines:
        blockers.append(f"malformed_alert_lines={malformed_alert_lines}")
    if heartbeat_summary["ws_disconnected"]:
        blockers.append(f"ws_disconnected_heartbeats={heartbeat_summary['ws_disconnected']}")
    if heartbeat_summary["max_ws_reconnect_count"]:
        blockers.append(f"max_ws_reconnect_count={heartbeat_summary['max_ws_reconnect_count']}")
    if heartbeat_summary["max_exchange_error_count"]:
        blockers.append(
            f"max_exchange_error_count={heartbeat_summary['max_exchange_error_count']}"
        )
    if sidecar_rows["orders"] <= 0:
        blockers.append("no_orders")
    if sidecar_rows["fills"] <= 0:
        blockers.append("no_fills")
    if sidecar_rows["positions"] <= 0:
        blockers.append("no_positions")
    if sidecar_rows["signal_lineage"] <= 0:
        blockers.append("no_signal_lineage")
    if sidecar_rows["orders"] != sidecar_rows["fills"]:
        blockers.append(
            f"orders_fills_mismatch orders={sidecar_rows['orders']} fills={sidecar_rows['fills']}"
        )
    if _nonempty_count(lineage, "order_ids") <= 0:
        blockers.append("no_lineage_order_ids")
    if _nonempty_count(lineage, "fill_ids") <= 0:
        blockers.append("no_lineage_fill_ids")
    if not _any_fill_has_signal_id(fills):
        blockers.append("no_fill_signal_id")
    if not positions_flat:
        blockers.append("positions_not_flat")
    return blockers


def _any_fill_has_signal_id(fills: pd.DataFrame) -> bool:
    return _nonempty_count(fills, "signal_id") > 0


def _positions_are_flat(positions: pd.DataFrame) -> bool:
    if positions.empty:
        return False
    if "side" not in positions.columns:
        return False
    sides = {side for side in positions["side"].fillna("").astype(str).unique() if side}
    return bool(sides) and sides <= {"FLAT"}


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number_or_none(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _int_or_zero(value: Any) -> int:
    return _int_or_none(value) or 0


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize an ADR-008 testnet canary bundle for retro evidence.",
    )
    parser.add_argument("bundle_dirs", type=Path, nargs="+")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full report as JSON instead of the text summary.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help=(
            "Emit a Markdown aggregate summary. With one bundle this still "
            "renders an aggregate table."
        ),
    )
    parser.add_argument(
        "--continuity",
        action="store_true",
        help="Emit a per-day continuity gate summary for 14-day testnet evidence.",
    )
    parser.add_argument(
        "--min-clean-hours-per-day",
        type=float,
        default=6.0,
        help="Minimum clean completed testnet hours required for a qualified day.",
    )
    parser.add_argument(
        "--required-consecutive-days",
        type=int,
        default=14,
        help="Required current consecutive qualified days for the continuity gate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.continuity:
            continuity = load_testnet_continuity_summary(
                list(args.bundle_dirs),
                min_clean_hours_per_day=args.min_clean_hours_per_day,
                required_consecutive_days=args.required_consecutive_days,
            )
            if args.json:
                print(json.dumps(asdict(continuity), indent=2, sort_keys=True))
            elif args.markdown:
                print(render_continuity_markdown(continuity))
            else:
                print(render_continuity_text(continuity))
            return 0
        if len(args.bundle_dirs) == 1 and not args.markdown:
            report = load_testnet_bundle_report(args.bundle_dirs[0])
            if args.json:
                print(json.dumps(asdict(report), indent=2, sort_keys=True))
            else:
                print(render_text_report(report))
            return 0
        summary = load_testnet_evidence_summary(list(args.bundle_dirs))
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    if args.json:
        print(json.dumps(asdict(summary), indent=2, sort_keys=True))
    elif args.markdown:
        print(render_markdown_summary(summary))
    else:
        print(render_summary_text(summary))
    return 0


__all__ = [
    "TestnetBundleReport",
    "TestnetContinuityDay",
    "TestnetContinuitySummary",
    "TestnetEvidenceSummary",
    "TestnetRunSummary",
    "load_testnet_continuity_summary",
    "load_testnet_evidence_summary",
    "load_testnet_bundle_report",
    "render_continuity_markdown",
    "render_continuity_text",
    "render_markdown_summary",
    "render_summary_text",
    "render_text_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

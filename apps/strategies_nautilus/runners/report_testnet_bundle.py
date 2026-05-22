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
from datetime import datetime
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
    if runtime.get("open_positions") != 0:
        blockers.append(f"open_positions={runtime.get('open_positions')}")
    if runtime.get("open_state_source") != "live_sidecars":
        blockers.append("open_state_source_not_live_sidecars")
    if _int_or_zero(runtime.get("strategies_registered")) <= 0:
        blockers.append("no_strategies_registered")
    if source is None:
        blockers.append("source_unknown")
    if model_version is None:
        blockers.append("model_version_unknown")
    sidecar = _dict_or_empty(runtime.get("sidecar"))
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
    if not _positions_are_flat(positions):
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
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full report as JSON instead of the text summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report = load_testnet_bundle_report(args.bundle_dir)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    return 0


__all__ = [
    "TestnetBundleReport",
    "load_testnet_bundle_report",
    "render_text_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

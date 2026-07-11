"""Build PnL-free point-in-time factors from verified Research Protocol v2 snapshots."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from apps.ops.research_v2_snapshot import verify_snapshot
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    audit_point_in_time_frame,
)

SCHEMA_VERSION = "research.factor_qualification.v1"
_BASIS_NUMERIC_FIELDS = {
    "spot_price",
    "front_futures_price",
    "next_futures_price",
    "front_days_to_expiry",
    "next_days_to_expiry",
}


def _payloads(envelope: dict[str, Any]) -> dict[str, Any]:
    requests = envelope.get("requests")
    if not isinstance(requests, list):
        raise ValueError("snapshot requests must be a list")
    result = {str(request["name"]): request["payload"] for request in requests}
    if len(result) != len(requests):
        raise ValueError("snapshot request names must be unique")
    return result


def _decision_time(retrieved_at: pd.Timestamp) -> pd.Timestamp:
    decision = retrieved_at.ceil("1D")
    if decision < retrieved_at:
        raise AssertionError("decision time must not precede retrieval")
    return decision


def basis_factor_row(snapshot_path: Path) -> dict[str, Any]:
    review = verify_snapshot(snapshot_path)
    if review["kind"] != "basis":
        raise ValueError("basis factor input must be a verified basis snapshot")
    envelope = json.loads(snapshot_path.read_text())
    payloads = _payloads(envelope)
    current = payloads["current_quarter_basis"]
    next_quarter = payloads["next_quarter_basis"]
    exchange = payloads["coin_m_exchange_info"]
    if len(current) != 1 or len(next_quarter) != 1:
        raise ValueError("basis snapshots require one current and one next row")
    front = current[0]
    back = next_quarter[0]
    retrieved_at = pd.Timestamp(envelope["retrieved_at"])
    decision = _decision_time(retrieved_at)
    for label, row in (("front", front), ("next", back)):
        observation = pd.to_datetime(int(row["timestamp"]), unit="ms", utc=True)
        if observation > retrieved_at:
            raise ValueError(f"{label} basis timestamp is after snapshot retrieval")

    front_index = float(front["indexPrice"])
    next_index = float(back["indexPrice"])
    if not math.isclose(front_index, next_index, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("current and next basis rows disagree on index price")
    symbols = {
        row["contractType"]: row
        for row in exchange["symbols"]
        if row.get("pair") == "BTCUSD"
        and row.get("contractType") in {"CURRENT_QUARTER", "NEXT_QUARTER"}
        and row.get("contractStatus") == "TRADING"
    }
    if set(symbols) != {"CURRENT_QUARTER", "NEXT_QUARTER"}:
        raise ValueError("basis snapshot lacks current/next exchange mappings")
    front_delivery = pd.to_datetime(
        int(symbols["CURRENT_QUARTER"]["deliveryDate"]), unit="ms", utc=True
    )
    next_delivery = pd.to_datetime(
        int(symbols["NEXT_QUARTER"]["deliveryDate"]), unit="ms", utc=True
    )
    front_days = (front_delivery - decision).total_seconds() / 86_400.0
    next_days = (next_delivery - decision).total_seconds() / 86_400.0
    if not 0.0 < front_days < next_days:
        raise ValueError("basis delivery horizons must satisfy 0 < front < next")
    return {
        "ts_event": decision.isoformat(),
        "available_at": retrieved_at.isoformat(),
        "vintage_id": envelope["vintage_id"],
        "snapshot_sha256": envelope["snapshot_sha256"],
        "spot_price": front_index,
        "front_futures_price": float(front["futuresPrice"]),
        "next_futures_price": float(back["futuresPrice"]),
        "front_days_to_expiry": front_days,
        "next_days_to_expiry": next_days,
    }


def build_basis_factor_frame(snapshot_paths: list[Path]) -> pd.DataFrame:
    if not snapshot_paths:
        raise ValueError("at least one basis snapshot is required")
    rows = [basis_factor_row(path) for path in snapshot_paths]
    frame = pd.DataFrame(rows)
    timestamps = pd.to_datetime(frame.pop("ts_event"), utc=True, errors="raise")
    frame.index = pd.DatetimeIndex(timestamps, name="ts_event")
    frame = frame.sort_index()
    return audit_point_in_time_frame(frame, required_numeric=_BASIS_NUMERIC_FIELDS)


def qualification_summary(frame: pd.DataFrame, snapshot_paths: list[Path]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "basis",
        "row_count": len(frame),
        "first_ts_event": frame.index[0].isoformat(),
        "last_ts_event": frame.index[-1].isoformat(),
        "snapshot_paths": [str(path) for path in snapshot_paths],
        "snapshot_sha256": frame["snapshot_sha256"].tolist(),
        "boundaries": {
            "pnl_computed": False,
            "returns_loaded": False,
            "signal_store_written": False,
            "signals_generated": False,
            "nautilus_run": False,
            "source_policy_mutated": False,
        },
        "valid": True,
    }


def write_basis_factor_csv(snapshot_paths: list[Path], output_path: Path) -> dict[str, Any]:
    frame = build_basis_factor_frame(snapshot_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export = frame.reset_index()
    with output_path.open("x", encoding="utf-8", newline="") as handle:
        export.to_csv(handle, index=False)
    return {**qualification_summary(frame, snapshot_paths), "output_path": str(output_path)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basis-snapshot", type=Path, action="append", default=[])
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    frame = build_basis_factor_frame(args.basis_snapshot)
    if args.dry_run:
        report = qualification_summary(frame, args.basis_snapshot)
    else:
        if args.output_csv is None:
            raise SystemExit("--output-csv is required unless --dry-run is set")
        report = write_basis_factor_csv(args.basis_snapshot, args.output_csv)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

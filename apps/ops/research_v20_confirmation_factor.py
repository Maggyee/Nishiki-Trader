"""Open the frozen v20 safe-asset holdout and export its D+5 factor."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_v20_confirmation import (
    DEFAULT_CONTRACT,
    SNAPSHOT_PATH,
    SNAPSHOT_SHA256,
    load_and_validate,
)
from apps.ops.research_v20_snapshot import verify_snapshot

SCHEMA_VERSION = "research.v20.confirmation_data.v1"
WARMUP_OBSERVATION_START = date(2022, 11, 1)
CONFIRMATION_START = date(2023, 1, 1)
CONFIRMATION_END = date(2025, 12, 31)
DECISION_LAG_DAYS = 5


def _safe_asset_rows(raw: bytes) -> list[dict[str, Any]]:
    payload = json.loads(raw)
    points = payload["Flight_to_Safety"]["data"]
    rows: list[dict[str, Any]] = []
    for point in points:
        observation = datetime.fromtimestamp(int(point[0]) / 1000, UTC).date()
        value = float(point[1])
        if not math.isfinite(value):
            raise ValueError("Protocol v20 safe-asset value must be finite")
        rows.append({"date": observation.isoformat(), "safe_asset_stress": value})
    return rows


def _available_date(row: dict[str, Any]) -> date:
    return date.fromisoformat(str(row["date"])) + timedelta(days=DECISION_LAG_DAYS)


def _audit_confirmation_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    data = contract["data_contract"]
    decisions = [
        _available_date(row)
        for row in rows
        if CONFIRMATION_START <= _available_date(row) <= CONFIRMATION_END
    ]
    if len(decisions) < int(data["minimum_confirmation_decisions"]):
        raise ValueError("Protocol v20 confirmation coverage is insufficient")
    if decisions[0] > date.fromisoformat(data["first_decision_on_or_before"]):
        raise ValueError("Protocol v20 confirmation decisions start too late")
    if decisions[-1] < date.fromisoformat(data["last_decision_on_or_after"]):
        raise ValueError("Protocol v20 confirmation decisions end too early")
    max_gap = max(
        (right - left).days
        for left, right in zip(decisions[:-1], decisions[1:], strict=True)
    )
    if max_gap > int(data["maximum_calendar_gap_days"]):
        raise ValueError("Protocol v20 confirmation gap exceeds frozen maximum")
    annual_counts = {
        str(year): sum(day.year == year for day in decisions)
        for year in (2023, 2024, 2025)
    }
    return {
        "confirmation_decision_count": len(decisions),
        "annual_decision_counts": annual_counts,
        "first_decision_date": decisions[0].isoformat(),
        "last_decision_date": decisions[-1].isoformat(),
        "maximum_calendar_gap_days": max_gap,
        "forward_fill_used": False,
        "partition_basis": "decision_available_at",
    }


def request_plan() -> dict[str, Any]:
    result = load_and_validate()
    return {
        "schema_version": "research.v20.confirmation_factor_plan.v1",
        "contract_sha256": result["contract_sha256"],
        "snapshot_path": str(SNAPSHOT_PATH),
        "snapshot_sha256": SNAPSHOT_SHA256,
        "network_accessed": False,
        "confirmation_values_opened": False,
        "data_written": False,
    }


def write_confirmation_factor(
    snapshot_path: Path,
    output_path: Path,
    *,
    qualification_output: Path | None = None,
) -> dict[str, Any]:
    contract = load_and_validate()
    if snapshot_path != SNAPSHOT_PATH:
        raise ValueError("Protocol v20 confirmation snapshot path drifted")
    verification = verify_snapshot(snapshot_path)
    if verification["snapshot_sha256"] != SNAPSHOT_SHA256:
        raise ValueError("Protocol v20 confirmation snapshot fingerprint drifted")
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows = _safe_asset_rows(raw)
    audit = _audit_confirmation_rows(rows)
    selected = [
        row
        for row in rows
        if date.fromisoformat(row["date"]) >= WARMUP_OBSERVATION_START
        and _available_date(row) <= CONFIRMATION_END
    ]
    warmup_rows = sum(_available_date(row) < CONFIRMATION_START for row in selected)
    if warmup_rows < 5:
        raise ValueError("Protocol v20 confirmation warmup is insufficient")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    if qualification_output is not None and qualification_output.exists():
        raise FileExistsError(f"refusing to overwrite {qualification_output}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ts_event",
                "available_at",
                "vintage_id",
                "snapshot_sha256",
                "safe_asset_stress",
            ],
        )
        writer.writeheader()
        for row in selected:
            available = datetime.combine(_available_date(row), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "safe_asset_stress": format(
                        float(row["safe_asset_stress"]), ".12g"
                    ),
                }
            )
    result = {
        "schema_version": SCHEMA_VERSION,
        "classification": "provider_qualified",
        "contract_sha256": contract["contract_sha256"],
        "source_snapshot": {
            "path": str(snapshot_path),
            "snapshot_sha256": envelope["snapshot_sha256"],
            "vintage_id": envelope["vintage_id"],
        },
        "audit": {**audit, "warmup_rows": warmup_rows},
        "factor": {
            "path": str(output_path),
            "row_count": len(selected),
            "sha256": "sha256:"
            + hashlib.sha256(output_path.read_bytes()).hexdigest(),
        },
        "boundaries": {
            "network_accessed": False,
            "returns_computed": False,
            "pnl_opened": False,
            "future_blind_opened": False,
            "source_policy_mutated": False,
            "trading_touched": False,
            "historical_vintage_claim": False,
        },
    }
    if qualification_output is not None:
        qualification_output.parent.mkdir(parents=True, exist_ok=True)
        qualification_output.write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/research-v20/confirmation/factors/safe_asset.csv"),
    )
    parser.add_argument("--qualification-output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = (
        request_plan()
        if args.dry_run
        else write_confirmation_factor(
            args.snapshot,
            args.output,
            qualification_output=args.qualification_output,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Extract 2023-2025 confirmation factor CSV from the qualified FVX snapshot."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_v34_confirmation import load_and_validate_confirmation
from apps.ops.research_v34_snapshot import parse_and_audit_csv, verify_snapshot

CONFIRMATION_START = date(2023, 1, 1)
CONFIRMATION_END = date(2025, 12, 31)
CONFIRMATION_WARMUP_START = date(2022, 11, 1)


def extract_confirmation_factor(
    snapshot_path: Path,
    output_path: Path,
    *,
    contract_path: Path = Path("docs/progress/phase-2-research-v34-confirmation.json"),
) -> dict[str, Any]:
    load_and_validate_confirmation(contract_path)
    verification = verify_snapshot(snapshot_path)
    if verification["kind"] != "fvx":
        raise ValueError("Protocol v34 confirmation only extracts fvx")
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_csv("fvx", raw)
    selected = [
        row
        for row in rows
        if CONFIRMATION_WARMUP_START <= date.fromisoformat(row["date"]) <= CONFIRMATION_END
    ]
    warmup = [
        row
        for row in selected
        if CONFIRMATION_WARMUP_START <= date.fromisoformat(row["date"]) < CONFIRMATION_START
    ]
    confirmation = [
        row
        for row in selected
        if CONFIRMATION_START <= date.fromisoformat(row["date"]) <= CONFIRMATION_END
    ]
    if len(confirmation) < 700:
        raise ValueError(f"FVX confirmation reserve has only {len(confirmation)} rows")
    if len(warmup) < 5:
        raise ValueError("FVX confirmation warmup has fewer than 5 rows")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ts_event",
                "available_at",
                "observation_date",
                "vintage_id",
                "snapshot_sha256",
                "index_value",
            ],
        )
        writer.writeheader()
        for row in selected:
            observed = date.fromisoformat(row["date"])
            available = datetime.combine(observed + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "observation_date": observed.isoformat(),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "index_value": format(float(row["value"]), ".12g"),
                }
            )
    return {
        "kind": "fvx",
        "path": str(output_path),
        "sha256": "sha256:" + hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "row_count": len(selected),
        "confirmation_row_count": len(confirmation),
        "warmup_row_count": len(warmup),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": verification["snapshot_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(extract_confirmation_factor(args.snapshot, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

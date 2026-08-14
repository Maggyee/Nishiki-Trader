"""Extract the frozen 2023-2025 confirmation factor CSV for Protocol v38 without network access."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_v38_confirmation import load_and_validate
from apps.ops.research_v38_snapshot import parse_and_audit_csv, verify_snapshot

CONFIRMATION_START = date(2023, 1, 1)
CONFIRMATION_END = date(2025, 12, 31)
WARMUP_START = date(2022, 11, 1)


def extract_confirmation_factor(
    snapshot_path: Path, output_path: Path, data_sources_path: Path
) -> dict[str, Any]:
    load_and_validate()
    verification = verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_csv(verification["kind"], raw)
    selected = [
        row for row in rows if WARMUP_START <= date.fromisoformat(row["date"]) <= CONFIRMATION_END
    ]
    warmup = [
        row for row in selected if WARMUP_START <= date.fromisoformat(row["date"]) < CONFIRMATION_START
    ]
    confirmation = [
        row
        for row in selected
        if CONFIRMATION_START <= date.fromisoformat(row["date"]) <= CONFIRMATION_END
    ]
    if len(confirmation) < 700:
        raise ValueError(f"confirmation reserve has only {len(confirmation)} rows")
    if len(warmup) < 5:
        raise ValueError(f"warmup reserve has only {len(warmup)} rows")
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
    factor_sha = "sha256:" + hashlib.sha256(output_path.read_bytes()).hexdigest()
    data_sources_payload = {
        "schema_version": "research.v38.confirmation.data_sources.v1",
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": verification["snapshot_sha256"],
        "factor_csv_path": str(output_path),
        "factor_csv_sha256": factor_sha,
        "row_count": len(selected),
        "confirmation_row_count": len(confirmation),
        "warmup_row_count": len(warmup),
        "first_confirmation_date": confirmation[0]["date"],
        "last_confirmation_date": confirmation[-1]["date"],
        "network_accessed": False,
        "historical_vintage_claim": False,
    }
    data_sources_path.write_text(
        json.dumps(data_sources_payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return {
        "kind": verification["kind"],
        "path": str(output_path),
        "sha256": factor_sha,
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
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-data-sources", type=Path, required=True)
    args = parser.parse_args(argv)
    result = extract_confirmation_factor(args.snapshot, args.output_csv, args.output_data_sources)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

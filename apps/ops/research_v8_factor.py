"""Build the frozen Protocol v8 GVZ point-in-time factor from the v7 snapshot."""

from __future__ import annotations

import argparse
import base64
import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v8 import DEFAULT_SOURCES, load_and_validate
from apps.ops.research_v7_snapshot import parse_and_audit_csv, verify_snapshot

SCHEMA_VERSION = "research.factor.v8"


def write_factor(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    """Write the exact 2022-11 warmup through 2025 confirmation factor."""
    load_and_validate()
    sources = json.loads(DEFAULT_SOURCES.read_text())
    expected = sources["signal_source"]
    verification = verify_snapshot(snapshot_path)
    if verification["snapshot_sha256"] != expected["snapshot_sha256"]:
        raise ValueError("Protocol v8 GVZ snapshot hash drifted")
    if verification["vintage_id"] != expected["vintage_id"]:
        raise ValueError("Protocol v8 GVZ vintage drifted")
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_csv("gvz", raw)
    start = date(2022, 11, 1)
    end = date(2025, 12, 31)
    selected = [row for row in rows if start <= date.fromisoformat(row["date"]) <= end]
    if not selected or date.fromisoformat(selected[-1]["date"]) < date(2025, 12, 30):
        raise ValueError("Protocol v8 GVZ factor does not cover the holdout")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ts_event", "available_at", "vintage_id", "snapshot_sha256", "vol_close"],
        )
        writer.writeheader()
        for row in selected:
            available = datetime.combine(
                date.fromisoformat(row["date"]) + timedelta(days=1),
                datetime.min.time(),
                UTC,
            )
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "vol_close": format(float(row["close"]), ".12g"),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "output_path": str(output_path),
        "row_count": len(selected),
        "first_observation_date": selected[0]["date"],
        "last_observation_date": selected[-1]["date"],
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(write_factor(args.snapshot, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

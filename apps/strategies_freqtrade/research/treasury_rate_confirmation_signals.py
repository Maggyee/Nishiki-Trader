"""Generate the unchanged Protocol v16 confirmation signal."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import pandas as pd

from apps.bridge.store import SignalStore
from apps.ops.research_v16_confirmation_snapshot import (
    combine_and_audit,
)
from apps.ops.research_v16_confirmation_snapshot import (
    request_specs as confirmation_request_specs,
)
from apps.ops.research_v16_confirmation_snapshot import (
    verify_snapshot as verify_confirmation_snapshot,
)
from apps.ops.research_v16_snapshot import parse_route, request_specs, verify_snapshot
from apps.strategies_freqtrade.research.treasury_rate_signals import (
    generate_treasury_rate_signals,
)


def build_confirmation_frame(development_snapshot: Path, confirmation_snapshot: Path) -> pd.DataFrame:
    verify_snapshot(development_snapshot)
    verify_confirmation_snapshot(confirmation_snapshot)
    development = json.loads(development_snapshot.read_text())
    warmup = None
    for spec, record in zip(request_specs(), development["requests"], strict=True):
        if spec["year"] == 2022 and spec["route"] == "nominal":
            raw = base64.b64decode(record["payload_raw_base64"], validate=True)
            warmup = parse_route(raw, route="nominal", year=2022)
            break
    if warmup is None:
        raise ValueError("Protocol v16 confirmation warmup is missing")
    confirmation = json.loads(confirmation_snapshot.read_text())
    payloads = []
    for spec, record in zip(confirmation_request_specs(), confirmation["requests"], strict=True):
        payloads.append((spec, base64.b64decode(record["payload_raw_base64"], validate=True)))
    rows, _ = combine_and_audit(payloads)
    values = [(day, data["10 yr"]) for day, data in warmup.items()]
    values.extend((pd.Timestamp(row["observation_date"]).date(), row["nominal_10y"]) for row in rows)
    records = []
    for day, value in sorted(values):
        decision = pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=2)
        records.append({"ts_event": decision, "nominal_10y": float(value), "available_at": decision, "snapshot_sha256": confirmation["snapshot_sha256"], "vintage_id": confirmation["vintage_id"]})
    return pd.DataFrame(records).set_index("ts_event").sort_index()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-snapshot", type=Path, required=True)
    parser.add_argument("--confirmation-snapshot", type=Path, required=True)
    parser.add_argument("--signal-store-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    events = generate_treasury_rate_signals(
        build_confirmation_frame(args.development_snapshot, args.confirmation_snapshot),
        candidate="treasury_volatility_relief",
        start_date="2023-01-01",
        end_date="2025-12-31",
    )
    print(f"generated {len(events)} confirmation signals")
    if not args.dry_run:
        if args.signal_store_path is None:
            parser.error("--signal-store-path is required unless --dry-run")
        written, duplicates = SignalStore(args.signal_store_path).write_many(events)
        print(f"wrote {written}, skipped {duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

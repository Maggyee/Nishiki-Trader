"""Daily point-in-time snapshot and shadow signal runner for Protocol v40 (VXN)."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.bridge.store import SignalStore
from apps.ops.research_v40_snapshot import (
    collect_snapshot,
    parse_and_audit_csv,
)
from apps.strategies_freqtrade.research.equity_vol_relief_signals import (
    generate_equity_vol_relief_signals,
)
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)

SCHEMA_VERSION = "research.protocol.v40.paper_shadow_status.v1"
CANDIDATE = "vxn_relief"
RAW_DIR = Path("data/research-v40/shadow/raw")
FACTORS_DIR = Path("data/research-v40/shadow/factors")
SIGNAL_STORE_PATH = Path("data/research-v40/shadow/signals.db")
STATE_FILE = Path("data/research-v40/shadow/state.json")
STATUS_FILE = Path("docs/progress/phase-2-research-v40-paper-shadow-status.json")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run_daily_shadow(
    raw_dir: Path = RAW_DIR,
    factors_dir: Path = FACTORS_DIR,
    signal_store_path: Path = SIGNAL_STORE_PATH,
    state_file: Path = STATE_FILE,
    status_file: Path = STATUS_FILE,
) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    factors_dir.mkdir(parents=True, exist_ok=True)
    signal_store_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot_path, envelope = collect_snapshot("vxn", output_dir=raw_dir)
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, audit = parse_and_audit_csv("vxn", raw)

    latest_date_str = rows[-1]["date"]
    latest_date = date.fromisoformat(latest_date_str)
    factor_csv = factors_dir / f"vxn_shadow_{latest_date_str}.csv"

    warmup_start = latest_date - timedelta(days=90)
    selected = [r for r in rows if date.fromisoformat(r["date"]) >= warmup_start]

    with factor_csv.open("w", newline="") as handle:
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
        for r in selected:
            obs = date.fromisoformat(r["date"])
            avail = datetime.combine(obs + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(avail.timestamp() * 1_000_000_000),
                    "available_at": avail.isoformat().replace("+00:00", "Z"),
                    "observation_date": obs.isoformat(),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "index_value": format(float(r["value"]), ".12g"),
                }
            )

    df = load_point_in_time_csv(factor_csv)
    events = generate_equity_vol_relief_signals(
        df,
        candidate=CANDIDATE,
        start_date=warmup_start.isoformat(),
        end_date=latest_date.isoformat(),
    )

    store = SignalStore(signal_store_path)
    written, duplicates = store.write_many(events)

    state: dict[str, Any] = {"history": []}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except Exception:
            state = {"history": []}

    run_record = {
        "run_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "latest_observation_date": latest_date_str,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "factor_csv": str(factor_csv),
        "factor_sha256": _sha256(factor_csv),
        "events_generated": len(events),
        "signals_written": written,
        "duplicates_skipped": duplicates,
    }
    state["history"].append(run_record)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

    total_runs = len(state["history"])
    source = "rule_cboe_vxn_relief_v1"
    model = "cboe-vxn-diff5-negative-lag1d-v1"
    total_signals = len(list(store.replay(source=source, model_version=model)))

    status_payload = {
        "schema_version": SCHEMA_VERSION,
        "strategy": CANDIDATE,
        "source": source,
        "model_version": model,
        "last_run_at": run_record["run_at"],
        "last_observation_date": latest_date_str,
        "total_days_collected": total_runs,
        "total_signals_stored": total_signals,
        "health": "HEALTHY",
        "latest_snapshot_sha256": envelope["snapshot_sha256"],
        "latest_factor_sha256": run_record["factor_sha256"],
    }
    status_file.write_text(json.dumps(status_payload, indent=2, sort_keys=True) + "\n")
    return status_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--factors-dir", type=Path, default=FACTORS_DIR)
    parser.add_argument("--signal-store", type=Path, default=SIGNAL_STORE_PATH)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--status-file", type=Path, default=STATUS_FILE)
    args = parser.parse_args(argv)
    result = run_daily_shadow(
        raw_dir=args.raw_dir,
        factors_dir=args.factors_dir,
        signal_store_path=args.signal_store,
        state_file=args.state_file,
        status_file=args.status_file,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

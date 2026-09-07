"""Daily point-in-time snapshot and shadow signal runner for Protocol v40 (VXN)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_shadow_runtime import run_forward_series, write_daily_factors
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
STATUS_FILE = Path("data/research-v40/shadow/status.json")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run_daily_shadow(
    raw_dir: Path = RAW_DIR, factors_dir: Path = FACTORS_DIR,
    signal_store_path: Path = SIGNAL_STORE_PATH, state_file: Path = STATE_FILE,
    status_file: Path = STATUS_FILE, *, now: datetime | None = None, git_state: dict | None = None,
) -> dict[str, Any]:
    def fetch_rows(directory):
        path, envelope = collect_snapshot("vxn", output_dir=directory)
        rows, _ = parse_and_audit_csv("vxn", base64.b64decode(envelope["payload_raw_base64"], validate=True))
        return path, envelope, rows

    def build_events(rows, envelope, path):
        write_daily_factors(rows, envelope, path)
        return generate_equity_vol_relief_signals(load_point_in_time_csv(path), candidate=CANDIDATE,
            start_date=(date.fromisoformat(rows[-1]["date"]) - timedelta(days=90)).isoformat(), end_date=(date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat())

    return run_forward_series(protocol="v40", candidate=CANDIDATE,
        source="rule_cboe_vxn_relief_v1", model="cboe-vxn-diff5-negative-lag1d-v1",
        fetch_snapshot=fetch_rows, build_events=build_events, raw_dir=raw_dir,
        factors_dir=factors_dir, signal_store_path=signal_store_path,
        state_file=state_file, status_file=status_file, max_age_days=4, now=now, git_state=git_state)


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
    return 0 if result["health"] == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

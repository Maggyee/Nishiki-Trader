"""Daily automated paper shadow runner for Protocol v48 (Binance Perpetual Basis Relief)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_forward_archives import snapshot_forward
from apps.ops.research_shadow_runtime import run_forward_series
from apps.ops.research_v48_snapshot import (
    compute_factors,
)
from apps.strategies_freqtrade.research.crypto_basis_signals import (
    generate_basis_signals,
)
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)

SCHEMA_VERSION = "research.protocol.v48.paper_shadow_status.v1"
CANDIDATE = "btc_basis_below_ma10"
RAW_DIR = Path("data/research-v48/shadow/raw")
FACTORS_DIR = Path("data/research-v48/shadow/factors")
SIGNAL_STORE_PATH = Path("data/research-v48/shadow/signals.db")
STATE_FILE = Path("data/research-v48/shadow/state.json")
STATUS_FILE = Path("data/research-v48/shadow/status.json")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_and_snapshot_basis(output_dir: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    return snapshot_forward("basis", output_dir)


def generate_shadow_factor_csv(
    rows: list[dict[str, Any]],
    vintage_id: str,
    snapshot_sha: str,
    output_path: Path,
    start_date: date = date(2026, 1, 1),
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    factors = compute_factors(rows)[CANDIDATE]
    selected = [r for r in factors if date.fromisoformat(r["date"]) >= start_date]

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
        for r in selected:
            obs = date.fromisoformat(r["date"])
            avail = datetime.combine(obs + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(avail.timestamp() * 1_000_000_000),
                    "available_at": avail.isoformat().replace("+00:00", "Z"),
                    "observation_date": obs.isoformat(),
                    "vintage_id": vintage_id,
                    "snapshot_sha256": snapshot_sha,
                    "index_value": format(float(r["value"]), ".12g"),
                }
            )
    return output_path


def run_daily_shadow_collection(
    raw_dir: Path = RAW_DIR, factors_dir: Path = FACTORS_DIR,
    signal_store_path: Path = SIGNAL_STORE_PATH, state_file: Path = STATE_FILE,
    status_file: Path = STATUS_FILE, *, now: datetime | None = None, git_state: dict | None = None,
) -> dict[str, Any]:
    def fetch_rows(directory):
        return fetch_and_snapshot_basis(directory)

    def build_events(rows, envelope, path):
        generate_shadow_factor_csv(rows, envelope["vintage_id"], envelope["snapshot_sha256"], path)
        return generate_basis_signals(load_point_in_time_csv(path), candidate=CANDIDATE,
            start_date="2026-01-01", end_date=(date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat())

    return run_forward_series(protocol="v48", candidate=CANDIDATE,
        source="rule_crypto_basis_relief_v1", model="crypto-btc-basis-below-ma10-lag1d-v1",
        fetch_snapshot=fetch_rows, build_events=build_events, raw_dir=raw_dir,
        factors_dir=factors_dir, signal_store_path=signal_store_path,
        state_file=state_file, status_file=status_file, max_age_days=2, now=now, git_state=git_state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", help="Execute one daily shadow collection run")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--factors-dir", type=Path, default=FACTORS_DIR)
    parser.add_argument("--signal-store", type=Path, default=SIGNAL_STORE_PATH)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--status-file", type=Path, default=STATUS_FILE)
    args = parser.parse_args(argv)
    status = run_daily_shadow_collection(
        raw_dir=args.raw_dir,
        factors_dir=args.factors_dir,
        signal_store_path=args.signal_store,
        state_file=args.state_file,
        status_file=args.status_file,
    )
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status["health"] == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

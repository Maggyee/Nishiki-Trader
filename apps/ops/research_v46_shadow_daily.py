"""Daily automated paper shadow runner for Protocol v46 (Binance Perpetual Premium Index Relief)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.bridge.store import SignalStore
from apps.ops.research_v46_snapshot import (
    compute_factors,
    fetch_premium_daily_range,
)
from apps.strategies_freqtrade.research.crypto_premium_standard_signals import (
    generate_premium_standard_signals,
)
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)

SCHEMA_VERSION = "research.protocol.v46.paper_shadow_status.v1"
CANDIDATE = "btc_prem_diff5_negative"
RAW_DIR = Path("data/research-v46/shadow/raw")
FACTORS_DIR = Path("data/research-v46/shadow/factors")
SIGNAL_STORE_PATH = Path("data/research-v46/shadow/signals.db")
STATE_FILE = Path("data/research-v46/shadow/state.json")
STATUS_FILE = Path("docs/progress/phase-2-research-v46-paper-shadow-status.json")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_and_snapshot_premium(output_dir: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    current_year = datetime.now(UTC).year
    years = list(range(2020, current_year + 1))
    rows = fetch_premium_daily_range(years=years)
    if not rows:
        raise ValueError("failed to fetch premium rows")

    observed_at = datetime.now(UTC)
    envelope = {
        "schema_version": "research.v46.snapshot.v1",
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "premium_row_count": len(rows),
        "premium_rows": rows,
    }
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    snapshot_sha = f"sha256:{digest}"
    vintage_id = f"binance-vision-btc-prem:{observed_at.isoformat()}:{digest[:12]}"
    envelope["vintage_id"] = vintage_id
    envelope["snapshot_sha256"] = snapshot_sha

    snapshot_path = output_dir / f"binance-vision-btc-prem-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    snapshot_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return snapshot_path, envelope, rows


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
    raw_dir: Path = RAW_DIR,
    factors_dir: Path = FACTORS_DIR,
    signal_store_path: Path = SIGNAL_STORE_PATH,
    state_file: Path = STATE_FILE,
    status_file: Path = STATUS_FILE,
) -> dict[str, Any]:
    snapshot_path, envelope, rows = fetch_and_snapshot_premium(raw_dir)
    vintage_id = envelope["vintage_id"]
    snapshot_sha = envelope["snapshot_sha256"]

    factor_path = factors_dir / f"{CANDIDATE}_shadow.csv"
    generate_shadow_factor_csv(rows, vintage_id, snapshot_sha, factor_path)

    factors_df = load_point_in_time_csv(factor_path)
    events = generate_premium_standard_signals(
        factors_df,
        candidate=CANDIDATE,
        start_date="2026-01-01",
        end_date="2026-12-31",
    )

    signal_store_path.parent.mkdir(parents=True, exist_ok=True)
    store = SignalStore(signal_store_path)
    written, duplicates = store.write_many(events)

    source = "rule_crypto_prem_relief_v1"
    model = "crypto-btc-prem-diff5-negative-lag1d-v1"
    total_signals = len(list(store.replay(source=source, model_version=model)))

    state: dict[str, Any] = {}
    if state_file.exists():
        state = json.loads(state_file.read_text())
    run_history = state.get("run_history", [])
    run_history.append(
        {
            "collected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "snapshot_path": str(snapshot_path),
            "snapshot_sha256": snapshot_sha,
            "signals_written": written,
            "signals_duplicates": duplicates,
            "total_signals_stored": total_signals,
        }
    )
    state["candidate"] = CANDIDATE
    state["source"] = source
    state["model_version"] = model
    state["last_run_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    state["qualified_runs"] = len(run_history)
    state["run_history"] = run_history
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

    status = {
        "schema_version": SCHEMA_VERSION,
        "candidate": CANDIDATE,
        "source": source,
        "model_version": model,
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "HEALTHY",
        "qualified_runs": len(run_history),
        "target_runs": 7,
        "total_signals_stored": total_signals,
        "last_snapshot_sha256": snapshot_sha,
        "signal_store_path": str(signal_store_path),
        "boundaries": {
            "loads_credentials": False,
            "mutates_source_policy": False,
            "touches_live_path": False,
        },
    }
    status_file.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", help="Execute one daily shadow collection run")
    args = parser.parse_args(argv)
    if args.run_once:
        status = run_daily_shadow_collection()
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    parser.error("--run-once is required")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

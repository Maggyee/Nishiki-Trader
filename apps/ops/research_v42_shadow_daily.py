"""Daily automated paper shadow runner for Protocol v42 (VIX6M Relief)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_shadow_runtime import run_forward_series, write_daily_factors
from apps.ops.research_v42_snapshot import parse_and_audit_csv
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)
from apps.strategies_freqtrade.research.vol_term_structure_signals import (
    generate_vol_term_structure_signals,
)

SCHEMA_VERSION = "research.protocol.v42.paper_shadow_status.v1"
CANDIDATE = "vix6m_relief"
RAW_DIR = Path("data/research-v42/shadow/raw")
FACTORS_DIR = Path("data/research-v42/shadow/factors")
SIGNAL_STORE_PATH = Path("data/research-v42/shadow/signals.db")
STATE_FILE = Path("data/research-v42/shadow/state.json")
STATUS_FILE = Path("data/research-v42/shadow/status.json")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_and_snapshot_vix6m(output_dir: Path) -> tuple[Path, dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX6M_History.csv"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v42-shadow (+https://github.com/Maggyee/Nishiki-Trader)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw_csv = resp.read()

    observed_at = datetime.now(UTC)
    raw_sha = "sha256:" + hashlib.sha256(raw_csv).hexdigest()
    rows, audit = parse_and_audit_csv("vix6m", raw_csv)

    envelope = {
        "schema_version": "research.v42.snapshot.v1",
        "kind": "vix6m",
        "ticker": "VIX6M",
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "raw_sha256": raw_sha,
        "audit": audit,
        "payload_raw_base64": base64.b64encode(raw_csv).decode("ascii"),
    }
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    snapshot_sha = f"sha256:{digest}"
    vintage_id = f"cboe-vix6m-shadow:{observed_at.isoformat()}:{digest[:12]}"
    envelope["vintage_id"] = vintage_id
    envelope["snapshot_sha256"] = snapshot_sha

    snapshot_path = output_dir / f"cboe-vix6m-shadow-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    snapshot_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return snapshot_path, envelope


def run_daily_shadow(
    raw_dir: Path = RAW_DIR, factors_dir: Path = FACTORS_DIR,
    signal_store_path: Path = SIGNAL_STORE_PATH, state_file: Path = STATE_FILE,
    status_file: Path = STATUS_FILE, *, now: datetime | None = None, git_state: dict | None = None,
) -> dict[str, Any]:
    def fetch_rows(directory):
        path, envelope = fetch_and_snapshot_vix6m(directory)
        rows, _ = parse_and_audit_csv("vix6m", base64.b64decode(envelope["payload_raw_base64"], validate=True))
        return path, envelope, rows

    def build_events(rows, envelope, path):
        write_daily_factors(rows, envelope, path)
        return generate_vol_term_structure_signals(load_point_in_time_csv(path), candidate=CANDIDATE,
            start_date=(date.fromisoformat(rows[-1]["date"]) - timedelta(days=90)).isoformat(), end_date=(date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat())

    return run_forward_series(protocol="v42", candidate=CANDIDATE,
        source="rule_cboe_vix6m_relief_v1", model="cboe-vix6m-diff5-negative-lag1d-v1",
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

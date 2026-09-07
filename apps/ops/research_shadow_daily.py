"""One scheduled entrypoint for the ten existing forward collectors.

Run from an immutable, pushed checkout using --expected-commit. Each existing
schedule can select one protocol; no new jobs or trading stages are introduced.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from apps.ops.research_shadow_runtime import atomic_json

PROTOCOLS = (8, 16, 18, 22, 34, 36, 40, 42, 46, 48)


def run_one(protocol: int, data_base: Path, expected_commit: str) -> dict:
    if protocol not in PROTOCOLS:
        raise ValueError("collector not registered")
    root = Path.cwd()
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    if actual != expected_commit or dirty:
        raise ValueError("collector deployment commit mismatch or dirty checkout")
    module = importlib.import_module(f"apps.ops.research_v{protocol}_shadow_daily")
    data_root = data_base / (f"research-v{protocol}-forward" if protocol < 40 else f"research-v{protocol}/shadow")
    if protocol < 40:
        result = module.collect_daily(repo_root=root, data_root=data_root)
        status = result["status"]
    else:
        run = module.run_daily_shadow if protocol in (40, 42) else module.run_daily_shadow_collection
        status = run(raw_dir=data_root / "raw", factors_dir=data_root / "factors",
                     signal_store_path=data_root / "signals.db", state_file=data_root / "state.json",
                     status_file=data_root / "status.json")
    status["deployment_commit"] = actual
    atomic_json(data_root / "status.json", status)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=int, choices=PROTOCOLS, required=True)
    parser.add_argument("--data-base", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args(argv)
    try:
        status = run_one(args.protocol, args.data_base.resolve(), args.expected_commit)
    except Exception as exc:
        root = args.data_base / (f"research-v{args.protocol}-forward" if args.protocol < 40 else f"research-v{args.protocol}/shadow")
        path = root / "status.json"
        try:
            prior = json.loads(path.read_text())
            if not isinstance(prior, dict):
                prior = {}
        except (OSError, ValueError):
            prior = {}
        prior.update(updated_at=datetime.now(UTC).isoformat(), health="DEGRADED",
                     review_eligible=False, latest_blockers=[f"runner_failed:{type(exc).__name__}:{exc}"])
        prior["anomaly_blockers"] = sorted(set(prior.get("anomaly_blockers", [])) | set(prior["latest_blockers"]))
        atomic_json(path, prior)
        print(json.dumps(prior, sort_keys=True))
        return 2
    print(json.dumps(status, sort_keys=True))
    return 2 if status.get("latest_blockers", []) else 0


if __name__ == "__main__":
    raise SystemExit(main())

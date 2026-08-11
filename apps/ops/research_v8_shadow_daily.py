"""Collect one forward Protocol v8 GVZ/BTC paper-shadow evidence attempt."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import math
import subprocess
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.store import SignalStore
from apps.ops.research_v7_snapshot import collect_snapshot, parse_and_audit_csv
from apps.strategies_freqtrade.research.cross_asset_volatility_signals import (
    STRATEGY_IDENTITIES,
    generate_volatility_relief_signals,
)

CONTRACT_PATH = Path("docs/progress/phase-2-research-v8-paper-shadow.json")
SCHEMA_VERSION = "research.v8.paper_shadow_attempt.v1"
STATUS_SCHEMA_VERSION = "research.v8.paper_shadow_status.v1"
BTC_STEP_MS = 3_600_000
Fetch = Callable[[str], bytes]


def _strict_json(raw: str | bytes) -> Any:
    return json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {value!r}")
        ),
    )


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _strict_json(path.read_bytes())
    if not isinstance(contract, dict):
        raise ValueError("paper-shadow contract must be an object")
    if contract.get("schema_version") != "research.v8.paper_shadow_contract.v1":
        raise ValueError("paper-shadow contract schema drifted")
    if contract.get("status") != "prospectively_locked":
        raise ValueError("paper-shadow contract is not prospectively locked")
    if contract.get("candidate", {}).get("strategy") != "gold_vol_relief":
        raise ValueError("paper-shadow candidate identity drifted")
    if contract.get("policy") != {
        "stage": "paper_shadow",
        "dry_run": True,
        "position_pct_multiplier": 0.2,
        "min_confidence_override": None,
    }:
        raise ValueError("paper-shadow policy drifted")
    boundaries = contract.get("boundaries", {})
    if any(boundaries.values()):
        raise ValueError("paper-shadow boundaries must all remain false")
    return contract


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v8"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _git_state(repo_root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    branch = git("branch", "--show-current")
    upstream_contains_head = False
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        upstream_contains_head = True
    except subprocess.CalledProcessError:
        pass
    return {
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "origin_main_contains_commit": upstream_contains_head,
    }


def _parse_btc_bars(raw: bytes, *, observed_at: datetime) -> list[dict[str, Any]]:
    payload = _strict_json(raw)
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("Binance hourly response must contain at least two bars")
    bars: list[dict[str, Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError(f"Binance hourly row {index} is malformed")
        open_ms = int(row[0])
        close_ms = int(row[6])
        values = [float(row[position]) for position in (1, 2, 3, 4, 5)]
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError(f"Binance hourly row {index} has invalid numeric values")
        open_px, high, low, close, volume = values
        if min(open_px, high, low, close) <= 0 or high < max(open_px, close) or low > min(
            open_px, close
        ):
            raise ValueError(f"Binance hourly row {index} has invalid OHLC bounds")
        if open_ms % BTC_STEP_MS or close_ms != open_ms + BTC_STEP_MS - 1:
            raise ValueError(f"Binance hourly row {index} is off the one-hour grid")
        if close_ms >= int(observed_at.timestamp() * 1000):
            continue
        bars.append(
            {
                "open_time_ms": open_ms,
                "open": format(open_px, ".12g"),
                "high": format(high, ".12g"),
                "low": format(low, ".12g"),
                "close": format(close, ".12g"),
                "volume": format(volume, ".12g"),
            }
        )
    opens = [row["open_time_ms"] for row in bars]
    if len(bars) < 24 or len(opens) != len(set(opens)):
        raise ValueError("Binance response has too few closed bars or duplicate timestamps")
    if any(right - left != BTC_STEP_MS for left, right in zip(opens, opens[1:], strict=False)):
        raise ValueError("Binance closed hourly bars are not contiguous")
    return bars


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = _strict_json(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"state at {path} must be an object")
    return value


def _merge_observations(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> tuple[dict[str, Any], list[str], int]:
    revisions = sorted(key for key in previous.keys() & current.keys() if previous[key] != current[key])
    merged = {**previous, **current}
    return merged, revisions, len(set(current) - set(previous))


def _factor_frame(rows: list[dict[str, Any]], *, vintage_id: str, snapshot_sha256: str) -> pd.DataFrame:
    selected = [row for row in rows if date.fromisoformat(row["date"]) >= date(2025, 12, 1)]
    records = []
    for row in selected:
        available = datetime.combine(
            date.fromisoformat(row["date"]) + timedelta(days=1), datetime.min.time(), UTC
        )
        records.append(
            {
                "ts_event": available,
                "available_at": available,
                "vintage_id": vintage_id,
                "snapshot_sha256": snapshot_sha256,
                "vol_close": row["close"],
            }
        )
    return pd.DataFrame.from_records(records).set_index("ts_event")


def summarize_attempts(records: list[dict[str, Any]], *, gate_days: int, gate_signals: int) -> dict[str, Any]:
    qualified_dates = sorted({row["collection_date"] for row in records if row["qualified_day"]})
    anomaly_blockers = sorted(
        {blocker for row in records for blocker in row.get("blockers", []) if blocker}
    )
    forward_ids = {
        signal_id for row in records for signal_id in row.get("new_forward_signal_ids", [])
    }
    threshold_met = len(qualified_dates) >= gate_days or len(forward_ids) >= gate_signals
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "attempt_count": len(records),
        "qualified_collection_dates": qualified_dates,
        "qualified_day_count": len(qualified_dates),
        "new_forward_signal_count": len(forward_ids),
        "new_forward_signal_ids": sorted(forward_ids),
        "gate": {"days": gate_days, "signals": gate_signals, "operator": "or"},
        "threshold_met": threshold_met,
        "review_eligible": threshold_met and not anomaly_blockers,
        "anomaly_blockers": anomaly_blockers,
        "next_action": "human_paper_simulated_review"
        if threshold_met and not anomaly_blockers
        else "continue_paper_shadow_collection",
    }


def collect_daily(
    *,
    repo_root: Path,
    data_root: Path,
    contract_path: Path = CONTRACT_PATH,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
    git_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    contract = load_contract(contract_path)
    contract_hash = f"sha256:{hashlib.sha256(contract_path.read_bytes()).hexdigest()}"
    data_root.mkdir(parents=True, exist_ok=True)
    lock_path = data_root / ".collector.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_dir = data_root / "state"
        raw_dir = data_root / "raw"
        journal_dir = data_root / "journal"
        state_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        journal_dir.mkdir(parents=True, exist_ok=True)

        repo = git_state or _git_state(repo_root)
        snapshot_path, snapshot = collect_snapshot(
            "gvz", output_dir=raw_dir / "gvz", fetch=fetch, now=observed_at
        )
        envelope = _strict_json(snapshot_path.read_bytes())
        gvz_raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
        gvz_rows, gvz_audit = parse_and_audit_csv("gvz", gvz_raw)

        btc_url = contract["collection"]["btc_url"]
        btc_raw = fetch(btc_url)
        btc_bars = _parse_btc_bars(btc_raw, observed_at=observed_at)
        attempt_id = f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{snapshot['snapshot_sha256'][-12:]}"
        btc_raw_path = raw_dir / "btc" / f"btc-1h-{attempt_id}.json"
        btc_raw_path.parent.mkdir(parents=True, exist_ok=True)
        btc_raw_path.write_bytes(btc_raw)

        gvz_state_path = state_dir / "gvz-observations.json"
        previous_gvz = _load_state(gvz_state_path)
        current_gvz = {row["date"]: format(float(row["close"]), ".12g") for row in gvz_rows}
        merged_gvz, gvz_revisions, new_gvz_rows = _merge_observations(previous_gvz, current_gvz)

        btc_state_path = state_dir / "btc-hourly-observations.json"
        previous_btc = _load_state(btc_state_path)
        current_btc = {str(row["open_time_ms"]): row for row in btc_bars}
        merged_btc, btc_revisions, new_btc_rows = _merge_observations(previous_btc, current_btc)
        btc_opens = sorted(int(value) for value in merged_btc)
        btc_contiguous = all(
            right - left == BTC_STEP_MS
            for left, right in zip(btc_opens, btc_opens[1:], strict=False)
        )

        frame = _factor_frame(
            gvz_rows,
            vintage_id=snapshot["vintage_id"],
            snapshot_sha256=snapshot["snapshot_sha256"],
        )
        events = generate_volatility_relief_signals(
            frame,
            strategy=contract["candidate"]["strategy"],
            symbol=contract["candidate"]["symbol"],
            venue=contract["candidate"]["venue"],
            start_date="2026-01-01",
        )
        store = SignalStore(data_root / "signals.db")
        source, model_version, _ = STRATEGY_IDENTITIES[contract["candidate"]["strategy"]]
        existing_ids = {
            event.signal_id
            for event in store.replay(source=source, model_version=model_version)
        }
        forward_start_ns = int(pd.Timestamp(contract["forward_started_at"]).value)
        new_forward = [
            event
            for event in events
            if event.ts_event >= forward_start_ns and event.signal_id not in existing_ids
        ]
        written, duplicates = store.write_many(events, now_ns=int(observed_at.timestamp() * 1e9))

        last_gvz_date = date.fromisoformat(gvz_audit["last_date"])
        gvz_age_days = (observed_at.date() - last_gvz_date).days
        blockers: list[str] = []
        if repo["dirty"]:
            blockers.append("git_dirty")
        if not repo["origin_main_contains_commit"]:
            blockers.append("commit_not_on_origin_main")
        if gvz_age_days < 0 or gvz_age_days > contract["collection"]["gvz_max_age_calendar_days"]:
            blockers.append(f"gvz_stale:{gvz_age_days}_days")
        if gvz_revisions:
            blockers.append(f"gvz_historical_revision:{len(gvz_revisions)}")
        if btc_revisions:
            blockers.append(f"btc_historical_revision:{len(btc_revisions)}")
        if not btc_contiguous:
            blockers.append("btc_hourly_gap")

        record = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "collection_date": observed_at.date().isoformat(),
            "contract_path": str(contract_path),
            "contract_sha256": contract_hash,
            "git": repo,
            "policy": contract["policy"],
            "gvz": {
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "vintage_id": snapshot["vintage_id"],
                "first_date": gvz_audit["first_date"],
                "last_date": gvz_audit["last_date"],
                "age_calendar_days": gvz_age_days,
                "new_observation_rows": new_gvz_rows,
                "historical_revisions": gvz_revisions,
            },
            "btc": {
                "url": btc_url,
                "raw_path": str(btc_raw_path),
                "raw_sha256": f"sha256:{hashlib.sha256(btc_raw).hexdigest()}",
                "closed_bar_rows": len(btc_bars),
                "first_open_time_ms": btc_bars[0]["open_time_ms"],
                "last_open_time_ms": btc_bars[-1]["open_time_ms"],
                "new_observation_rows": new_btc_rows,
                "historical_revisions": btc_revisions,
                "cumulative_contiguous": btc_contiguous,
            },
            "signals": {
                "generated_total": len(events),
                "baseline_before_forward_start": sum(
                    event.ts_event < forward_start_ns for event in events
                ),
                "generated_at_or_after_forward_start": sum(
                    event.ts_event >= forward_start_ns for event in events
                ),
                "written": written,
                "duplicates": duplicates,
                "new_forward": len(new_forward),
            },
            "new_forward_signal_ids": [event.signal_id for event in new_forward],
            "blockers": sorted(blockers),
            "qualified_day": not blockers,
            "boundaries": {
                "credentials_loaded": False,
                "orders_submitted": False,
                "fills_created": False,
                "testnet_touched": False,
                "live_path_touched": False,
                "future_blind_opened": False,
            },
        }
        journal_path = journal_dir / f"{attempt_id}.json"
        if journal_path.exists():
            raise FileExistsError(f"refusing to overwrite {journal_path}")
        journal_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        if not blockers:
            gvz_state_path.write_text(json.dumps(merged_gvz, indent=2, sort_keys=True) + "\n")
            btc_state_path.write_text(json.dumps(merged_btc, indent=2, sort_keys=True) + "\n")

        records = [_strict_json(path.read_bytes()) for path in sorted(journal_dir.glob("*.json"))]
        gate = contract["evidence_gate"]
        status = summarize_attempts(
            records,
            gate_days=gate["qualified_distinct_utc_collection_days"],
            gate_signals=gate["new_forward_signal_events"],
        )
        status.update(
            {
                "updated_at": record["observed_at"],
                "latest_attempt_id": attempt_id,
                "contract_sha256": contract_hash,
                "stage": "paper_shadow",
                "policy": contract["policy"],
                "future_blind_status": "sealed_unopened",
                "testnet_status": "blocked",
                "live_status": "blocked",
            }
        )
        (data_root / "status.json").write_text(
            json.dumps(status, indent=2, sort_keys=True) + "\n"
        )
        return {"record": record, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=Path("data/research-v8-forward"))
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    result = collect_daily(
        repo_root=args.repo_root.resolve(),
        data_root=args.data_root,
        contract_path=args.contract,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["record"]["qualified_day"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

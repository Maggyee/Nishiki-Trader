"""Collect one forward Protocol v18 VXN/BTC paper-shadow evidence attempt."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import subprocess
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.store import SignalStore
from apps.ops.research_v8_shadow_daily import _merge_observations, _parse_btc_bars
from apps.ops.research_v18_snapshot import collect_snapshot, parse_and_audit_csv
from apps.strategies_freqtrade.research.geographic_vol_ohlc_signals import (
    STRATEGY_IDENTITIES,
    generate_geographic_vol_signals,
)

CONTRACT_PATH = Path("docs/progress/phase-2-research-v18-paper-shadow.json")
SCHEMA_VERSION = "research.v18.paper_shadow_attempt.v1"
STATUS_SCHEMA_VERSION = "research.v18.paper_shadow_status.v1"
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
    if contract.get("schema_version") != "research.v18.paper_shadow_contract.v1":
        raise ValueError("paper-shadow contract schema drifted")
    if contract.get("status") != "prospectively_locked":
        raise ValueError("paper-shadow contract is not prospectively locked")
    if contract.get("candidate") != {
        "source": "rule_nasdaq_vol_relief_v2",
        "model_version": "cboe-vxn-ohlc5obs-negative-1d-v1",
        "strategy": "nasdaq_vol_relief",
        "symbol": "BTCUSDT",
        "venue": "BINANCE",
    }:
        raise ValueError("paper-shadow candidate identity drifted")
    if contract.get("policy") != {
        "stage": "paper_shadow",
        "dry_run": True,
        "position_pct_multiplier": 0.2,
        "min_confidence_override": None,
    }:
        raise ValueError("paper-shadow policy drifted")
    collection = contract.get("collection", {})
    if (
        collection.get("vxn_url")
        != "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv"
        or collection.get("btc_url")
        != "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=168"
        or collection.get("schedule") != "weekdays at 03:30 UTC"
        or collection.get("vxn_max_age_calendar_days") != 4
        or collection.get("btc_closed_bar_lookback") != 167
        or collection.get("decision_lag_calendar_days") != 1
        or collection.get("collector_implemented") is not True
        or collection.get("missing_policy") != "no_synthetic_rows_and_no_forward_fill"
        or collection.get("historical_revision_policy")
        != "fail_closed_and_require_human_review"
    ):
        raise ValueError("paper-shadow collection contract drifted")
    if any(contract.get("boundaries", {}).values()):
        raise ValueError("paper-shadow boundaries must all remain false")
    return contract


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v18"})
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


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = _strict_json(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"state at {path} must be an object")
    return value


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
            "vxn", output_dir=raw_dir / "vxn", fetch=fetch, now=observed_at
        )
        envelope = _strict_json(snapshot_path.read_bytes())
        vxn_raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
        vxn_rows, vxn_audit = parse_and_audit_csv("vxn", vxn_raw)

        btc_url = contract["collection"]["btc_url"]
        btc_raw = fetch(btc_url)
        btc_bars = _parse_btc_bars(btc_raw, observed_at=observed_at)
        attempt_id = f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{snapshot['snapshot_sha256'][-12:]}"
        btc_raw_path = raw_dir / "btc" / f"btc-1h-{attempt_id}.json"
        btc_raw_path.parent.mkdir(parents=True, exist_ok=True)
        btc_raw_path.write_bytes(btc_raw)

        vxn_state_path = state_dir / "vxn-observations.json"
        previous_vxn = _load_state(vxn_state_path)
        current_vxn = {row["date"]: format(float(row["close"]), ".12g") for row in vxn_rows}
        merged_vxn, vxn_revisions, new_vxn_rows = _merge_observations(previous_vxn, current_vxn)

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
            vxn_rows,
            vintage_id=snapshot["vintage_id"],
            snapshot_sha256=snapshot["snapshot_sha256"],
        )
        events = generate_geographic_vol_signals(
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

        last_vxn_date = date.fromisoformat(vxn_audit["last_date"])
        vxn_age_days = (observed_at.date() - last_vxn_date).days
        lookback = int(contract["collection"]["btc_closed_bar_lookback"])
        blockers: list[str] = []
        if repo["dirty"]:
            blockers.append("git_dirty")
        if not repo["origin_main_contains_commit"]:
            blockers.append("commit_not_on_origin_main")
        if vxn_age_days < 0 or vxn_age_days > contract["collection"]["vxn_max_age_calendar_days"]:
            blockers.append(f"vxn_stale:{vxn_age_days}_days")
        if vxn_revisions:
            blockers.append(f"vxn_historical_revision:{len(vxn_revisions)}")
        if btc_revisions:
            blockers.append(f"btc_historical_revision:{len(btc_revisions)}")
        if not btc_contiguous:
            blockers.append("btc_hourly_gap")
        if len(btc_bars) < lookback:
            blockers.append(f"btc_insufficient_closed_bars:{len(btc_bars)}")

        record = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "collection_date": observed_at.date().isoformat(),
            "contract_path": str(contract_path),
            "contract_sha256": contract_hash,
            "git": repo,
            "policy": contract["policy"],
            "vxn": {
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "vintage_id": snapshot["vintage_id"],
                "first_date": vxn_audit["first_date"],
                "last_date": vxn_audit["last_date"],
                "age_calendar_days": vxn_age_days,
                "new_observation_rows": new_vxn_rows,
                "historical_revisions": vxn_revisions,
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
            vxn_state_path.write_text(json.dumps(merged_vxn, indent=2, sort_keys=True) + "\n")
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
                "paper_simulated_status": "not_authorized",
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
    parser.add_argument("--data-root", type=Path, default=Path("data/research-v18-forward"))
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

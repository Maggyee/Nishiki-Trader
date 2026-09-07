"""Collect one forward Protocol v22 COR1M/BTC paper-shadow evidence attempt."""

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
from apps.ops.research_protocol_v22 import IDENTITIES
from apps.ops.research_shadow_runtime import (
    atomic_json,
    captured_btc_observations,
    summarize_qualified,
)
from apps.ops.research_v8_shadow_daily import _merge_observations, _parse_btc_bars
from apps.ops.research_v22_snapshot import collect_snapshot, parse_and_audit_csv
from apps.strategies_freqtrade.research.option_surface_signals import (
    generate_option_surface_signals,
)

CONTRACT_PATH = Path("docs/progress/phase-2-research-v22-paper-shadow.json")
SCHEMA_VERSION = "research.v22.paper_shadow_attempt.v1"
STATUS_SCHEMA_VERSION = "research.v22.paper_shadow_status.v1"
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
    if contract.get("schema_version") != "research.v22.paper_shadow_contract.v1":
        raise ValueError("paper-shadow contract schema drifted")
    if contract.get("status") != "prospectively_locked":
        raise ValueError("paper-shadow contract is not prospectively locked")
    if contract.get("candidate", {}).get("source") != "rule_cboe_implied_correlation_relief_v1" or contract.get("candidate", {}).get("model_version") != "cboe-cor1m-diff5-negative-lag1d-v1":
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
        collection.get("cor1m_url")
        != "https://cdn.cboe.com/api/global/us_indices/daily_prices/COR1M_History.csv"
        or collection.get("btc_url")
        != "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=168"
        or collection.get("cor1m_max_age_calendar_days") != 4
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
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v22"})
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
                "observation_date": row["date"],
                "vintage_id": vintage_id,
                "snapshot_sha256": snapshot_sha256,
                "index_value": row["value"],
            }
        )
    return pd.DataFrame.from_records(records).set_index("ts_event")


def summarize_attempts(records: list[dict[str, Any]], *, gate_days: int, gate_signals: int) -> dict[str, Any]:
    return {"schema_version": STATUS_SCHEMA_VERSION, **summarize_qualified(records, gate_days=gate_days, gate_signals=gate_signals)}



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
            "cor1m", output_dir=raw_dir / "cor1m", fetch=fetch, now=observed_at
        )
        envelope = _strict_json(snapshot_path.read_bytes())
        cor1m_raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
        cor1m_rows, cor1m_audit = parse_and_audit_csv("cor1m", cor1m_raw)

        btc_url = contract["collection"]["btc_url"]
        btc_raw = fetch(btc_url)
        btc_bars = _parse_btc_bars(btc_raw, observed_at=observed_at)
        attempt_id = f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{snapshot['snapshot_sha256'][-12:]}"
        btc_raw_path = raw_dir / "btc" / f"btc-1h-{attempt_id}.json"
        btc_raw_path.parent.mkdir(parents=True, exist_ok=True)
        btc_raw_path.write_bytes(btc_raw)

        cor1m_state_path = state_dir / "cor1m-observations.json"
        previous_cor1m = _load_state(cor1m_state_path)
        current_cor1m = {row["date"]: format(float(row["value"]), ".12g") for row in cor1m_rows}
        merged_cor1m, cor1m_revisions, new_cor1m_rows = _merge_observations(previous_cor1m, current_cor1m)

        btc_state_path = state_dir / "btc-hourly-observations.json"
        previous_btc = captured_btc_observations(_load_state(btc_state_path), journal_dir)
        current_btc = {str(row["open_time_ms"]): row for row in btc_bars}
        merged_btc, btc_revisions, new_btc_rows = _merge_observations(previous_btc, current_btc)
        btc_opens = sorted(int(value) for value in merged_btc)
        btc_contiguous = all(
            right - left == BTC_STEP_MS
            for left, right in zip(btc_opens, btc_opens[1:], strict=False)
        )

        frame = _factor_frame(
            cor1m_rows,
            vintage_id=snapshot["vintage_id"],
            snapshot_sha256=snapshot["snapshot_sha256"],
        )
        candidate_key = contract["candidate"].get("candidate_key", "implied_correlation_relief")
        events = generate_option_surface_signals(
            frame,
            candidate=candidate_key,
            symbol=contract["candidate"]["symbol"],
            venue=contract["candidate"]["venue"],
            start_date="2026-01-01",
        )
        store = SignalStore(data_root / "signals.db")
        source, model_version = IDENTITIES[candidate_key]
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
        written = duplicates = 0

        last_cor1m_date = date.fromisoformat(cor1m_audit["last_date"])
        cor1m_age_days = (observed_at.date() - last_cor1m_date).days
        lookback = int(contract["collection"]["btc_closed_bar_lookback"])
        blockers: list[str] = []
        if repo["dirty"]:
            blockers.append("git_dirty")
        if not repo["origin_main_contains_commit"]:
            blockers.append("commit_not_on_origin_main")
        if cor1m_age_days < 0 or cor1m_age_days > contract["collection"]["cor1m_max_age_calendar_days"]:
            blockers.append(f"cor1m_stale:{cor1m_age_days}_days")
        if cor1m_revisions:
            blockers.append(f"cor1m_historical_revision:{len(cor1m_revisions)}")
        if btc_revisions:
            blockers.append(f"btc_historical_revision:{len(btc_revisions)}")
        if not btc_contiguous:
            blockers.append("btc_hourly_gap")
        if len(btc_bars) < lookback:
            blockers.append(f"btc_insufficient_closed_bars:{len(btc_bars)}")

        if not blockers:
            written, duplicates = store.write_many(events, now_ns=int(observed_at.timestamp() * 1e9))
        else:
            new_forward = []

        record = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "collection_date": observed_at.date().isoformat(),
            "contract_path": str(contract_path),
            "contract_sha256": contract_hash,
            "git": repo,
            "policy": contract["policy"],
            "cor1m": {
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "vintage_id": snapshot["vintage_id"],
                "first_date": cor1m_audit["first_date"],
                "last_date": cor1m_audit["last_date"],
                "age_calendar_days": cor1m_age_days,
                "new_observation_rows": new_cor1m_rows,
                "historical_revisions": cor1m_revisions,
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
            cor1m_state_path.write_text(json.dumps(merged_cor1m, indent=2, sort_keys=True) + "\n")
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
        atomic_json(data_root / "status.json", status)
        return {"record": record, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=Path("data/research-v22-forward"))
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

"""Collect one immutable Protocol v12 stablecoin-forward evidence attempt."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v12 import MODEL_VERSION, SOURCE, load_and_validate
from apps.ops.research_v8_shadow_daily import (
    _git_state,
    _merge_observations,
    _parse_btc_bars,
    _strict_json,
)
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id

CONTRACT_PATH = Path("docs/progress/phase-2-research-protocol-v12.json")
SCHEMA_VERSION = "research.v12.forward_attempt.v1"
STATUS_SCHEMA_VERSION = "research.v12.forward_status.v1"
Fetch = Callable[[str], bytes]


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    load_and_validate(path)
    payload = _strict_json(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v12 contract must be an object")
    return payload


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v12"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _coinmetrics_url(contract: dict[str, Any], target_day: date) -> str:
    collection = contract["collection"]
    params = {**collection["coinmetrics_params"], "end_time": target_day.isoformat()}
    return f"{collection['coinmetrics_url']}?{urllib.parse.urlencode(params)}"


def _parse_time(value: Any) -> date:
    timestamp = pd.Timestamp(str(value))
    if timestamp.tz is None:
        raise ValueError("Coin Metrics time must include a timezone")
    timestamp = timestamp.tz_convert("UTC")
    if timestamp != timestamp.normalize():
        raise ValueError("Coin Metrics time must identify a UTC day")
    return timestamp.date()


def parse_stablecoin_rows(
    raw: bytes, *, start_day: date, target_day: date
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _strict_json(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Coin Metrics response must contain a data list")
    if payload.get("next_page_token") or payload.get("next_page_url"):
        raise ValueError("Coin Metrics response unexpectedly requires pagination")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, date]] = set()
    for index, row in enumerate(payload["data"]):
        if not isinstance(row, dict):
            raise ValueError(f"Coin Metrics row {index} must be an object")
        asset = str(row.get("asset"))
        if asset not in {"usdt", "usdc"}:
            raise ValueError(f"unexpected stablecoin asset {asset!r}")
        observation_day = _parse_time(row.get("time"))
        if not start_day <= observation_day <= target_day:
            raise ValueError("Coin Metrics response escaped the locked date range")
        key = (asset, observation_day)
        if key in seen:
            raise ValueError("Coin Metrics asset/day rows must be unique")
        seen.add(key)
        try:
            supply = float(row["SplyCur"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Coin Metrics row is missing numeric SplyCur") from exc
        if not math.isfinite(supply) or supply <= 0.0:
            raise ValueError("Coin Metrics SplyCur must be finite and positive")
        normalized.append(
            {"asset": asset, "date": observation_day.isoformat(), "supply": format(supply, ".17g")}
        )
    expected_days = (target_day - start_day).days + 1
    expected = {
        (asset, start_day + timedelta(days=offset))
        for asset in ("usdt", "usdc")
        for offset in range(expected_days)
    }
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    if missing or extra:
        raise ValueError(
            f"Coin Metrics stablecoin grid is incomplete: missing={len(missing)} extra={len(extra)}"
        )
    normalized.sort(key=lambda row: (row["date"], row["asset"]))
    return normalized, {
        "row_count": len(normalized),
        "asset_row_counts": {"usdc": expected_days, "usdt": expected_days},
        "first_date": start_day.isoformat(),
        "last_date": target_day.isoformat(),
        "complete_daily_grid": True,
    }


def _factor_frame(
    rows: list[dict[str, Any]], *, snapshot_sha256: str, vintage_id: str
) -> pd.DataFrame:
    raw = pd.DataFrame(rows)
    raw["supply"] = pd.to_numeric(raw["supply"], errors="raise")
    grouped = raw.groupby("date", sort=True)["supply"].sum().to_frame("stablecoin_supply")
    observation_days = pd.to_datetime(grouped.index, utc=True, errors="raise")
    grouped.index = observation_days + pd.Timedelta(days=2)
    grouped.index.name = "ts_event"
    grouped["observation_date"] = [value.date().isoformat() for value in observation_days]
    grouped["available_at"] = grouped.index
    grouped["snapshot_sha256"] = snapshot_sha256
    grouped["vintage_id"] = vintage_id
    return grouped


def generate_forward_events(
    frame: pd.DataFrame,
    *,
    contract: dict[str, Any],
) -> list[SignalEvent]:
    params = contract["candidate"]["parameters"]
    change_days = int(params["change_observations"])
    change = frame["stablecoin_supply"].pct_change(change_days)
    states = (change > float(params["maximum_change"])).where(change.notna())
    start = pd.Timestamp(contract["collection"]["forward_decision_start"])
    current_long = False
    feature_body = {
        "protocol": "research.protocol.v12",
        "candidate": contract["candidate"]["key"],
        "parameters": params,
    }
    feature_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(feature_body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    events: list[SignalEvent] = []
    for timestamp, desired in states.items():
        if pd.isna(desired) or timestamp < start:
            continue
        desired_long = bool(desired)
        if desired_long == current_long:
            continue
        row = frame.loc[timestamp]
        side = "buy" if desired_long else "flat"
        metric = float(change.loc[timestamp])
        ts_event = int(timestamp.value)
        events.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": _make_signal_id(
                        source=SOURCE,
                        model_version=MODEL_VERSION,
                        symbol=contract["candidate"]["symbol"],
                        venue=contract["candidate"]["venue"],
                        ts_event_ns=ts_event,
                        side=side,
                    ),
                    "symbol": contract["candidate"]["symbol"],
                    "venue": contract["candidate"]["venue"],
                    "ts_event": ts_event,
                    "horizon": "1d",
                    "side": side,
                    "score": math.tanh(max(0.0, metric)) if desired_long else 0.0,
                    "confidence": float(params["confidence"]),
                    "source": SOURCE,
                    "model_version": MODEL_VERSION,
                    "ttl_seconds": int(params["ttl_seconds"]),
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": "research.protocol.v12",
                        "candidate": contract["candidate"]["key"],
                        "observation_date": row["observation_date"],
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "snapshot_sha256": row["snapshot_sha256"],
                        "vintage_id": row["vintage_id"],
                        "point_in_time": True,
                        "forward_data_candidate": True,
                        "stablecoin_supply": round(float(row["stablecoin_supply"]), 8),
                        "change_30_observations": round(metric, 12),
                        **params,
                    },
                }
            )
        )
        current_long = desired_long
    return events


def summarize_attempts(
    records: list[dict[str, Any]], *, required_days: int, required_events: int
) -> dict[str, Any]:
    observation_dates = sorted(
        {
            value
            for row in records
            if row.get("qualified_attempt")
            for value in row.get("new_forward_observation_dates", [])
        }
    )
    event_ids = sorted(
        {
            value
            for row in records
            if row.get("qualified_attempt")
            for value in row.get("new_forward_signal_ids", [])
        }
    )
    anomalies = sorted(
        {
            blocker
            for row in records
            for blocker in row.get("blockers", [])
            if "revision" in blocker or "gap" in blocker or "grid" in blocker
        }
    )
    threshold = len(observation_dates) >= required_days and len(event_ids) >= required_events
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "attempt_count": len(records),
        "qualified_forward_observation_dates": observation_dates,
        "qualified_forward_observation_count": len(observation_dates),
        "new_forward_signal_ids": event_ids,
        "new_forward_state_change_count": len(event_ids),
        "gate": {
            "observation_days": required_days,
            "state_changes": required_events,
            "operator": "and",
        },
        "threshold_met": threshold,
        "continuation_review_eligible": threshold and not anomalies,
        "promotion_eligible": False,
        "anomaly_blockers": anomalies,
        "next_action": "human_continuation_review"
        if threshold and not anomalies
        else "continue_forward_data_collection",
    }


def _write_snapshot(
    *,
    raw: bytes,
    rows_audit: dict[str, Any],
    url: str,
    observed_at: datetime,
    output_dir: Path,
    protocol_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    payload_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    core = {
        "schema_version": "research.raw_snapshot.v12",
        "retrieved_at": observed_at.isoformat().replace("+00:00", "Z"),
        "url": url,
        "protocol_sha256": protocol_sha256,
        "payload_sha256": payload_hash,
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        "audit": rows_audit,
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": f"sha256:{digest}",
        "vintage_id": f"coinmetrics-stablecoin-forward:{observed_at.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"stablecoin-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path, envelope


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
    validation = load_and_validate(contract_path)
    target_day = observed_at.date() - timedelta(days=2)
    start_day = date.fromisoformat(contract["collection"]["coinmetrics_params"]["start_time"])
    if target_day < start_day:
        raise ValueError("Protocol v12 target day precedes bootstrap start")
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / ".collector.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw_dir = data_root / "raw"
        state_dir = data_root / "state"
        journal_dir = data_root / "journal"
        for path in (raw_dir, state_dir, journal_dir):
            path.mkdir(parents=True, exist_ok=True)

        repo = git_state or _git_state(repo_root)
        cm_url = _coinmetrics_url(contract, target_day)
        cm_raw = fetch(cm_url)
        rows, audit = parse_stablecoin_rows(cm_raw, start_day=start_day, target_day=target_day)
        snapshot_path, snapshot = _write_snapshot(
            raw=cm_raw,
            rows_audit=audit,
            url=cm_url,
            observed_at=observed_at,
            output_dir=raw_dir / "stablecoin",
            protocol_sha256=validation["protocol_sha256"],
        )
        btc_url = contract["collection"]["btc_url"]
        btc_raw = fetch(btc_url)
        btc_bars = _parse_btc_bars(btc_raw, observed_at=observed_at)
        attempt_id = f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{snapshot['snapshot_sha256'][-12:]}"
        btc_path = raw_dir / "btc" / f"btc-1h-{attempt_id}.json"
        btc_path.parent.mkdir(parents=True, exist_ok=True)
        if btc_path.exists():
            raise FileExistsError(f"refusing to overwrite {btc_path}")
        btc_path.write_bytes(btc_raw)

        stable_state_path = state_dir / "stablecoin-observations.json"
        previous_stable = (
            _strict_json(stable_state_path.read_bytes()) if stable_state_path.exists() else {}
        )
        current_stable = {f"{row['asset']}:{row['date']}": row["supply"] for row in rows}
        merged_stable, stable_revisions, _ = _merge_observations(previous_stable, current_stable)

        btc_state_path = state_dir / "btc-hourly-observations.json"
        previous_btc = _strict_json(btc_state_path.read_bytes()) if btc_state_path.exists() else {}
        current_btc = {str(row["open_time_ms"]): row for row in btc_bars}
        merged_btc, btc_revisions, _ = _merge_observations(previous_btc, current_btc)
        btc_times = sorted(int(value) for value in merged_btc)
        btc_contiguous = all(
            right - left == 3_600_000 for left, right in zip(btc_times, btc_times[1:], strict=False)
        )

        frame = _factor_frame(
            rows,
            snapshot_sha256=snapshot["snapshot_sha256"],
            vintage_id=snapshot["vintage_id"],
        )
        events = generate_forward_events(frame, contract=contract)
        store = SignalStore(data_root / "signals.db")
        existing_ids = {
            event.signal_id for event in store.replay(source=SOURCE, model_version=MODEL_VERSION)
        }
        new_events = [event for event in events if event.signal_id not in existing_ids]

        blockers: list[str] = []
        if repo["dirty"]:
            blockers.append("git_dirty")
        if not repo["origin_main_contains_commit"]:
            blockers.append("commit_not_on_origin_main")
        if stable_revisions:
            blockers.append(f"stablecoin_historical_revision:{len(stable_revisions)}")
        if btc_revisions:
            blockers.append(f"btc_historical_revision:{len(btc_revisions)}")
        if not btc_contiguous:
            blockers.append("btc_hourly_gap")
        qualified = not blockers
        forward_start = date.fromisoformat(contract["collection"]["forward_observation_start"])
        new_forward_dates = (
            [target_day.isoformat()] if qualified and target_day >= forward_start else []
        )
        written = duplicates = 0
        if qualified:
            written, duplicates = store.write_many(
                events, now_ns=int(observed_at.timestamp() * 1_000_000_000)
            )
            stable_state_path.write_text(json.dumps(merged_stable, indent=2, sort_keys=True) + "\n")
            btc_state_path.write_text(json.dumps(merged_btc, indent=2, sort_keys=True) + "\n")

        record = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "collection_date": observed_at.date().isoformat(),
            "target_observation_date": target_day.isoformat(),
            "contract_sha256": validation["protocol_sha256"],
            "git": repo,
            "stablecoin": {
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "vintage_id": snapshot["vintage_id"],
                "row_count": audit["row_count"],
                "first_date": audit["first_date"],
                "last_date": audit["last_date"],
                "complete_daily_grid": audit["complete_daily_grid"],
                "historical_revisions": stable_revisions,
            },
            "btc": {
                "raw_path": str(btc_path),
                "raw_sha256": f"sha256:{hashlib.sha256(btc_raw).hexdigest()}",
                "closed_bar_rows": len(btc_bars),
                "historical_revisions": btc_revisions,
                "cumulative_contiguous": btc_contiguous,
            },
            "signals": {
                "generated_total": len(events),
                "new_forward": len(new_events) if qualified else 0,
                "written": written,
                "duplicates": duplicates,
            },
            "new_forward_signal_ids": [event.signal_id for event in new_events]
            if qualified
            else [],
            "new_forward_observation_dates": new_forward_dates,
            "blockers": sorted(blockers),
            "qualified_attempt": qualified,
            "boundaries": {
                "credentials_loaded": False,
                "orders_submitted": False,
                "fills_created": False,
                "source_policy_mutated": False,
                "paper_shadow_touched": False,
                "testnet_touched": False,
                "live_path_touched": False,
                "historical_confirmation_opened": False,
                "future_blind_opened": False,
            },
        }
        journal_path = journal_dir / f"{attempt_id}.json"
        if journal_path.exists():
            raise FileExistsError(f"refusing to overwrite {journal_path}")
        journal_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        records = [_strict_json(path.read_bytes()) for path in sorted(journal_dir.glob("*.json"))]
        gate = contract["evidence_gate"]
        status = summarize_attempts(
            records,
            required_days=int(gate["qualified_distinct_forward_observation_days"]),
            required_events=int(gate["new_forward_state_change_events"]),
        )
        status.update(
            {
                "updated_at": record["observed_at"],
                "latest_attempt_id": attempt_id,
                "contract_sha256": validation["protocol_sha256"],
                "stage": "forward_data_candidate",
                "historical_confirmation_status": "sealed_unopened",
                "future_blind_status": "sealed_unopened",
                "paper_shadow_status": "not_authorized",
                "testnet_status": "blocked",
                "live_status": "blocked",
            }
        )
        (data_root / "status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
        return {"record": record, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=Path("data/research-v12-forward"))
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    result = collect_daily(
        repo_root=args.repo_root.resolve(),
        data_root=args.data_root,
        contract_path=args.contract,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["record"]["qualified_attempt"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

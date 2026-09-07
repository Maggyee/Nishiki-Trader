"""Shared forward data integrity helpers; never evaluates returns or promotes a source."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import math
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from apps.bridge.store import SignalStore


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x") as handle:
            json.dump(value, handle, allow_nan=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def collection_lock(data_root: Path):
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / ".runtime.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def captured_btc_observations(previous: dict, journal_dir: Path) -> dict:
    """Recover ONLY retained, hash-verified observations, never qualified dates.

    A dirty-code attempt can capture valid raw bars without earning evidence.
    Replaying that capture prevents its expiry from the 168-hour REST window
    from permanently stalling the independently evaluated qualification cursor.
    """
    from apps.ops.research_v8_shadow_daily import _parse_btc_bars

    merged = dict(previous)
    lineage = []
    for path in sorted(journal_dir.glob("*.json")):
        record = json.loads(path.read_text())
        btc = record.get("btc", {})
        raw_path = btc.get("raw_path")
        expected = btc.get("raw_sha256")
        if not raw_path or not expected:
            raise ValueError(f"BTC capture lacks hash/path: {path.name}")
        capture = Path(raw_path)
        if not capture.is_absolute():
            # Legacy journals used data/<collector>/raw/... relative to the
            # authoring checkout, not the now-pinned deployment checkout.
            prefix = Path("data") / journal_dir.parent.name
            capture = journal_dir.parent / capture.relative_to(prefix)
        raw = capture.read_bytes()
        if "sha256:" + hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"BTC capture checksum mismatch: {path.name}")
        observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
        for bar in _parse_btc_bars(raw, observed_at=observed):
            key = str(bar["open_time_ms"])
            if key in merged and merged[key] != bar:
                raise ValueError(f"BTC captured observation revision: {key}")
            merged[key] = bar
        lineage.append({"journal": str(path), "raw_sha256": expected})
    atomic_json(journal_dir.parent / "state/captured-btc-lineage.json", {
        "schema_version": "research.captured_btc.v1", "captures": lineage,
        "observation_count": len(merged), "qualifies_historical_days": False,
    })
    return merged


def summarize_qualified(records: list[dict], *, gate_days: int, gate_signals: int) -> dict:
    dates = sorted({r["collection_date"] for r in records if r.get("qualified_day") is True})
    ids = sorted({s for r in records if r.get("qualified_day") is True
                  for s in r.get("new_forward_signal_ids", [])})
    historical = sorted({b for r in records for b in r.get("blockers", [])})
    last = records[-1] if records else {}
    qualified = [r.get("observed_at", r["collection_date"]) for r in records if r.get("qualified_day")]
    threshold = len(dates) >= gate_days or len(ids) >= gate_signals
    return {
        "attempt_count": len(records), "qualified_collection_dates": dates,
        "qualified_day_count": len(dates), "new_forward_signal_ids": ids,
        "new_forward_signal_count": len(ids), "last_qualified_at": max(qualified, default=None),
        "gate": {"days": gate_days, "signals": gate_signals, "operator": "or"},
        "threshold_met": threshold, "review_eligible": threshold and not historical,
        "anomaly_blockers": historical, "latest_blockers": last.get("blockers", []),
        "historical_anomalies_require_review": bool(historical),
        "next_action": "human_paper_simulated_review" if threshold and not historical else "continue_paper_shadow_collection",
    }


def write_daily_factors(rows: list[dict], envelope: dict, output: Path) -> Path:
    """Same D+1 index-value representation as the existing Cboe collectors."""
    output.parent.mkdir(parents=True, exist_ok=True)
    start = date.fromisoformat(rows[-1]["date"]) - timedelta(days=90)
    with output.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ts_event", "available_at", "observation_date",
                                                    "vintage_id", "snapshot_sha256", "index_value"])
        writer.writeheader()
        for row in rows:
            obs = date.fromisoformat(row["date"])
            if obs < start:
                continue
            available = datetime.combine(obs + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow({"ts_event": int(available.timestamp()*1e9),
                             "available_at": available.isoformat(), "observation_date": row["date"],
                             "vintage_id": envelope["vintage_id"],
                             "snapshot_sha256": envelope["snapshot_sha256"],
                             "index_value": format(float(row["value"]), ".12g")})
    return output


def run_forward_series(*, protocol: str, candidate: str, source: str, model: str,
                       fetch_snapshot, build_events, raw_dir: Path, factors_dir: Path,
                       signal_store_path: Path, state_file: Path, status_file: Path,
                       max_age_days: int, now: datetime | None = None,
                       git_state: dict | None = None) -> dict:
    """Qualify new forward observations; old invocation totals are never evidence.

    Existing state.json and snapshots are retained. The v2 checkpoint and journal
    start a new operational accounting epoch, without changing research identity.
    """
    observed = now or datetime.now(UTC)
    from apps.ops.research_v8_shadow_daily import _git_state

    repo = git_state if git_state is not None else _git_state(Path.cwd())
    root = state_file.parent
    journal = root / "runtime-journal"
    checkpoint = root / "runtime-state.json"
    with collection_lock(root):
        journal.mkdir(parents=True, exist_ok=True)
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text())  # corruption must not reset history
        else:
            state = {"forward_started_at": observed.isoformat(), "observations": {}}
        record = {"observed_at": observed.isoformat(), "collection_date": observed.date().isoformat(),
                  "qualified_day": False, "new_forward_signal_ids": [], "blockers": [], "git": repo}
        attempt_id = observed.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
        try:
            snapshot_path, envelope, rows = fetch_snapshot(raw_dir)
            snapshot_bytes = snapshot_path.read_bytes()
            record["snapshot_path"] = str(snapshot_path)
            record["snapshot_file_sha256"] = "sha256:" + hashlib.sha256(snapshot_bytes).hexdigest()
            dates = [date.fromisoformat(r["date"]) for r in rows]
            if not dates or dates != sorted(set(dates)):
                raise ValueError("empty, duplicate or unordered observations")
            # Ignore neither missing rows nor revisions of previously captured history.
            current = {r["date"]: {k: v for k, v in r.items() if k != "date"} for r in rows}
            for row in current.values():
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in row.values()):
                    raise ValueError("invalid observation value")
            previous = state["observations"]
            if any(current[k] != previous[k] for k in current.keys() & previous.keys()):
                raise ValueError("historical_observation_revision")
            if previous and any(k not in current for k in previous if dates[0].isoformat() <= k):
                raise ValueError("historical_observation_missing")
            age = (observed.date() - dates[-1]).days
            record.update(last_observation_date=dates[-1].isoformat(), observation_age_days=age,
                          new_observation_count=len(current.keys() - previous.keys()))
            if not 1 <= age <= max_age_days:
                raise ValueError(f"stale_or_unclosed_observation:{age}_days")
            gaps = [(b-a).days for a,b in zip(dates, dates[1:], strict=False)]
            if gaps and max(gaps) > (1 if protocol in {"v46", "v48"} else 4):
                raise ValueError("observation_gap")
            if repo.get("dirty") is not False or repo.get("origin_main_contains_commit") is not True:
                raise ValueError("clean_pushed_git_commit_required")
            factor_path = factors_dir / f"factors-{attempt_id}.csv"
            events = build_events(rows, envelope, factor_path)
            record.update(factor_path=str(factor_path),
                          factor_sha256="sha256:" + hashlib.sha256(factor_path.read_bytes()).hexdigest())
            store = SignalStore(signal_store_path)
            existing = {e.signal_id for e in store.replay(source=source, model_version=model)}
            boundary_ns = int(datetime.fromisoformat(state["forward_started_at"]).timestamp()*1e9)
            now_ns = int(observed.timestamp()*1e9)
            events = [e for e in events if e.ts_event <= now_ns]
            forward = [e.signal_id for e in events if e.ts_event > boundary_ns and e.signal_id not in existing]
            written, duplicates = store.write_many(events, now_ns=now_ns)
            record.update(signals_written=written, duplicates_skipped=duplicates,
                          qualified_day=bool(current.keys() - previous.keys()),
                          new_forward_signal_ids=forward)
            state["observations"].update(current)
            atomic_json(checkpoint, state)
        except Exception as exc:
            record["blockers"] = [f"collection_failed:{type(exc).__name__}:{exc}"]
        atomic_json(journal / f"{attempt_id}.json", record)
        records = [json.loads(p.read_text()) for p in sorted(journal.glob("*.json"))]
        status = summarize_qualified(records, gate_days=7, gate_signals=50)
        status.update({"schema_version": "research.shadow.runtime.v2", "protocol": protocol,
                       "source": source, "model_version": model, "strategy": candidate,
                       "stage": "paper_shadow", "policy": {"dry_run": True,
                           "position_pct_multiplier": 0.2, "min_confidence_override": None},
                       "updated_at": observed.isoformat(), "last_run_at": observed.isoformat(),
                       "last_observation_date": record.get("last_observation_date"),
                       "health": "DEGRADED" if record["blockers"] else "HEALTHY",
                       "legacy_history_path": str(state_file),
                       "legacy_run_counts_are_evidence": False,
                       "future_blind_status": "sealed_unopened", "testnet_status": "blocked", "live_status": "blocked"})
        atomic_json(status_file, status)
        return status

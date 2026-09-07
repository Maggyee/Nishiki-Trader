from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from apps.ops.research_shadow_runtime import (
    captured_btc_observations,
    run_forward_series,
    summarize_qualified,
)


def test_failed_attempt_signals_never_count():
    result = summarize_qualified([
        {"collection_date": "2026-08-20", "qualified_day": False, "new_forward_signal_ids": ["bad"], "blockers": ["gap"]},
        {"collection_date": "2026-08-21", "qualified_day": True, "new_forward_signal_ids": ["good"], "blockers": []},
    ], gate_days=1, gate_signals=1)
    assert result["new_forward_signal_ids"] == ["good"]
    assert result["threshold_met"] and not result["review_eligible"]
    assert result["latest_blockers"] == [] and result["anomaly_blockers"] == ["gap"]


def test_captured_btc_recovery_preserves_failed_attempt(tmp_path):
    journal = tmp_path / "journal"
    journal.mkdir()
    raw = json.dumps([[i*3600000, "100", "102", "99", "101", "10", (i+1)*3600000-1] for i in range(48)]).encode()
    capture = tmp_path / "bars.json"
    capture.write_bytes(raw)
    record = {"observed_at": "1970-01-03T00:00:00+00:00", "qualified_day": False,
              "btc": {"raw_path": str(capture), "raw_sha256": "sha256:"+hashlib.sha256(raw).hexdigest()}}
    path = journal / "failed.json"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    assert len(captured_btc_observations({}, journal)) == 48
    assert path.read_bytes() == before
    capture.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        captured_btc_observations({}, journal)


def run_fixture(tmp_path, *, now, rows, protocol="v46"):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(rows))
    def events(rows, envelope, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
        return []
    return run_forward_series(protocol=protocol, candidate="fixture", source="fixture", model="v1",
        fetch_snapshot=lambda _: (snapshot, {}, rows), build_events=events,
        raw_dir=tmp_path / "raw", factors_dir=tmp_path / "factors", signal_store_path=tmp_path / "signals.db",
        state_file=tmp_path / "state.json", status_file=tmp_path / "status.json", max_age_days=2, now=now,
        git_state={"dirty": False, "origin_main_contains_commit": True})


def test_duplicate_and_stale_runs_do_not_advance_days(tmp_path):
    now = datetime(2026, 9, 7, 4, tzinfo=UTC)
    rows = [{"date": "2026-09-06", "value": 1.0}]
    assert run_fixture(tmp_path, now=now, rows=rows)["qualified_day_count"] == 1
    duplicate = run_fixture(tmp_path, now=now+timedelta(seconds=1), rows=rows)
    assert duplicate["qualified_day_count"] == 1
    assert duplicate["attempt_count"] == 2
    stale = run_fixture(tmp_path, now=now+timedelta(days=3), rows=rows)
    assert stale["health"] == "DEGRADED"
    assert stale["qualified_day_count"] == 1


def test_revision_does_not_advance_or_replace_state(tmp_path):
    now = datetime(2026, 9, 7, 4, tzinfo=UTC)
    run_fixture(tmp_path, now=now, rows=[{"date": "2026-09-06", "value": 1.0}])
    before = (tmp_path / "runtime-state.json").read_bytes()
    result = run_fixture(tmp_path, now=now+timedelta(days=1), rows=[{"date": "2026-09-06", "value": 2.0}])
    assert result["health"] == "DEGRADED"
    assert (tmp_path / "runtime-state.json").read_bytes() == before


def test_old_cboe_closure_does_not_block_current_factor_window(tmp_path):
    rows = [{"date": "2012-10-26", "value": 1.0}, {"date": "2012-10-31", "value": 1.0},
            {"date": "2026-09-06", "value": 1.0}]
    result = run_fixture(tmp_path, now=datetime(2026,9,7,tzinfo=UTC), rows=rows, protocol="v40")
    assert result["qualified_day_count"] == 1
    assert result["latest_blockers"] == []

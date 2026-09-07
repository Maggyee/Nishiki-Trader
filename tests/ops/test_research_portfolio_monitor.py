from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apps.bridge.store import SignalStore
from apps.ops.research_portfolio_monitor import (
    CANDIDATE_SPECS,
    compute_portfolio_metrics,
    generate_portfolio_markdown_report,
    load_candidate_data,
    run_monitor,
)


def test_candidate_specs_roster() -> None:
    assert len(CANDIDATE_SPECS) == 10
    protocols = {c["protocol"] for c in CANDIDATE_SPECS}
    assert protocols == {"v8", "v16", "v18", "v22", "v34", "v36", "v40", "v42", "v46", "v48"}


@pytest.fixture
def sample_repo(tmp_path):
    now = datetime.now(UTC)
    for spec in CANDIDATE_SPECS:
        db = tmp_path / spec["db_path"]
        SignalStore(db)
        (db.parent / "status.json").write_text(json.dumps({
            "updated_at": now.isoformat(), "qualified_day_count": 7,
            "threshold_met": True, "review_eligible": True,
            "anomaly_blockers": [], "policy": {"dry_run": True},
        }))
    return tmp_path


def test_load_candidate_data_from_repo(sample_repo) -> None:
    candidates = load_candidate_data(sample_repo)
    v40 = next(c for c in candidates if c["protocol"] == "v40")
    assert v40["threshold_met"] is True
    assert v40["qualified_days"] == 7
    assert v40["signals_count"] == 0
    assert v40["review_eligible"] is True


def test_compute_portfolio_metrics_and_exposure(sample_repo) -> None:
    candidates = load_candidate_data(sample_repo)
    metrics = compute_portfolio_metrics(candidates)
    assert metrics["active_series_count"] == 0
    assert "correlation_matrix" in metrics
    assert "overlap_matrix" in metrics
    assert "portfolio_exposure_stats" in metrics
    assert metrics["portfolio_exposure_stats"] == {}


def test_generate_portfolio_markdown_report(sample_repo) -> None:
    candidates = load_candidate_data(sample_repo)
    metrics = compute_portfolio_metrics(candidates)
    md = generate_portfolio_markdown_report(candidates, metrics)
    assert "# Phase 5 Multi-Candidate Forward Paper-Shadow Portfolio Report" in md
    assert "## 1. Candidate Roster & Progress" in md
    assert "## 2. Cross-Strategy Correlation Matrix" in md


def test_run_monitor_end_to_end(tmp_path: Path, sample_repo) -> None:
    json_path = tmp_path / "portfolio_status.json"
    md_path = tmp_path / "portfolio_report.md"
    payload = run_monitor(
        repo_root=sample_repo,
        output_json_path=json_path,
        output_md_path=md_path,
    )
    assert payload["schema_version"] == "research.portfolio_shadow_monitor.v2"
    assert json_path.exists()
    assert md_path.exists()


@pytest.mark.parametrize("fault", ["corrupt_db", "missing_db", "stale", "invalid_json", "invalid_gate", "denied", "legacy"])
def test_bad_inputs_never_create_review_eligibility(sample_repo, fault):
    spec = CANDIDATE_SPECS[0]
    db = sample_repo / spec["db_path"]
    path = db.parent / "status.json"
    status = json.loads(path.read_text())
    if fault == "corrupt_db":
        db.write_bytes(b"not a sqlite database")
    elif fault == "missing_db":
        db.unlink()
    elif fault == "stale":
        status["updated_at"] = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    elif fault == "invalid_gate":
        status["gate"] = []
    elif fault == "denied":
        status["review_eligible"] = False
    elif fault == "legacy":
        status.pop("qualified_day_count")
        status["total_days_collected"] = 100
    path.write_text("[" if fault == "invalid_json" else json.dumps(status))
    c = load_candidate_data(sample_repo, [spec])[0]
    assert not c["review_eligible"]
    if fault != "denied":
        assert c["anomaly_blockers"]


def test_missing_inputs_are_reported_without_creating_db(tmp_path):
    candidates = load_candidate_data(tmp_path)
    assert all(not c["review_eligible"] for c in candidates)
    assert not list(tmp_path.rglob("*.db"))


def test_sparse_events_never_imply_flat_holdings_or_leverage():
    def candidate(proto, entries):
        return {"protocol": proto, "signals": [
            {"dt_utc": f"2026-08-{day:02d}T00:00:00+00:00", "side": side}
            for day, side in entries]}
    metrics = compute_portfolio_metrics([
        candidate("v18", [(1, "BUY"), (3, "FLAT")]),
        candidate("v40", [(2, "BUY"), (3, "FLAT")]),
    ])
    assert metrics["total_days_observed"] == 3
    assert metrics["pairwise_sample_days"]["v18"]["v40"] == 1
    assert metrics["correlation_matrix"]["v18"]["v40"] is None
    assert metrics["missing_signal_days"]["v18"] == 1
    assert metrics["portfolio_exposure_stats"] == {}
    assert metrics["portfolio_evaluation"]["actual_leverage"] is None
    assert metrics["holding_state_inferred"] is False

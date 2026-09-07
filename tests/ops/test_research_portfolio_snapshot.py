from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from apps.ops.dashboard_snapshot import build_dashboard_snapshot
from apps.ops.research_portfolio_monitor import CANDIDATE_SPECS, SCHEMA_VERSION
from apps.ops.research_portfolio_snapshot import read_portfolio_snapshot


@pytest.mark.parametrize("fault", [None, "stale", "corrupt", "roster", "identity", "boundary"])
def test_passive_portfolio_input_validation(tmp_path, fault):
    now = datetime.now(UTC)
    rows = [{"protocol": s["protocol"], "source": s["source"], "model_version": s["model_version"],
             "qualified_days": 3, "gate_days": 7, "review_eligible": False,
             "anomaly_blockers": []} for s in CANDIDATE_SPECS]
    payload = {"schema_version": SCHEMA_VERSION, "updated_at": now.isoformat(), "candidates": rows,
               "boundaries": {"dry_run": True, "live_trading_blocked": True,
                              "phase_6_gate_closed": True, "future_blind_sealed": True}}
    if fault == "stale":
        payload["updated_at"] = (now - timedelta(days=5)).isoformat()
    elif fault == "roster":
        rows.pop()
    elif fault == "identity":
        rows[0]["source"] = "unexpected"
    elif fault == "boundary":
        payload["boundaries"]["dry_run"] = False
    path = tmp_path / "status.json"
    path.write_text("{" if fault == "corrupt" else json.dumps(payload))
    before = path.read_bytes()
    result = read_portfolio_snapshot(path, generated_at_ns=int(now.timestamp()*1e9))
    assert result["state"] == ("attention" if fault else "healthy")
    assert path.read_bytes() == before
    if fault:
        assert result["candidates"] == [] and result["issue_count"] == 1


def test_dashboard_missing_portfolio_counts_as_attention(tmp_path):
    snapshot = build_dashboard_snapshot(project_status_path=tmp_path / "status.md",
        agent_advice_db_path=tmp_path / "advice.db", observability_textfile_dir=None,
        research_portfolio_status_path=tmp_path / "missing.json")
    assert snapshot["ops_status"]["counts"]["research_portfolio_issue_count"] == 1
    assert snapshot["ops_status"]["state"] == "attention"
    assert any(i["category"] == "research_portfolio" for i in snapshot["snapshot_inputs"]["items"])
    assert not list(tmp_path.glob("*.db"))

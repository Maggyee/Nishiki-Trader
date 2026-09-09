from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps.ops import portfolio_execution_plan as plan


def anchor():
    return json.loads(Path(plan.ANCHOR_PATH).read_text())


def test_frozen_cohort_and_proposal(monkeypatch):
    current = anchor()
    monkeypatch.setattr(plan.evidence, "build_report", lambda root: current)
    result = plan.build_plan(Path("."))
    assert [r["protocol"] for r in result["sleeves"]] == list(plan.SLEEVES)
    assert result["verified_evidence_cohort"] == list(plan.VERIFIED)
    assert result["capital_usdt"] == "500"
    assert result["daily_loss_usdt"] == "50"
    assert result["peak_drawdown_limit_usdt"] == "250"
    assert result["promotion_allowed"] is False
    assert result["runtime_risk_change_authorized"] is False
    assert result["status"] == "offline_engineering_only"
    committed = Path("docs/progress/portfolio-execution-plan-2026-09-09.json")
    assert result == json.loads(committed.read_text())


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "duplicate",
        "source",
        "model_version",
        "evidence",
        "execution_path_sha256",
        "excluded",
    ],
)
def test_changed_cohort_fails_closed(fault):
    original = anchor()
    current = copy.deepcopy(original)
    if fault == "missing":
        current["candidates"].pop()
    elif fault in {"extra", "duplicate"}:
        current["candidates"].append(current["candidates"][0])
    elif fault == "excluded":
        current["excluded"].pop()
    else:
        current["candidates"][0][fault] = "tampered"
    with pytest.raises(ValueError):
        plan.validate_cohort(original, current)


def test_duplicate_relation_required_even_when_two_reports_agree():
    changed = anchor()
    changed["candidates"][-1]["execution_path_sha256"] = "different"
    with pytest.raises(ValueError, match="duplicate-path"):
        plan.validate_cohort(changed, changed)


def test_missing_original_evidence_never_falls_back(tmp_path, capsys):
    assert plan.main(["--repo-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"

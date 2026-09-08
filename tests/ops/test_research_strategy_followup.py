import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from apps.ops import research_strategy_followup as followup
from apps.ops.research_shadow_runtime import summarize_signal_pipeline


def budget(**overrides):
    prices = pd.Series(
        [100000.0, 100000.0, 90000.0], index=pd.date_range("2022-12-31", periods=3, tz="UTC")
    )
    curve = pd.DataFrame(
        {
            "qty": [0.001, 0.001],
            "gross": [0.0, -10.0],
            "base": [-0.12, -10.12],
            "stress": [-0.15, -10.15],
        },
        index=prices.index[1:],
    )
    settings = {"capital": 100.0, "max_drawdown": 0.5, "daily_loss": 50.0, **overrides}
    return followup.planned_budget({"fixture": curve}, prices, {"fixture": 1.0}, **settings)


def test_planned_cash_includes_costs_and_honors_operator_budget_without_runtime_change():
    result = budget()
    base = result["scenarios"]["base"]
    assert result["diagnostic_budget_source"] == "operator_input"
    assert result["differs_from_unchanged_runtime_daily_rule"] is True
    assert result["unchanged_runtime_daily_rule_fraction"] == 0.05
    assert base["fixed_diagnostic_daily_loss_amount_usdt"] == 50.0
    assert base["daily_sampled_cash_funding_required_usdt"] == pytest.approx(100.12)
    assert base["minimum_daily_sampled_free_cash_at_planned_capital_usdt"] == pytest.approx(-0.12)
    assert base["cash_feasible_at_daily_marks"] is False
    assert base["daily_marked_max_drawdown_usdt"] == pytest.approx(10.12)
    assert base["worst_sampled_daily_loss_usdt"] == 10.0
    assert base["days_at_or_above_fixed_diagnostic_loss_amount"] == 0
    assert base["within_requested_drawdown_amount"] is True
    assert result["actual_account_return_pct"] is None
    assert result["actual_account_leverage"] is None
    assert result["runtime_risk_settings_changed"] is False


def test_stricter_user_daily_preference_remains_stricter():
    result = budget(daily_loss=2.0)
    assert result["diagnostic_budget_source"] == "operator_input"
    assert result["scenarios"]["base"]["fixed_diagnostic_daily_loss_amount_usdt"] == 2.0


@pytest.mark.parametrize("daily_loss, expected_days", [(5.0, 1), (10.0, 1), (50.0, 0)])
def test_daily_comparison_uses_exact_input_and_includes_threshold(daily_loss, expected_days):
    result = budget(daily_loss=daily_loss)
    assert result["scenarios"]["base"]["fixed_diagnostic_daily_loss_amount_usdt"] == daily_loss
    assert (
        result["scenarios"]["base"]["days_at_or_above_fixed_diagnostic_loss_amount"]
        == expected_days
    )
    assert result["runtime_risk_settings_changed"] is False


@pytest.mark.parametrize(
    "settings",
    [
        {"capital": 0.0},
        {"capital": float("nan")},
        {"max_drawdown": 1.1},
        {"daily_loss": 101.0},
        {"daily_loss": -1.0},
    ],
)
def test_invalid_risk_preferences_rejected(settings):
    with pytest.raises(ValueError, match="invalid planned"):
        budget(**settings)


def test_current_hashes_never_restore_historical_proof_and_dirty_is_blocker(tmp_path):
    path = tmp_path / "run_manifest.json"
    path.write_text(
        json.dumps(
            {
                "kind": "backtest",
                "git_dirty": True,
                "git_commit": "fixture",
                "backtest_start": "2023-01-01T00:00:00Z",
                "backtest_end": "2025-12-31T23:00:00Z",
                "signal_source": {"filter": {"source": "fixture", "model_version": "v1"}},
            }
        )
    )
    (tmp_path / "fills.parquet").write_bytes(
        b"opaque; audit inventories bytes without opening returns"
    )
    row = followup.inventory_manifest(path, {"source": "fixture", "model_version": "v1"})
    assert row["historical_provenance_verified"] is False
    assert "historical_git_not_clean" in row["blockers"]
    assert len(row["observed_now_hashes_not_original_proof"]["fills.parquet"]) == 64


def records_and_status():
    record = {
        "signal_pipeline_version": 2,
        "observed_at": "2026-09-08T01:00:00+00:00",
        "collection_date": "2026-09-08",
        "qualified_day": True,
        "blockers": [],
        "new_forward_signal_ids": [],
        "git": {"dirty": False, "origin_main_contains_commit": True},
    }
    records = [record, {**record, "observed_at": "2026-09-08T02:00:00+00:00"}]
    status = summarize_signal_pipeline(records, gate_days=7, gate_signals=50)
    status["signal_pipeline_started_at"] = record["observed_at"]
    return records, status


def test_same_day_attempts_never_become_elapsed_days():
    records, status = records_and_status()
    result = followup.check_prospective(records, status, [], datetime(2026, 9, 8, 3, tzinfo=UTC))
    assert result["qualified_day_count"] == 1
    assert result["threshold_met"] is False


@pytest.mark.parametrize(
    "fault", ["inflated_days", "future_attempt", "dirty_qualification", "invented_signal"]
)
def test_false_forward_evidence_fails_closed(fault):
    records, status = records_and_status()
    if fault == "inflated_days":
        status["qualified_day_count"] = 7
    elif fault == "future_attempt":
        records[1]["observed_at"] = "2026-09-09T02:00:00+00:00"
    elif fault == "dirty_qualification":
        records[1]["git"] = {"dirty": True, "origin_main_contains_commit": True}
    elif fault == "invented_signal":
        records[1]["new_forward_signal_ids"] = ["nonexistent"]
        status.update(summarize_signal_pipeline(records, gate_days=7, gate_signals=50))
    with pytest.raises(ValueError):
        followup.check_prospective(records, status, [], datetime(2026, 9, 8, 3, tzinfo=UTC))


def test_existing_report_never_overwritten(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("old")
    with pytest.raises(SystemExit):
        followup.main(
            [
                "--capital",
                "100",
                "--max-drawdown",
                ".5",
                "--daily-loss",
                "50",
                "--output",
                str(path),
            ]
        )
    assert path.read_text() == "old"


@pytest.mark.parametrize("fault", ["backfill", "duplicate", "future"])
def test_stored_event_does_not_make_invalid_prospective_evidence(fault):
    records, status = records_and_status()
    stamp = datetime(2026, 9, 8, 1, 30, tzinfo=UTC)
    if fault == "backfill":
        stamp = datetime(2026, 9, 8, 0, 30, tzinfo=UTC)
    elif fault == "future":
        stamp = datetime(2026, 9, 9, tzinfo=UTC)
    event = SimpleNamespace(signal_id="fixture", ts_event=int(stamp.timestamp() * 1e9))
    records[1]["new_forward_signal_ids"] = [event.signal_id]
    if fault == "duplicate":
        records.append({**records[1], "observed_at": "2026-09-08T02:30:00+00:00"})
    status.update(summarize_signal_pipeline(records, gate_days=7, gate_signals=50))
    with pytest.raises(ValueError):
        followup.check_prospective(records, status, [event], datetime(2026, 9, 8, 3, tzinfo=UTC))

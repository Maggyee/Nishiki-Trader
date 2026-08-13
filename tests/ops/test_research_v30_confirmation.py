from __future__ import annotations

import copy
import json

import pytest

from pathlib import Path

from apps.ops.research_v30_confirmation import DEFAULT_CONTRACT, validate_contract
from apps.ops.research_v30_confirmation_factor import _audit_confirmation_rows
from apps.ops.research_v30_confirmation_review import _classification

from datetime import date, timedelta


def _payload() -> dict:
    return json.loads(DEFAULT_CONTRACT.read_text())


def test_v30_confirmation_contract_is_valid() -> None:
    assert validate_contract(_payload())["valid"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidate", "parameters", "change_observations"), 3),
        (("development_evidence", "committed_review"), "uncommitted"),
        (("data_contract", "decision_lag_calendar_days"), 0),
        (("cost_scenarios", "base", "fee_bps_per_fill"), 9),
        (("data_access_disclosure", "confirmation_pnl_computed"), True),
        (("boundaries_effect", "opens_future_blind"), True),
    ],
)
def test_v30_confirmation_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_contract(payload)


def _rows(*, omitted: set[date] | None = None) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    current = date(2023, 1, 1)
    end = date(2025, 12, 31)
    while current <= end:
        if current.weekday() < 5 and current not in (omitted or set()):
            values.append({"date": current.isoformat(), "value": 20.0})
        current += timedelta(days=1)
    return values


def test_v30_confirmation_factor_audit_accepts_complete_grid() -> None:
    audit = _audit_confirmation_rows(_rows())
    assert audit["confirmation_row_count"] >= 700
    assert audit["annual_row_counts"].keys() == {"2023", "2024", "2025"}
    assert audit["forward_fill_used"] is False


def test_v30_confirmation_factor_audit_rejects_large_gap() -> None:
    omitted = {
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    }
    with pytest.raises(ValueError, match="gap exceeds"):
        _audit_confirmation_rows(_rows(omitted=omitted))


def test_v30_confirmation_classification() -> None:
    assert _classification(True, True) == "paper_shadow_review_eligible"
    assert _classification(False, True) == "reject_candidate"
    assert _classification(True, False) == "insufficient_confirmation_evidence"


def test_v30_confirmation_results_reject_google_vol_relief() -> None:
    payload = json.loads(
        Path("docs/progress/phase-2-research-v30-confirmation-results.json").read_text()
    )

    assert payload["recommendation"] == "stop_protocol_v30_confirmation_failed"
    assert payload["candidate"]["classification"] == "reject_candidate"
    assert payload["candidate"]["key"] == "google_vol_relief"
    assert payload["candidate"]["reproducible"] is True
    assert payload["candidate"]["leave_best_base_net_pnl"] < 0
    assert payload["boundaries"]["opens_future_blind"] is False

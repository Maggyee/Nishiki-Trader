from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_v19_review import (
    PROVIDER_QUALIFICATION,
    load_provider_qualification,
)


def test_v19_provider_qualification_locks_two_development_candidates() -> None:
    payload = load_provider_qualification()
    assert payload["development_eligible_candidates"] == [
        "russell_vol_relief",
        "dow_vol_relief",
    ]
    assert payload["provider_rejected_candidates"]["china_vol_relief"] == {
        "reason": "development_rows_533_below_locked_minimum_700",
        "request_openings": 1,
        "retry_allowed": False,
    }


def test_v19_provider_qualification_rejects_drift(tmp_path) -> None:
    payload = copy.deepcopy(json.loads(PROVIDER_QUALIFICATION.read_text()))
    payload["provider_rejected_candidates"]["china_vol_relief"]["retry_allowed"] = True
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="rejection evidence drifted"):
        load_provider_qualification(path)

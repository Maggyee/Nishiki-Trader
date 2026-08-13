from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_v20_review import (
    PROVIDER_QUALIFICATION,
    _classification,
    load_provider_qualification,
)


def test_v20_development_classification() -> None:
    assert (
        _classification(
            performance_pass=True,
            evidence_pass=True,
            base=1.0,
            stress=1.0,
            positions=30,
        )
        == "development_pass_confirmation_open_eligible"
    )
    assert (
        _classification(
            performance_pass=False,
            evidence_pass=True,
            base=1.0,
            stress=1.0,
            positions=20,
        )
        == "insufficient_evidence"
    )


def test_v20_provider_qualification_is_locked() -> None:
    payload = load_provider_qualification()
    assert payload["classification"] == "provider_qualified"
    assert payload["audit"]["development_row_count"] == 762
    assert payload["boundaries"]["pnl_opened"] is False


def test_v20_provider_qualification_rejects_drift(tmp_path) -> None:
    payload = copy.deepcopy(json.loads(PROVIDER_QUALIFICATION.read_text()))
    payload["audit"]["common_timestamps"] = False
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="coverage evidence drifted"):
        load_provider_qualification(path)

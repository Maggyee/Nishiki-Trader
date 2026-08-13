from __future__ import annotations

from apps.ops.research_v20_review import _classification


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

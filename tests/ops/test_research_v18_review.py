from __future__ import annotations

from apps.ops.research_v18_review import _classification


def test_v18_classification_uses_frozen_sparse_evidence_rule() -> None:
    assert (
        _classification(
            performance_pass=False,
            evidence_pass=True,
            base=3.0,
            stress=2.0,
            positions=12,
        )
        == "insufficient_evidence"
    )
    assert (
        _classification(
            performance_pass=False,
            evidence_pass=True,
            base=-1.0,
            stress=-2.0,
            positions=40,
        )
        == "reject_candidate"
    )
    assert (
        _classification(
            performance_pass=True,
            evidence_pass=True,
            base=1.0,
            stress=0.5,
            positions=40,
        )
        == "development_pass_confirmation_open_eligible"
    )

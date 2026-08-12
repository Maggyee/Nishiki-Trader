from __future__ import annotations

from apps.ops.research_v16_review import _classification


def test_v16_classification_distinguishes_sparse_positive_evidence() -> None:
    assert _classification(performance_pass=False, evidence_pass=True, base=2.0, stress=1.0, positions=7) == "insufficient_evidence"
    assert _classification(performance_pass=False, evidence_pass=True, base=-1.0, stress=-2.0, positions=40) == "reject_candidate"
    assert _classification(performance_pass=True, evidence_pass=True, base=1.0, stress=0.5, positions=40) == "development_pass_confirmation_open_eligible"

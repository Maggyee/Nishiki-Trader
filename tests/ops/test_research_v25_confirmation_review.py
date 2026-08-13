from __future__ import annotations

from apps.ops.research_v25_confirmation_review import _classification


def test_v25_confirmation_classification() -> None:
    assert _classification(True, True) == "paper_shadow_review_eligible"
    assert _classification(False, True) == "reject_candidate"
    assert _classification(True, False) == "insufficient_confirmation_evidence"

from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path("docs/progress/phase-2-research-v37-development-results.json")


def test_v37_development_results_structure_and_passes() -> None:
    payload = json.loads(RESULTS_PATH.read_text())
    assert payload["schema_version"] == "research.v37.development_results.v1"
    candidates = payload["candidates"]
    assert "bxn_expansion" in candidates
    assert "bxy_expansion" in candidates
    assert "bxr_expansion" in candidates
    assert candidates["bxn_expansion"]["pass_gates"] is True
    assert candidates["bxy_expansion"]["pass_gates"] is True
    assert candidates["bxr_expansion"]["pass_gates"] is False
    assert set(payload["passing_candidates"]) == {"bxn_expansion", "bxy_expansion"}
    assert payload["best_candidate"] == "bxn_expansion"

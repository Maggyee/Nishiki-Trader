from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path("docs/progress/phase-2-research-v36-development-results.json")


def test_v36_development_results_structure_and_passes() -> None:
    payload = json.loads(RESULTS_PATH.read_text())
    assert payload["schema_version"] == "research.v36.development_results.v1"
    candidates = payload["candidates"]
    assert "vpn_expansion" in candidates
    assert "bxm_expansion" in candidates
    assert "put_expansion" in candidates
    assert candidates["vpn_expansion"]["pass_gates"] is True
    assert candidates["bxm_expansion"]["pass_gates"] is True
    assert candidates["put_expansion"]["pass_gates"] is False
    assert set(payload["passing_candidates"]) == {"vpn_expansion", "bxm_expansion"}

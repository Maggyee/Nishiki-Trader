from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path("docs/progress/phase-2-research-v40-development-results.json")


def test_v40_development_results_structure_and_passes() -> None:
    payload = json.loads(RESULTS_PATH.read_text())
    assert payload["schema_version"] == "research.v40.development_results.v1"
    candidates = payload["candidates"]
    assert "vxn_relief" in candidates
    assert "rvx_relief" in candidates
    assert "vxd_relief" in candidates
    assert candidates["vxn_relief"]["pass_gates"] is True
    assert candidates["vxd_relief"]["pass_gates"] is True
    assert candidates["rvx_relief"]["pass_gates"] is False
    assert set(payload["passing_candidates"]) == {"vxn_relief", "vxd_relief"}
    assert payload["best_candidate"] == "vxn_relief"

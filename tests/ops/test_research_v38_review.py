from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path("docs/progress/phase-2-research-v38-development-results.json")


def test_v38_development_results_structure_and_passes() -> None:
    payload = json.loads(RESULTS_PATH.read_text())
    assert payload["schema_version"] == "research.v38.development_results.v1"
    candidates = payload["candidates"]
    assert "cll_expansion" in candidates
    assert "pput_expansion" in candidates
    assert "vpd_expansion" in candidates
    assert candidates["cll_expansion"]["pass_gates"] is True
    assert candidates["pput_expansion"]["pass_gates"] is True
    assert candidates["vpd_expansion"]["pass_gates"] is False
    assert set(payload["passing_candidates"]) == {"cll_expansion", "pput_expansion"}
    assert payload["best_candidate"] == "cll_expansion"

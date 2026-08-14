from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path("docs/progress/phase-2-research-v39-development-results.json")


def test_v39_development_results_structure_and_passes() -> None:
    payload = json.loads(RESULTS_PATH.read_text())
    assert payload["schema_version"] == "research.v39.development_results.v1"
    candidates = payload["candidates"]
    assert "lovol_expansion" in candidates
    assert "putd_expansion" in candidates
    assert "cndr_expansion" in candidates
    assert candidates["lovol_expansion"]["pass_gates"] is True
    assert candidates["putd_expansion"]["pass_gates"] is False
    assert candidates["cndr_expansion"]["pass_gates"] is False
    assert set(payload["passing_candidates"]) == {"lovol_expansion"}
    assert payload["best_candidate"] == "lovol_expansion"

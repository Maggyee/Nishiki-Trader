from __future__ import annotations

import json

from apps.ops.research_program_review import build_research_program_review


def test_program_review_triggers_stop_when_every_candidate_is_rejected(tmp_path) -> None:
    evidence = tmp_path / "evidence.md"
    evidence.write_text("# evidence\n")
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "research.candidate.registry.v1",
                "candidates": [
                    {
                        "family": "test",
                        "source": "rule_test_v1",
                        "model_version": "model-v1",
                        "classification": "reject",
                        "base_net_pnl": -1.0,
                        "stress_net_pnl": -2.0,
                        "closed_positions": 10,
                        "evidence_path": "evidence.md",
                        "failure_reasons": ["base_negative"],
                    }
                ],
            }
        )
    )

    result = build_research_program_review(registry, repo_root=tmp_path)

    assert result["candidate_count"] == 1
    assert result["stop_rule"]["triggered"] is True
    assert result["recommendation"] == "pause_new_candidate_generation_until_independent_evidence"

from __future__ import annotations

from pathlib import Path

from apps.ops.research_v40_shadow_daily import run_daily_shadow


def test_research_v40_shadow_daily_structure(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    factors_dir = tmp_path / "factors"
    signal_store = tmp_path / "signals.db"
    state_file = tmp_path / "state.json"
    status_file = tmp_path / "status.json"

    result = run_daily_shadow(
        raw_dir=raw_dir,
        factors_dir=factors_dir,
        signal_store_path=signal_store,
        state_file=state_file,
        status_file=status_file,
    )
    assert result["schema_version"] == "research.protocol.v40.paper_shadow_status.v1"
    assert result["strategy"] == "vxn_relief"
    assert result["health"] == "HEALTHY"
    assert result["total_days_collected"] == 1
    assert status_file.exists()
    assert state_file.exists()
    assert signal_store.exists()

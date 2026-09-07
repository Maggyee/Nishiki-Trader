from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apps.ops.research_v42_shadow_daily import run_daily_shadow


def test_research_v42_shadow_daily_structure(tmp_path: Path, monkeypatch) -> None:
    from apps.ops import research_v42_shadow_daily as module
    start = datetime.now(UTC).date() - timedelta(days=601)
    raw = "DATE,CLOSE\n" + "\n".join(f"{start + timedelta(days=i)},20" for i in range(601))
    envelope = {"payload_raw_base64": base64.b64encode(raw.encode()).decode(),
                "vintage_id": "fixture", "snapshot_sha256": "sha256:" + "a" * 64}
    monkeypatch.setattr(module, "fetch_and_snapshot_vix6m", lambda *a, **k: (tmp_path / "snapshot.json", envelope))
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
    assert result["schema_version"] == "research.protocol.v42.paper_shadow_status.v1"
    assert result["strategy"] == "vix6m_relief"
    assert result["health"] == "HEALTHY"
    assert result["total_days_collected"] == 1
    assert status_file.exists()
    assert state_file.exists()
    assert signal_store.exists()

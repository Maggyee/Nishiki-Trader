from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v13_snapshot import collect_snapshot, verify_snapshot


def _history(*, omit_day: date | None = None) -> bytes:
    rows = []
    current = date(2019, 11, 1)
    value = 100.0
    while current <= date(2022, 12, 31):
        if current != omit_day:
            rows.append(
                {
                    "asset": "btc",
                    "time": f"{current.isoformat()}T00:00:00.000000000Z",
                    "AdrActCnt": str(value),
                    "TxTfrCnt": str(value * 2),
                    "CapMVRVCur": "1.1",
                }
            )
        current += timedelta(days=1)
        value += 1.0
    return json.dumps({"data": rows}).encode()


def test_v13_snapshot_round_trip(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        output_dir=tmp_path,
        fetch=lambda _: _history(),
        now=datetime(2026, 8, 12, 3, tzinfo=UTC),
    )

    assert result["valid"] is True
    assert result["audit"]["complete_daily_grid"] is True
    assert result["audit"]["row_count"] == 1157
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]


def test_v13_snapshot_rejects_incomplete_grid(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="grid is incomplete"):
        collect_snapshot(
            output_dir=tmp_path,
            fetch=lambda _: _history(omit_day=date(2021, 1, 1)),
        )


def test_v13_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=lambda _: _history())
    payload = json.loads(path.read_text())
    payload["audit"]["row_count"] += 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

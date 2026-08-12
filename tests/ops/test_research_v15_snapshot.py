from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v15_snapshot import START, collect_snapshot, verify_snapshot


def _history(*, omit_day: date | None = None) -> bytes:
    lines = ["observation_date,DFII10,T10Y2Y,DGS10"]
    current = START
    value = 1.0
    while current <= date(2022, 12, 31):
        if current.weekday() < 5 and current != omit_day:
            lines.append(f"{current.isoformat()},{value},{value - 0.5},{value + 1.0}")
            value += 0.001
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


def test_v15_snapshot_round_trip(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        output_dir=tmp_path,
        fetch=lambda _: _history(),
        now=datetime(2026, 8, 12, 9, 5, tzinfo=UTC),
    )

    assert result["valid"] is True
    assert result["audit"]["complete_weekday_grid"] is True
    assert result["audit"]["complete_joint_row_count"] >= 780
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]


def test_v15_snapshot_rejects_incomplete_weekday_grid(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="weekday grid"):
        collect_snapshot(
            output_dir=tmp_path,
            fetch=lambda _: _history(omit_day=date(2021, 1, 4)),
        )


def test_v15_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=lambda _: _history())
    payload = json.loads(path.read_text())
    payload["audit"]["complete_joint_row_count"] -= 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

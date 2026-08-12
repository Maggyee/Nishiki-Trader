from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

from apps.ops.research_v16_confirmation_snapshot import collect_snapshot, verify_snapshot


def _csv(year: int, *, omit_days: set[date] | None = None) -> bytes:
    lines = ["Date,2 Yr,10 Yr"]
    current = date(year, 1, 1)
    value = 3.0
    while current.year == year:
        if current.weekday() < 5 and current not in (omit_days or set()):
            lines.append(f"{current.strftime('%m/%d/%Y')},{value},{value + 0.5}")
            value += 0.001
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


def _fetch(url: str) -> bytes:
    year = int(urlparse(url).path.split("/")[-2])
    return _csv(year)


def test_v16_confirmation_snapshot_round_trip(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        output_dir=tmp_path,
        fetch=_fetch,
        now=datetime(2026, 8, 12, 9, 25, tzinfo=UTC),
    )
    assert result["valid"] is True
    assert result["audit"]["row_count"] >= 740
    assert result["audit"]["forward_fill_used"] is False
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]


def test_v16_confirmation_snapshot_rejects_large_gap(tmp_path: Path) -> None:
    omitted = {
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    }

    def fetch(url: str) -> bytes:
        year = int(urlparse(url).path.split("/")[-2])
        return _csv(year, omit_days=omitted if year == 2024 else None)

    with pytest.raises(ValueError, match="gap exceeds"):
        collect_snapshot(output_dir=tmp_path, fetch=fetch)


def test_v16_confirmation_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=_fetch)
    payload = json.loads(path.read_text())
    payload["audit"]["row_count"] -= 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

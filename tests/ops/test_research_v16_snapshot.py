from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from apps.ops.research_v16_snapshot import collect_snapshot, verify_snapshot


def _csv(year: int, route: str, *, omit_day: date | None = None) -> bytes:
    lines = ["Date,2 Yr,10 Yr"] if route == "nominal" else ["Date,10 YR"]
    current = date(year, 1, 1)
    value = 1.0
    while current.year == year:
        if current.weekday() < 5 and current != omit_day:
            if route == "nominal":
                lines.append(f"{current.strftime('%m/%d/%Y')},{value},{value + 0.5}")
            else:
                lines.append(f"{current.strftime('%m/%d/%Y')},{value - 0.25}")
            value += 0.001
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


def _fetch(url: str, *, omit_day: date | None = None) -> bytes:
    parsed = urlparse(url)
    year = int(parsed.path.split("/")[-2])
    route = (
        "real"
        if parse_qs(parsed.query)["type"][0] == "daily_treasury_real_yield_curve"
        else "nominal"
    )
    return _csv(year, route, omit_day=omit_day)


def test_v16_snapshot_round_trip(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        output_dir=tmp_path,
        fetch=_fetch,
        now=datetime(2026, 8, 12, 9, 10, tzinfo=UTC),
    )

    assert result["valid"] is True
    assert result["audit"]["joint_row_count"] >= 780
    assert result["audit"]["forward_fill_used"] is False
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]


def test_v16_snapshot_rejects_large_joint_gap(tmp_path: Path) -> None:
    omitted = {date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 6)}

    def fetch(url: str) -> bytes:
        parsed = urlparse(url)
        year = int(parsed.path.split("/")[-2])
        route = (
            "real"
            if parse_qs(parsed.query)["type"][0] == "daily_treasury_real_yield_curve"
            else "nominal"
        )
        raw = _csv(year, route)
        if year != 2021:
            return raw
        lines = raw.decode().splitlines()
        return ("\n".join(line for line in lines if not any(day.strftime('%m/%d/%Y') in line for day in omitted)) + "\n").encode()

    with pytest.raises(ValueError, match="gap above five days"):
        collect_snapshot(output_dir=tmp_path, fetch=fetch)


def test_v16_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=_fetch)
    payload = json.loads(path.read_text())
    payload["audit"]["joint_row_count"] -= 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

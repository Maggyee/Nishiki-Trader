from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from apps.ops.research_v21_snapshot import (
    collect_snapshot,
    verify_snapshot,
    write_factor_csv,
)


def _series_csv(series_id: str, *, omit: set[date] | None = None) -> bytes:
    omitted = omit or set()
    lines = [f"observation_date,{series_id}"]
    current = date(2019, 10, 1)
    index = 0
    while current <= date(2022, 12, 31):
        include = series_id == "RRPONTSYD" or current.weekday() == 2
        if include and current not in omitted:
            if series_id == "WALCL":
                value = 7_000_000 + index * 100
            elif series_id == "WDTGAL":
                value = 500_000 + index * 10
            else:
                value = 1000 + index * 0.1
            lines.append(f"{current.isoformat()},{value}")
            index += 1
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


def _fetch(url: str) -> bytes:
    series_id = parse_qs(urlparse(url).query)["id"][0]
    return _series_csv(series_id)


def test_v21_snapshot_round_trip_and_factor(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        output_dir=tmp_path,
        fetch=_fetch,
        now=datetime(2026, 8, 13, 5, 0, tzinfo=UTC),
    )
    factor_path = tmp_path / "net-liquidity.csv"
    factor = write_factor_csv(path, factor_path)

    assert result["valid"] is True
    assert result["audit"]["development_common_row_count"] >= 150
    assert result["audit"]["forward_fill_used"] is False
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]
    assert factor["row_count"] > result["audit"]["development_common_row_count"]
    assert factor["sha256"].startswith("sha256:")


def test_v21_snapshot_rejects_large_common_gap(tmp_path: Path) -> None:
    omitted = {
        date(2021, 1, 6),
        date(2021, 1, 13),
        date(2021, 1, 20),
    }

    def fetch(url: str) -> bytes:
        series_id = parse_qs(urlparse(url).query)["id"][0]
        return _series_csv(series_id, omit=omitted if series_id == "WALCL" else None)

    with pytest.raises(ValueError, match="gap exceeds fourteen days"):
        collect_snapshot(output_dir=tmp_path, fetch=fetch)


def test_v21_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=_fetch)
    payload = json.loads(path.read_text())
    payload["audit"]["development_common_row_count"] -= 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

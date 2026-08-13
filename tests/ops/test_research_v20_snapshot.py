from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v20_snapshot import (
    REQUIRED_SERIES,
    collect_snapshot,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)


def _history(*, omitted: set[date] | None = None) -> bytes:
    series = {key: {"name": key.replace("_", " "), "data": []} for key in REQUIRED_SERIES}
    current = date(2019, 11, 1)
    index = 0
    while current <= date(2022, 12, 31):
        if current.weekday() < 5 and current not in (omitted or set()):
            timestamp = int(datetime.combine(current, datetime.min.time(), UTC).timestamp() * 1000)
            for offset, key in enumerate(REQUIRED_SERIES):
                series[key]["data"].append([timestamp, index / 100 + offset - 2])
            index += 1
        current += timedelta(days=1)
    return json.dumps(series, separators=(",", ":")).encode()


def test_v20_dry_run_has_no_network_or_write() -> None:
    plan = request_plan()
    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["values_reported"] is False
    assert plan["url"].endswith("/financial-stress-index/data/fsi.json")


def test_v20_snapshot_round_trip_and_factor_lag(tmp_path: Path) -> None:
    snapshot_path, result = collect_snapshot(
        output_dir=tmp_path / "raw",
        fetch=lambda _: _history(),
        now=datetime(2026, 8, 13, 3, 30, tzinfo=UTC),
    )
    assert result["valid"] is True
    assert result["audit"]["development_row_count"] > 700
    assert result["audit"]["forward_fill_used"] is False
    assert verify_snapshot(snapshot_path)["snapshot_sha256"] == result["snapshot_sha256"]

    factor_path = tmp_path / "fsi.csv"
    factor = write_factor_csv(snapshot_path, factor_path)
    assert factor["row_count"] > 700
    with factor_path.open() as handle:
        first = next(csv.DictReader(handle))
    assert first["available_at"].startswith("2019-11-06T00:00:00")


def test_v20_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=lambda _: _history())
    payload = json.loads(path.read_text())
    payload["audit"]["development_row_count"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)


def test_v20_snapshot_rejects_non_common_timestamps(tmp_path: Path) -> None:
    payload = json.loads(_history())
    payload["Credit"]["data"].pop(100)
    with pytest.raises(ValueError, match="do not share"):
        collect_snapshot(
            output_dir=tmp_path,
            fetch=lambda _: json.dumps(payload).encode(),
        )


def test_v20_snapshot_rejects_large_gap(tmp_path: Path) -> None:
    omitted = {date(2021, 6, day) for day in range(7, 15)}
    with pytest.raises(ValueError, match="gap exceeds"):
        collect_snapshot(
            output_dir=tmp_path,
            fetch=lambda _: _history(omitted=omitted),
        )

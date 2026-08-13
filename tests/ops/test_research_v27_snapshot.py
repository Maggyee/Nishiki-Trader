from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v27_snapshot import (
    collect_snapshot,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)


def _history(*, extra_2023: bool = False) -> bytes:
    items: list[list[object]] = []
    current = date(2019, 11, 1)
    last = date(2023, 1, 1) if extra_2023 else date(2022, 12, 31)
    value = 1_000_000.0
    while current <= last:
        midnight = datetime(current.year, current.month, current.day, tzinfo=UTC)
        items.append([int(midnight.timestamp()), value])
        value += 1_000.0
        current += timedelta(days=1)
    return json.dumps({"totalDataChart": items}).encode()


def test_v27_dry_run_has_no_network_or_write() -> None:
    plan = request_plan("daily_revenue")

    assert plan["network_accessed"] is False
    assert plan["values_reported"] is False
    assert "dataType=dailyRevenue" in plan["url"]


def test_v27_snapshot_round_trip_and_factor(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        "daily_fees",
        output_dir=tmp_path / "raw",
        fetch=lambda _: _history(extra_2023=True),
        now=datetime(2026, 8, 13, 8, 20, tzinfo=UTC),
    )
    factor_path = tmp_path / "fees.csv"
    factor = write_factor_csv(path, factor_path)

    assert result["valid"] is True
    assert result["audit"]["development_row_count"] > 700
    assert result["audit"]["trailing_rows_ignored"] == 1
    assert result["audit"]["confirmation_values_used"] is False
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]
    with factor_path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["available_at"].startswith("2019-11-03T00:00:00")
    assert rows[-1]["observation_date"] == "2022-12-31"
    assert "amount" in rows[0]
    assert factor["sha256"].startswith("sha256:")


def test_v27_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "daily_holders_revenue", output_dir=tmp_path, fetch=lambda _: _history()
    )
    payload = json.loads(path.read_text())
    payload["audit"]["development_row_count"] -= 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

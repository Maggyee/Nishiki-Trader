from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apps.ops.research_protocol_v24 import ALLOWED_CLASSIFICATIONS
from apps.ops.research_v24_snapshot import (
    collect_snapshot,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)

NY = ZoneInfo("America/New_York")


def _history(*, extra_2023: bool = False) -> bytes:
    items: list[dict[str, object]] = []
    current = date(2019, 11, 1)
    last = date(2023, 1, 1) if extra_2023 else date(2022, 12, 31)
    index = 0
    while current <= last:
        noon = datetime(current.year, current.month, current.day, 12, 0, tzinfo=NY)
        items.append(
            {
                "value": str(index % 101),
                "value_classification": ALLOWED_CLASSIFICATIONS[index % 5],
                "timestamp": str(int(noon.timestamp())),
            }
        )
        index += 1
        current += timedelta(days=1)
    items.reverse()
    return json.dumps({"name": "Fear and Greed Index", "data": items, "metadata": {"error": None}}).encode()


def test_v24_dry_run_has_no_network_or_write() -> None:
    plan = request_plan()

    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["values_reported"] is False
    assert plan["url"] == "https://api.alternative.me/fng/?limit=0&format=json"


def test_v24_snapshot_round_trip_and_factor(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        output_dir=tmp_path / "raw",
        fetch=lambda _: _history(extra_2023=True),
        now=datetime(2026, 8, 13, 6, 0, tzinfo=UTC),
    )
    factor_path = tmp_path / "fng.csv"
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
    assert factor["sha256"].startswith("sha256:")


def test_v24_snapshot_rejects_unknown_classification(tmp_path: Path) -> None:
    payload = json.loads(_history())
    payload["data"][0]["value_classification"] = "Panic"
    with pytest.raises(ValueError, match="not locked"):
        collect_snapshot(output_dir=tmp_path, fetch=lambda _: json.dumps(payload).encode())


def test_v24_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(output_dir=tmp_path, fetch=lambda _: _history())
    payload = json.loads(path.read_text())
    payload["audit"]["development_row_count"] -= 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

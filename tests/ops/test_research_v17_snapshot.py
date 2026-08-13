from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v17_snapshot import (
    collect_snapshot,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)


def _history(*, kind: str = "vxeem") -> bytes:
    header = "DATE,OPEN,HIGH,LOW,CLOSE" if kind == "vxn" else f"DATE,{kind.upper()}"
    rows = [header]
    current = date(2019, 11, 1)
    value = 20.0
    while current <= date(2022, 12, 31):
        if current.weekday() < 5:
            if kind == "vxn":
                rows.append(
                    f"{current.strftime('%m/%d/%Y')},{value:.2f},{value + 1:.2f},{value - 1:.2f},{value + 0.25:.2f}"
                )
            else:
                rows.append(f"{current.strftime('%m/%d/%Y')},{value + 0.25:.2f}")
            value += 0.01
        current += timedelta(days=1)
    return ("\n".join(rows) + "\n").encode()


def test_v17_dry_run_has_no_network_or_write() -> None:
    plan = request_plan("vxeem")
    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["boundaries"]["credentials_loaded"] is False
    assert plan["url"].endswith("VXEEM_History.csv")


def test_v17_snapshot_round_trip_and_factor_lag(tmp_path: Path) -> None:
    snapshot_path, result = collect_snapshot(
        "vxefa",
        output_dir=tmp_path / "raw",
        fetch=lambda _: _history(kind="vxefa"),
        now=datetime(2026, 8, 13, 2, 30, tzinfo=UTC),
    )
    assert result["valid"] is True
    assert result["audit"]["reserve_row_count"] > 700
    assert result["audit"]["forward_fill_used"] is False
    assert verify_snapshot(snapshot_path)["snapshot_sha256"] == result["snapshot_sha256"]

    factor_path = tmp_path / "vxefa.csv"
    factor = write_factor_csv(snapshot_path, factor_path)
    assert factor["row_count"] > 700
    with factor_path.open() as handle:
        first = next(csv.DictReader(handle))
    assert first["available_at"].startswith("2019-11-02T00:00:00")


def test_v17_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "vxn",
        output_dir=tmp_path,
        fetch=lambda _: _history(kind="vxn"),
        now=datetime(2026, 8, 13, 2, 30, tzinfo=UTC),
    )
    payload = json.loads(path.read_text())
    payload["audit"]["reserve_row_count"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)


def test_v17_snapshot_rejects_wrong_header(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="columns"):
        collect_snapshot(
            "vxeem",
            output_dir=tmp_path,
            fetch=lambda _: b"date,close\n2020-01-01,20\n",
            now=datetime(2026, 8, 13, 2, 30, tzinfo=UTC),
        )

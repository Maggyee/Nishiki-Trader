from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v33_snapshot import (
    collect_snapshot,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)


def _history(kind: str, *, schema: str = "scalar") -> bytes:
    index = {"cor3m": "COR3M", "cor6m": "COR6M", "cor1y": "COR1Y"}[kind]
    lines = [f"DATE,{index}"] if schema == "scalar" else ["DATE,OPEN,HIGH,LOW,CLOSE"]
    current = date(2019, 11, 1)
    value = 50.0
    while current <= date(2022, 12, 31):
        if current.weekday() < 5:
            if schema == "scalar":
                lines.append(f"{current.strftime('%m/%d/%Y')},{value:.4f}")
            else:
                lines.append(
                    f"{current.strftime('%m/%d/%Y')},{value:.4f},{value + 1:.4f},{value - 1:.4f},{value + 0.25:.4f}"
                )
            value += 0.01
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


def test_v33_dry_run_has_no_network_or_write() -> None:
    plan = request_plan("cor3m")

    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["url"].endswith("COR3M_History.csv")


@pytest.mark.parametrize(("kind", "schema"), [("cor3m", "scalar"), ("cor6m", "ohlc")])
def test_v33_snapshot_round_trip_and_factor(tmp_path: Path, kind: str, schema: str) -> None:
    path, result = collect_snapshot(
        kind,
        output_dir=tmp_path / "raw",
        fetch=lambda _: _history(kind, schema=schema),
        now=datetime(2026, 8, 14, 1, 35, tzinfo=UTC),
    )
    factor_path = tmp_path / f"{kind}.csv"
    factor = write_factor_csv(path, factor_path)

    assert result["valid"] is True
    assert result["audit"]["development_row_count"] > 700
    assert result["audit"]["schema"] == schema
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]
    assert factor["sha256"].startswith("sha256:")
    with factor_path.open() as handle:
        first = next(csv.DictReader(handle))
    assert first["available_at"].startswith("2019-11-02T00:00:00")


def test_v33_snapshot_rejects_unknown_header(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="locked schemas"):
        collect_snapshot(
            "cor1y",
            output_dir=tmp_path,
            fetch=lambda _: b"date,close\n2020-01-01,20\n",
        )


def test_v33_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot("cor3m", output_dir=tmp_path, fetch=lambda _: _history("cor3m"))
    payload = json.loads(path.read_text())
    payload["audit"]["development_row_count"] -= 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

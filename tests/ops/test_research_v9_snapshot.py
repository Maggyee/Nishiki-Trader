from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v9_snapshot import collect_snapshot, request_plan, verify_snapshot


def _history(*, ohlc: bool = False) -> bytes:
    rows = ["DATE,OPEN,HIGH,LOW,CLOSE" if ohlc else "DATE,VALUE"]
    current = date(2019, 12, 1)
    value = 20.0
    while current <= date(2023, 1, 15):
        if current.weekday() < 5:
            if ohlc:
                rows.append(
                    f"{current:%m/%d/%Y},{value:.2f},{value + 1:.2f},{value - 1:.2f},{value + 0.2:.2f}"
                )
            else:
                rows.append(f"{current:%m/%d/%Y},{value:.2f}")
            value += 0.01
        current += timedelta(days=1)
    return ("\n".join(rows) + "\n").encode()


def test_v9_request_plan_does_not_access_network_or_data() -> None:
    plan = request_plan("vix9d")

    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["qualification_only"] is True
    assert plan["boundaries"]["pnl_calculated"] is False


@pytest.mark.parametrize(("kind", "ohlc"), [("vix9d", True), ("vvix", False)])
def test_v9_snapshot_round_trip_records_schema_not_values(
    tmp_path: Path, kind: str, ohlc: bool
) -> None:
    path, result = collect_snapshot(
        kind,
        output_dir=tmp_path,
        fetch=lambda _: _history(ohlc=ohlc),
        now=datetime(2026, 8, 11, 10, tzinfo=UTC),
    )

    assert result["valid"] is True
    assert result["audit"]["development_coverage"] is True
    assert "values" not in result["audit"]
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]


def test_v9_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "vvix",
        output_dir=tmp_path,
        fetch=lambda _: _history(),
        now=datetime(2026, 8, 11, 10, tzinfo=UTC),
    )
    payload = json.loads(path.read_text())
    payload["audit"]["row_count"] += 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)


def test_v9_snapshot_rejects_incomplete_reserve(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only"):
        collect_snapshot(
            "vix9d",
            output_dir=tmp_path,
            fetch=lambda _: b"DATE,VIX9D\n01/02/2020,12.0\n",
            now=datetime(2026, 8, 11, 10, tzinfo=UTC),
        )

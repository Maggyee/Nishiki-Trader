from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v10_snapshot import collect_snapshot, request_plan, verify_snapshot


def _history(kind: str, *, include_status_time: bool = True) -> bytes:
    if kind == "stablecoin_supply":
        assets, metric = ("usdt", "usdc"), "SplyCur"
    elif kind == "hashrate":
        assets, metric = ("btc",), "HashRate"
    else:
        assets, metric = ("btc",), "FeeTotNtv"
    rows = []
    current = date(2019, 11, 1)
    value = 100.0
    while current <= date(2022, 12, 31):
        for asset in assets:
            row = {
                "asset": asset,
                "time": f"{current.isoformat()}T00:00:00.000000000Z",
                metric: str(value),
            }
            if include_status_time:
                row[f"{metric}-status"] = "reviewed"
                row[f"{metric}-status-time"] = (
                    f"{(current + timedelta(days=1)).isoformat()}T12:00:00Z"
                )
            rows.append(row)
            value += 1.0
        current += timedelta(days=1)
    return json.dumps({"data": rows}).encode()


def test_v10_request_plan_is_zero_access() -> None:
    plan = request_plan("hashrate")

    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["qualification_only"] is True
    assert plan["boundaries"]["values_reported"] is False


@pytest.mark.parametrize("kind", ["hashrate", "stablecoin_supply", "btc_fees"])
def test_v10_snapshot_round_trip_records_point_in_time_audit(tmp_path: Path, kind: str) -> None:
    path, result = collect_snapshot(
        kind,
        output_dir=tmp_path,
        fetch=lambda _: _history(kind),
        now=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )

    assert result["valid"] is True
    assert result["audit"]["development_coverage"] is True
    assert result["audit"]["all_rows_point_in_time_eligible"] is True
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]


def test_v10_snapshot_fails_point_in_time_audit_without_status_time(tmp_path: Path) -> None:
    _, result = collect_snapshot(
        "btc_fees",
        output_dir=tmp_path,
        fetch=lambda _: _history("btc_fees", include_status_time=False),
        now=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )

    assert result["audit"]["all_rows_point_in_time_eligible"] is False


def test_v10_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "hashrate",
        output_dir=tmp_path,
        fetch=lambda _: _history("hashrate"),
        now=datetime(2026, 8, 11, 12, tzinfo=UTC),
    )
    payload = json.loads(path.read_text())
    payload["audit"]["row_count"] += 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

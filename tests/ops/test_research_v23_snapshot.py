from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v23_snapshot import (
    collect_snapshot,
    parse_and_audit_json,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)

ARTICLES = {"bitcoin": "Bitcoin", "ethereum": "Ethereum", "cryptocurrency": "Cryptocurrency"}


def _history(kind: str, *, extra: list[dict[str, object]] | None = None) -> bytes:
    article = ARTICLES[kind]
    items: list[dict[str, object]] = []
    current = date(2019, 11, 1)
    views = 10_000
    while current <= date(2022, 12, 31):
        items.append(
            {
                "project": "en.wikipedia",
                "article": article,
                "granularity": "daily",
                "timestamp": current.strftime("%Y%m%d") + "00",
                "access": "all-access",
                "agent": "user",
                "views": views,
            }
        )
        views += 1
        current += timedelta(days=1)
    if extra:
        items.extend(extra)
    return json.dumps({"items": items}).encode()


def test_v23_dry_run_has_no_network_or_write() -> None:
    plan = request_plan("bitcoin")

    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["values_reported"] is False
    assert "/Bitcoin/daily/2019110100/2022123100" in plan["url"]
    assert "2023" not in plan["url"]


def test_v23_snapshot_round_trip_and_factor(tmp_path: Path) -> None:
    path, result = collect_snapshot(
        "ethereum",
        output_dir=tmp_path / "raw",
        fetch=lambda _: _history("ethereum"),
        now=datetime(2026, 8, 13, 5, 30, tzinfo=UTC),
    )
    factor_path = tmp_path / "ethereum.csv"
    factor = write_factor_csv(path, factor_path)

    assert result["valid"] is True
    assert result["audit"]["development_row_count"] > 700
    assert result["audit"]["confirmation_opened"] is False
    assert verify_snapshot(path)["snapshot_sha256"] == result["snapshot_sha256"]
    assert factor["sha256"].startswith("sha256:")
    with factor_path.open() as handle:
        first = next(csv.DictReader(handle))
    assert first["available_at"].startswith("2019-11-03T00:00:00")


def test_v23_snapshot_rejects_confirmation_timestamp() -> None:
    extra = [
        {
            "project": "en.wikipedia",
            "article": "Bitcoin",
            "granularity": "daily",
            "timestamp": "2023010100",
            "access": "all-access",
            "agent": "user",
            "views": 1,
        }
    ]
    with pytest.raises(ValueError, match="opened confirmation"):
        parse_and_audit_json("bitcoin", _history("bitcoin", extra=extra))


def test_v23_snapshot_rejects_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "cryptocurrency",
        output_dir=tmp_path,
        fetch=lambda _: _history("cryptocurrency"),
    )
    payload = json.loads(path.read_text())
    payload["audit"]["development_row_count"] -= 1
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(path)

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v2_snapshot import collect_snapshot
from apps.ops.research_v2_snapshot_review import review_snapshots
from tests.ops.test_research_v2_snapshot import _basis_payloads, _bytes, _option_payload

START = datetime(2026, 7, 11, 8, 0, tzinfo=UTC)


def _basis_fetch(url: str) -> bytes:
    payloads = _basis_payloads()
    if "exchangeInfo" in url:
        return payloads["exchangeInfo"]
    if "NEXT_QUARTER" in url:
        return payloads["NEXT_QUARTER"]
    return payloads["CURRENT_QUARTER"]


def _pair(root: Path, now: datetime) -> list[Path]:
    option, _ = collect_snapshot(
        "options",
        output_dir=root / "options",
        fetch=lambda _: _bytes(_option_payload()),
        now=now,
    )
    basis, _ = collect_snapshot(
        "basis",
        output_dir=root / "basis",
        fetch=_basis_fetch,
        now=now,
    )
    return [option, basis]


def test_single_paired_day_is_honestly_insufficient(tmp_path: Path) -> None:
    review = review_snapshots(_pair(tmp_path, START))

    assert review["status"] == "collecting_insufficient_days"
    assert review["paired_day_count"] == 1
    assert review["blockers"] == []
    assert review["recommendation"] == "continue_daily_snapshot_collection"
    assert set(review["boundaries"].values()) == {False}


def test_seven_exact_paired_days_pass_coverage_qualification(tmp_path: Path) -> None:
    paths = []
    for offset in range(7):
        paths.extend(_pair(tmp_path / str(offset), START + timedelta(days=offset)))

    review = review_snapshots(paths)

    assert review["status"] == "qualification_coverage_pass"
    assert review["paired_day_count"] == 7
    assert review["coverage"]["options"]["missing_dates"] == []
    assert review["coverage"]["basis"]["duplicate_dates"] == []


def test_internal_gap_blocks_even_when_both_kinds_match(tmp_path: Path) -> None:
    paths = [
        *_pair(tmp_path / "day0", START),
        *_pair(tmp_path / "day2", START + timedelta(days=2)),
    ]

    review = review_snapshots(paths)

    assert review["status"] == "blocked_invalid_coverage"
    assert "internal_gaps:options" in review["blockers"]
    assert "internal_gaps:basis" in review["blockers"]
    assert review["coverage"]["options"]["missing_dates"] == ["2026-07-12"]


def test_duplicate_or_unpaired_day_blocks_coverage(tmp_path: Path) -> None:
    paths = _pair(tmp_path / "first", START)
    duplicate, _ = collect_snapshot(
        "options",
        output_dir=tmp_path / "duplicate",
        fetch=lambda _: _bytes(_option_payload()),
        now=START + timedelta(minutes=5),
    )

    review = review_snapshots([*paths, duplicate])

    assert review["status"] == "blocked_invalid_coverage"
    assert "duplicate_days:options" in review["blockers"]
    assert review["coverage"]["options"]["snapshot_count"] == 2


def test_snapshot_tampering_fails_before_coverage_is_computed(tmp_path: Path) -> None:
    paths = _pair(tmp_path, START)
    payload = json.loads(paths[0].read_text())
    payload["audit"]["row_count"] += 1
    paths[0].write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit summary"):
        review_snapshots(paths)

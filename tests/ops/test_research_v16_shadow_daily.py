from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v16_shadow_daily import (
    collect_daily,
    parse_and_audit_treasury,
    parse_treasury_csv,
    summarize_attempts,
    verify_snapshot,
)


def _treasury_csv(year: int, *, through: date, revision: float = 0.0) -> bytes:
    rows = ["Date,10 YR"]
    current = date(year, 1, 1)
    index = 0
    value = 3.0
    while current <= through:
        change = 0.01 if (index // 12) % 2 == 0 else 0.18
        value += change
        if revision and index == 10:
            value += revision
        rows.append(f"{current.strftime('%m/%d/%Y')},{value:.6f}")
        current += timedelta(days=1)
        index += 1
    return ("\n".join(rows) + "\n").encode()


def _btc_history(observed_at: datetime) -> bytes:
    latest_closed = int(observed_at.timestamp() // 3600) * 3_600_000 - 3_600_000
    first = latest_closed - 166 * 3_600_000
    rows = []
    for index in range(168):
        open_ms = first + index * 3_600_000
        rows.append(
            [open_ms, "100", "102", "99", "101", "10", open_ms + 3_600_000 - 1]
        )
    return json.dumps(rows).encode()


def test_treasury_parser_enforces_target_and_unique_dates() -> None:
    raw = _treasury_csv(2026, through=date(2026, 8, 12))

    rows = parse_treasury_csv(raw, year=2026, target_day=date(2026, 8, 10))

    assert rows[-1]["observation_date"] == "2026-08-10"
    assert all(row["observation_date"] <= "2026-08-10" for row in rows)
    duplicated = raw + b"08/10/2026,4.0\n"
    with pytest.raises(ValueError, match="unique"):
        parse_treasury_csv(
            duplicated, year=2026, target_day=date(2026, 8, 10)
        )


def test_treasury_audit_uses_consecutive_previous_and_current_years() -> None:
    payloads = [
        (
            {"year": 2025},
            _treasury_csv(2025, through=date(2025, 12, 31)),
        ),
        (
            {"year": 2026},
            _treasury_csv(2026, through=date(2026, 8, 12)),
        ),
    ]

    rows, audit = parse_and_audit_treasury(
        payloads, target_day=date(2026, 8, 10)
    )

    assert audit["last_date"] == "2026-08-10"
    assert audit["maximum_calendar_gap_days"] == 1
    assert audit["forward_fill_used"] is False
    assert len(rows) == audit["row_count"]


def test_summary_uses_or_gate_but_never_auto_authorizes_simulated() -> None:
    records = [
        {
            "collection_date": f"2026-08-{day:02d}",
            "qualified_day": True,
            "new_forward_signal_ids": [],
            "blockers": [],
        }
        for day in range(12, 19)
    ]

    status = summarize_attempts(records, gate_days=7, gate_signals=50)

    assert status["threshold_met"] is True
    assert status["review_eligible"] is True
    assert status["automatic_paper_simulated_authorization"] is False


def test_summary_preserves_any_prior_anomaly() -> None:
    records = [
        {
            "collection_date": "2026-08-12",
            "qualified_day": False,
            "new_forward_signal_ids": [],
            "blockers": ["treasury_historical_revision:1"],
        },
        {
            "collection_date": "2026-08-13",
            "qualified_day": True,
            "new_forward_signal_ids": [f"s{index}" for index in range(50)],
            "blockers": [],
        },
    ]

    status = summarize_attempts(records, gate_days=7, gate_signals=50)

    assert status["threshold_met"] is True
    assert status["review_eligible"] is False
    assert status["anomaly_blockers"] == ["treasury_historical_revision:1"]


def test_daily_collection_qualifies_without_touching_execution(tmp_path: Path) -> None:
    observed = datetime(2026, 8, 12, 12, 30, tzinfo=UTC)

    def fetch(url: str) -> bytes:
        if "/2025/" in url:
            return _treasury_csv(2025, through=date(2025, 12, 31))
        if "/2026/" in url:
            return _treasury_csv(2026, through=date(2026, 8, 12))
        return _btc_history(observed)

    result = collect_daily(
        repo_root=Path.cwd(),
        data_root=tmp_path,
        fetch=fetch,
        now=observed,
        git_state={
            "commit": "a" * 40,
            "branch": "main",
            "dirty": False,
            "origin_main_contains_commit": True,
        },
    )

    record = result["record"]
    assert record["qualified_day"] is True
    assert record["treasury"]["last_date"] == "2026-08-10"
    assert record["treasury"]["eligible_age_calendar_days"] == 0
    assert record["btc"]["closed_bar_rows"] == 167
    assert record["signals"]["new_forward"] == 0
    assert record["boundaries"]["orders_submitted"] is False
    assert record["boundaries"]["source_policy_mutated"] is False
    assert result["status"]["qualified_day_count"] == 1
    assert result["status"]["paper_simulated_status"] == "not_authorized"
    assert result["status"]["scheduler_installed"] is False

    snapshot_path = Path(record["treasury"]["snapshot_path"])
    assert verify_snapshot(snapshot_path)["valid"] is True
    payload = json.loads(snapshot_path.read_text())
    payload["audit"]["row_count"] += 1
    snapshot_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="audit mismatch"):
        verify_snapshot(snapshot_path)

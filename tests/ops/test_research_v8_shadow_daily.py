from datetime import UTC, datetime

import pytest

from apps.ops.research_v8_shadow_daily import (
    _merge_observations,
    _parse_btc_bars,
    summarize_attempts,
)


def _bar(open_ms: int, close: str = "101") -> list[object]:
    return [open_ms, "100", "102", "99", close, "10", open_ms + 3_600_000 - 1]


def test_parse_btc_bars_excludes_open_bar_and_requires_continuity() -> None:
    raw = __import__("json").dumps([_bar(index * 3_600_000) for index in range(25)]).encode()
    observed = datetime.fromtimestamp(24.5 * 3600, UTC)

    bars = _parse_btc_bars(raw, observed_at=observed)

    assert len(bars) == 24
    assert bars[-1]["open_time_ms"] == 23 * 3_600_000


def test_parse_btc_bars_rejects_gap() -> None:
    rows = [_bar(index * 3_600_000) for index in range(25)]
    rows.pop(10)
    raw = __import__("json").dumps(rows).encode()

    with pytest.raises(ValueError, match="not contiguous"):
        _parse_btc_bars(raw, observed_at=datetime.fromtimestamp(26 * 3600, UTC))


def test_merge_observations_detects_revisions_without_losing_new_rows() -> None:
    merged, revisions, added = _merge_observations(
        {"a": "1", "b": "2"}, {"b": "3", "c": "4"}
    )

    assert merged == {"a": "1", "b": "3", "c": "4"}
    assert revisions == ["b"]
    assert added == 1


def test_summary_counts_distinct_days_and_unique_forward_signals() -> None:
    records = [
        {
            "collection_date": "2026-08-11",
            "qualified_day": True,
            "new_forward_signal_ids": ["s1"],
            "blockers": [],
        },
        {
            "collection_date": "2026-08-11",
            "qualified_day": True,
            "new_forward_signal_ids": ["s1"],
            "blockers": [],
        },
        {
            "collection_date": "2026-08-12",
            "qualified_day": True,
            "new_forward_signal_ids": ["s2"],
            "blockers": [],
        },
    ]

    status = summarize_attempts(records, gate_days=7, gate_signals=2)

    assert status["qualified_day_count"] == 2
    assert status["new_forward_signal_count"] == 2
    assert status["review_eligible"] is True


def test_summary_does_not_clear_historical_anomaly_at_threshold() -> None:
    records = [
        {
            "collection_date": f"2026-08-{day:02d}",
            "qualified_day": day != 12,
            "new_forward_signal_ids": [],
            "blockers": ["gvz_historical_revision:1"] if day == 12 else [],
        }
        for day in range(11, 19)
    ]

    status = summarize_attempts(records, gate_days=7, gate_signals=50)

    assert status["qualified_day_count"] == 7
    assert status["threshold_met"] is True
    assert status["review_eligible"] is False

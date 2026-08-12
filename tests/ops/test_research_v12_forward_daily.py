from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v12_forward_daily import (
    collect_daily,
    generate_forward_events,
    parse_stablecoin_rows,
    summarize_attempts,
)


def _stablecoin_history(target: date, *, increasing: bool = True) -> bytes:
    rows = []
    current = date(2026, 6, 1)
    offset = 0
    while current <= target:
        base = 100_000_000.0 + (offset * 1_000_000.0 if increasing else 0.0)
        for asset, extra in (("usdt", 1_000.0), ("usdc", 2_000.0)):
            rows.append(
                {
                    "asset": asset,
                    "time": f"{current.isoformat()}T00:00:00.000000000Z",
                    "SplyCur": str(base + extra),
                }
            )
        current += timedelta(days=1)
        offset += 1
    return json.dumps({"data": rows}).encode()


def _btc_history(observed_at: datetime) -> bytes:
    latest_closed = int(observed_at.timestamp() // 3600) * 3_600_000 - 3_600_000
    first = latest_closed - 166 * 3_600_000
    rows = []
    for index in range(168):
        open_ms = first + index * 3_600_000
        rows.append([open_ms, "100", "102", "99", "101", "10", open_ms + 3_600_000 - 1])
    return json.dumps(rows).encode()


def test_stablecoin_parser_requires_complete_two_asset_grid() -> None:
    target = date(2026, 8, 12)
    raw = _stablecoin_history(target)

    rows, audit = parse_stablecoin_rows(raw, start_day=date(2026, 6, 1), target_day=target)

    assert audit["complete_daily_grid"] is True
    assert audit["row_count"] == 146
    assert rows[-1]["date"] == "2026-08-12"

    payload = json.loads(raw)
    payload["data"].pop()
    with pytest.raises(ValueError, match="grid is incomplete"):
        parse_stablecoin_rows(
            json.dumps(payload).encode(), start_day=date(2026, 6, 1), target_day=target
        )


def test_forward_signal_starts_only_at_locked_decision_boundary() -> None:
    from apps.ops.research_v12_forward_daily import _factor_frame, load_contract

    rows, _ = parse_stablecoin_rows(
        _stablecoin_history(date(2026, 8, 12)),
        start_day=date(2026, 6, 1),
        target_day=date(2026, 8, 12),
    )
    frame = _factor_frame(rows, snapshot_sha256="sha256:" + "a" * 64, vintage_id="v1")
    events = generate_forward_events(frame, contract=load_contract())

    assert len(events) == 1
    assert events[0].side == "buy"
    assert events[0].ts_event == int(datetime(2026, 8, 14, tzinfo=UTC).timestamp() * 1e9)


def test_forward_summary_requires_days_and_events() -> None:
    records = [
        {
            "qualified_attempt": True,
            "new_forward_observation_dates": [f"2026-08-{day:02d}"],
            "new_forward_signal_ids": ["s1"] if day == 12 else (["s2"] if day == 13 else []),
            "blockers": [],
        }
        for day in range(12, 15)
    ]

    status = summarize_attempts(records, required_days=3, required_events=2)

    assert status["threshold_met"] is True
    assert status["continuation_review_eligible"] is True
    assert status["promotion_eligible"] is False


def test_daily_collection_preserves_day_one_without_touching_trading(tmp_path: Path) -> None:
    observed = datetime(2026, 8, 14, 12, 30, tzinfo=UTC)

    def fetch(url: str) -> bytes:
        if "coinmetrics" in url:
            assert "end_time=2026-08-12" in url
            return _stablecoin_history(date(2026, 8, 12))
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

    assert result["record"]["qualified_attempt"] is True
    assert result["record"]["new_forward_observation_dates"] == ["2026-08-12"]
    assert result["record"]["signals"]["new_forward"] == 1
    assert result["record"]["boundaries"]["orders_submitted"] is False
    assert result["status"]["qualified_forward_observation_count"] == 1
    assert result["status"]["promotion_eligible"] is False

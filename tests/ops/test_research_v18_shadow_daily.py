from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from apps.ops.research_v18_shadow_daily import (
    collect_daily,
    load_contract,
    summarize_attempts,
)


def test_v18_shadow_contract_is_locked() -> None:
    contract = load_contract()
    assert contract["candidate"]["strategy"] == "nasdaq_vol_relief"
    assert contract["collection"]["schedule"] == "weekdays at 03:30 UTC"
    assert contract["collection"]["collector_implemented"] is True


def test_v18_shadow_contract_rejects_url_drift(tmp_path: Path) -> None:
    payload = json.loads(Path("docs/progress/phase-2-research-v18-paper-shadow.json").read_text())
    payload["collection"]["vxn_url"] = "https://example.invalid/VXN.csv"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="collection contract drifted"):
        load_contract(path)


def test_summary_counts_distinct_days_and_unique_forward_signals() -> None:
    records = [
        {
            "collection_date": "2026-08-13",
            "qualified_day": True,
            "new_forward_signal_ids": ["s1"],
            "blockers": [],
        },
        {
            "collection_date": "2026-08-13",
            "qualified_day": True,
            "new_forward_signal_ids": ["s1"],
            "blockers": [],
        },
        {
            "collection_date": "2026-08-14",
            "qualified_day": True,
            "new_forward_signal_ids": ["s2"],
            "blockers": [],
        },
    ]
    status = summarize_attempts(records, gate_days=7, gate_signals=2)
    assert status["qualified_day_count"] == 2
    assert status["new_forward_signal_count"] == 2
    assert status["review_eligible"] is True


def _vxn_csv() -> bytes:
    lines = ["DATE,OPEN,HIGH,LOW,CLOSE"]
    current = date(2020, 1, 1)
    while current <= date(2026, 8, 12):
        if current.weekday() < 5:
            lines.append(f"{current.strftime('%m/%d/%Y')},20,21,19,20.5")
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


def _btc_payload(*, count: int = 168) -> bytes:
    rows = []
    for index in range(count):
        open_ms = index * 3_600_000
        rows.append([open_ms, "100", "102", "99", "101", "10", open_ms + 3_600_000 - 1])
    return json.dumps(rows).encode()


def test_collect_daily_qualifies_clean_attempt(tmp_path: Path) -> None:
    vxn_url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv"
    btc_url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=168"
    payloads = {vxn_url: _vxn_csv(), btc_url: _btc_payload()}

    def fetch(url: str) -> bytes:
        return payloads[url]

    result = collect_daily(
        repo_root=Path.cwd(),
        data_root=tmp_path,
        fetch=fetch,
        now=datetime(2026, 8, 13, 3, 15, tzinfo=UTC),
        git_state={
            "commit": "abc123",
            "branch": "main",
            "dirty": False,
            "origin_main_contains_commit": True,
        },
    )
    assert result["record"]["qualified_day"] is True
    assert result["record"]["blockers"] == []
    assert result["record"]["btc"]["closed_bar_rows"] >= 167
    assert result["record"]["boundaries"]["orders_submitted"] is False
    assert result["status"]["qualified_day_count"] == 1
    assert result["status"]["paper_simulated_status"] == "not_authorized"


def test_collect_daily_fail_closes_on_revision(tmp_path: Path) -> None:
    vxn_url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv"
    btc_url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=168"
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "vxn-observations.json").write_text(
        json.dumps({"2020-01-02": "99"})
    )
    payloads = {vxn_url: _vxn_csv(), btc_url: _btc_payload()}

    def fetch(url: str) -> bytes:
        return payloads[url]

    result = collect_daily(
        repo_root=Path.cwd(),
        data_root=tmp_path,
        fetch=fetch,
        now=datetime(2026, 8, 13, 3, 16, tzinfo=UTC),
        git_state={
            "commit": "abc123",
            "branch": "main",
            "dirty": False,
            "origin_main_contains_commit": True,
        },
    )
    assert result["record"]["qualified_day"] is False
    assert any(item.startswith("vxn_historical_revision") for item in result["record"]["blockers"])

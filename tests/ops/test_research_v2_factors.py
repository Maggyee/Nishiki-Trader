from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from apps.ops.research_v2_factors import (
    basis_factor_row,
    build_basis_factor_frame,
    qualification_summary,
    write_basis_factor_csv,
)
from apps.ops.research_v2_snapshot import collect_snapshot

NOW = datetime(2026, 7, 11, 8, 15, tzinfo=UTC)


def _bytes(payload) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _fetcher(front_price: str = "101000", next_price: str = "103000"):
    payloads = {
        "CURRENT_QUARTER": _bytes(
            [
                {
                    "pair": "BTCUSD",
                    "contractType": "CURRENT_QUARTER",
                    "indexPrice": "100000",
                    "futuresPrice": front_price,
                    "annualizedBasisRate": "0.04",
                    "timestamp": 1783728000000,
                }
            ]
        ),
        "NEXT_QUARTER": _bytes(
            [
                {
                    "pair": "BTCUSD",
                    "contractType": "NEXT_QUARTER",
                    "indexPrice": "100000",
                    "futuresPrice": next_price,
                    "annualizedBasisRate": "0.05",
                    "timestamp": 1783728000000,
                }
            ]
        ),
        "exchangeInfo": _bytes(
            {
                "symbols": [
                    {
                        "pair": "BTCUSD",
                        "symbol": "BTCUSD_260925",
                        "contractType": "CURRENT_QUARTER",
                        "contractStatus": "TRADING",
                        "deliveryDate": 1790323200000,
                    },
                    {
                        "pair": "BTCUSD",
                        "symbol": "BTCUSD_261225",
                        "contractType": "NEXT_QUARTER",
                        "contractStatus": "TRADING",
                        "deliveryDate": 1798185600000,
                    },
                ]
            }
        ),
    }

    def fetch(url: str) -> bytes:
        if "exchangeInfo" in url:
            return payloads["exchangeInfo"]
        if "NEXT_QUARTER" in url:
            return payloads["NEXT_QUARTER"]
        return payloads["CURRENT_QUARTER"]

    return fetch


def _snapshot(tmp_path: Path, *, now: datetime = NOW, front: str = "101000") -> Path:
    path, _ = collect_snapshot(
        "basis",
        output_dir=tmp_path,
        fetch=_fetcher(front_price=front),
        now=now,
    )
    return path


def test_basis_factor_delays_decision_until_next_utc_day_and_preserves_lineage(
    tmp_path: Path,
) -> None:
    path = _snapshot(tmp_path)

    row = basis_factor_row(path)

    assert row["ts_event"] == "2026-07-12T00:00:00+00:00"
    assert pd.Timestamp(row["available_at"]) < pd.Timestamp(row["ts_event"])
    assert row["front_days_to_expiry"] < row["next_days_to_expiry"]
    assert row["vintage_id"].startswith("basis:")
    assert row["snapshot_sha256"].startswith("sha256:")


def test_basis_factor_frame_rejects_duplicate_decision_days(tmp_path: Path) -> None:
    first = _snapshot(tmp_path / "one")
    second = _snapshot(
        tmp_path / "two",
        now=NOW + timedelta(minutes=10),
        front="101100",
    )

    with pytest.raises(ValueError, match="unique"):
        build_basis_factor_frame([first, second])


def test_basis_factor_rejects_future_dated_observation(tmp_path: Path) -> None:
    path = _snapshot(tmp_path)
    payload = json.loads(path.read_text())
    payload["requests"][0]["payload"][0]["timestamp"] = 1999999999999
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="differs from raw bytes"):
        basis_factor_row(path)


def test_factor_qualification_summary_has_no_return_signal_or_pnl_boundary(
    tmp_path: Path,
) -> None:
    path = _snapshot(tmp_path)
    frame = build_basis_factor_frame([path])

    summary = qualification_summary(frame, [path])

    assert summary["valid"] is True
    assert summary["row_count"] == 1
    assert set(summary["boundaries"].values()) == {False}
    assert "pnl" not in frame.columns
    assert "return" not in frame.columns


def test_basis_factor_csv_is_complete_and_cannot_be_overwritten(tmp_path: Path) -> None:
    path = _snapshot(tmp_path / "raw")
    output = tmp_path / "factors" / "basis.csv"

    report = write_basis_factor_csv([path], output)
    loaded = pd.read_csv(output)

    assert report["output_path"] == str(output)
    assert set(loaded) == {
        "ts_event",
        "available_at",
        "vintage_id",
        "snapshot_sha256",
        "spot_price",
        "front_futures_price",
        "next_futures_price",
        "front_days_to_expiry",
        "next_days_to_expiry",
    }
    with pytest.raises(FileExistsError):
        write_basis_factor_csv([path], output)

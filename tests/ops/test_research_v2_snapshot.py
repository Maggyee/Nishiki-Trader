from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apps.ops.research_v2_snapshot import (
    PROVIDER_CONTRACT,
    build_requests,
    collect_snapshot,
)

NOW = datetime(2026, 7, 11, 8, 0, tzinfo=UTC)


def _bytes(payload) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _option_payload() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": [
            {
                "instrument_name": "BTC-25JUL26-100000-C",
                "base_currency": "BTC",
                "quote_currency": "USD",
                "creation_timestamp": 1780000000000,
                "mark_price": 0.01,
                "mark_iv": 55.0,
                "underlying_price": 100000.0,
                "underlying_index": "BTC-25JUL26",
                "interest_rate": 0.0,
                "bid_price": 0.009,
                "ask_price": 0.011,
                "open_interest": 1.0,
            },
            {
                "instrument_name": "BTC-25SEP26-90000-P",
                "base_currency": "BTC",
                "quote_currency": "USD",
                "creation_timestamp": 1780000000000,
                "mark_price": 0.0,
                "mark_iv": 60.0,
                "underlying_price": 100100.0,
                "underlying_index": "BTC-25SEP26",
                "interest_rate": 0.0,
                "bid_price": None,
                "ask_price": None,
                "open_interest": 0.5,
            },
        ],
    }


def _basis_payloads() -> dict[str, bytes]:
    return {
        "CURRENT_QUARTER": _bytes(
            [
                {
                    "pair": "BTCUSD",
                    "contractType": "CURRENT_QUARTER",
                    "indexPrice": "100000",
                    "futuresPrice": "101000",
                    "annualizedBasisRate": "0.04",
                    "timestamp": 1783756800000,
                }
            ]
        ),
        "NEXT_QUARTER": _bytes(
            [
                {
                    "pair": "BTCUSD",
                    "contractType": "NEXT_QUARTER",
                    "indexPrice": "100000",
                    "futuresPrice": "103000",
                    "annualizedBasisRate": "0.05",
                    "timestamp": 1783756800000,
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
                        "deliveryDate": 1790294400000,
                    },
                    {
                        "pair": "BTCUSD",
                        "symbol": "BTCUSD_261225",
                        "contractType": "NEXT_QUARTER",
                        "contractStatus": "TRADING",
                        "deliveryDate": 1798156800000,
                    },
                ]
            }
        ),
    }


def _stablecoin_payload() -> dict:
    return {
        "data": [
            {
                "asset": "usdt",
                "time": "2026-07-01T00:00:00Z",
                "SplyCur": "100000000",
                "TxTfrValUSD": "50000000",
            },
            {
                "asset": "usdc",
                "time": "2026-07-01T00:00:00Z",
                "SplyCur": "50000000",
                "TxTfrValUSD": "25000000",
            },
        ]
    }


def test_provider_contract_matches_locked_request_builders() -> None:
    contract = json.loads(PROVIDER_CONTRACT.read_text())

    for kind in ("options", "basis"):
        actual = [
            {"name": spec.name, "url": spec.url, "params": spec.params}
            for spec in build_requests(kind)
        ]
        assert actual == contract["providers"][kind]["requests"]
    stable = build_requests("stablecoin", start_date="2026-07-01", end_date="2026-07-10")
    locked = contract["providers"]["stablecoin"]["requests"][0]
    assert stable[0].name == locked["name"]
    assert stable[0].url == locked["url"]
    for key, value in locked["params"].items():
        assert stable[0].params[key] == value


def test_option_snapshot_is_immutable_and_records_only_schema_audit(tmp_path: Path) -> None:
    path, envelope = collect_snapshot(
        "options",
        output_dir=tmp_path,
        fetch=lambda _: _bytes(_option_payload()),
        now=NOW,
    )

    assert path.exists()
    assert envelope["audit"] == {
        "row_count": 2,
        "expiry_count": 2,
        "two_sided_positive_mark_count": 1,
        "zero_mark_count": 1,
    }
    assert envelope["snapshot_sha256"].startswith("sha256:")
    assert envelope["requests"][0]["payload_sha256"].startswith("sha256:")
    assert envelope["boundaries"]["pnl_computed"] is False
    assert envelope["boundaries"]["signal_store_written"] is False

    with pytest.raises(FileExistsError):
        collect_snapshot(
            "options",
            output_dir=tmp_path,
            fetch=lambda _: _bytes(_option_payload()),
            now=NOW,
        )


def test_option_snapshot_fails_closed_on_unexplained_instrument_or_missing_iv(tmp_path: Path) -> None:
    payload = _option_payload()
    payload["result"][0]["instrument_name"] = "ETH-25JUL26-100000-C"
    with pytest.raises(ValueError, match="unexpected BTC option"):
        collect_snapshot("options", output_dir=tmp_path, fetch=lambda _: _bytes(payload), now=NOW)

    payload = _option_payload()
    payload["result"][0]["mark_iv"] = None
    with pytest.raises(ValueError, match="mark_iv"):
        collect_snapshot("options", output_dir=tmp_path, fetch=lambda _: _bytes(payload), now=NOW)


def test_basis_snapshot_maps_current_and_next_delivery_without_pnl(tmp_path: Path) -> None:
    payloads = _basis_payloads()

    def fetch(url: str) -> bytes:
        if "exchangeInfo" in url:
            return payloads["exchangeInfo"]
        if "NEXT_QUARTER" in url:
            return payloads["NEXT_QUARTER"]
        return payloads["CURRENT_QUARTER"]

    _, envelope = collect_snapshot("basis", output_dir=tmp_path, fetch=fetch, now=NOW)

    assert envelope["audit"]["symbols"] == {
        "CURRENT_QUARTER": "BTCUSD_260925",
        "NEXT_QUARTER": "BTCUSD_261225",
    }
    assert envelope["boundaries"]["pnl_computed"] is False


def test_basis_snapshot_rejects_expired_or_reversed_delivery_mapping(tmp_path: Path) -> None:
    payloads = _basis_payloads()
    exchange = json.loads(payloads["exchangeInfo"])
    exchange["symbols"][0]["deliveryDate"] = 1700000000000
    payloads["exchangeInfo"] = _bytes(exchange)

    def fetch(url: str) -> bytes:
        if "exchangeInfo" in url:
            return payloads["exchangeInfo"]
        if "NEXT_QUARTER" in url:
            return payloads["NEXT_QUARTER"]
        return payloads["CURRENT_QUARTER"]

    with pytest.raises(ValueError, match="lacks trading"):
        collect_snapshot("basis", output_dir=tmp_path, fetch=fetch, now=NOW)


def test_stablecoin_snapshot_is_july_only_and_requires_locked_universe(tmp_path: Path) -> None:
    _, envelope = collect_snapshot(
        "stablecoin",
        output_dir=tmp_path,
        start_date="2026-07-01",
        end_date="2026-07-10",
        fetch=lambda _: _bytes(_stablecoin_payload()),
        now=NOW,
    )

    assert envelope["audit"] == {"row_count": 2, "assets": ["usdc", "usdt"]}
    with pytest.raises(ValueError, match="July 2026"):
        build_requests("stablecoin", start_date="2026-06-01", end_date="2026-07-01")

    payload = _stablecoin_payload()
    payload["data"] = payload["data"][:1]
    with pytest.raises(ValueError, match="both usdt and usdc"):
        collect_snapshot(
            "stablecoin",
            output_dir=tmp_path / "missing",
            start_date="2026-07-01",
            end_date="2026-07-10",
            fetch=lambda _: _bytes(payload),
            now=NOW,
        )

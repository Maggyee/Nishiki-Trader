"""Tests for ADR-008 Phase 3c-b Binance Spot testnet ExchangeClient."""

from __future__ import annotations

import inspect
import urllib.parse
from collections.abc import Mapping
from decimal import Decimal

import pytest

from apps.strategies_nautilus.runners import binance_testnet_exchange
from apps.strategies_nautilus.runners.binance_testnet_exchange import (
    BinanceSpotTestnetCredentials,
    BinanceSpotTestnetError,
    BinanceSpotTestnetExchangeClient,
)
from apps.strategies_nautilus.runners.emergency_flatten import (
    EmergencyFlattenSettings,
    FlattenValidationError,
)
from apps.strategies_nautilus.runners.emergency_flatten import (
    main as emergency_flatten_main,
)

VALID_KEY = "K" * 40
# Raw base64 PKCS#8-like Ed25519 DER fixture: OID 1.3.101.112 + seed bytes 0..31.
VALID_ED25519_SECRET = (
    "MC4CAQAwBQYDK2VwBCIEIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f"
)
VALID_ENV = {
    "BINANCE_TESTNET_API_KEY": VALID_KEY,
    "BINANCE_TESTNET_API_SECRET": VALID_ED25519_SECRET,
}
INSTRUMENT_ID = "BTCUSDT.BINANCE"


class _FakeTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        data: bytes | None,
        timeout_seconds: float,
    ):
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": parsed.path,
                "query": query,
                "headers": dict(headers),
                "data": data,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self._responses:
            raise AssertionError(f"unexpected HTTP call: {method} {url}")
        return self._responses.pop(0)


def _client(responses) -> tuple[BinanceSpotTestnetExchangeClient, _FakeTransport]:
    credentials = BinanceSpotTestnetCredentials.from_env(VALID_ENV)
    transport = _FakeTransport(responses)
    client = BinanceSpotTestnetExchangeClient(
        credentials=credentials,
        transport=transport,
        clock_ms=lambda: 1716033600123,
    )
    return client, transport


def _settings(tmp_path) -> EmergencyFlattenSettings:
    return EmergencyFlattenSettings(
        kind="testnet",
        run_id="20260518-122839Z-24bf3db2",
        operator="pytest",
        reason="cancel-only integration test",
        instrument_ids=(INSTRUMENT_ID,),
        output_root=tmp_path / "data" / "testnet",
        cancel_only=True,
        fill_timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        sigkill_delay_seconds=0.0,
    )


def test_credentials_require_ed25519_secret() -> None:
    with pytest.raises(FlattenValidationError, match="ed25519_credentials_required"):
        BinanceSpotTestnetCredentials.from_env(
            {
                "BINANCE_TESTNET_API_KEY": VALID_KEY,
                "BINANCE_TESTNET_API_SECRET": "S" * 40,
            }
        )
    credentials = BinanceSpotTestnetCredentials.from_env(VALID_ENV)
    rendered = repr(credentials)
    assert VALID_KEY not in rendered
    assert VALID_ED25519_SECRET not in rendered
    assert credentials.credentials_key_prefix == VALID_KEY[:8]


def test_list_open_orders_signs_request_and_maps_remaining_quantity() -> None:
    client, transport = _client(
        [
            [
                {
                    "orderId": 12345,
                    "side": "BUY",
                    "origQty": "0.10000000",
                    "executedQty": "0.02000000",
                    "time": 1716033600123,
                }
            ]
        ]
    )

    orders = client.list_open_orders(INSTRUMENT_ID)

    assert len(orders) == 1
    assert orders[0].order_id == "12345"
    assert orders[0].side == "BUY"
    assert orders[0].quantity == Decimal("0.08000000")
    assert orders[0].submitted_at == "2024-05-18T12:00:00.123Z"

    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/api/v3/openOrders"
    assert call["headers"]["X-MBX-APIKEY"] == VALID_KEY
    assert call["query"]["symbol"] == ["BTCUSDT"]
    assert call["query"]["recvWindow"] == ["5000"]
    assert call["query"]["timestamp"] == ["1716033600123"]
    assert "signature" in call["query"]
    assert VALID_ED25519_SECRET not in call["url"]


def test_cancel_order_returns_true_for_terminal_cancel_response() -> None:
    client, transport = _client([{"orderId": 12345, "status": "CANCELED"}])

    assert client.cancel_order(order_id="12345", instrument_id=INSTRUMENT_ID) is True

    call = transport.calls[0]
    assert call["method"] == "DELETE"
    assert call["path"] == "/api/v3/order"
    assert call["query"]["symbol"] == ["BTCUSDT"]
    assert call["query"]["orderId"] == ["12345"]


def test_cancel_order_returns_false_for_non_terminal_response() -> None:
    client, _ = _client([{"orderId": 12345, "status": "NEW"}])

    assert client.cancel_order(order_id="12345", instrument_id=INSTRUMENT_ID) is False


def test_list_open_positions_infers_long_spot_inventory_from_account_balance() -> None:
    client, transport = _client(
        [
            {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                    }
                ]
            },
            {
                "balances": [
                    {"asset": "BTC", "free": "0.05000000", "locked": "0.01000000"},
                    {"asset": "USDT", "free": "10000.00", "locked": "0.00"},
                ]
            },
        ]
    )

    positions = client.list_open_positions(INSTRUMENT_ID)

    assert len(positions) == 1
    assert positions[0].side == "LONG"
    assert positions[0].quantity == Decimal("0.06000000")
    assert transport.calls[0]["path"] == "/api/v3/exchangeInfo"
    assert transport.calls[0]["headers"] == {}
    assert "signature" not in transport.calls[0]["query"]
    assert transport.calls[1]["path"] == "/api/v3/account"
    assert "signature" in transport.calls[1]["query"]


def test_submit_reduce_only_market_order_uses_spot_market_sell_without_reduce_only_param():
    client, transport = _client([{"orderId": 98765, "status": "FILLED"}])

    order_id = client.submit_reduce_only_market_order(
        instrument_id=INSTRUMENT_ID,
        side="SELL",
        quantity=Decimal("0.01000000"),
        client_order_id="EF-20260518-BTCUSDT",
    )

    assert order_id == "98765"
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/v3/order"
    assert call["query"]["symbol"] == ["BTCUSDT"]
    assert call["query"]["side"] == ["SELL"]
    assert call["query"]["type"] == ["MARKET"]
    assert call["query"]["quantity"] == ["0.01"]
    assert call["query"]["newClientOrderId"] == ["EF-20260518-BTCUSDT"]
    assert "reduceOnly" not in call["query"]


def test_submit_reduce_only_market_order_rejects_spot_short_close() -> None:
    client, _ = _client([])

    with pytest.raises(BinanceSpotTestnetError, match="spot_reduce_only_short"):
        client.submit_reduce_only_market_order(
            instrument_id=INSTRUMENT_ID,
            side="BUY",
            quantity=Decimal("0.01"),
            client_order_id="EF-short",
        )


def test_query_order_maps_filled_quantity_and_average_price() -> None:
    client, _ = _client(
        [
            {
                "orderId": 98765,
                "status": "FILLED",
                "executedQty": "0.05000000",
                "cummulativeQuoteQty": "1500.00000000",
            }
        ]
    )

    snapshot = client.query_order(order_id="98765", instrument_id=INSTRUMENT_ID)

    assert snapshot.status == "FILLED"
    assert snapshot.filled_quantity == Decimal("0.05000000")
    assert snapshot.avg_price == Decimal("30000")


def test_get_account_snapshot_maps_balances_without_credentials() -> None:
    client, _ = _client(
        [
            {
                "balances": [
                    {"asset": "USDT", "free": "10000.00", "locked": "0.00"},
                    {"asset": "BTC", "free": "1.00", "locked": "0.00"},
                ]
            }
        ]
    )

    snapshot = client.get_account_snapshot()

    assert snapshot.account_id == "BINANCE-SPOT-master"
    assert [b.asset for b in snapshot.balances] == ["USDT", "BTC"]
    rendered = repr(snapshot)
    assert VALID_KEY not in rendered
    assert VALID_ED25519_SECRET not in rendered


def test_default_emergency_flatten_factory_dispatches_testnet_driver(
    tmp_path, monkeypatch, capsys
) -> None:
    class _CancelOnlyExchange:
        def list_open_orders(self, instrument_id):
            return []

        def cancel_order(self, *, order_id, instrument_id):  # pragma: no cover
            raise AssertionError("no open orders")

        def list_open_positions(self, instrument_id):  # pragma: no cover
            raise AssertionError("cancel-only skips positions")

        def submit_reduce_only_market_order(self, **kwargs):  # pragma: no cover
            raise AssertionError("cancel-only skips submissions")

        def query_order(self, **kwargs):  # pragma: no cover
            raise AssertionError("cancel-only skips query")

        def get_account_snapshot(self):
            from apps.strategies_nautilus.runners.emergency_flatten import (
                AccountBalance,
                AccountSnapshot,
            )

            return AccountSnapshot(
                account_id="BINANCE-SPOT-master",
                fetched_at="2026-05-18T12:00:00.000Z",
                balances=(AccountBalance("USDT", Decimal("10000"), Decimal("0")),),
            )

    def _fake_factory(settings, *, env=None):
        assert settings.kind == "testnet"
        assert env == VALID_ENV
        return _CancelOnlyExchange()

    monkeypatch.setattr(
        "apps.strategies_nautilus.runners.emergency_flatten."
        "_default_exchange_factory",
        _fake_factory,
    )

    settings = _settings(tmp_path)
    rc = emergency_flatten_main(
        [
            "--kind",
            "testnet",
            "--run-id",
            settings.run_id,
            "--operator",
            settings.operator,
            "--reason",
            settings.reason,
            "--instrument-id",
            INSTRUMENT_ID,
            "--output-root",
            str(settings.output_root),
            "--cancel-only",
            "--fill-timeout-seconds",
            "1",
            "--poll-interval-seconds",
            "0.1",
            "--sigkill-delay-seconds",
            "0",
        ],
        env=VALID_ENV,
        signaller=lambda pid, sig: None,
    )

    assert rc == 0
    assert '"kind": "testnet"' in capsys.readouterr().out


def test_driver_source_does_not_reference_live_binance_credentials() -> None:
    source = inspect.getsource(binance_testnet_exchange)
    assert "BINANCE_API_KEY" not in source
    assert "BINANCE_API_SECRET" not in source
    assert "MAINNET" not in source

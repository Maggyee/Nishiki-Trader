"""Independent testnet engineering scope and non-matching TRADE validation.

No execution client, order engine, source promotion or matching endpoint exists here.
The full-account portfolio baseline remains unqualified under ADR-015/016.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from urllib.parse import urlencode

from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_testnet_capabilities import (
    TestnetCapabilityHttpClient,
    review_capabilities,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.portfolio_venue import VenueInputError, _decimal, _unique_object

POLICY_ID = "testnet-engineering-session-v1-20260911"
VALIDATE_PATH = "/api/v3/order/test"
FIXED = {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "timeInForce": "GTC",
    "quantity": "0.0001",
    "computeCommissionRates": "true",
}


def session_contract():
    return {
        "policy_id": POLICY_ID,
        "environment": "binance_spot_testnet",
        "scope": "single engineering session; not portfolio or strategy admission",
        "capital_scope": "10 existing free test USDT earmarked in a future durable session ledger",
        "maximum_total_buy_debit_usdt": "10",
        "fixed_buy_quantity_btc": "0.0001",
        "maximum_buy_submissions": 1,
        "maximum_cleanup_sell_submissions": 1,
        "maximum_outstanding_orders": 1,
        "maximum_session_seconds": 180,
        "cancel_after_acknowledgement_seconds": 2,
        "fees": "first session requires every standard/special/tax fee component to be zero",
        "owned_inventory": "start at zero; acquire only actual net fills of the one session BUY",
        "cleanup": "whole owned steps only; retain dust; reject below-minimum exits",
        "proceeds_reusable": False,
        "automatic_retry_or_replacement": False,
        "scope_survives_restart": "uncertain or spent BUY stays blocked; never reset budget or IDs",
        "unrelated_assets": "retain all balances; never value at zero, fund from, or sell them",
        "full_account_utc_baseline_qualified": False,
        "portfolio_risk_policy_changed": False,
        "native_execution_runner_wired": False,
        "strict_continuity_days": 0,
        "runtime_ready": False,
    }


def validation_price(capture, now_ns):
    """Review exact fresh captures; only this zero-fee engineering probe is allowed."""
    review = review_capabilities(capture)
    if (
        type(now_ns) is not int
        or not 0 <= now_ns - capture["captures"][-1]["received_ns"] <= 5_000_000_000
    ):
        raise VenueInputError("fresh capability capture required for validation")
    required = (
        "account_read_accepted",
        "account_reports_can_trade",
        "full_balances_unchanged",
        "account_metadata_unchanged",
        "account_wide_open_orders_empty",
        "at_least_10_free_test_usdt",
        "native_rules_parsed",
        "buy_within_effective_price_bands",
        "buy_within_effective_order_filters",
    )
    if not all(review.get(key) is True for key in required):
        raise VenueInputError("testnet validation prerequisites incomplete")
    if _decimal(review["fee_rate_bound"]) != 0:
        raise VenueInputError("first engineering session requires exact zero fees")
    plan = review["lifecycle_proposal"]
    if not plan["captured_basic_filter_checks_passed"]:
        raise VenueInputError("testnet basic filters rejected")
    price = plan["illustrative_buy_limit_price"]
    if not 0 < _decimal(price) * _decimal(FIXED["quantity"]) <= 10:
        raise VenueInputError("testnet validation debit cap exceeded")
    return price


class TestnetOrderValidationHttpClient(TestnetCapabilityHttpClient):
    """Allow POST /order/test only; /order and all cancellation methods are refused."""

    __test__ = False

    async def send_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        if http_method == HttpMethod.GET:
            return await super().send_request(http_method, url_path, payload, ratelimiter_keys)
        params = dict(payload or {})
        if (
            self.base_url != TESTNET_REST
            or http_method != HttpMethod.POST
            or url_path != VALIDATE_PATH
            or set(params) != set(FIXED) | {"price", "timestamp", "signature"}
            or any(params.get(k) != v for k, v in FIXED.items())
            or not 0 < _decimal(params["price"]) * _decimal(FIXED["quantity"]) <= 10
        ):
            raise VenueInputError("only fixed non-matching testnet order validation allowed")
        try:
            async with asyncio.timeout(10):
                response = await self._client.request(
                    HttpMethod.POST,
                    url=TESTNET_REST + VALIDATE_PATH + "?" + urlencode(params),
                    headers=self.headers,
                    body=None,
                    keys=ratelimiter_keys,
                )
            if len(response.body) > 65_536:
                raise ValueError
            return response.status, response.body
        except Exception:
            raise VenueInputError("testnet order validation failed; no automatic retry") from None


async def validate_order(http, capture, clock_ns):
    # Bind even a fresh capture to this exact selected client. No self-declared UID swap.
    if (
        http.base_url != TESTNET_REST
        or capture["source"]["key_sha256"] != hashlib.sha256(http.api_key.encode()).hexdigest()
    ):
        raise VenueInputError("validation/capability source mismatch")
    started = clock_ns()
    price = validation_price(capture, started)
    params = FIXED | {"price": price, "timestamp": str(started // 1_000_000)}
    status, raw = await http.sign_request(HttpMethod.POST, VALIDATE_PATH, params)
    received = clock_ns()
    body = json.loads(raw, object_pairs_hook=_unique_object)
    fees_zero = False
    if status == 200 and isinstance(body, dict):
        try:
            fees_zero = all(
                _decimal(body[group][liquidity]) == 0
                for group in (
                    "standardCommissionForOrder",
                    "specialCommissionForOrder",
                    "taxCommissionForOrder",
                )
                for liquidity in ("maker", "taker")
            )
            if any(
                type(body["discount"][key]) is not bool
                for key in ("enabledForAccount", "enabledForSymbol")
            ):
                fees_zero = False
        except (KeyError, TypeError, ValueError, ArithmeticError):
            fees_zero = False
    return {
        "path": VALIDATE_PATH,
        "method": "POST",
        "params": FIXED | {"price": price},
        "started_ns": started,
        "received_ns": received,
        "status": status,
        "body": raw.decode(),
        "body_sha256": hashlib.sha256(raw).hexdigest(),
        "trade_validation_request_accepted": status == 200,
        "zero_fee_validation_passed": status == 200 and fees_zero,
        "returned_order_fee_rates_zero": fees_zero,
        "request_timing_valid": 0 <= received - started <= 10_000_000_000,
        "api_key_restrictions_verified": False,
        "matching_order_permission_proven": False,
        "matching_engine_order_submitted": False,
        "runtime_ready": False,
    }

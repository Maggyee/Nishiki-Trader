"""Bounded testnet GET diagnostics; no trading or API-restriction inference."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from urllib.parse import urlencode

from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    Ed25519TestnetReadOnlyHttpClient,
)
from apps.strategies_nautilus.portfolio_testnet_observation import (
    _open_orders,
    account_balances,
    select_initial_observation,
)
from apps.strategies_nautilus.portfolio_testnet_order_plan import lifecycle_test_plan
from apps.strategies_nautilus.portfolio_venue import (
    CapturedResponse,
    PriceReference,
    VenueInputError,
    _decimal,
    _filters,
    _unique_object,
    parse_binance_rules,
)

PRIVATE = {
    "/api/v3/account": {"omitZeroBalances": "false"},
    "/api/v3/openOrders": {},
    "/api/v3/account/commission": {"symbol": "BTCUSDT"},
    "/api/v3/myFilters": {"symbol": "BTCUSDT"},
}
PUBLIC = {
    path: {"symbol": "BTCUSDT"}
    for path in (
        "/api/v3/exchangeInfo",
        "/api/v3/referencePrice",
        "/api/v3/avgPrice",
        "/api/v3/ticker/bookTicker",
    )
}
PATHS = (
    "/api/v3/account",
    "/api/v3/openOrders",
    "/api/v3/account/commission",
    "/api/v3/myFilters",
    *PUBLIC,
    "/api/v3/openOrders",
    "/api/v3/account",
)


class TestnetCapabilityHttpClient(Ed25519TestnetReadOnlyHttpClient):
    """Separate exact-path/parameter whitelist; the strict collector is unchanged.

    Returns raw status/body for diagnostic capture, including venue rejections.
    Never uses upstream signed-URL logging and never sends a key on public reads.
    """

    __test__ = False

    async def send_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        params = dict(payload or {})
        private = url_path in PRIVATE
        expected = PRIVATE.get(url_path) if private else PUBLIC.get(url_path)
        unsigned = {k: v for k, v in params.items() if k not in {"timestamp", "signature"}}
        if (
            self.base_url != TESTNET_REST
            or http_method != HttpMethod.GET
            or expected is None
            or unsigned != expected
            or (private and set(params) != set(expected) | {"timestamp", "signature"})
            or (not private and params != expected)
        ):
            raise VenueInputError("only fixed testnet capability GET requests allowed")
        try:
            async with asyncio.timeout(10):
                response = await self._client.request(
                    HttpMethod.GET,
                    url=TESTNET_REST + url_path + ("?" + urlencode(params) if params else ""),
                    headers=self.headers if private else {},
                    body=None,
                    keys=ratelimiter_keys,
                )
            if len(response.body) > 8 * 1024 * 1024:
                raise ValueError
            return response.status, response.body
        except Exception:
            raise VenueInputError("testnet capability GET failed") from None


async def collect_capabilities(http, initial_raw, selection_sha256, clock_ns):
    """Ten GETs, at most 60 seconds, bracketed by full account/open-order reads."""
    binding = select_initial_observation(initial_raw, selection_sha256, http)
    result = {
        "schema_version": "portfolio.testnet_capabilities.v1",
        "selection_sha256": selection_sha256,
        "source": asdict(binding),
        "captures": [],
    }
    previous = clock_ns()
    async with asyncio.timeout(60):
        for path in PATHS:
            started = clock_ns()
            if started < previous:
                raise VenueInputError("capability capture clock regressed")
            if path in PRIVATE:
                params = PRIVATE[path] | {"timestamp": str(started // 1_000_000)}
                status, raw = await http.sign_request(HttpMethod.GET, path, params)
            else:
                status, raw = await http.send_request(HttpMethod.GET, path, PUBLIC[path])
            received = clock_ns()
            if received < started:
                raise VenueInputError("capability capture clock regressed")
            previous = received
            body = json.loads(raw, object_pairs_hook=_unique_object)
            result["captures"].append(
                {
                    "path": path,
                    "params": dict(PRIVATE[path] if path in PRIVATE else PUBLIC[path]),
                    "started_ns": started,
                    "received_ns": received,
                    "status": status,
                    "body": raw.decode(),
                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            if path == "/api/v3/account":
                if status != 200:
                    raise VenueInputError("account capability read rejected")
                account_balances(body, binding.account_uid)
    result["review"] = review_capabilities(result)
    return result


def review_capabilities(capture):
    """Diagnostic only; native parser refusal stays explicit, readiness stays false."""
    rows = capture["captures"]
    uid = capture["source"]["account_uid"]
    if capture["source"]["endpoint"] != TESTNET_REST or tuple(r["path"] for r in rows) != PATHS:
        raise VenueInputError("unexpected capability capture source/sequence")
    previous = rows[0]["started_ns"]
    for row in rows:
        if (
            row["params"] != (PRIVATE | PUBLIC)[row["path"]]
            or hashlib.sha256(row["body"].encode()).hexdigest() != row["body_sha256"]
            or not previous <= row["started_ns"] <= row["received_ns"]
            or row["received_ns"] - rows[0]["started_ns"] > 60_000_000_000
        ):
            raise VenueInputError("invalid capability capture hash/parameters/time")
        previous = row["received_ns"]
    parsed = [json.loads(r["body"], object_pairs_hook=_unique_object) for r in rows]
    by_path = {r["path"]: (r, body) for r, body in zip(rows, parsed, strict=True)}
    first = account_balances(parsed[0], uid)
    last = account_balances(parsed[-1], uid)
    account_ok = rows[0]["status"] == rows[-1]["status"] == 200
    orders_ok = rows[1]["status"] == rows[-2]["status"] == 200
    if orders_ok:
        _open_orders(parsed[1])
        _open_orders(parsed[-2])
    review = {
        "review_scope": "GET collection before optional non-matching TRADE validation",
        "account_read_accepted": account_ok,
        "account_reports_can_trade": parsed[0]["canTrade"] and parsed[-1]["canTrade"],
        "selected_uid_matches": True,
        "asset_count": len(last),
        "full_balances_unchanged": account_ok and first == last,
        "account_metadata_unchanged": account_ok and parsed[0] == parsed[-1],
        "account_wide_open_orders_empty": orders_ok and parsed[1] == parsed[-2] == [],
        "at_least_10_free_test_usdt": last.get("USDT", (Decimal(0),))[0] >= 10,
        "http_results": {r["path"]: r["status"] for r in rows},
        "venue_error_codes": {
            r["path"]: body.get("code") if isinstance(body, dict) else None
            for r, body in zip(rows, parsed, strict=True)
            if r["status"] != 200
        },
        "commission_read_accepted": by_path["/api/v3/account/commission"][0]["status"] == 200,
        "my_filters_read_accepted": by_path["/api/v3/myFilters"][0]["status"] == 200,
        "native_rules_parsed": False,
        "native_rules_error": None,
        "buy_fee_currency": None,
        "sell_fee_currency": None,
        "fee_rate_bound": None,
        "key_trade_permission_verified": False,
        "api_key_restrictions_verified": False,
        "trade_permission_probe_performed": False,
        "account_market_atomicity_verified": False,
        "full_account_baseline_qualified": False,
        "testnet_order_ready": False,
        "runtime_ready": False,
    }
    try:

        info_row, info = by_path["/api/v3/exchangeInfo"]
        book_row, book = by_path["/api/v3/ticker/bookTicker"]
        if info_row["status"] == book_row["status"] == 200:
            review["lifecycle_proposal"] = lifecycle_test_plan(info, [book])
        rules = capability_rules(capture, now_ns=rows[-1]["received_ns"])
        review.update(
            native_rules_parsed=True,
            buy_fee_currency=rules.buy_fee_currency,
            sell_fee_currency=rules.sell_fee_currency,
            fee_rate_bound=str(rules.fee_rate),
        )
        plan = review.get("lifecycle_proposal", {})
        if plan.get("captured_basic_filter_checks_passed"):
            price = _decimal(plan["illustrative_buy_limit_price"])
            quantity = _decimal(plan["fixed_buy_quantity_btc"])
            notional = price * quantity
            review["buy_within_effective_price_bands"] = all(
                band.minimum <= price <= band.maximum
                for band in rules.price_bands
                if band.side == "BUY"
            )
            review["buy_within_effective_order_filters"] = (
                rules.quantity_min <= quantity <= rules.quantity_max
                and quantity % rules.quantity_step == 0
                and price >= rules.price_min
                and (not rules.price_max or price <= rules.price_max)
                and (not rules.price_tick or price % rules.price_tick == 0)
                and notional >= rules.notional_min
                and (rules.notional_max is None or notional <= rules.notional_max)
                and (rules.max_open_orders is None or rules.max_open_orders >= 1)
                and (
                    rules.max_position is None
                    or sum(last.get("BTC", (Decimal(0),))) + quantity <= rules.max_position
                )
            )
    except VenueInputError as exc:
        review["native_rules_error"] = str(exc)
    except (KeyError, TypeError, ValueError, ArithmeticError, IndexError):
        review["native_rules_error"] = "capability response schema unsupported"
    return review


def capability_rules(capture, *, now_ns, max_age_ns=60_000_000_000):
    """Parse effective rules from the original fee/filter/reference responses."""
    uid = capture["source"]["account_uid"]
    by_path = {r["path"]: (r, json.loads(r["body"], object_pairs_hook=_unique_object))
               for r in capture["captures"]}
    def response(path, private=False):
        row, _ = by_path[path]
        if row["status"] != 200:
            raise VenueInputError("required capability endpoint rejected")
        return CapturedResponse(
            row["body"],
            row["received_ns"],
            uid if private else None,
            "BTCUSDT" if private else None,
        )

    _, info = by_path["/api/v3/exchangeInfo"]
    references = []
    filters = _filters(info["symbols"][0]["filters"])
    ref_row, ref = by_path["/api/v3/referencePrice"]
    avg_row, avg = by_path["/api/v3/avgPrice"]
    for name in ("PERCENT_PRICE", "PERCENT_PRICE_BY_SIDE"):
        if name not in filters:
            continue
        minutes = filters[name]["avgPriceMins"]
        absent = (ref_row["status"] == 400 and ref.get("code") == -2043) or (
            ref_row["status"] == 200
            and ref.get("symbol") == "BTCUSDT"
            and "referencePrice" in ref
            and ref["referencePrice"] is None
        )
        if not absent:
            if ref_row["status"] != 200 or ref.get("symbol") != "BTCUSDT":
                raise VenueInputError("reference-price precedence unknown")
            price, ts = _decimal(ref["referencePrice"]), ref["timestamp"] * 1_000_000
            kind = "reference_price"
        else:
            if avg_row["status"] != 200 or minutes == 0 or avg.get("mins") != minutes:
                raise VenueInputError("effective average-price window unavailable")
            price, ts = _decimal(avg["price"]), avg["closeTime"] * 1_000_000
            kind = "weighted_average"
        references.append(PriceReference(name, price, ts, minutes, kind, absent))
    evidence = parse_binance_rules(
        exchange_info=response("/api/v3/exchangeInfo"),
        commission=response("/api/v3/account/commission", True),
        my_filters=response("/api/v3/myFilters", True),
        account_id=uid,
        now_ns=now_ns,
        max_age_ns=max_age_ns,
        references=tuple(references),
        allow_testnet_zero_fee_null_discount=True,
    )
    return evidence.rules

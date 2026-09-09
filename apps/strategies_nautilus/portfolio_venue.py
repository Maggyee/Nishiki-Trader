"""Offline Binance response adapter for the dedicated BTC/USDT LIMIT contract.

Consumes captured response bodies; performs no HTTP, credential lookup or orders.
Receipt times and account identity are collector assertions, not authenticated by
this parser. An authoritative collector/reconciler is still required for runtime.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from apps.strategies_nautilus.portfolio_preflight import InstrumentRules, PriceBand

D = Decimal


class VenueInputError(ValueError):
    """Missing, stale, unsupported or ambiguous venue input."""


@dataclass(frozen=True)
class CapturedResponse:
    body: str
    received_ns: int
    account_id: str | None = None  # mandatory for private response matching
    requested_symbol: str | None = None  # myFilters does not echo its request symbol


@dataclass(frozen=True)
class PriceReference:
    filter_type: str
    price: Decimal
    ts_ns: int
    average_minutes: int
    kind: str  # reference_price, weighted_average, last_price
    reference_price_known_absent: bool = False


@dataclass(frozen=True)
class VenueRulesEvidence:
    rules: InstrumentRules
    account_id: str
    response_sha256: tuple[tuple[str, str], ...]
    inapplicable_filters: tuple[str, ...]
    price_references: tuple[PriceReference, ...]


def _fresh(ts, now, age):
    if type(ts) is not int or not 0 < ts <= now or now - ts > age:
        raise VenueInputError("stale/future/missing venue input timestamp")


def _decimal(value):
    if not isinstance(value, str):
        raise VenueInputError("venue decimal must be a string")
    result = D(value)
    if not result.is_finite() or result < 0:
        raise VenueInputError("invalid venue decimal")
    return result


def _integer(value):
    if type(value) is not int or value < 0:
        raise VenueInputError("nonnegative integer required")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VenueInputError("duplicate JSON key")
        result[key] = value
    return result


def _filters(rows):
    if not isinstance(rows, list):
        raise VenueInputError("explicit filter list required")
    result = {}
    for row in rows:
        name = row["filterType"]
        if name in result:
            raise VenueInputError("duplicate filter type")
        result[name] = row
    return result


# Only inapplicable because the consumer supports ordinary, unamended LIMIT
# orders, with no iceberg, stop, trailing, order list, SOR or pegged instructions.
INAPPLICABLE_SYMBOL = frozenset(
    {
        "MARKET_LOT_SIZE",
        "ICEBERG_PARTS",
        "MAX_NUM_ALGO_ORDERS",
        "MAX_NUM_ICEBERG_ORDERS",
        "TRAILING_DELTA",
        "MAX_NUM_ORDER_AMENDS",
        "MAX_NUM_ORDER_LISTS",
    }
)
INAPPLICABLE_EXCHANGE = frozenset(
    {
        "EXCHANGE_MAX_NUM_ALGO_ORDERS",
        "EXCHANGE_MAX_NUM_ICEBERG_ORDERS",
        "EXCHANGE_MAX_NUM_ORDER_LISTS",
    }
)
SUPPORTED_SYMBOL = frozenset(
    {
        "PRICE_FILTER",
        "LOT_SIZE",
        "MIN_NOTIONAL",
        "NOTIONAL",
        "PERCENT_PRICE",
        "PERCENT_PRICE_BY_SIDE",
        "MAX_NUM_ORDERS",
        "MAX_POSITION",
    }
)


def parse_binance_rules(
    exchange_info: CapturedResponse,
    commission: CapturedResponse,
    my_filters: CapturedResponse,
    *,
    account_id: str,
    now_ns: int,
    max_age_ns: int,
    references: tuple[PriceReference, ...] = (),
) -> VenueRulesEvidence:
    """Translate explicit captured inputs, retaining their oldest freshness time.

    Public exchangeInfo is insufficient: private commissions and myFilters must
    be supplied for the same account. Conflicting duplicate public/private rules
    are refused until the collector obtains a consistent revision. Never infer a
    missing fee, empty myFilters, or weighted average from a ticker/bid price.
    """
    try:
        return _parse(
            exchange_info, commission, my_filters, account_id, now_ns, max_age_ns, references
        )
    except (KeyError, TypeError, ArithmeticError, ValueError, AttributeError) as exc:
        if isinstance(exc, VenueInputError):
            raise
        # Do not echo raw private responses in error messages.
        raise VenueInputError("malformed or incomplete venue inputs") from exc


def _parse(exchange_info, commission, my_filters, account_id, now, age, references):
    if type(now) is not int or type(age) is not int or now <= 0 or age <= 0:
        raise VenueInputError("invalid evaluation time/age")
    if not isinstance(account_id, str) or not account_id:
        raise VenueInputError("explicit account identity required")
    if commission.account_id != account_id or my_filters.account_id != account_id:
        raise VenueInputError("private response account mismatch")
    if commission.requested_symbol != "BTCUSDT" or my_filters.requested_symbol != "BTCUSDT":
        raise VenueInputError("private response request symbol mismatch")
    payloads, hashes, timestamps = {}, [], []
    for name, response in (
        ("exchange_info", exchange_info),
        ("commission", commission),
        ("my_filters", my_filters),
    ):
        _fresh(response.received_ns, now, age)
        payloads[name] = json.loads(response.body, object_pairs_hook=_unique_object)
        hashes.append((name, hashlib.sha256(response.body.encode()).hexdigest()))
        timestamps.append(response.received_ns)
    info, fees, private = (payloads[key] for key in ("exchange_info", "commission", "my_filters"))
    symbols = [s for s in info["symbols"] if s["symbol"] == "BTCUSDT"]
    if len(symbols) != 1:
        raise VenueInputError("exactly one BTCUSDT symbol required")
    symbol = symbols[0]
    if (
        symbol["status"] != "TRADING"
        or symbol["isSpotTradingAllowed"] is not True
        or symbol["baseAsset"] != "BTC"
        or symbol["quoteAsset"] != "USDT"
        or not isinstance(symbol["orderTypes"], list)
        or "LIMIT" not in symbol["orderTypes"]
    ):
        raise VenueInputError("BTCUSDT spot LIMIT trading unavailable")
    # Authorization still belongs to the future account adapter; do not infer it
    # from symbol permissionSets or from isSpotTradingAllowed.
    sf, ef = _filters(symbol["filters"]), _filters(info["exchangeFilters"])
    for target, rows in ((sf, private["symbolFilters"]), (ef, private["exchangeFilters"])):
        for name, row in _filters(rows).items():
            if name in target and target[name] != row:
                raise VenueInputError("conflicting public/private filters")
            target[name] = row
    if (
        set(sf) - SUPPORTED_SYMBOL - INAPPLICABLE_SYMBOL
        or set(ef) - {"EXCHANGE_MAX_NUM_ORDERS"} - INAPPLICABLE_EXCHANGE
    ):
        raise VenueInputError("unsupported venue filter")
    price, lot = sf["PRICE_FILTER"], sf["LOT_SIZE"]
    pmin, pmax, tick = (_decimal(price[k]) for k in ("minPrice", "maxPrice", "tickSize"))
    qmin, qmax, step = (_decimal(lot[k]) for k in ("minQty", "maxQty", "stepSize"))
    if qmin <= 0 or qmax < qmin or step <= 0 or (pmax and pmax < pmin):
        raise VenueInputError("invalid PRICE_FILTER/LOT_SIZE bounds")
    if not {"MIN_NOTIONAL", "NOTIONAL"} & set(sf):
        raise VenueInputError("explicit notional rule required")
    nmin, nmax = D("0"), None
    for name in ("MIN_NOTIONAL", "NOTIONAL"):
        if name in sf:
            nmin = max(nmin, _decimal(sf[name]["minNotional"]))
            if name == "NOTIONAL":
                nmax = _decimal(sf[name]["maxNotional"])
                if nmax <= 0:
                    raise VenueInputError("invalid NOTIONAL maximum")
    seen_assets = set()
    if not isinstance(private["assetFilters"], list):
        raise VenueInputError("explicit asset filters required")
    for row in private["assetFilters"]:
        asset = row["asset"]
        if row["filterType"] != "MAX_ASSET" or asset not in {"BTC", "USDT"} or asset in seen_assets:
            raise VenueInputError("unknown/duplicate asset filter")
        seen_assets.add(asset)
        limit = _decimal(row["limit"])
        if limit <= 0:
            raise VenueInputError("invalid MAX_ASSET limit")
        if asset == "BTC":
            qmax = min(qmax, limit)
        else:
            nmax = min(nmax, limit) if nmax is not None else limit
    if qmax < qmin or (nmax is not None and nmin > nmax):
        raise VenueInputError("incompatible intersected venue limits")
    counts = [
        _integer(rows[name]["maxNumOrders"])
        for rows, name in ((sf, "MAX_NUM_ORDERS"), (ef, "EXCHANGE_MAX_NUM_ORDERS"))
        if name in rows
    ]
    max_position = _decimal(sf["MAX_POSITION"]["maxPosition"]) if "MAX_POSITION" in sf else None
    if max_position is not None and max_position <= 0:
        raise VenueInputError("invalid MAX_POSITION")
    bands, reference_types = [], set()
    for ref in references:
        if ref.filter_type in reference_types or ref.filter_type not in {
            "PERCENT_PRICE",
            "PERCENT_PRICE_BY_SIDE",
        }:
            raise VenueInputError("duplicate/unknown price reference")
        reference_types.add(ref.filter_type)
    for name in ("PERCENT_PRICE", "PERCENT_PRICE_BY_SIDE"):
        if name not in sf:
            continue
        row = sf[name]
        minutes = _integer(row["avgPriceMins"])
        matching = [ref for ref in references if ref.filter_type == name]
        if len(matching) != 1:
            raise VenueInputError("missing effective price reference")
        ref = matching[0]
        _fresh(ref.ts_ns, now, age)
        timestamps.append(ref.ts_ns)
        if (
            not isinstance(ref.price, D)
            or not ref.price.is_finite()
            or ref.price <= 0
            or type(ref.average_minutes) is not int
            or ref.average_minutes != minutes
        ):
            raise VenueInputError("invalid price reference/window")
        if ref.kind != "reference_price" and not (
            ref.reference_price_known_absent is True
            and ref.kind == ("last_price" if minutes == 0 else "weighted_average")
        ):
            raise VenueInputError("unverified price-reference precedence")
        for side, prefix in (("BUY", "bid"), ("SELL", "ask")):
            down, up = (
                ("multiplierDown", "multiplierUp")
                if name == "PERCENT_PRICE"
                else (prefix + "MultiplierDown", prefix + "MultiplierUp")
            )
            lower, upper = _decimal(row[down]), _decimal(row[up])
            if lower <= 0 or upper < lower:
                raise VenueInputError("invalid percent-price multipliers")
            bands.append(PriceBand(side, ref.price * lower, ref.price * upper))
    if reference_types - set(sf):
        raise VenueInputError("price reference without matching filter")
    if fees["symbol"] != "BTCUSDT":
        raise VenueInputError("commission symbol mismatch")
    rates = {}
    for liquidity in ("maker", "taker"):
        for side in ("buyer", "seller"):
            rates[liquidity, side] = sum(
                (
                    _decimal(fees[group][liquidity]) + _decimal(fees[group][side])
                    for group in ("standardCommission", "taxCommission", "specialCommission")
                ),
                D("0"),
            )
    fee_bound = max(rates.values())
    if fee_bound >= 1:
        raise VenueInputError("invalid total commission bound")
    discount = fees["discount"]
    if any(type(discount[k]) is not bool for k in ("enabledForAccount", "enabledForSymbol")):
        raise VenueInputError("invalid commission discount flags")
    bnb = discount["enabledForAccount"] and discount["enabledForSymbol"]
    if bnb and discount["discountAsset"] != "BNB":
        raise VenueInputError("unsupported commission discount asset")
    currencies = []
    for side, received in (("buyer", "BTC"), ("seller", "USDT")):
        nonzero = max(rates[liquidity, side] for liquidity in ("maker", "taker")) > 0
        currencies.append(("BNB_OR_" + received if bnb else received) if nonzero else "USDT")
    rules = InstrumentRules(
        "BTCUSDT.BINANCE",
        min(timestamps),
        qmin,
        qmax,
        step,
        pmin,
        pmax,
        tick,
        nmin,
        nmax,
        fee_bound,
        buy_fee_currency=currencies[0],
        sell_fee_currency=currencies[1],
        price_bands=tuple(bands),
        max_open_orders=min(counts) if counts else None,
        max_position=max_position,
    )
    return VenueRulesEvidence(
        rules,
        account_id,
        tuple(hashes),
        tuple(sorted((set(sf) & INAPPLICABLE_SYMBOL) | (set(ef) & INAPPLICABLE_EXCHANGE))),
        tuple(references),
    )

"""Prepare a bounded lifecycle-test proposal; never an executable order payload."""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from apps.strategies_nautilus.portfolio_venue import _decimal, _filters


def lifecycle_test_plan(info, books):
    """Fixed engineering quantity; neither portfolio sizing nor an alpha identity."""
    quantity, debit_cap = Decimal("0.0001"), Decimal("10")
    plan = {
        "schema_version": "portfolio.testnet_lifecycle_plan.v1",
        "status": "draft_not_executable",
        "environment": "binance_spot_testnet",
        "instrument_id": "BTCUSDT.BINANCE",
        "scope": "single BUY then cancel; at most one owned-inventory cleanup SELL",
        "fixed_buy_quantity_btc": str(quantity),
        "max_total_buy_quote_debit_usdt": str(debit_cap),
        "maximum_buy_submissions": 1,
        "maximum_total_order_submissions": 2,
        "maximum_outstanding_orders": 1,
        "maximum_session_seconds": 180,
        "cancel_after_acceptance_seconds": 2,
        "cleanup_policy": "whole_steps_v1; retain exact residual ownership; no dust sweep",
        "retry_policy": "no automatic resubmit, replacement, amendment or second BUY",
        "expected_baseline": "qualified account/UTC-day baseline and native recovery state",
        "signal_boundary": "reviewed fixture SignalEvent v1 -> Nautilus Strategy -> risk -> execution",
        "research_or_legacy_source_promotion": False,
        "illustrative_buy_limit_price": None,
        "illustrative_buy_notional_usdt": None,
        "captured_basic_filter_checks_passed": False,
        "fee_budget_verified": False,
        "effective_filters_verified": False,
        "runner_wired": False,
        "execution_authorized": False,
        "testnet_order_ready": False,
        "runtime_ready": False,
        "remaining_checks": [
            "qualify account identity, key permissions, valuation and day-open history",
            "verify actual commission currency, fee rounding and 10 USDT total debit cap",
            "verify effective myFilters, average-price bands and full current batch risk",
            "qualify fixture consumer identity and native testnet adapter integration",
            "prove uncertain-submit/cancel and abrupt-process recovery with preserved latches",
            "review concrete test session scope before any order run",
        ],
    }
    try:
        symbol = next(row for row in info["symbols"] if row["symbol"] == "BTCUSDT")
        book = next(row for row in books if row["symbol"] == "BTCUSDT")
        filters = _filters(symbol["filters"])
        price_rule, lot, notional = (
            filters[name] for name in ("PRICE_FILTER", "LOT_SIZE", "NOTIONAL")
        )
        tick, step = _decimal(price_rule["tickSize"]), _decimal(lot["stepSize"])
        if tick <= 0 or step <= 0:
            return plan
        price = (_decimal(book["bidPrice"]) / tick).to_integral_value(
            rounding=ROUND_FLOOR
        ) * tick - tick
        amount = price * quantity
        passed = (
            symbol["status"] == "TRADING"
            and symbol["isSpotTradingAllowed"] is True
            and "LIMIT" in symbol["orderTypes"]
            and price > 0
            and _decimal(book["bidQty"]) > 0
            and _decimal(price_rule["minPrice"]) <= price <= _decimal(price_rule["maxPrice"])
            and _decimal(lot["minQty"]) <= quantity <= _decimal(lot["maxQty"])
            and quantity % step == 0
            and _decimal(notional["minNotional"]) <= amount <= _decimal(notional["maxNotional"])
            and amount < debit_cap
        )
        if passed:
            plan.update(
                illustrative_buy_limit_price=str(price),
                illustrative_buy_notional_usdt=str(amount),
                captured_basic_filter_checks_passed=True,
            )
    except (StopIteration, KeyError, ValueError, TypeError, ArithmeticError):
        pass  # partial public filters cannot become order readiness
    return plan

from __future__ import annotations

import asyncio
import copy
from decimal import Decimal as D

import pytest
from nautilus_trader.accounting.accounts.cash import CashAccount
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import LiveExecEngineConfig, StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.events import AccountState, OrderFilled
from nautilus_trader.model.identifiers import AccountId, PositionId, StrategyId, TraderId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import AccountBalance, Money, Price, Quantity
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.events import TestEventStubs
from nautilus_trader.test_kit.stubs.execution import TestExecStubs
from nautilus_trader.trading.strategy import Strategy

from apps.strategies_nautilus.portfolio_adapter_recovery import (
    AdapterRecoveryError,
    EvidenceOnlyExecutionEngine,
    reconcile_binance_reports,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND


@pytest.fixture
def recovery():
    loop = asyncio.new_event_loop()
    clock = TestClock()
    clock.set_time(BASE_NS + 10 * SECOND)
    bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
    cache = Cache()
    portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
    engine = EvidenceOnlyExecutionEngine(
        loop=loop,
        msgbus=bus,
        cache=cache,
        clock=clock,
        config=LiveExecEngineConfig(filter_unclaimed_external_orders=False),
    )
    fields = CurrencyPair.to_dict(TestInstrumentProvider.btcusdt_binance())
    fields.update(size_precision=8, size_increment="0.00000100", maker_fee="0", taker_fee="0")
    inst = CurrencyPair.from_dict(fields)
    cache.add_instrument(inst)
    aid = AccountId("BINANCE-001")
    account = CashAccount(
        AccountState(
            account_id=aid,
            account_type=AccountType.CASH,
            base_currency=None,
            balances=[
                AccountBalance(Money(500, USDT), Money(0, USDT), Money(500, USDT)),
                AccountBalance(Money(0, BTC), Money(0, BTC), Money(0, BTC)),
            ],
            margins=[],
            reported=True,
            info={},
            event_id=UUID4(),
            ts_event=BASE_NS,
            ts_init=BASE_NS,
        ),
        calculate_account_state=True,
    )
    cache.add_account(account)
    sid = StrategyId("PORTFOLIO-FIXTURE-PF")
    strategy = Strategy(
        StrategyConfig(strategy_id="PORTFOLIO-FIXTURE", order_id_tag="PF", oms_type="HEDGING")
    )
    assert strategy.id == sid
    engine.register_oms_type(strategy)
    order = TestExecStubs.limit_order(
        instrument=inst,
        strategy_id=sid,
        quantity=Quantity.from_str("0.00100000"),
        price=Price.from_str("100000.00"),
    )
    order.apply(TestEventStubs.order_submitted(order, account_id=aid, ts_event=BASE_NS))
    cache.add_order(order, position_id=PositionId("v16-original"))
    portfolio.initialize_orders()
    portfolio.initialize_positions()
    yield engine, cache, account, order, aid
    engine.dispose()
    loop.close()


def bodies(order, *, status="FILLED", partial=False):
    qty = "0.00033300" if partial else "0.00100000"
    row = {
        "symbol": "BTCUSDT",
        "orderId": 123,
        "clientOrderId": str(order.client_order_id),
        "price": "100000.00",
        "origQty": "0.00100000",
        "executedQty": qty,
        "cummulativeQuoteQty": "33.300000" if partial else "100.000000",
        "status": status,
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
        "time": BASE_NS // 1_000_000,
        "updateTime": (BASE_NS + 2 * SECOND) // 1_000_000,
        "orderListId": -1,
    }
    trade = {
        "symbol": "BTCUSDT",
        "orderId": 123,
        "id": 456,
        "price": "100000.00",
        "qty": qty,
        "quoteQty": row["cummulativeQuoteQty"],
        "commission": "0.00000050" if partial else "0.00000150",
        "commissionAsset": "BTC",
        "isBuyer": True,
        "isMaker": True,
        "time": (BASE_NS + SECOND) // 1_000_000,
    }
    return [row], [trade]


def apply(case, rows, trades):
    engine, cache, _, _, aid = case
    reconcile_binance_reports(
        engine, cache, account_id=aid, orders=rows, trades=trades, now_ns=BASE_NS + 10 * SECOND
    )


def test_native_binance_reports_resolve_submitted_order_and_actual_base_fee(recovery):
    _, cache, account, order, _ = recovery
    rows, trades = bodies(order)
    apply(recovery, rows, trades)
    assert order.status.name == "FILLED"
    assert order.filled_qty.as_decimal() == D("0.001")
    assert cache.positions()[0].quantity.as_decimal() == D("0.00099850")
    assert str(cache.positions()[0].id) == "v16-original"
    assert account.balance_total(BTC).as_decimal() == D("0.00099850")
    assert account.balance_total(USDT).as_decimal() == D("400")
    apply(recovery, rows, trades)
    assert len([e for e in order.events if isinstance(e, OrderFilled)]) == 1
    assert account.balance_total(BTC).as_decimal() == D("0.00099850")


def test_native_recovery_applies_late_fill_then_terminal_cancel(recovery):
    _, cache, account, order, _ = recovery
    rows, trades = bodies(order, status="PARTIALLY_FILLED", partial=True)
    apply(recovery, rows, trades)
    order.apply(TestEventStubs.order_pending_cancel(order))
    rows = copy.deepcopy(rows)
    rows[0].update(status="CANCELED", executedQty="0.00066600", cummulativeQuoteQty="66.600000")
    trades = [*trades, {**trades[0], "id": 457, "time": (BASE_NS + 2 * SECOND) // 1_000_000}]
    apply(recovery, rows, trades)
    assert order.status.name == "CANCELED"
    assert order.filled_qty.as_decimal() == D("0.00066600")
    assert cache.positions()[0].quantity.as_decimal() == D("0.00066500")
    assert account.balance_total(USDT).as_decimal() == D("433.4")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r, t: t.clear(),
        lambda r, t: t.append(t[0]),
        lambda r, t: t[0].update(commissionAsset="BNB"),
        lambda r, t: t[0].update(commission="0.0001"),
        lambda r, t: t[0].update(commission="0.000001499"),
        lambda r, t: t[0].update(price="100000.001", quoteQty="100.000001"),
        lambda r, t: t[0].update(qty="0.00099950"),
        lambda r, t: t[0].update(isBuyer=False),
        lambda r, t: t[0].update(time=0),
        lambda r, t: r[0].update(clientOrderId="external"),
        lambda r, t: r[0].update(status="NEW"),
        lambda r, t: r[0].update(origQty="0.002"),
    ],
)
def test_incomplete_or_conflicting_reports_cannot_mutate_native_state(recovery, mutation):
    _, cache, account, order, _ = recovery
    rows, trades = bodies(order)
    mutation(rows, trades)
    with pytest.raises(ValueError):
        apply(recovery, rows, trades)
    assert order.status.name == "SUBMITTED"
    assert not cache.positions()
    assert account.balance_total(USDT).as_decimal() == 500


def test_existing_trade_cannot_change_commission_on_replay(recovery):
    order = recovery[3]
    rows, trades = bodies(order)
    apply(recovery, rows, trades)
    trades[0]["commission"] = "0.00000149"
    with pytest.raises(AdapterRecoveryError, match="historical native fill conflict"):
        apply(recovery, rows, trades)


def test_isolated_native_engine_rejects_clients_commands_and_inference(recovery):
    engine = recovery[0]
    for method in (
        engine.register_client,
        engine.register_default_client,
        engine.register_venue_routing,
        engine.execute,
        engine._generate_inferred_fill,
    ):
        with pytest.raises(AdapterRecoveryError):
            method(None)


@pytest.mark.parametrize(
    "status, expected", [("NEW", "ACCEPTED"), ("CANCELED", "CANCELED"), ("EXPIRED", "EXPIRED")]
)
def test_no_fill_recovery_does_not_create_inventory(recovery, status, expected):
    _, cache, account, order, _ = recovery
    rows, _ = bodies(order, status=status)
    rows[0].update(executedQty="0", cummulativeQuoteQty="0")
    apply(recovery, rows, [])
    assert order.status.name == expected
    assert not cache.positions()
    assert account.balance_total(USDT).as_decimal() == 500


def test_actual_quote_commission_is_preserved(recovery):
    _, cache, account, order, _ = recovery
    rows, trades = bodies(order)
    trades[0].update(commissionAsset="USDT", commission="0.15")
    apply(recovery, rows, trades)
    assert cache.positions()[0].quantity.as_decimal() == D("0.001")
    assert account.balance_total(USDT).as_decimal() == D("399.85")


def test_terminal_order_cannot_be_reopened(recovery):
    rows, trades = bodies(recovery[3], status="CANCELED", partial=True)
    apply(recovery, rows, trades)
    rows[0]["status"] = "PARTIALLY_FILLED"
    with pytest.raises(AdapterRecoveryError, match="terminal native"):
        apply(recovery, rows, trades)


def test_native_success_boolean_does_not_replace_exact_postconditions(recovery, monkeypatch):
    rows, trades = bodies(recovery[3])
    monkeypatch.setattr(recovery[0], "_reconcile_execution_mass_status", lambda reports: True)
    with pytest.raises(AdapterRecoveryError, match="postcondition failed"):
        apply(recovery, rows, trades)

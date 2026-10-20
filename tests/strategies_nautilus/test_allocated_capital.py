"""Synthetic engine tests for the strategy's quote-currency capital sleeve."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import PositionId, StrategyId, TraderId
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.model.position import Position
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.events import TestEventStubs

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import Authorization, SourcePolicy
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    BaselineNautilusStrategy,
    BaselineNautilusStrategyParams,
)
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig


class RecordingStrategy(BaselineNautilusStrategy):
    def __init__(self, params):
        super().__init__(params)
        self.fills = []
        self.marks = []

    def on_order_filled(self, event):
        super().on_order_filled(event)
        self.fills.append((event, self.sleeve_cash, self.sleeve_equity, self._net_position()))

    def on_bar(self, bar):
        super().on_bar(bar)
        self.marks.append((self.sleeve_cash, self.sleeve_equity, self._net_position()))


@pytest.fixture
def sleeve_run(make_payload):
    engines = []

    def run(
        *,
        allocated=Decimal(1000),
        fraction=Decimal(".4"),
        prices=(50_000, 100_000, 25_000, 30_000, 30_000),
        events=(("entry", 0, "buy"), ("close", 3, "sell")),
        balances=None,
        weekday=6,
        policy=None,
        trade_size=Decimal(0),
        trade_notional=None,
        restored=(),
    ):
        instrument = TestInstrumentProvider.btcusdt_binance()
        bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
        times = pd.DatetimeIndex([
            "2026-01-01T00:00:00Z",
            "2026-01-05T00:00:00Z",
            "2026-01-12T00:00:00Z",
            "2026-01-13T00:00:00Z",
            "2026-01-13T00:01:00Z",
        ][:len(prices)])
        signals = [
            SignalEvent.model_validate(make_payload(
                signal_id=signal_id, ts_event=times[row].value, side=side
            ))
            for signal_id, row, side in events
        ]
        params = BaselineNautilusStrategyParams(
            instrument_id=instrument.id,
            bar_type=bar_type,
            baseline_config=BaselineStrategyConfig(
                venue="BINANCE",
                auth=Authorization(
                    allowed_sources=frozenset({"freqai_v1"}),
                    allowed_model_versions=frozenset({"2026-05-14"}),
                    policies={("freqai_v1", "2026-05-14"): policy} if policy else {},
                ),
                min_confidence=.5,
            ),
            trade_size=trade_size,
            trade_notional=trade_notional,
            equity_currency=USDT,
            target_equity_fraction=fraction,
            rebalance_weekday=weekday,
            allocated_capital=allocated,
            signals=signals,
        )
        engine = BacktestEngine(config=BacktestEngineConfig(
            trader_id=TraderId("SLEEVE-001"),
            logging=LoggingConfig(bypass_logging=True),
        ))
        engines.append(engine)
        engine.add_venue(
            venue=instrument.id.venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            starting_balances=balances or [Money(10_000, USDT), Money(1, BTC)],
            base_currency=None,
        )
        engine.add_instrument(instrument)
        frame = pd.DataFrame(
            {"open": prices, "high": prices, "low": prices,
             "close": prices, "volume": 100.0},
            index=times,
        )
        engine.add_data(BarDataWrangler(bar_type, instrument).process(frame))
        strategy = RecordingStrategy(params)
        engine.add_strategy(strategy)
        for owner, quantity in restored:
            strategy_id = strategy.id if owner == "own" else StrategyId("Other-000")
            order = strategy.order_factory.market(
                instrument_id=instrument.id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(quantity),
            )
            fill = TestEventStubs.order_filled(
                order,
                instrument,
                strategy_id=strategy_id,
                position_id=PositionId(f"{instrument.id}-{strategy_id}"),
                last_px=instrument.make_price(prices[0]),
            )
            engine.cache.add_position(Position(instrument, fill), OmsType.NETTING)
        engine.run()
        assert engine.get_result().iterations == len(prices)
        return strategy, engine, instrument

    yield run
    for engine in engines:
        engine.dispose()


@pytest.mark.parametrize("multiplier", [1.0, .5])
def test_faucet_assets_do_not_inflate_allocated_entry(sleeve_run, multiplier):
    strategy, _, _ = sleeve_run(policy=SourcePolicy(position_pct_multiplier=multiplier))
    assert strategy.fills[0][0].last_qty.as_decimal() == Decimal(".008") * Decimal(str(multiplier))
    assert strategy.fills[0][1] == Decimal(1000) - Decimal(400) * Decimal(str(multiplier)) * Decimal("1.001")


def test_sleeve_buy_reduce_top_up_close_books_fills_and_fees(sleeve_run):
    strategy, _, _ = sleeve_run()
    # 400 + .4 fee; then sell .002402 BTC at 100k; buy .010074 at 25k;
    # finally close .015672 at 30k. Each fill charges a .1% quote fee.
    assert [row[0].order_side for row in strategy.fills] == [
        OrderSide.BUY, OrderSide.SELL, OrderSide.BUY, OrderSide.SELL,
    ]
    expected = [
        (".008", "599.6", "999.6", ".008"),
        (".002402", "839.5598", "1399.3598", ".005598"),
        (".010074", "587.45795", "979.25795", ".015672"),
        (".015672", "1057.14779", "1057.14779", "0"),
    ]
    for (fill, cash, equity, quantity), values in zip(strategy.fills, expected, strict=True):
        assert (fill.last_qty.as_decimal(), cash, equity, quantity) == tuple(map(Decimal, values))
        assert fill.commission.as_decimal() == fill.last_qty.as_decimal() * fill.last_px.as_decimal() * Decimal(".001")
    assert strategy.sleeve_cash == strategy.sleeve_equity == Decimal("1057.14779")
    with pytest.raises(AttributeError):
        strategy.sleeve_cash = Decimal(0)
    with pytest.raises(AttributeError):
        strategy.sleeve_equity = Decimal(0)


@pytest.mark.parametrize("quote_balance", [100, 10_000])
def test_sleeve_buy_respects_sleeve_and_account_cash_caps(sleeve_run, quote_balance):
    strategy, _, instrument = sleeve_run(
        fraction=Decimal(1), weekday=None,
        balances=[Money(quote_balance, USDT), Money(1, BTC)],
        events=(("entry", 0, "buy"), ("close", 1, "flat")),
        prices=(50_000, 50_000),
    )
    budget = min(Decimal(1000), Decimal(quote_balance))
    expected = instrument.make_qty(budget / Decimal(50050), round_down=True).as_decimal()
    assert strategy.fills[0][0].last_qty.as_decimal() == expected
    assert strategy.fills[0][1] >= 0
    assert strategy.fills[0][1] == Decimal(1000) - expected * Decimal(50050)


def test_allocation_equal_to_account_reproduces_account_fraction(sleeve_run):
    allocated, _, _ = sleeve_run(allocated=Decimal(10_000), balances=[Money(10_000, USDT)])
    account, _, _ = sleeve_run(allocated=None, balances=[Money(10_000, USDT)])
    assert len(allocated.fills) == len(account.fills)
    for left, right in zip(allocated.fills, account.fills, strict=True):
        assert left[0].order_side == right[0].order_side
        assert abs(left[0].last_qty.as_decimal() - right[0].last_qty.as_decimal()) <= Decimal(".000001")
    assert allocated.sleeve_cash == account.portfolio.account(allocated.instrument_id.venue).balance_total(USDT).as_decimal()
    assert account.sleeve_cash is None and account.sleeve_equity is None


def test_opening_mark_and_rebalance_use_only_strategy_positions(sleeve_run):
    strategy, _, _ = sleeve_run(
        restored=(("own", Decimal(".008")), ("other", Decimal(".1"))),
    )
    # The first buy is a no-op because this strategy already owns .008 BTC.
    # Existing holdings are charged at the first close without a new fee.
    assert strategy.marks[0] == (Decimal(600), Decimal(1000), Decimal(".008"))
    assert strategy.fills[0][0].order_side == OrderSide.SELL
    assert strategy.fills[0][0].last_qty.as_decimal() == Decimal(".0024")
    assert strategy.fills[0][2] == Decimal("1399.76")
    assert len(strategy.cache.positions_open(strategy_id=StrategyId("Other-000"))) == 1


def test_other_strategy_position_does_not_block_sleeve_entry(sleeve_run):
    strategy, _, _ = sleeve_run(restored=(("other", Decimal(".1")),))
    assert strategy.fills[0][0].order_side == OrderSide.BUY
    assert strategy.fills[0][0].last_qty.as_decimal() == Decimal(".008")


@pytest.mark.parametrize("commission_currency, fee", [(USDT, "1"), (BTC, ".00002")])
def test_quote_and_base_commissions_are_booked_at_fill_price(
    sleeve_run, commission_currency, fee,
):
    strategy, engine, instrument = sleeve_run()
    first = strategy.fills[0][0]
    fill = TestEventStubs.order_filled(
        engine.cache.order(first.client_order_id), instrument,
        last_qty=instrument.make_qty(".001"),
        last_px=instrument.make_price(50_000),
        commission=Money(Decimal(fee), commission_currency),
    )
    cash = strategy.sleeve_cash
    strategy.on_order_filled(fill)
    assert strategy.sleeve_cash == cash - Decimal(51)


def test_foreign_commission_warns_once_and_unrelated_fills_are_ignored(sleeve_run, monkeypatch):
    strategy, engine, instrument = sleeve_run()
    first = strategy.fills[0][0]
    logger = SimpleNamespace(warning=Mock())
    monkeypatch.setattr(RecordingStrategy, "log", logger)
    order = engine.cache.order(first.client_order_id)
    fill = TestEventStubs.order_filled(
        order, instrument, last_qty=instrument.make_qty(".001"),
        last_px=instrument.make_price(50_000),
        commission=Money(1, Currency.from_str("BNB")),
    )
    cash = strategy.sleeve_cash
    strategy.on_order_filled(fill)
    strategy.on_order_filled(fill)
    assert strategy.sleeve_cash == cash - Decimal(100)
    logger.warning.assert_called_once()
    foreign = TestEventStubs.order_filled(order, instrument, strategy_id=StrategyId("Other-000"))
    strategy.on_order_filled(foreign)
    assert strategy.sleeve_cash == cash - Decimal(100)
    other_instrument = TestInstrumentProvider.ethusdt_binance()
    foreign = SimpleNamespace(strategy_id=strategy.id, instrument_id=other_instrument.id)
    strategy.on_order_filled(foreign)
    assert strategy.sleeve_cash == cash - Decimal(100)


@pytest.mark.parametrize("allocated", [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_allocations_rejected(sleeve_run, allocated):
    with pytest.raises(ValueError, match="allocated_capital"):
        sleeve_run(allocated=allocated)


def test_allocation_requires_equity_fraction(sleeve_run):
    with pytest.raises(ValueError, match="allocated_capital requires target_equity_fraction"):
        sleeve_run(fraction=None, weekday=None, trade_size=Decimal(".001"))


@pytest.mark.parametrize("notional", [None, Decimal(100)])
def test_old_sizing_modes_keep_no_sleeve(sleeve_run, notional):
    strategy, _, _ = sleeve_run(
        allocated=None, fraction=None, weekday=None,
        trade_size=Decimal(".001"), trade_notional=notional,
    )
    assert strategy.fills[0][0].last_qty.as_decimal() == (
        Decimal(".001") if notional is None else Decimal(".002")
    )
    assert strategy.sleeve_cash is None and strategy.sleeve_equity is None


@pytest.mark.parametrize("dry_run", [False, True])
def test_allocation_does_not_bypass_kill_switch_or_dry_run(sleeve_run, monkeypatch, dry_run):
    if not dry_run:
        update = BaselineNautilusStrategy._update_daily_risk_state

        def with_loss(strategy, now_ns):
            update(strategy, now_ns)
            strategy._baseline.on_account_update(equity_open=1000, equity_now=900)

        monkeypatch.setattr(BaselineNautilusStrategy, "_update_daily_risk_state", with_loss)
    strategy, _, _ = sleeve_run(policy=SourcePolicy(dry_run=dry_run))
    assert not strategy.fills
    assert strategy.sleeve_cash == strategy.sleeve_equity == Decimal(1000)


def test_sleeve_starts_at_first_bar_even_without_account(sleeve_run, monkeypatch):
    run, _, instrument = sleeve_run()
    strategy = BaselineNautilusStrategy(replace(run._params, signals=[], rebalance_weekday=None))
    assert strategy.sleeve_cash is None and strategy.sleeve_equity is None
    monkeypatch.setattr(
        BaselineNautilusStrategy, "portfolio",
        SimpleNamespace(account=lambda venue: None, equity=lambda **kwargs: {}),
    )
    monkeypatch.setattr(
        BaselineNautilusStrategy, "cache", SimpleNamespace(positions_open=lambda **kwargs: []),
    )
    strategy.on_bar(SimpleNamespace(ts_event=0, close=instrument.make_price(50_000)))
    assert strategy.sleeve_cash == strategy.sleeve_equity == Decimal(1000)
    assert strategy._sizing_equity(instrument) == Decimal(1000)


def test_close_then_reentry_sizes_from_realized_sleeve_cash(sleeve_run):
    strategy, _, instrument = sleeve_run(
        weekday=None,
        events=(("entry", 0, "buy"), ("close", 1, "sell"),
                ("reentry", 2, "buy"), ("final-close", 3, "flat")),
    )
    # Buy .008 at 50k; close at 100k: 599.6 + 800 - .8 = 1398.8.
    assert strategy.fills[1][1] == strategy.fills[1][2] == Decimal("1398.8")
    expected = instrument.make_qty(Decimal(".4") * Decimal("1398.8") / Decimal(25_000), round_down=True)
    assert strategy.fills[2][0].last_qty == expected
    assert len(strategy.fills) == 4
    assert strategy.sleeve_cash == strategy.sleeve_equity

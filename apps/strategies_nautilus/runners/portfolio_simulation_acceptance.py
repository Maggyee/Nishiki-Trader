"""Deterministic synthetic acceptance harness using the real Nautilus backtest engine.

No exchange adapter, credentials, retained research signals or market downloads.
Not a paper promotion runner. Fixture quotes do not constitute PnL evidence.
"""

from __future__ import annotations

from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.portfolio_simulation import (
    INSTRUMENT,
    MODEL,
    D,
    PortfolioSimulationStrategy,
)

BASE_NS = 1_767_225_600_000_000_000  # synthetic 2026-01-01, no historical market data
SECOND = 1_000_000_000


def fixture_signal(sleeve, suffix, ts_ns, side="buy"):
    return SignalEvent(
        schema_version="signal.v1",
        signal_id=f"fixture:{sleeve}:{suffix}",
        source=f"rule_fixture_{sleeve}",
        model_version=MODEL,
        symbol="BTCUSDT",
        venue="BINANCE",
        ts_event=ts_ns,
        horizon="1m",
        side=side,
        score=0.8 if side == "buy" else 0.0,
        confidence=0.9,
        ttl_seconds=60,
        metadata={"fixture": True},
    )


class ScriptedSimulation(PortfolioSimulationStrategy):
    def __init__(self, checkpoint, actions=None):
        super().__init__(checkpoint)
        self.actions = actions or {}

    def on_quote_tick(self, quote):
        super().on_quote_tick(quote)
        action = self.actions.get(quote.ts_event)
        if action:
            action(self)


def build_simulation(checkpoint: Path, actions=None, *, cancel_latency_ns=0):
    instrument = TestInstrumentProvider.btcusdt_binance()
    fields = CurrencyPair.to_dict(instrument)
    fields.update(maker_fee="0.0015", taker_fee="0.0015")
    instrument = CurrencyPair.from_dict(fields)
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    engine.add_venue(
        INSTRUMENT.venue,
        OmsType.HEDGING,
        AccountType.CASH,
        [Money(500, USDT), Money(0, BTC)],
        latency_model=LatencyModel(base_latency_nanos=0, cancel_latency_nanos=cancel_latency_ns),
        liquidity_consumption=True,
        allow_cash_borrowing=False,
    )
    engine.add_instrument(instrument)
    strategy = ScriptedSimulation(checkpoint, actions)
    engine.add_strategy(strategy)
    return engine, strategy, instrument


def quote(instrument, ts_ns, *, bid="100000", ask="100010", size="1"):
    return QuoteTick(
        INSTRUMENT,
        instrument.make_price(D(bid)),
        instrument.make_price(D(ask)),
        instrument.make_qty(D(size)),
        instrument.make_qty(D(size)),
        ts_ns,
        ts_ns,
    )


def advance(engine, instrument, start_ns, *, bid="100000", ask="100010", size="1"):
    engine.clear_data()
    engine.add_data(
        [
            quote(instrument, start_ns, bid=bid, ask=ask, size=size),
            quote(instrument, start_ns + SECOND, bid=bid, ask=ask, size=size),
        ]
    )
    engine.run(streaming=True)


def restart_strategy(engine, strategy, actions=None):
    engine.trader.stop()
    engine.trader.remove_strategy(strategy.id)
    replacement = ScriptedSimulation(strategy.checkpoint, actions)
    engine.add_strategy(replacement)
    replacement.clock.set_time(strategy.clock.timestamp_ns())
    engine.trader.start_strategy(replacement.id)
    engine.trader.resume()
    return replacement


def run_acceptance(checkpoint: Path) -> dict:
    """Run a fixed synthetic smoke scenario, failing on any accounting drift."""
    from apps.ops.portfolio_execution_plan import SLEEVES
    from apps.strategies_nautilus.portfolio_simulation import SimulationBlocked

    admissions = []

    def submit(strategy):
        admissions.append(
            strategy.process_signals(
                tuple(fixture_signal(sleeve, "initial", BASE_NS - 1) for sleeve in SLEEVES)
            )
        )
        admissions.append(strategy.process_signals((fixture_signal("v36", "second", BASE_NS),)))

    engine, strategy, instrument = build_simulation(checkpoint, {BASE_NS: submit})
    try:
        advance(engine, instrument, BASE_NS)
        first, second = admissions
        if (
            len(first.selected) != 4
            or first.preflight.required_quote != D("400.60")
            or second.selected
            or second.preflight.available_quote != D("99.40")
        ):
            raise SimulationBlocked("funded admission / reservation acceptance failed")
        strategy = restart_strategy(engine, strategy)
        advance(engine, instrument, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        snapshot = strategy.snapshot()
        if snapshot.total_base != D("0.004") or snapshot.total_quote != D("99.40"):
            raise SimulationBlocked("native fill accounting acceptance failed")
        reduction = strategy.process_signals(
            (fixture_signal("v18", "flat", BASE_NS + 2 * SECOND, "flat"),)
        )
        advance(engine, instrument, BASE_NS + 4 * SECOND)
        snapshot = strategy.snapshot()
        if (
            len(reduction.selected) != 1
            or dict(snapshot.holdings)["v18"] != 0
            or snapshot.total_base != D("0.003")
            or snapshot.total_quote != D("199.25")
        ):
            raise SimulationBlocked("sleeve reduction acceptance failed")
        return {
            "status": "passed",
            "scope": "synthetic_nautilus_lifecycle_only",
            "performance_evidence": False,
            "selected_sleeves": [c.order.sleeve for c in first.selected],
            "skipped_sleeves": ["v36"],
            "required_quote_usdt": str(first.preflight.required_quote),
            "second_batch_available_usdt": str(second.preflight.available_quote),
            "native_order_count": len(engine.cache.orders()),
            "final_quote_usdt": str(snapshot.total_quote),
            "final_base_btc": str(snapshot.total_base),
            "holdings_btc": {sleeve: str(qty) for sleeve, qty in snapshot.holdings},
            "warm_restart": "passed",
        }
    finally:
        engine.end()
        engine.dispose()


def main() -> int:
    import json
    import tempfile

    # No paths, credentials or research inputs accepted: this is a bounded fixture.
    with tempfile.TemporaryDirectory(prefix="trader-portfolio-acceptance-") as directory:
        report = run_acceptance(Path(directory) / "checkpoint.json")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic synthetic acceptance harness using the real Nautilus backtest engine.

No exchange adapter, credentials, retained research signals or market downloads.
Not a paper promotion runner. Fixture quotes do not constitute PnL evidence.
"""

from __future__ import annotations

from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FeeModel, LatencyModel
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.portfolio_inventory import EXIT_POLICIES
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


class ReceivedAssetFeeModel(FeeModel):
    """Synthetic 15 bps received-asset commission through Nautilus's fee hook.

    Price matching, fills, cash and position adjustments remain native. This
    extension is a fixture, not a Binance account fee provider.
    """

    def get_commission(self, order, fill_qty, fill_px, instrument):
        quantity = fill_qty.as_decimal()
        if quantity % instrument.size_increment.as_decimal():
            raise ValueError("synthetic fill must respect the venue quantity grid")
        if order.side == OrderSide.BUY:
            return Money(quantity * D("0.0015"), BTC)
        if order.side == OrderSide.SELL:
            return Money(quantity * fill_px.as_decimal() * D("0.0015"), USDT)
        raise ValueError("unsupported synthetic order side")


class ScriptedSimulation(PortfolioSimulationStrategy):
    def __init__(self, checkpoint, actions=None, *, fee_mode="quote", exit_policy="exact_v1"):
        super().__init__(checkpoint, fee_mode=fee_mode, exit_policy=exit_policy)
        self.actions = actions or {}

    def on_quote_tick(self, quote):
        super().on_quote_tick(quote)
        action = self.actions.get(quote.ts_event)
        if action:
            action(self)


def build_simulation(
    checkpoint: Path, actions=None, *, cancel_latency_ns=0, fee_mode="quote", exit_policy="exact_v1"
):
    instrument = TestInstrumentProvider.btcusdt_binance()
    fields = CurrencyPair.to_dict(instrument)
    fields.update(maker_fee="0.0015", taker_fee="0.0015")
    if fee_mode == "received_asset":
        # Native position adjustments round to size_precision. Retain BTC's
        # 8-place ledger precision WITHOUT changing the 0.000001 order step.
        fields.update(size_precision=8, size_increment="0.00000100", maker_fee="0", taker_fee="0")
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
        fee_model=ReceivedAssetFeeModel() if fee_mode == "received_asset" else None,
    )
    engine.add_instrument(instrument)
    strategy = ScriptedSimulation(checkpoint, actions, fee_mode=fee_mode, exit_policy=exit_policy)
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
    replacement = ScriptedSimulation(
        strategy.checkpoint, actions, fee_mode=strategy.fee_mode, exit_policy=strategy.exit_policy
    )
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


def run_received_asset_acceptance(checkpoint: Path) -> dict:
    """Verify native net inventory and the unchanged no-rounding exit contract."""
    from dataclasses import asdict

    from apps.ops.portfolio_execution_plan import SLEEVES
    from apps.strategies_nautilus.portfolio_simulation import SimulationBlocked

    def submit(strategy):
        strategy.process_signals(tuple(fixture_signal(s, "received-fee", BASE_NS) for s in SLEEVES))

    engine, strategy, instrument = build_simulation(
        checkpoint, {BASE_NS: submit}, fee_mode="received_asset"
    )
    try:
        advance(engine, instrument, BASE_NS)
        advance(engine, instrument, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        strategy = restart_strategy(engine, strategy)
        advance(engine, instrument, BASE_NS + 4 * SECOND)
        snapshot = strategy.snapshot()
        diagnostics = strategy.inventory_diagnostics()
        reduction = strategy.process_signals(
            (fixture_signal("v16", "full-exit", BASE_NS + 4 * SECOND, "flat"),)
        )
        if (
            snapshot.total_base != D("0.003994")
            or snapshot.total_quote != D("100")
            or len(engine.cache.orders()) != 4
            or reduction.selected
            or reduction.skipped[0].reasons != ("quantity_step",)
            or diagnostics[0].step_remainder != D("0.00000050")
        ):
            raise SimulationBlocked("received-asset native accounting acceptance failed")
        return {
            "status": "passed",
            "scope": "synthetic_received_asset_fee_accounting",
            "performance_evidence": False,
            "runtime_ready": False,
            "native_order_count": len(engine.cache.orders()),
            "total_quote_usdt": str(snapshot.total_quote),
            "net_base_btc": str(snapshot.total_base),
            "full_exit": "blocked_quantity_step_without_rounding",
            "inventory": [asdict(row) for row in diagnostics],
            "warm_restart": "passed",
        }
    finally:
        engine.end()
        engine.dispose()


def run_residual_exit_acceptance(checkpoint: Path, *, fee_mode: str = "received_asset") -> dict:
    """Sell whole steps natively and retain exact residual ownership across restart."""
    from dataclasses import asdict

    from apps.ops.portfolio_execution_plan import SLEEVES
    from apps.strategies_nautilus.portfolio_simulation import SimulationBlocked

    def submit(strategy):
        strategy.process_signals(tuple(fixture_signal(s, "entry", BASE_NS) for s in SLEEVES))

    engine, strategy, instrument = build_simulation(
        checkpoint, {BASE_NS: submit}, fee_mode=fee_mode, exit_policy="whole_steps_v1"
    )
    try:
        advance(engine, instrument, BASE_NS)
        advance(engine, instrument, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        exits = tuple(fixture_signal(s, "exit", BASE_NS + 2 * SECOND, "flat") for s in SLEEVES[:4])
        result = strategy.process_signals(exits)
        advance(engine, instrument, BASE_NS + 4 * SECOND)
        strategy = restart_strategy(engine, strategy)
        advance(engine, instrument, BASE_NS + 6 * SECOND)
        strategy.process_signals(exits)  # consumed signals cannot cause another order
        snapshot = strategy.snapshot()
        base = D("0.00000200") if fee_mode == "received_asset" else D("0")
        cash = D("498.60120") if fee_mode == "received_asset" else D("498.80")
        if (
            len(result.selected) != 4
            or len(engine.cache.orders()) != 8
            or snapshot.total_base != base
            or snapshot.total_quote != cash
            or any(dict(snapshot.holdings)[s] != base / 4 for s in SLEEVES[:4])
        ):
            raise SimulationBlocked("whole-step residual exit acceptance failed")
        return {
            "status": "passed",
            "scope": "synthetic_residual_exit_only",
            "exit_policy": strategy.exit_policy,
            "fee_mode": fee_mode,
            "runtime_ready": False,
            "performance_evidence": False,
            "native_order_count": len(engine.cache.orders()),
            "total_quote_usdt": str(snapshot.total_quote),
            "net_base_btc": str(snapshot.total_base),
            "flat": snapshot.total_base == 0,
            "exit_audits": [
                strategy.state_data["signals"][s.signal_id]["exit_sizing"] for s in exits
            ],
            "inventory": [asdict(row) for row in strategy.inventory_diagnostics()],
            "warm_restart": "passed",
        }
    finally:
        engine.end()
        engine.dispose()


def main() -> int:
    import argparse
    import json
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fee-mode", choices=("quote", "received_asset"), default="quote")
    parser.add_argument("--exit-policy", choices=EXIT_POLICIES, default="exact_v1")
    args = parser.parse_args()
    # No paths, credentials or research inputs accepted: this is a bounded fixture.
    with tempfile.TemporaryDirectory(prefix="trader-portfolio-acceptance-") as directory:
        checkpoint = Path(directory) / "checkpoint.json"
        if args.exit_policy == "whole_steps_v1":
            report = run_residual_exit_acceptance(checkpoint, fee_mode=args.fee_mode)
        else:
            run = (
                run_received_asset_acceptance
                if args.fee_mode == "received_asset"
                else run_acceptance
            )
            report = run(checkpoint)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D

import pytest

from apps.ops.portfolio_execution_plan import SLEEVES, preflight_limits
from apps.strategies_nautilus.portfolio_preflight import (
    AccountSnapshot,
    InstrumentRules,
    ProposedOrder,
    check_batch,
)
from apps.strategies_nautilus.portfolio_simulation import SimulationBlocked
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
    BASE_NS,
    SECOND,
    advance,
    build_simulation,
    fixture_signal,
    restart_strategy,
)


@contextmanager
def received_simulation(tmp_path, *, all_sleeves=True, cancel_latency_ns=0):
    def submit(strategy):
        return strategy.process_signals(
            tuple(
                fixture_signal(s, "base-fee", BASE_NS)
                for s in (SLEEVES if all_sleeves else ("v16",))
            )
        )

    engine, strategy, instrument = build_simulation(
        tmp_path / "checkpoint.json",
        {BASE_NS: submit},
        fee_mode="received_asset",
        cancel_latency_ns=cancel_latency_ns,
    )
    try:
        advance(engine, instrument, BASE_NS)
        yield engine, strategy, instrument
    finally:
        engine.end()
        engine.dispose()


def test_native_base_commission_reconciles_exact_net_inventory_and_preserves_size(tmp_path):
    with received_simulation(tmp_path) as (engine, s, inst):
        assert inst.size_precision == 8
        assert inst.size_increment.as_decimal() == D("0.000001")
        assert len(engine.cache.orders()) == 4
        assert all(order.quantity.as_decimal() == D("0.001") for order in engine.cache.orders())
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        snapshot = s.snapshot()
        assert snapshot.total_quote == D("100")  # no invented quote fee deduction
        assert snapshot.total_base == D("0.00399400")
        assert sum(dict(snapshot.holdings).values()) == snapshot.total_base
        assert all(
            pos.quantity.as_decimal() == D("0.00099850") for pos in engine.cache.positions_open()
        )
        assert sum(
            fee.as_decimal() for pos in engine.cache.positions_open() for fee in pos.commissions()
        ) == D("0.00000600")
        # Fee rounds at BTC's 8 places and is subtracted only by Nautilus.
        assert all(len(pos.adjustments) == 1 for pos in engine.cache.positions_open())


def test_off_grid_full_exit_is_blocked_without_hiding_or_transferring_dust(tmp_path):
    with received_simulation(tmp_path) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        before = s.snapshot()
        rows = s.inventory_diagnostics()
        assert rows[0].net_quantity == D("0.00099850")
        assert rows[0].step_remainder == D("0.00000050")
        assert rows[0].whole_steps_quantity == D("0.00099800")
        assert rows[0].full_exit_blockers == ("quantity_step",)
        result = s.process_signals((fixture_signal("v16", "flat", BASE_NS + 2 * SECOND, "flat"),))
        assert not result.selected
        assert result.skipped[0].reasons == ("quantity_step",)
        assert len(engine.cache.orders()) == 4
        assert s.snapshot() == before
        refill = s.process_signals((fixture_signal("v16", "top-up", BASE_NS + 2 * SECOND + 1),))
        assert not refill.selected
        assert "sleeve_exposure_limit" in refill.skipped[0].reasons


def test_partial_native_base_fees_cancel_and_grid_aligned_exact_exit(tmp_path):
    with received_simulation(tmp_path, all_sleeves=False) as (engine, s, inst):
        # Two .000333 fills each pay .00000050 BTC after native Money rounding.
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000", size="0.000333")
        advance(engine, inst, BASE_NS + 4 * SECOND)  # move away, then replenish liquidity
        advance(engine, inst, BASE_NS + 6 * SECOND, bid="99998", ask="99999", size="0.000333")
        order = engine.cache.orders()[0]
        snapshot = s.snapshot()
        assert order.filled_qty.as_decimal() == D("0.000666")
        assert snapshot.total_base == D("0.00066500")
        assert snapshot.pending[0].remaining == D("0.000334")
        s.request_cancel(str(order.client_order_id))
        advance(engine, inst, BASE_NS + 8 * SECOND)
        assert order.is_closed
        assert s.inventory_diagnostics()[0].full_exit_blockers == ()
        result = s.process_signals(
            (fixture_signal("v16", "exact-flat", BASE_NS + 8 * SECOND, "flat"),)
        )
        assert result.selected[0].order.quantity == D("0.00066500")
        advance(engine, inst, BASE_NS + 10 * SECOND)
        assert s.snapshot().total_base == 0
        assert s.snapshot().total_quote == D("499.80025")
        assert not engine.cache.positions_open()


def test_late_partial_base_fees_remain_reconciled_while_cancel_in_flight(tmp_path):
    with received_simulation(tmp_path, all_sleeves=False, cancel_latency_ns=4 * SECOND) as (
        engine,
        s,
        inst,
    ):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000", size="0.0002")
        order = engine.cache.orders()[0]
        before = s.snapshot().total_base
        s.request_cancel(str(order.client_order_id))
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="99999", ask="100000", size="0.0001")
        assert s.snapshot().total_base > before
        assert s.snapshot().pending[0].remaining > 0
        advance(engine, inst, BASE_NS + 8 * SECOND)
        assert s.snapshot().pending[0].remaining == 0
        assert order.is_closed
        assert sum(dict(s.snapshot().holdings).values()) == s.snapshot().total_base


def test_base_net_inventory_and_dust_survive_warm_restart_without_double_charging(tmp_path):
    with received_simulation(tmp_path) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        before = s.snapshot()
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="99999", ask="100000")
        assert s.snapshot().total_quote == before.total_quote
        assert s.snapshot().holdings == before.holdings
        for order in engine.cache.orders():
            for event in reversed(order.events):
                s.on_order_event(event)
        assert s.snapshot().total_base == D("0.003994")
        assert s.inventory_diagnostics()[0].step_remainder == D("0.00000050")


def test_base_fee_loss_latch_includes_net_base_and_survives_restart(tmp_path):
    with received_simulation(tmp_path) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="87000", ask="87010")
        assert s.snapshot().risk_latched
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 6 * SECOND)
        result = s.process_signals((fixture_signal("v36", "blocked", BASE_NS + 6 * SECOND),))
        assert not result.selected
        assert "risk_latched" in result.skipped[0].reasons


def test_received_fee_mode_refuses_low_native_position_precision(tmp_path):
    from nautilus_trader.model.instruments import CurrencyPair

    engine, _, inst = build_simulation(tmp_path / "checkpoint.json", fee_mode="received_asset")
    fields = CurrencyPair.to_dict(inst)
    fields.update(size_precision=6, size_increment="0.000001")
    engine.cache.add_instrument(CurrencyPair.from_dict(fields))
    try:
        with pytest.raises(SimulationBlocked, match="fee configuration mismatch"):
            advance(engine, inst, BASE_NS)
        assert not engine.cache.orders()
    finally:
        engine.end()
        engine.dispose()


def risk_fixture():
    account = AccountSnapshot(
        "BTCUSDT.BINANCE",
        BASE_NS,
        BASE_NS,
        True,
        D("500"),
        D("500"),
        D("0"),
        D("0"),
        tuple((s, D("0")) for s in SLEEVES),
        (),
        frozenset(),
        D("100000"),
        D("524"),
        D("524"),
    )
    rules = InstrumentRules(
        "BTCUSDT.BINANCE",
        BASE_NS,
        D("0.000001"),
        D("1"),
        D("0.000001"),
        D("0"),
        D("0"),
        D("0.01"),
        D("10"),
        None,
        D("0.0015"),
        buy_fee_currency="BTC",
        base_fee_quantum=D("0.00000001"),
    )
    order = ProposedOrder("buy", "v16", "BUY", D("0.001"), D("100000"))
    return account, rules, order


def test_per_fill_base_fee_rounding_is_included_at_inclusive_projected_loss_limit():
    account, rules, order = risk_fixture()
    result = check_batch(
        account, rules, preflight_limits(), (order,), now_ns=BASE_NS, allow_base_buy_fees=True
    )
    # 1,000 minimum-step fills, conservatively <= 1 satoshi each: 1 USDT.
    assert "projected_daily_loss_limit" in result.reasons
    assert result.required_quote == D("100.15")  # quote buffer retained despite base fees
    account = replace(account, day_open_equity=D("523.99"), peak_equity=D("523.99"))
    assert check_batch(
        account, rules, preflight_limits(), (order,), now_ns=BASE_NS, allow_base_buy_fees=True
    ).checks_passed


@pytest.mark.parametrize(
    "change",
    [
        {"base_fee_quantum": None},
        {"base_fee_quantum": D("NaN")},
        {"buy_fee_currency": "BNB_OR_BTC"},
        {"buy_fee_currency": "BNB"},
    ],
)
def test_opt_in_never_assumes_missing_quantum_or_bnb_accounting(change):
    account, rules, order = risk_fixture()
    account = replace(account, day_open_equity=D("500"), peak_equity=D("500"))
    assert not check_batch(
        account,
        replace(rules, **change),
        preflight_limits(),
        (order,),
        now_ns=BASE_NS,
        allow_base_buy_fees=True,
    ).checks_passed


def test_quote_only_default_still_blocks_base_fees():
    account, rules, order = risk_fixture()
    result = check_batch(account, rules, preflight_limits(), (order,), now_ns=BASE_NS)
    assert "unsupported_order_fee_currency" in result.reasons


def test_native_commission_above_frozen_fixture_bound_halts_admission(tmp_path, monkeypatch):
    from nautilus_trader.model.currencies import BTC
    from nautilus_trader.model.objects import Money

    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
        ReceivedAssetFeeModel,
    )

    with received_simulation(tmp_path, all_sleeves=False) as (engine, s, inst):
        monkeypatch.setattr(
            ReceivedAssetFeeModel, "get_commission", lambda *args: Money(D("0.000002"), BTC)
        )
        with pytest.raises(SimulationBlocked, match="commission exceeds"):
            advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        assert "commission exceeds" in s.state_data["halt_reason"]
        with pytest.raises(SimulationBlocked, match="commission exceeds"):
            s.process_signals((fixture_signal("v18", "blocked", BASE_NS + 2 * SECOND),))


def test_fee_mode_mismatch_cannot_reuse_checkpoint(tmp_path):
    with received_simulation(tmp_path, all_sleeves=False):
        pass
    engine, _, inst = build_simulation(tmp_path / "checkpoint.json")
    try:
        with pytest.raises(SimulationBlocked, match="checkpoint integrity/config mismatch"):
            advance(engine, inst, BASE_NS)
    finally:
        engine.end()
        engine.dispose()


def test_received_asset_smoke_report_is_reproducible(tmp_path):
    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
        run_received_asset_acceptance,
    )

    first = run_received_asset_acceptance(tmp_path / "first.json")
    assert first == run_received_asset_acceptance(tmp_path / "second.json")
    assert first["full_exit"] == "blocked_quantity_step_without_rounding"
    assert first["runtime_ready"] is False


def test_sub_step_fill_is_rejected_by_fixture_fee_hook():
    from types import SimpleNamespace

    from nautilus_trader.model.enums import OrderSide
    from nautilus_trader.model.objects import Price, Quantity

    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
        ReceivedAssetFeeModel,
    )

    with pytest.raises(ValueError, match="venue quantity grid"):
        ReceivedAssetFeeModel().get_commission(
            SimpleNamespace(side=OrderSide.BUY),
            Quantity.from_str("0.00000050"),
            Price.from_str("100000"),
            SimpleNamespace(size_increment=Quantity.from_str("0.00000100")),
        )


def test_pending_base_fees_use_rounding_bound_and_reject_off_grid_remainders():
    from apps.strategies_nautilus.portfolio_preflight import PendingOrder

    account, rules, order = risk_fixture()
    pending = PendingOrder("pending", "v18", "BUY", D("0.0005"), D("100000"), "partially_filled")
    account = replace(
        account,
        pending=(pending,),
        used_order_ids=frozenset({"pending"}),
        day_open_equity=D("523.5"),
        peak_equity=D("523.5"),
    )
    result = check_batch(
        account, rules, preflight_limits(), (order,), now_ns=BASE_NS, allow_base_buy_fees=True
    )
    assert "projected_daily_loss_limit" in result.reasons  # .5 pending + 1 proposed
    account = replace(account, pending=(replace(pending, remaining=D("0.00000050")),))
    result = check_batch(
        account, rules, preflight_limits(), (), now_ns=BASE_NS, allow_base_buy_fees=True
    )
    assert not result.checks_passed
    assert "supported fill grid" in result.reasons[0]


def test_inventory_report_retains_sub_minimum_inventory_without_order_proposal():
    from apps.strategies_nautilus.portfolio_inventory import inventory_diagnostics

    account, rules, _ = risk_fixture()
    qty = D("0.00000050")
    account = replace(
        account,
        total_base=qty,
        venue_free_base=qty,
        holdings=tuple((s, qty if s == "v16" else D("0")) for s in SLEEVES),
    )
    diagnostic = inventory_diagnostics(account, rules, limit_price=D("100000"))[0]
    assert diagnostic.net_quantity == qty
    assert diagnostic.whole_steps_quantity == 0
    assert set(diagnostic.full_exit_blockers) == {
        "quantity_step",
        "quantity_bounds",
        "notional_bounds",
    }

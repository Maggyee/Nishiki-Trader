from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D

import pytest

from apps.strategies_nautilus.portfolio_inventory import size_exit
from apps.strategies_nautilus.portfolio_simulation import (
    PortfolioSimulationStrategy,
    SimulationBlocked,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
    BASE_NS,
    SECOND,
    advance,
    build_simulation,
    fixture_signal,
    restart_strategy,
    run_residual_exit_acceptance,
)


@contextmanager
def filled_sleeve(tmp_path, *, cancel_latency_ns=0, buy_fill_size="1"):
    def enter(s):
        s.process_signals((fixture_signal("v16", "entry", BASE_NS),))

    engine, s, inst = build_simulation(
        tmp_path / "checkpoint.json",
        {BASE_NS: enter},
        fee_mode="received_asset",
        exit_policy="whole_steps_v1",
        cancel_latency_ns=cancel_latency_ns,
    )
    try:
        advance(engine, inst, BASE_NS)
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000", size=buy_fill_size)
        yield engine, s, inst
    finally:
        engine.end()
        engine.dispose()


def exit_signal(s, suffix="exit"):
    return fixture_signal("v16", suffix, s.clock.timestamp_ns(), "flat")


@pytest.mark.parametrize("quantity", ["0", "0.00000050", "0.00099850", "0.00066500"])
def test_explicit_policy_conserves_quantity_and_preserves_exact_default(quantity):
    q, step = D(quantity), D("0.000001")
    assert size_exit(q, step).proposed_quantity == q
    sized = size_exit(q, step, policy="whole_steps_v1")
    assert sized.proposed_quantity + sized.retained_if_filled == q
    assert sized.proposed_quantity % step == 0
    assert 0 <= sized.retained_if_filled < step


@pytest.mark.parametrize(
    "quantity,step,policy",
    [
        ("NaN", "0.000001", "whole_steps_v1"),
        ("-1", "0.000001", "whole_steps_v1"),
        ("Infinity", "0.000001", "whole_steps_v1"),
        ("1", "0", "whole_steps_v1"),
        ("1", "NaN", "whole_steps_v1"),
        ("1", "-1", "whole_steps_v1"),
        ("1", "0.000001", "automatic_sweep"),
    ],
)
def test_exit_sizing_rejects_invalid_inputs(quantity, step, policy):
    with pytest.raises(ValueError):
        size_exit(D(quantity), D(step), policy=policy)


def test_native_reduction_audit_is_durable_and_dust_remains_owned_after_restart(
    tmp_path, monkeypatch
):
    with filled_sleeve(tmp_path) as (engine, s, inst):
        signal = exit_signal(s)
        submit = s._submit_native

        def inspect_prepared(order, position_id):
            saved = json.loads(s.checkpoint.read_text())["state"]
            audit = saved["signals"][signal.signal_id]["exit_sizing"]
            assert audit["policy"] == "whole_steps_v1"
            assert D(audit["requested_net_quantity"]) == D("0.00099850")
            assert D(audit["proposed_quantity"]) == D("0.00099800")
            assert D(audit["prepared_quantity"]) == order.quantity.as_decimal()
            assert D(audit["retained_if_filled"]) == D("0.00000050")
            submit(order, position_id)

        monkeypatch.setattr(s, "_submit_native", inspect_prepared)
        result = s.process_signals((signal,))
        assert result.selected[0].order.quantity == D("0.00099800")
        advance(engine, inst, BASE_NS + 4 * SECOND)
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 6 * SECOND)
        snapshot = s.snapshot()
        assert s.exit_policy == "whole_steps_v1"
        assert snapshot.total_quote == D("499.65030")
        assert snapshot.total_base == D("0.00000050")
        assert dict(snapshot.holdings)["v16"] == snapshot.total_base
        assert all(q == 0 for sleeve, q in snapshot.holdings if sleeve != "v16")
        assert snapshot.total_quote + snapshot.total_base * snapshot.mark_price == D("499.70030")
        assert len(engine.cache.positions_open()) == 1  # never label dust flat
        s.process_signals((signal,))
        dust = exit_signal(s, "dust")
        assert not s.process_signals((dust,)).selected
        row = s.state_data["signals"][dust.signal_id]
        assert row["reasons"] == ["residual_below_step"]
        assert D(row["exit_sizing"]["retained_if_filled"]) == snapshot.total_base
        advance(engine, inst, BASE_NS + 8 * SECOND)
        buy = fixture_signal("v16", "no-top-up", s.clock.timestamp_ns())
        refill = s.process_signals((buy,))
        assert not refill.selected
        assert "sleeve_exposure_limit" in refill.skipped[0].reasons
        assert len(engine.cache.orders()) == 2  # no sweep, retry or resized buy


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"notional_min": D("100")}, "notional_bounds"),
        ({"notional_max": D("99")}, "notional_bounds"),
        ({"quantity_min": D("0.001")}, "quantity_bounds"),
        ({"quantity_max": D("0.0009")}, "quantity_bounds"),
    ],
)
def test_reduction_passes_actual_quantity_through_filters_without_further_resizing(
    tmp_path, monkeypatch, changes, reason
):
    with filled_sleeve(tmp_path) as (engine, s, _):
        rules = replace(s.rules(), **changes)
        monkeypatch.setattr(s, "rules", lambda: rules)
        signal = exit_signal(s)
        result = s.process_signals((signal,))
        assert not result.selected
        assert reason in result.skipped[0].reasons
        assert len(engine.cache.orders()) == 1
        audit = s.state_data["signals"][signal.signal_id]["exit_sizing"]
        assert D(audit["proposed_quantity"]) == D("0.00099800")
        assert audit["prepared_quantity"] == "0"
        assert s.snapshot().total_base == D("0.00099850")


def test_pending_partial_sell_cancel_and_late_fill_preserve_reservations_and_ownership(tmp_path):
    with filled_sleeve(tmp_path, cancel_latency_ns=4 * SECOND) as (engine, s, inst):
        result = s.process_signals((exit_signal(s),))
        oid = result.selected[0].order.order_id
        # Rest below the sell limit, then restart with the pending reservation.
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="99999", ask="100010")
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 6 * SECOND, bid="99999", ask="100010")
        blocked = s.process_signals((exit_signal(s, "pending"),))
        assert "sleeve_has_pending_order" in blocked.skipped[0].reasons
        advance(engine, inst, BASE_NS + 8 * SECOND, size="0.000333")
        assert s.snapshot().total_base == D("0.00066550")
        s.request_cancel(oid)
        advance(engine, inst, BASE_NS + 10 * SECOND, bid="100001", ask="100010", size="0.000333")
        snap = s.snapshot()
        assert snap.total_base == D("0.00033250")  # native late fill during cancel
        assert next(p for p in snap.pending if p.order_id == oid).remaining == D("0.00033200")
        blocked = s.process_signals((exit_signal(s, "cancel-pending"),))
        assert "sleeve_has_pending_order" in blocked.skipped[0].reasons
        advance(engine, inst, BASE_NS + 14 * SECOND, bid="99999", ask="100010")
        assert next(p for p in s.snapshot().pending if p.order_id == oid).remaining == 0
        assert len(engine.cache.orders()) == 2  # no automatic replacement at cancel ack
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 16 * SECOND, bid="99999", ask="100010")
        final = s.process_signals((exit_signal(s, "fresh-exit"),))
        assert final.selected[0].order.quantity == D("0.00033200")
        advance(engine, inst, BASE_NS + 18 * SECOND, bid="100002", ask="100010")
        assert s.snapshot().total_base == D("0.00000050")
        assert s.inventory_diagnostics()[0].net_quantity == D("0.00000050")


def test_small_partial_buy_retains_entire_sub_notional_inventory_without_rounding_up(tmp_path):
    with filled_sleeve(tmp_path, buy_fill_size="0.0001") as (engine, s, inst):
        buy = engine.cache.orders()[0]
        s.request_cancel(str(buy.client_order_id))
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="99999", ask="100010")
        assert buy.is_closed
        assert s.snapshot().total_base == D("0.00009985")
        signal = exit_signal(s)
        result = s.process_signals((signal,))
        assert not result.selected
        assert "notional_bounds" in result.skipped[0].reasons
        audit = s.state_data["signals"][signal.signal_id]["exit_sizing"]
        assert D(audit["proposed_quantity"]) == D("0.00009900")
        assert audit["prepared_quantity"] == "0"
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 6 * SECOND)
        assert s.snapshot().total_base == D("0.00009985")
        assert len(engine.cache.orders()) == 1


def test_risk_latch_allows_owned_reduction_and_remains_latched_after_restart(tmp_path):
    with filled_sleeve(tmp_path) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="40000", ask="40010")
        assert s.snapshot().risk_latched
        assert s.process_signals((exit_signal(s),)).selected
        advance(engine, inst, BASE_NS + 6 * SECOND)
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 8 * SECOND)
        assert s.snapshot().risk_latched
        assert s.snapshot().total_base == D("0.00000050")
        buy = fixture_signal("v18", "blocked", s.clock.timestamp_ns())
        assert "risk_latched" in s.process_signals((buy,)).skipped[0].reasons


def test_exit_policy_mismatch_and_missing_native_state_fail_closed(tmp_path):
    with filled_sleeve(tmp_path) as (_, s, _):
        saved = s.on_save()
        exact = PortfolioSimulationStrategy(tmp_path / "other.json", fee_mode="received_asset")
        with pytest.raises(SimulationBlocked, match="config mismatch"):
            exact.on_load(saved)
    engine, _, inst = build_simulation(
        tmp_path / "checkpoint.json", fee_mode="received_asset", exit_policy="whole_steps_v1"
    )
    try:
        with pytest.raises(SimulationBlocked, match="missing from native cache"):
            advance(engine, inst, BASE_NS)
        assert not engine.cache.orders()
    finally:
        engine.end()
        engine.dispose()


@pytest.mark.parametrize("fee_mode", ["quote", "received_asset"])
def test_residual_smoke_is_reproducible_and_reports_actual_flatness(tmp_path, fee_mode):
    first = run_residual_exit_acceptance(tmp_path / "first.json", fee_mode=fee_mode)
    assert first == run_residual_exit_acceptance(tmp_path / "second.json", fee_mode=fee_mode)
    assert first["flat"] == (fee_mode == "quote")
    assert first["runtime_ready"] is False

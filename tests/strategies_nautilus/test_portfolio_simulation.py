from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from apps.ops.portfolio_execution_plan import SLEEVES, preflight_limits
from apps.strategies_nautilus.portfolio_simulation import DAY_NS, D, SimulationBlocked
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
    BASE_NS,
    SECOND,
    advance,
    build_simulation,
    fixture_signal,
    restart_strategy,
)


def test_real_nautilus_cash_reservations_prevent_second_batch_reuse(tmp_path):
    results = []

    def submit(strategy):
        signals = tuple(fixture_signal(s, "first", BASE_NS - 2) for s in SLEEVES)
        results.append(strategy.process_signals(signals))
        results.append(strategy.process_signals((fixture_signal("v36", "second", BASE_NS - 1),)))

    engine, strategy, instrument = build_simulation(tmp_path / "checkpoint.json", {BASE_NS: submit})
    try:
        advance(engine, instrument, BASE_NS)
        assert len(results[0].selected) == 4
        assert results[0].preflight.required_quote == D("400.60")
        assert not results[1].selected
        assert results[1].preflight.available_quote == D("99.40")
        assert len(engine.cache.orders()) == 4
        advance(engine, instrument, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        assert len(engine.cache.positions_open()) == 4
        snapshot = strategy.snapshot()
        assert snapshot.total_base == D("0.004")
        assert snapshot.total_quote == D("99.40")
        assert dict(snapshot.holdings)["v36"] == 0
    finally:
        engine.end()
        engine.dispose()


@contextmanager
def simulation(tmp_path, actions=None, **kwargs):
    engine, strategy, instrument = build_simulation(tmp_path / "checkpoint.json", actions, **kwargs)
    try:
        advance(engine, instrument, BASE_NS)
        yield engine, strategy, instrument
    finally:
        engine.end()
        engine.dispose()


def buy_all(strategy):
    return strategy.process_signals(
        tuple(fixture_signal(s, "initial", BASE_NS - 1) for s in SLEEVES)
    )


def test_current_daily_stop_persists_through_rebound_restart_and_midnight(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        assert s.snapshot().total_base == D("0.004")
        advance(engine, inst, BASE_NS + 3 * SECOND, bid="93902.5", ask="93903")
        assert not s.snapshot().risk_latched  # equity 475.01
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="93900", ask="93901")
        assert s.snapshot().risk_latched  # equity 475.00, exact 25 USDT loss
        advance(engine, inst, BASE_NS + 5 * SECOND)
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + DAY_NS)
        assert s.snapshot().risk_latched
        result = s.process_signals((fixture_signal("v36", "after-stop", BASE_NS + DAY_NS),))
        assert not result.selected
        assert "risk_latched" in result.skipped[0].reasons


def test_legacy_risk_checkpoint_cannot_resume_as_current_policy(tmp_path):
    from apps.strategies_nautilus.portfolio_simulation import PortfolioSimulationStrategy

    legacy = PortfolioSimulationStrategy(tmp_path / "legacy.json")
    legacy.limits = preflight_limits(revision=2)
    legacy.state_data["fingerprint"] = legacy._fingerprint()
    current = PortfolioSimulationStrategy(tmp_path / "current.json")
    with pytest.raises(SimulationBlocked, match="config mismatch"):
        current.on_load(legacy.on_save())


def test_partial_fill_cancel_latency_and_late_fill_use_native_remainder(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}, cancel_latency_ns=4 * SECOND) as (
        engine,
        s,
        inst,
    ):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000", size="0.0002")
        snap = s.snapshot()
        assert D("0") < snap.total_base < D("0.004")
        assert sum(p.remaining for p in snap.pending) + snap.total_base == D("0.004")
        assert snap.total_quote == D("500") - snap.total_base * D("100150")
        partial = next(
            o for o in engine.cache.orders() if o.filled_qty.as_decimal() > 0 and not o.is_closed
        )
        oid = str(partial.client_order_id)
        before = partial.leaves_qty.as_decimal()
        s.request_cancel(oid)
        assert next(p for p in s.snapshot().pending if p.order_id == oid).remaining == before
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="99999", ask="100000", size="0.0001")
        assert partial.leaves_qty.as_decimal() < before  # actual fill while cancel is in flight
        advance(engine, inst, BASE_NS + 8 * SECOND)
        assert partial.is_closed
        snap = s.snapshot()
        assert next(p for p in snap.pending if p.order_id == oid).remaining == 0
        assert snap.total_quote == D("500") - snap.total_base * D("100150")
        assert sum(dict(snap.holdings).values()) == snap.total_base


def test_cancel_ack_releases_cash_and_replay_does_not_revive_skipped_signal(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        order = engine.cache.orders()[0]
        s.request_cancel(str(order.client_order_id))
        advance(engine, inst, BASE_NS + 2 * SECOND)
        assert order.is_closed
        skipped = fixture_signal("v36", "initial", BASE_NS - 1)
        assert not s.process_signals((skipped,)).selected
        result = s.process_signals((fixture_signal("v36", "new", BASE_NS + 2 * SECOND),))
        assert len(result.selected) == 1
        assert result.preflight.available_quote == D("199.55")


def test_warm_restart_restores_reservations_dedup_and_sleeve_flatten(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 2 * SECOND)
        assert not buy_all(s).selected
        assert len(engine.cache.orders()) == 4
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="99999", ask="100000")
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 6 * SECOND)
        before = dict(s.snapshot().holdings)
        result = s.process_signals((fixture_signal("v18", "flat", BASE_NS + 6 * SECOND, "flat"),))
        assert len(result.selected) == 1
        advance(engine, inst, BASE_NS + 8 * SECOND)
        after = dict(s.snapshot().holdings)
        assert after["v18"] == 0
        assert all(after[k] == v for k, v in before.items() if k != "v18")
        assert s.snapshot().total_quote == D("199.25")


def test_risk_latch_survives_price_recovery_midnight_and_strategy_restart(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="87650", ask="87660")
        assert s.state_data["risk_latched"]  # equity exactly 450 = inclusive 50 USDT loss
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + DAY_NS)
        assert s.state_data["risk_latched"]
        result = s.process_signals((fixture_signal("v36", "blocked", BASE_NS + DAY_NS),))
        assert not result.selected
        assert "risk_latched" in result.skipped[0].reasons
        result = s.process_signals((fixture_signal("v16", "reduce", BASE_NS + DAY_NS, "flat"),))
        assert len(result.selected) == 1
        advance(engine, inst, BASE_NS + DAY_NS + 2 * SECOND)
        assert dict(s.snapshot().holdings)["v16"] == 0
        assert s.state_data["risk_latched"]


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"source": "llm_fixture_v16"}, "reject_unauthorized_source"),
        ({"source": "rule_cboe_fixture"}, "reject_unauthorized_source"),
        ({"model_version": "production"}, "reject_unauthorized_model"),
        ({"confidence": 0.1}, "reject_low_confidence"),
        ({"venue": "OTHER"}, "reject_venue"),
        ({"symbol": "ETHUSDT"}, "unsupported_instrument_or_direction"),
        ({"side": "sell", "score": -0.8}, "unsupported_instrument_or_direction"),
        ({"ts_event": BASE_NS + 2 * SECOND}, "future_or_expired_signal"),
        ({"ts_event": BASE_NS - 60 * SECOND}, "expired"),
    ],
)
def test_consumer_rejects_invalid_identity_direction_and_time(tmp_path, change, reason):
    with simulation(tmp_path) as (engine, s, _):
        sig = fixture_signal("v16", "invalid", BASE_NS).model_copy(update=change)
        assert not s.process_signals((sig,)).selected
        assert s.state_data["signals"][sig.signal_id]["reasons"] == [reason]
        assert not engine.cache.orders()


@pytest.mark.parametrize("reverse", [False, True])
def test_latest_flat_supersedes_older_buy_in_same_batch(tmp_path, reverse):
    with simulation(tmp_path) as (engine, s, _):
        sigs = [
            fixture_signal("v16", "old", BASE_NS - 1),
            fixture_signal("v16", "new", BASE_NS, "flat"),
        ]
        assert not s.process_signals(tuple(reversed(sigs) if reverse else sigs)).selected
        assert not engine.cache.orders()
        assert s.state_data["signals"][sigs[0].signal_id]["reasons"] == [
            "superseded_or_out_of_order_signal"
        ]
        assert not s.process_signals((fixture_signal("v16", "late", BASE_NS - 1),)).selected


def test_same_time_conflicting_sleeve_signals_fail_closed(tmp_path):
    with simulation(tmp_path) as (engine, s, _):
        sigs = (
            fixture_signal("v16", "buy", BASE_NS),
            fixture_signal("v16", "flat", BASE_NS, "flat"),
        )
        assert not s.process_signals(sigs).selected
        assert not engine.cache.orders()
        assert all(
            s.state_data["signals"][sig.signal_id]["reasons"]
            == ["ambiguous_same_time_sleeve_signals"]
            for sig in sigs
        )


def test_prepare_is_durable_before_first_submit_and_failure_keeps_entire_batch(
    tmp_path, monkeypatch
):
    with simulation(tmp_path) as (engine, s, inst):

        def fail(order, position_id):
            saved = json.loads(s.checkpoint.read_bytes())["state"]
            assert len(saved["orders"]) == 4
            assert sum(p.remaining for p in s.snapshot().pending) == D("0.004")
            raise RuntimeError("injected submit failure")

        monkeypatch.setattr(s, "_submit_native", fail)
        with pytest.raises(RuntimeError, match="injected submit"):
            buy_all(s)
        assert not engine.cache.orders()
        assert len(s.state_data["orders"]) == 4
        with pytest.raises(SimulationBlocked, match="injected submit"):
            s.process_signals((fixture_signal("v36", "retry", BASE_NS),))
        with pytest.raises(SimulationBlocked, match="missing from native cache"):
            restart_strategy(engine, s)


def test_cold_restart_refuses_to_infer_native_state_from_journal(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}):
        pass
    with pytest.raises(SimulationBlocked, match="missing from native cache"), simulation(tmp_path):
        pass


def test_corrupt_checkpoint_and_concurrent_writer_fail_closed(tmp_path):
    with simulation(tmp_path) as (_, s, _):
        with pytest.raises(BlockingIOError), simulation(tmp_path):
            pass
        wrapped = json.loads(s.checkpoint.read_text())
    wrapped["state"]["risk_latched"] = True
    s.checkpoint.write_text(json.dumps(wrapped))
    with pytest.raises(SimulationBlocked, match="integrity"), simulation(tmp_path):
        pass


def test_cross_thread_admission_cannot_mutate_state(tmp_path):
    with simulation(tmp_path) as (engine, s, _):
        before = s.checkpoint.read_bytes()
        with (
            ThreadPoolExecutor(max_workers=1) as pool,
            pytest.raises(SimulationBlocked, match="owning simulation thread"),
        ):
            pool.submit(buy_all, s).result()
        assert s.checkpoint.read_bytes() == before
        assert not engine.cache.orders()


def test_duplicate_and_late_native_callbacks_do_not_double_apply_cash(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        order = engine.cache.orders()[0]
        snap = s.snapshot()
        before = len(s.state_data["events"])
        for event in reversed(order.events):
            s.on_order_event(event)
        assert s.snapshot() == snap
        # All events delivered by Nautilus are already in the audit.
        assert len(s.state_data["events"]) == before


def test_unknown_native_order_stops_admission(tmp_path):
    from nautilus_trader.model.enums import OrderSide
    from nautilus_trader.model.identifiers import ClientOrderId

    from apps.strategies_nautilus.portfolio_simulation import INSTRUMENT

    with simulation(tmp_path) as (engine, s, inst):
        order = s.order_factory.limit(
            INSTRUMENT,
            OrderSide.BUY,
            inst.make_qty(D("0.001")),
            inst.make_price(D("100000")),
            client_order_id=ClientOrderId("unknown"),
        )
        engine.cache.add_order(order)
        with pytest.raises(SimulationBlocked, match="unknown native order"):
            buy_all(s)
        assert json.loads(s.checkpoint.read_text())["state"]["halt_reason"]


def test_unknown_order_callback_latch_is_durable(tmp_path):
    from types import SimpleNamespace

    with simulation(tmp_path) as (_, s, _):
        s.on_order_event(SimpleNamespace(client_order_id="unknown", id="unknown-event"))
        assert json.loads(s.checkpoint.read_text())["state"]["halt_reason"] == "unknown order event"
        with pytest.raises(SimulationBlocked, match="unknown order event"):
            buy_all(s)


def test_submit_interruption_after_first_native_order_preserves_unsubmitted_reservations(
    tmp_path, monkeypatch
):
    with simulation(tmp_path) as (engine, s, _):
        submit = s._submit_native
        calls = []

        def interrupted(order, position_id):
            calls.append(order)
            if len(calls) == 2:
                raise RuntimeError("interrupted after first submit")
            submit(order, position_id)

        monkeypatch.setattr(s, "_submit_native", interrupted)
        with pytest.raises(RuntimeError, match="interrupted after first"):
            buy_all(s)
        assert len(engine.cache.orders()) == 1
        assert sum(p.remaining * p.limit_price * D("1.0015") for p in s.snapshot().pending) == D(
            "400.60"
        )
        assert len(json.loads(s.checkpoint.read_text())["state"]["orders"]) == 4


def test_failed_checkpoint_replace_submits_nothing_and_preserves_last_checkpoint(
    tmp_path, monkeypatch
):
    with simulation(tmp_path) as (engine, s, _):
        before = s.checkpoint.read_bytes()

        def fail(*args):
            raise OSError("disk failure")

        monkeypatch.setattr("apps.strategies_nautilus.portfolio_simulation.os.replace", fail)
        with pytest.raises(OSError, match="disk failure"):
            buy_all(s)
        assert not engine.cache.orders()
        assert s.checkpoint.read_bytes() == before
        assert s.state_data["halt_reason"] == "disk failure"


def test_reentrant_admission_cannot_reuse_prepared_cash(tmp_path, monkeypatch):
    with simulation(tmp_path) as (engine, s, _):
        submit = s._submit_native

        def checked(order, position_id):
            with pytest.raises(SimulationBlocked, match="reentrant"):
                s.process_signals((fixture_signal("v36", "nested", BASE_NS),))
            assert sum(p.remaining for p in s.snapshot().pending) == D("0.004")
            submit(order, position_id)

        monkeypatch.setattr(s, "_submit_native", checked)
        assert len(buy_all(s).selected) == 4
        assert len(engine.cache.orders()) == 4


def test_stale_quote_blocks_before_mutating_daily_risk_baselines(tmp_path):
    with simulation(tmp_path) as (engine, s, _):
        day = s.state_data["day_ns"]
        from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import quote

        s.quote = quote(engine.cache.instrument(s.quote.instrument_id), BASE_NS - DAY_NS)
        with pytest.raises(SimulationBlocked, match="stale or future"):
            buy_all(s)
        assert s.state_data["day_ns"] == day
        assert not engine.cache.orders()


def test_same_batch_sell_cannot_finance_new_sleeve_until_settled(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        result = s.process_signals(
            (
                fixture_signal("v16", "flat", BASE_NS + 2 * SECOND, "flat"),
                fixture_signal("v36", "buy", BASE_NS + 2 * SECOND),
            )
        )
        assert [c.order.side for c in result.selected] == ["SELL"]
        assert "insufficient_unreserved_quote" in result.skipped[0].reasons
        advance(engine, inst, BASE_NS + 4 * SECOND)
        assert (
            len(s.process_signals((fixture_signal("v36", "fresh", BASE_NS + 4 * SECOND),)).selected)
            == 1
        )


def test_duplicate_ids_and_constructed_schema_violation_fail_before_submit(tmp_path):
    from pydantic import ValidationError

    with simulation(tmp_path) as (engine, s, _):
        sig = fixture_signal("v16", "bad", BASE_NS).model_copy(
            update={"schema_version": "order.v1"}
        )
        with pytest.raises(ValidationError):
            s.process_signals((sig,))
        assert not engine.cache.orders()
    # Independent checkpoint for the second failure case.
    with simulation(tmp_path / "duplicate") as (engine, s, _):
        sig = fixture_signal("v16", "duplicate", BASE_NS)
        with pytest.raises(SimulationBlocked, match="duplicate signal IDs"):
            s.process_signals((sig, sig))
        assert not engine.cache.orders()


def test_acceptance_cli_scenario_is_reproducible(tmp_path):
    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import run_acceptance

    first = run_acceptance(tmp_path / "first.json")
    second = run_acceptance(tmp_path / "second.json")
    assert first == second
    assert first["status"] == "passed"
    assert first["native_order_count"] == 5
    assert first["performance_evidence"] is False


def test_native_risk_engine_denial_releases_only_after_terminal_event(tmp_path):
    from nautilus_trader.model.enums import TradingState

    with simulation(tmp_path) as (engine, s, _):
        engine.kernel.risk_engine.set_trading_state(TradingState.HALTED)
        result = buy_all(s)
        assert len(result.selected) == 4  # preflight is not a native execution authorization
        assert all(o.status.name == "DENIED" for o in engine.cache.orders())
        assert all(p.remaining == 0 for p in s.snapshot().pending)
        assert not engine.cache.positions_open()
        assert s.snapshot().total_quote == D("500")


def test_peak_drawdown_latches_even_when_new_day_loss_is_below_limit(tmp_path):
    with simulation(tmp_path, {BASE_NS: buy_all}) as (engine, s, inst):
        advance(engine, inst, BASE_NS + 2 * SECOND, bid="99999", ask="100000")
        advance(engine, inst, BASE_NS + 4 * SECOND, bid="200000", ask="200010")
        assert D(s.state_data["peak"]) == D("899.40")
        advance(engine, inst, BASE_NS + DAY_NS, bid="137500", ask="137510")
        snapshot = s.snapshot()
        assert (
            snapshot.day_open_equity
            - (snapshot.total_quote + snapshot.total_base * snapshot.mark_price)
            == 0
        )
        assert snapshot.peak_equity - (
            snapshot.total_quote + snapshot.total_base * snapshot.mark_price
        ) == D("250")
        assert snapshot.risk_latched


def test_prepared_reservations_work_for_new_orders_after_warm_restart(tmp_path, monkeypatch):
    with simulation(tmp_path) as (engine, s, inst):
        s = restart_strategy(engine, s)
        advance(engine, inst, BASE_NS + 2 * SECOND)
        submit = s._submit_native

        def checked(order, position_id):
            assert sum(p.remaining for p in s.snapshot().pending) == D("0.004")
            submit(order, position_id)

        monkeypatch.setattr(s, "_submit_native", checked)
        assert len(buy_all(s).selected) == 4


def test_unexpected_native_fee_schedule_fails_before_orders(tmp_path):
    from nautilus_trader.model.instruments import CurrencyPair

    engine, s, inst = build_simulation(tmp_path / "checkpoint.json")
    fields = CurrencyPair.to_dict(inst)
    fields["maker_fee"] = "0.002"
    engine.cache.add_instrument(CurrencyPair.from_dict(fields))
    try:
        with pytest.raises(SimulationBlocked, match="fee configuration mismatch"):
            advance(engine, inst, BASE_NS)
        assert not engine.cache.orders()
    finally:
        engine.end()
        engine.dispose()

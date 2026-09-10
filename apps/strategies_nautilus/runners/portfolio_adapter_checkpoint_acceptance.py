"""Abrupt producer exit, native Binance reconciliation and fresh-process replay.

All account observations and keys are synthetic; no network or execution client.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

from nautilus_trader.accounting.accounts.cash import CashAccount
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.enums import AccountType, OrderSide, TimeInForce
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    PositionId,
    StrategyId,
    TraderId,
)
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import AccountBalance, Money, Price, Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.events import TestEventStubs
from nautilus_trader.trading.strategy import Strategy

from apps.strategies_nautilus.portfolio_account import AccountAnchor, AccountEvidence
from apps.strategies_nautilus.portfolio_account_collector import CollectedAccount
from apps.strategies_nautilus.portfolio_adapter_checkpoint import (
    NUMERIC_MODE,
    checkpoint_bytes,
    reconcile_adapter_checkpoint,
    write_new_checkpoint,
)
from apps.strategies_nautilus.portfolio_adapter_recovery import (
    EvidenceOnlyExecutionEngine,
    reconcile_binance_reports,
)
from apps.strategies_nautilus.portfolio_recovery import (
    capture_native,
    reconstruct_native,
    verify_checkpoint,
)
from apps.strategies_nautilus.portfolio_stream import SourceBinding, UserStreamJournal
from apps.strategies_nautilus.portfolio_venue import CapturedResponse
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND

ANCHOR = AccountAnchor("123", "BINANCE-001", BASE_NS, D("500"))
BINDING = SourceBinding(
    "https://api.binance.com", "123", hashlib.sha256(b"fixture-key").hexdigest()
)


def order_row(sleeve, status, qty, quote):
    return {
        "symbol": "BTCUSDT",
        "clientOrderId": f"adapter-{sleeve}",
        "orderId": 123 if sleeve == "v16" else 124,
        "side": "BUY",
        "origQty": "0.00100000",
        "executedQty": qty,
        "price": "100000.00",
        "cummulativeQuoteQty": quote,
        "status": status,
        "type": "LIMIT",
        "timeInForce": "GTC",
        "time": BASE_NS // 1_000_000,
        "updateTime": (BASE_NS + 5 * SECOND) // 1_000_000,
        "orderListId": -1,
    }


def trade_row(oid, tid, qty, quote, fee, ts):
    return {
        "symbol": "BTCUSDT",
        "orderId": oid,
        "id": tid,
        "price": "100000.00",
        "qty": qty,
        "quoteQty": quote,
        "commission": fee,
        "commissionAsset": "BTC",
        "isBuyer": True,
        "isMaker": True,
        "time": ts // 1_000_000,
    }


def original_partial():
    row = order_row("v18", "PARTIALLY_FILLED", "0.00033300", "33.300000")
    row["updateTime"] = (BASE_NS + SECOND) // 1_000_000
    return row, trade_row(124, 456, "0.00033300", "33.300000", "0.00000050", BASE_NS + SECOND)


def fixture_checkpoint(loop):
    """Preserve an uncertain submit and cancel with an existing native base fee."""
    clock = TestClock()
    clock.set_time(BASE_NS + 2 * SECOND)
    cache = Cache()
    fields = CurrencyPair.to_dict(TestInstrumentProvider.btcusdt_binance())
    fields.update(size_precision=8, size_increment="0.00000100", maker_fee="0", taker_fee="0")
    instrument = CurrencyPair.from_dict(fields)
    cache.add_instrument(instrument)
    aid = AccountId(ANCHOR.native_account_id)
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
    bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
    portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
    engine = EvidenceOnlyExecutionEngine(loop=loop, msgbus=bus, cache=cache, clock=clock)
    engine.register_oms_type(
        Strategy(
            StrategyConfig(strategy_id="PORTFOLIO-FIXTURE", order_id_tag="PF", oms_type="HEDGING")
        )
    )
    state = {
        "version": "portfolio.adapter_checkpoint_fixture.v1",
        "orders": {},
        "signals": {},
        "watermarks": {},
        "risk_latched": True,
        "halt_reason": None,
        "day_open": "500",
        "peak": "500",
        "day_ns": BASE_NS,
    }
    try:
        for sleeve in ("v18", "v16"):
            signal_id = f"fixture-{sleeve}-entry"
            order = LimitOrder(
                trader_id=TraderId("BACKTESTER-001"),
                strategy_id=StrategyId("PORTFOLIO-FIXTURE-PF"),
                instrument_id=instrument.id,
                client_order_id=ClientOrderId(f"adapter-{sleeve}"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.00100000"),
                price=Price.from_str("100000.00"),
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=BASE_NS,
                tags=[f"signal_id:{signal_id}", f"sleeve:{sleeve}"],
            )
            order.apply(TestEventStubs.order_submitted(order, account_id=aid, ts_event=BASE_NS))
            pid = PositionId(f"{sleeve}-original")
            cache.add_order(order, position_id=pid)
            state["orders"][str(order.client_order_id)] = {
                "position_id": str(pid),
                "sleeve": sleeve,
                "signal_id": signal_id,
                "quantity": "0.00100000",
                "price": "100000.00",
                "side": "BUY",
            }
            state["signals"][signal_id] = {
                "decision": "prepared",
                "order_ids": [str(order.client_order_id)],
            }
            state["watermarks"][sleeve] = BASE_NS
            if sleeve == "v18":
                portfolio.initialize_orders()
                portfolio.initialize_positions()
                row, trade = original_partial()
                reconcile_binance_reports(
                    engine,
                    cache,
                    account_id=aid,
                    orders=[row],
                    trades=[trade],
                    now_ns=clock.timestamp_ns(),
                )
                order.apply(
                    TestEventStubs.order_pending_cancel(order, ts_event=BASE_NS + 2 * SECOND)
                )
                cache.update_order(order)
        clock.set_time(BASE_NS + 3 * SECOND)
        native = capture_native(
            SimpleNamespace(cache=cache, clock=clock), venue_id_mode=NUMERIC_MODE, anchor=ANCHOR
        )
        return checkpoint_bytes(state, native)
    finally:
        engine.dispose()


def fixture_collected(stream, now_ns):
    """Independent fixed response bodies; never serialized from recovered balances."""
    _, first_trade = original_partial()
    orders = [
        order_row("v16", "FILLED", "0.00100000", "100.000000"),
        order_row("v18", "CANCELED", "0.00066600", "66.600000"),
    ]
    trades = [
        first_trade,
        trade_row(123, 457, "0.00100000", "100.000000", "0.00000150", BASE_NS + 4 * SECOND),
        trade_row(124, 458, "0.00033300", "33.300000", "0.00000050", BASE_NS + 5 * SECOND),
    ]
    account = {
        "uid": 123,
        "accountType": "SPOT",
        "canTrade": True,
        "permissions": ["SPOT"],
        "balances": [
            {"asset": "BTC", "free": "0.00166350", "locked": "0"},
            {"asset": "USDT", "free": "333.40000000", "locked": "0"},
        ],
    }

    def response(body, symbol=None):
        return CapturedResponse(json.dumps(body), now_ns, ANCHOR.venue_uid, symbol)

    evidence = AccountEvidence(
        response(account),
        response(orders, "BTCUSDT"),
        response(trades, "BTCUSDT"),
        response([]),
        BASE_NS,
        now_ns,
    )
    return CollectedAccount(evidence, (), False, stream_fence=stream.fence())


def resume(raw, expected_sha256, archive, now_ns):
    loop = asyncio.new_event_loop()
    stream = UserStreamJournal(archive, BINDING, clock_ns=lambda: now_ns)
    try:
        stream.subscribed(7, BINDING)  # fixture acknowledgement, no HTTP/WS authentication
        return reconcile_adapter_checkpoint(
            raw,
            expected_sha256=expected_sha256,
            anchor=ANCHOR,
            collected=fixture_collected(stream, now_ns),
            stream=stream,
            now_ns=now_ns,
            loop=loop,
        )
    finally:
        stream.close()
        loop.close()


def worker(directory, mode, expected_sha256=None):
    if mode == "produce":
        loop = asyncio.new_event_loop()
        try:
            raw = fixture_checkpoint(loop)
            write_new_checkpoint(directory / "original.json", raw)
        finally:
            loop.close()
        os._exit(23)
    input_path = directory / ("original.json" if mode == "resume" else "recovered.json")
    raw = input_path.read_bytes()
    now_ns = BASE_NS + (8 if mode == "resume" else 10) * SECOND
    result = resume(raw, expected_sha256, directory / f"{mode}.jsonl", now_ns)
    output_path = directory / ("recovered.json" if mode == "resume" else "replayed.json")
    write_new_checkpoint(output_path, result.checkpoint)
    recovered = verify_checkpoint(result.checkpoint)
    _, account, orders, positions = reconstruct_native(
        recovered["native"], venue_id_mode=NUMERIC_MODE
    )
    return {
        "pid": os.getpid(),
        "input_sha256": result.input_sha256,
        "output_sha256": result.output_sha256,
        "checks_passed": result.checks_passed,
        "runtime_ready": result.runtime_ready,
        "real_account_verified": result.real_account_verified,
        "downtime_risk_review_required": True,
        "state_sha256": recovered["sha256"],
        "risk_latched": result.risk_latched,
        "total_usdt": str(account.balance_total(USDT).as_decimal()),
        "total_btc": str(account.balance_total(BTC).as_decimal()),
        "orders": {str(o.client_order_id): o.status.name for o, _ in orders},
        "positions": {str(p.id): str(p.quantity.as_decimal()) for p in positions},
    }


def run_acceptance(directory):
    module = "apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance"
    command = [sys.executable, "-m", module, "--worker"]
    producer = subprocess.Popen(
        [*command, "produce", str(directory)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _, error = producer.communicate(timeout=30)
    except BaseException:
        producer.kill()
        producer.communicate()
        raise
    if producer.returncode != 23:
        raise RuntimeError(f"adapter checkpoint producer failed: {error}")
    original = (directory / "original.json").read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    reports = []
    selected_hash = original_hash
    for mode in ("resume", "replay"):
        completed = subprocess.run(
            [*command, mode, str(directory), "--expected-sha256", selected_hash],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode:
            raise RuntimeError(f"adapter checkpoint {mode} failed: {completed.stderr}")
        report = json.loads(completed.stdout)
        reports.append(report)
        selected_hash = report["output_sha256"]
    first, replay = reports
    if len({producer.pid, first["pid"], replay["pid"]}) != 3:
        raise RuntimeError("three distinct processes required")
    if any(
        first[key] != replay[key]
        for key in ("state_sha256", "orders", "positions", "total_usdt", "total_btc")
    ):
        raise RuntimeError("native recovery replay changed economic state")
    if (
        first["state_sha256"] != verify_checkpoint(original)["sha256"]
        or (directory / "original.json").read_bytes() != original
    ):
        raise RuntimeError("original checkpoint or strategy state changed")
    return {
        **replay,
        "distinct_processes": True,
        "producer_exit_code": 23,
        "original_preserved": True,
        "strategy_state_preserved": True,
        "replay_idempotent": True,
    }


def main():
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("produce", "resume", "replay"), help=argparse.SUPPRESS)
    parser.add_argument("directory", nargs="?", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if args.directory is None:
            parser.error("worker directory required")
        print(json.dumps(worker(args.directory, args.worker, args.expected_sha256)))
    else:
        with tempfile.TemporaryDirectory(prefix="adapter-checkpoint-") as directory:
            print(json.dumps(run_acceptance(Path(directory)), indent=2))


if __name__ == "__main__":
    main()

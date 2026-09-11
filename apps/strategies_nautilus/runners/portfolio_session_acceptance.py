"""Offline ADR-017 full-account native crash/recovery acceptance. No networking."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import BTC, ETH, USDT
from nautilus_trader.model.enums import AccountType, CurrencyType, OrderSide, TimeInForce
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    PositionId,
    StrategyId,
    TraderId,
)
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import AccountBalance, Currency, Money, Price, Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.events import TestEventStubs
from nautilus_trader.trading.strategy import Strategy

from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.portfolio_adapter_checkpoint import write_new_checkpoint
from apps.strategies_nautilus.portfolio_adapter_recovery import (
    EvidenceOnlyExecutionEngine,
    reconcile_binance_reports,
)
from apps.strategies_nautilus.portfolio_preflight import InstrumentRules
from apps.strategies_nautilus.portfolio_session_account import SessionCashAccount
from apps.strategies_nautilus.portfolio_session_ledger import (
    MODEL,
    SOURCE,
    STRATEGY,
    SessionLedger,
    read_session,
)
from apps.strategies_nautilus.portfolio_session_recovery import recover_session
from apps.strategies_nautilus.portfolio_stream import SourceBinding, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST

BASE = 1_789_056_000_000_000_000
SECOND = 1_000_000_000
SID = "fixture001"
BINDING = SourceBinding(TESTNET_REST, "123", hashlib.sha256(b"offline-session-key").hexdigest())


def fixture_context(loop, *, asset_count=3):
    clock = TestClock()
    clock.set_time(BASE)
    cache = Cache()
    fields = CurrencyPair.to_dict(TestInstrumentProvider.btcusdt_binance())
    # Accounting precision supports exact partial fills; effective order step is 0.00001.
    fields.update(size_precision=8, size_increment="0.00000001", maker_fee="0", taker_fee="0")
    instrument = CurrencyPair.from_dict(fields)
    cache.add_instrument(instrument)
    amounts = [(USDT, D("100")), (BTC, D("2")), (ETH, D("5"))]
    amounts += [
        (Currency(f"FX{i:03d}", 8, 0, f"Fixture asset {i}", CurrencyType.CRYPTO), D("1000"))
        for i in range(asset_count - 3)
    ]
    account = SessionCashAccount(
        AccountState(
            account_id=AccountId("BINANCE-123"),
            account_type=AccountType.CASH,
            base_currency=None,
            balances=[AccountBalance(Money(q, c), Money(0, c), Money(q, c)) for c, q in amounts],
            margins=[],
            reported=False,
            info={"offline_fixture": True},
            event_id=UUID4(),
            ts_event=BASE,
            ts_init=BASE,
        ),
        cache=cache,
    )
    cache.add_account(account)
    bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
    portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
    engine = EvidenceOnlyExecutionEngine(loop=loop, msgbus=bus, cache=cache, clock=clock)
    engine.register_oms_type(
        Strategy(
            StrategyConfig(strategy_id="TESTNET-SESSION", order_id_tag="TS", oms_type="HEDGING")
        )
    )
    return SimpleNamespace(cache=cache, clock=clock, portfolio=portfolio, engine=engine)


def rules(now):
    return InstrumentRules(
        "BTCUSDT.BINANCE",
        now,
        D("0.00001"),
        D("100"),
        D("0.00001"),
        D("0.01"),
        D("1000000"),
        D("0.01"),
        D("5"),
        D("9000000"),
        D(0),
    )


def signal(now, *, side="buy", suffix="entry"):
    return SignalEvent(
        schema_version="signal.v1",
        signal_id=f"session:{SID}:{suffix}",
        source=SOURCE,
        model_version=MODEL,
        symbol="BTCUSDT",
        venue="BINANCE",
        ts_event=now,
        horizon="1m",
        side=side,
        score=0.8 if side == "buy" else 0.0,
        confidence=0.9,
        ttl_seconds=60,
        metadata={"offline_fixture": True},
    )


def native_order(owner, sig, *, quantity="0.00010000", price="70000.00"):
    side = OrderSide.BUY if sig.side == "buy" else OrderSide.SELL
    return LimitOrder(
        trader_id=TraderId("BACKTESTER-001"),
        strategy_id=StrategyId(STRATEGY),
        instrument_id=owner.cache.instruments()[0].id,
        client_order_id=ClientOrderId(f"ts-{SID}-{'b' if sig.side == 'buy' else 's'}"),
        order_side=side,
        quantity=Quantity.from_str(quantity),
        price=Price.from_str(price),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=owner.clock.timestamp_ns(),
        tags=[f"signal_id:{sig.signal_id}", f"session_id:{SID}"],
    )


def install_submitted(owner, order):
    order.apply(
        TestEventStubs.order_submitted(
            order, account_id=owner.cache.accounts()[0].id, ts_event=owner.clock.timestamp_ns()
        )
    )
    owner.cache.add_order(order, position_id=PositionId(f"session-{SID}"))
    owner.portfolio.initialize_orders()
    owner.portfolio.initialize_positions()


def row(
    status,
    quantity,
    *,
    side="BUY",
    price="70000.00",
    original="0.00010000",
    time_offset=1,
    update_offset=6,
):
    return {
        "symbol": "BTCUSDT",
        "clientOrderId": f"ts-{SID}-{'b' if side == 'BUY' else 's'}",
        "orderId": 101 if side == "BUY" else 102,
        "side": side,
        "origQty": original,
        "executedQty": quantity,
        "price": price,
        "cummulativeQuoteQty": str(D(quantity) * D(price)),
        "status": status,
        "type": "LIMIT",
        "timeInForce": "GTC",
        "orderListId": -1,
        "time": (BASE + time_offset * SECOND) // 1_000_000,
        "updateTime": (BASE + update_offset * SECOND) // 1_000_000,
    }


def trade(tid, quantity, *, side="BUY", price="70000.00", offset=2):
    return {
        "symbol": "BTCUSDT",
        "orderId": 101 if side == "BUY" else 102,
        "id": tid,
        "price": price,
        "qty": quantity,
        "quoteQty": str(D(quantity) * D(price)),
        "commission": "0",
        "commissionAsset": "USDT",
        "isBuyer": side == "BUY",
        "isMaker": True,
        "time": (BASE + offset * SECOND) // 1_000_000,
    }


def recovery_evidence(*, asset_count=3, scenario="cancel", replay=False):
    # Independent fixed venue evidence; never obtained from recovered native balances.
    if scenario == "cancel":
        orders = [row("CANCELED", "0.00008000")]
        trades = [trade(201, "0.00004000"), trade(202, "0.00004000", offset=6)]
        quote, base = "94.40000000", "2.00008000"
    else:
        orders = [row("FILLED", "0.00010000")]
        trades = [trade(201, "0.00010000", offset=6)]
        quote, base = "93.00000000", "2.00010000"
    amounts = [("USDT", quote), ("BTC", base), ("ETH", "5")]
    amounts += [(f"FX{i:03d}", "1000") for i in range(asset_count - 3)]
    return canonical(
        {
            "profile": "offline_testnet_session_recovery_v1",
            "source": asdict(BINDING),
            "history_start_ns": BASE,
            "received_ns": BASE + (9 if replay else 8) * SECOND,
            "account": {
                "uid": 123,
                "accountType": "SPOT",
                "canTrade": True,
                "balances": [{"asset": a, "free": q, "locked": "0"} for a, q in amounts],
            },
            "orders": orders,
            "trades": trades,
            "open_orders": [],
        }
    )


def produce(path, scenario, asset_count):
    loop = asyncio.new_event_loop()
    owner = fixture_context(loop, asset_count=asset_count)
    ledger = SessionLedger(path).create(owner, session_id=SID, source=BINDING)
    owner.clock.set_time(BASE + SECOND)
    sig = signal(owner.clock.timestamp_ns())
    order = native_order(owner, sig)
    ledger.prepare(owner, signal=sig, order=order, rules=rules(owner.clock.timestamp_ns()))
    if scenario == "cancel":
        install_submitted(owner, order)
        owner.clock.set_time(BASE + 2 * SECOND)
        reconcile_binance_reports(
            owner.engine,
            owner.cache,
            account_id=owner.cache.accounts()[0].id,
            orders=[row("PARTIALLY_FILLED", "0.00004000", update_offset=2)],
            trades=[trade(201, "0.00004000")],
            now_ns=owner.clock.timestamp_ns(),
        )
        ledger.observe(owner)
        owner.clock.set_time(BASE + 5 * SECOND)
        ledger.prepare_cancel(owner, order)
        order.apply(TestEventStubs.order_pending_cancel(order, ts_event=owner.clock.timestamp_ns()))
        owner.cache.update_order(order)
        ledger.observe(owner)
    print(json.dumps({"pid": os.getpid(), "checkpoint_sha256": ledger.sha256}), flush=True)
    os._exit(23)  # Deliberately skip stop hooks, lock release and engine disposal.


def consume(path, output, scenario, asset_count, *, replay=False):
    raw = path.read_bytes()
    evidence = recovery_evidence(asset_count=asset_count, scenario=scenario, replay=replay)
    loop = asyncio.new_event_loop()
    try:
        result = recover_session(
            raw,
            evidence,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            evidence_sha256=hashlib.sha256(evidence).hexdigest(),
            now_ns=BASE + (9 if replay else 8) * SECOND,
            loop=loop,
        )
        write_new_checkpoint(output, result.pop("checkpoint"))
        result["pid"] = os.getpid()
        print(json.dumps(result, sort_keys=True))
    finally:
        loop.close()


def run_acceptance():
    reports = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for scenario in ("prepared", "cancel"):
            original, recovered, replayed = [
                root / f"{scenario}-{suffix}.json"
                for suffix in ("original", "recovered", "replayed")
            ]
            calls = [
                ("produce", original, recovered),
                ("consume", original, recovered),
                ("replay", recovered, replayed),
            ]
            stages = []
            for phase, source, output in calls:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        __name__
                        if __name__ != "__main__"
                        else "apps.strategies_nautilus.runners.portfolio_session_acceptance",
                        "--phase",
                        phase,
                        "--path",
                        str(source),
                        "--output",
                        str(output),
                        "--scenario",
                        scenario,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != (23 if phase == "produce" else 0):
                    raise RuntimeError(f"offline session {phase} failed: {result.stderr[-2500:]}")
                stages.append(json.loads(result.stdout.splitlines()[-1]))
            if len({s["pid"] for s in stages}) != 3 or stages[1]["view"] != stages[2]["view"]:
                raise RuntimeError("fresh-process native replay drift")
            original_state = read_session(original.read_bytes())["state"]
            restored_state = read_session(recovered.read_bytes())["state"]
            assert original_state["intents"] == restored_state["intents"]
            assert original_state["cancel_intents"] == restored_state["cancel_intents"]
            assert restored_state["view"]["buy_allowance_consumed"]
            reports[scenario] = {
                "three_distinct_processes": True,
                "full_assets_preserved": stages[1]["full_account_assets"],
                "owned_btc": stages[1]["view"]["owned_btc"],
                "buy_spent_usdt": stages[1]["view"]["buy_spent_usdt"],
                "native_replay_stable": True,
                "buy_allowance_preserved": True,
            }
    return {"scenarios": reports, "runtime_ready": False, "matching_requests_made": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("produce", "consume", "replay"))
    parser.add_argument("--path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scenario", choices=("prepared", "cancel"), default="cancel")
    args = parser.parse_args()
    if args.phase == "produce":
        produce(args.path, args.scenario, 502)
    elif args.phase:
        consume(args.path, args.output, args.scenario, 502, replay=args.phase == "replay")
    else:
        print(json.dumps(run_acceptance(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

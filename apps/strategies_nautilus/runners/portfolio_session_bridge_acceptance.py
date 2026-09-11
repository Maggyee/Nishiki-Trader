"""Queued native ADR-017 adapter acceptance with an in-memory HTTP sink only."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal as D
from pathlib import Path

import msgspec
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.risk.engine import RiskEngine

from apps.strategies_nautilus.portfolio_session_bridge import (
    SessionBinanceFixtureClient,
    SessionBridge,
    SessionExecutionEngine,
    SessionStrategy,
)
from apps.strategies_nautilus.portfolio_session_ledger import SessionLedger, read_session
from apps.strategies_nautilus.runners.portfolio_session_acceptance import (
    BASE,
    BINDING,
    SECOND,
    SID,
    fixture_context,
    rules,
    signal,
)


def build_bridge(path, *, asset_count=3, risk_cap=10):
    loop = asyncio.get_running_loop()
    owner = fixture_context(loop, asset_count=asset_count, with_engine=False)
    ledger = SessionLedger(path).create(owner, session_id=SID, source=BINDING)
    bridge = SessionBridge(owner, ledger)
    owner.ledger, owner.bridge = ledger, bridge
    owner.engine = SessionExecutionEngine(
        bridge=bridge,
        loop=loop,
        msgbus=owner.msgbus,
        cache=owner.cache,
        clock=owner.clock,
    )
    owner.risk = RiskEngine(
        portfolio=owner.portfolio,
        msgbus=owner.msgbus,
        cache=owner.cache,
        clock=owner.clock,
        config=RiskEngineConfig(max_notional_per_order={"BTCUSDT.BINANCE": risk_cap}),
    )
    owner.strategy = SessionStrategy(bridge)
    owner.strategy.register(
        trader_id=TraderId("BACKTESTER-001"),
        portfolio=owner.portfolio,
        msgbus=owner.msgbus,
        cache=owner.cache,
        clock=owner.clock,
    )
    owner.engine.register_oms_type(owner.strategy)
    owner.client = SessionBinanceFixtureClient(bridge=bridge, loop=loop, msgbus=owner.msgbus)
    owner.engine.register_client(owner.client)
    owner.portfolio.initialize_orders()
    owner.portfolio.initialize_positions()
    owner.risk.start()
    owner.engine.start()
    owner.strategy.start()
    owner.clock.set_time(BASE + SECOND)
    return owner


async def drain(owner):
    # Bounded cooperative scheduling, not wall-clock waiting. Includes queue ->
    # client task -> native event queue -> receipt future -> HTTP continuation.
    for _ in range(40):
        await asyncio.sleep(0)
    if owner.engine.cmd_qsize() or owner.engine.evt_qsize():
        raise AssertionError("native queues failed to drain")


async def close_bridge(owner):
    tasks = list(owner.client._tasks)
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    owner.strategy.stop()
    owner.risk.stop()
    owner.engine.stop()
    await asyncio.gather(
        owner.engine.get_cmd_queue_task(),
        owner.engine.get_evt_queue_task(),
    )
    owner.engine.dispose()
    owner.ledger.close()


def execution_report(
    owner, order, *, kind="NEW", quantity="0.00000000", total="0.00000000", tid=-1
):
    timestamp = owner.clock.timestamp_ms()
    is_trade = kind == "TRADE"
    return msgspec.json.encode(
        {
            "e": "executionReport",
            "E": timestamp,
            "s": "BTCUSDT",
            "c": str(order.client_order_id),
            "S": order.side.name,
            "o": "LIMIT",
            "f": "GTC",
            "q": str(order.quantity),
            "p": str(order.price),
            "P": "0",
            "F": "0",
            "g": -1,
            "C": str(order.client_order_id) if kind == "CANCELED" else "",
            "x": kind,
            "X": ("FILLED" if total == str(order.quantity) else "PARTIALLY_FILLED")
            if is_trade
            else kind,
            "r": "NONE",
            "i": 101 if order.side.name == "BUY" else 102,
            "l": quantity,
            "z": total,
            "L": str(order.price) if is_trade else "0",
            "n": "0",
            "N": "USDT",
            "T": timestamp,
            "t": tid,
            "I": 0,
            "w": kind == "NEW",
            "m": True,
            "M": False,
            "O": (BASE + SECOND) // 1_000_000,
            "Z": str(D(total) * order.price.as_decimal()),
            "Y": str(D(quantity) * order.price.as_decimal()),
            "Q": "0",
        }
    )


async def run_acceptance():
    with tempfile.TemporaryDirectory(prefix="session-bridge-") as directory:
        owner = build_bridge(Path(directory) / "session.json", asset_count=502)
        try:
            order = owner.strategy.consume(
                signal(owner.clock.timestamp_ns()),
                rules=rules(owner.clock.timestamp_ns()),
                price="70000.00",
            )
            await drain(owner)
            assert len(owner.client.sink.calls) == 1 and not owner.bridge.failed
            owner.clock.set_time(BASE + 2 * SECOND)
            owner.client._handle_user_ws_message(execution_report(owner, order))
            await drain(owner)
            owner.clock.set_time(BASE + 3 * SECOND)
            owner.client._handle_user_ws_message(
                execution_report(
                    owner,
                    order,
                    kind="TRADE",
                    quantity="0.00004000",
                    total="0.00004000",
                    tid=201,
                )
            )
            await drain(owner)
            owner.clock.set_time(BASE + 4 * SECOND)
            owner.strategy.request_cancel(order)
            await drain(owner)
            owner.clock.set_time(BASE + 5 * SECOND)
            late = execution_report(
                owner,
                order,
                kind="TRADE",
                quantity="0.00004000",
                total="0.00008000",
                tid=202,
            )
            owner.client._handle_user_ws_message(late)
            await drain(owner)
            owner.client._handle_user_ws_message(late)
            await drain(owner)
            owner.client._handle_user_ws_message(
                execution_report(
                    owner,
                    order,
                    kind="CANCELED",
                    total="0.00008000",
                )
            )
            await drain(owner)
            assert not owner.bridge.failed, owner.ledger.state["halt_reasons"]
            view = owner.ledger.state["view"]
            assert D(view["owned_btc"]) == D("0.00008")
            assert len(view["fills"]) == 2 and len(owner.client.sink.calls) == 2
            return {
                "mode": "offline_native_adapter_bridge",
                "runtime_ready": False,
                "network_requests": 0,
                "fixture_dispatches": len(owner.client.sink.calls),
                "assets_retained": len(owner.ledger.state["baseline"]),
                "owned_btc": view["owned_btc"],
                "buy_spent_usdt": view["buy_spent_usdt"],
                "order_status": order.status.name,
                "native_risk_commands": owner.risk.command_count,
            }
        finally:
            await close_bridge(owner)


async def crash_producer(path, kind):
    owner = build_bridge(path, asset_count=502)

    async def crash():
        os._exit(23)  # No strategy stop, task cleanup, or final snapshot.

    if kind == "submit":
        owner.client.sink.before_response = crash
    order = owner.strategy.consume(
        signal(owner.clock.timestamp_ns()),
        rules=rules(owner.clock.timestamp_ns()),
        price="70000.00",
    )
    await drain(owner)
    if kind == "cancel":
        owner.clock.set_time(BASE + 2 * SECOND)
        owner.client._handle_user_ws_message(execution_report(owner, order))
        await drain(owner)
        owner.client._handle_user_ws_message(
            execution_report(
                owner,
                order,
                kind="TRADE",
                quantity="0.00004000",
                total="0.00004000",
                tid=201,
            )
        )
        await drain(owner)
        owner.clock.set_time(BASE + 4 * SECOND)
        owner.client.sink.before_response = crash
        owner.strategy.request_cancel(order)
        await drain(owner)
    raise AssertionError("fixture did not reach the selected crash boundary")


def run_crash_acceptance():
    results = {}
    with tempfile.TemporaryDirectory(prefix="session-bridge-crash-") as directory:
        for kind in ("submit", "cancel"):
            original, recovered, replayed = [
                Path(directory) / f"{kind}-{stage}.json"
                for stage in ("original", "recovered", "replayed")
            ]
            producer = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance",
                    "--crash",
                    kind,
                    "--path",
                    str(original),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if producer.returncode != 23:
                raise AssertionError(f"bridge producer failed: {producer.stderr[-2000:]}")
            consumers = []
            for phase, source, output in (
                ("consume", original, recovered),
                ("replay", recovered, replayed),
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "apps.strategies_nautilus.runners.portfolio_session_acceptance",
                        "--phase",
                        phase,
                        "--path",
                        str(source),
                        "--output",
                        str(output),
                        "--scenario",
                        "prepared" if kind == "submit" else "cancel",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode:
                    raise AssertionError(f"bridge recovery failed: {result.stderr[-2000:]}")
                consumers.append(json.loads(result.stdout.splitlines()[-1]))
            before, after, replay = [
                read_session(p.read_bytes())["state"] for p in (original, recovered, replayed)
            ]
            assert before["dispatches"] == after["dispatches"] == replay["dispatches"]
            assert consumers[0]["pid"] != consumers[1]["pid"]
            assert consumers[0]["view"] == consumers[1]["view"]
            assert len(after["baseline"]) == 502
            results[kind] = {
                "abrupt_exit": True,
                "fresh_process_replay_stable": True,
                "dispatches_preserved": len(after["dispatches"]),
                "owned_btc": after["view"]["owned_btc"],
            }
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crash", choices=("submit", "cancel"))
    parser.add_argument("--path", type=Path)
    args = parser.parse_args()
    if args.crash:
        if args.path is None:
            parser.error("--path required for crash producer")
        asyncio.run(crash_producer(args.path, args.crash))
    else:
        result = asyncio.run(run_acceptance())
        result["crash_recovery"] = run_crash_acceptance()
        print(json.dumps(result, sort_keys=True))

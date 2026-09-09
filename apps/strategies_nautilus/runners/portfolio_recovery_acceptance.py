"""Two-process native crash/recovery acceptance with synthetic account evidence.

No credentials, HTTP, live execution, research data or production-readiness claim.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from nautilus_trader.model.events import OrderFilled

from apps.strategies_nautilus.portfolio_account import (
    AccountAnchor,
    AccountEvidence,
    native_account_view,
)
from apps.strategies_nautilus.portfolio_recovery import recover_simulation
from apps.strategies_nautilus.portfolio_simulation import D
from apps.strategies_nautilus.portfolio_venue import CapturedResponse
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
    BASE_NS,
    SECOND,
    advance,
    build_simulation,
    fixture_signal,
)


def fixture_account_evidence(strategy):
    """Independent serialized fixture observation, never a real signed response."""
    cache = strategy.cache
    account = cache.accounts()[0]
    anchor = AccountAnchor("synthetic-authority", str(account.id), BASE_NS, D("500"))
    orders = [(o, cache.position_id(o.client_order_id)) for o in cache.orders()]
    balances, rows, _ = native_account_view(
        account, orders, cache.positions(), strategy.state_data["orders"], anchor
    )
    now = strategy.clock.timestamp_ns()
    account_body = {
        "uid": anchor.venue_uid,
        "accountType": "SPOT",
        "canTrade": True,
        "permissions": ["SPOT"],
        "updateTime": now // 1_000_000,
        "balances": [
            {"asset": c, "free": str(v[1]), "locked": str(v[2])}
            for c, v in sorted(balances.items())
        ],
    }
    order_rows, trade_rows = [], []
    for order, _ in sorted(orders, key=lambda row: str(row[0].client_order_id)):
        oid = str(order.client_order_id)
        vid, side, qty, filled, price, notional, status = rows[oid]
        order_rows.append(
            {
                "symbol": "BTCUSDT",
                "clientOrderId": oid,
                "orderId": vid,
                "side": side,
                "origQty": str(qty),
                "executedQty": str(filled),
                "price": str(price),
                "cummulativeQuoteQty": str(notional),
                "status": status,
                "type": "LIMIT",
                "timeInForce": "GTC",
                "time": order.events[0].ts_init // 1_000_000,
            }
        )
        for event in order.events:
            if isinstance(event, OrderFilled):
                trade_rows.append(
                    {
                        "symbol": "BTCUSDT",
                        "orderId": vid,
                        "id": str(event.trade_id),
                        "qty": str(event.last_qty.as_decimal()),
                        "price": str(event.last_px.as_decimal()),
                        "quoteQty": str(event.last_qty.as_decimal() * event.last_px.as_decimal()),
                        "commission": str(event.commission.as_decimal()),
                        "commissionAsset": event.commission.currency.code,
                        "isBuyer": side == "BUY",
                        "time": event.ts_event // 1_000_000,
                    }
                )

    def response(body, symbol=None):
        return CapturedResponse(json.dumps(body), now, anchor.venue_uid, symbol)

    evidence = AccountEvidence(
        response(account_body),
        response(order_rows, "BTCUSDT"),
        response(trade_rows, "BTCUSDT"),
        response([row for row in order_rows if row["status"] in {"NEW", "PARTIALLY_FILLED"}]),
        BASE_NS,
        now,
    )
    return anchor, evidence


def produce(directory):
    def enter(strategy):
        strategy.process_signals(tuple(fixture_signal(s, "entry", BASE_NS) for s in ("v16", "v18")))

    engine, strategy, instrument = build_simulation(
        directory / "checkpoint.json",
        {BASE_NS: enter},
        fee_mode="received_asset",
        exit_policy="whole_steps_v1",
        persist_native=True,
    )
    advance(engine, instrument, BASE_NS)
    advance(engine, instrument, BASE_NS + 2 * SECOND, bid="99999", ask="100000", size="0.001333")
    advance(engine, instrument, BASE_NS + 4 * SECOND, bid="40000", ask="100010")
    assert strategy.snapshot().risk_latched
    strategy.process_signals((fixture_signal("v16", "exit", BASE_NS + 4 * SECOND, "flat"),))
    advance(engine, instrument, BASE_NS + 6 * SECOND)
    anchor, evidence = fixture_account_evidence(strategy)
    observed = {"anchor": asdict(anchor), "evidence": asdict(evidence), "producer_pid": os.getpid()}
    # Persist external fixture evidence independently; crash does not run stop hooks.
    with (directory / "observation.json").open("w") as stream:
        json.dump(observed, stream, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(23)


def resume(directory):
    observed = json.loads((directory / "observation.json").read_text())
    anchor = AccountAnchor(
        **{
            **observed["anchor"],
            "quote": D(observed["anchor"]["quote"]),
            "base": D(observed["anchor"]["base"]),
        }
    )
    fields = observed["evidence"]
    evidence = AccountEvidence(
        **{
            **fields,
            **{
                k: CapturedResponse(**fields[k])
                for k in ("account", "orders", "trades", "open_orders")
            },
        }
    )
    engine, strategy, instrument, checked = recover_simulation(
        directory / "checkpoint.json",
        evidence=evidence,
        anchor=anchor,
        now_ns=BASE_NS + 8 * SECOND,
    )
    try:
        advance(engine, instrument, BASE_NS + 8 * SECOND)
        before = strategy.snapshot()
        assert dict(before.holdings)["v16"] == D("0.00000050")
        assert dict(before.holdings)["v18"] == D("0.00033250")
        assert before.risk_latched
        assert len(engine.cache.orders()) == 3
        # Native matching resumes the original partial order, without resubmission.
        advance(engine, instrument, BASE_NS + 10 * SECOND, bid="99998", ask="99999")
        filled = strategy.snapshot()
        assert dict(filled.holdings)["v18"] == D("0.00099850")
        strategy.process_signals((fixture_signal("v18", "entry", BASE_NS),))
        blocked = strategy.process_signals(
            (fixture_signal("v22", "blocked", BASE_NS + 10 * SECOND),)
        )
        assert not blocked.selected and len(engine.cache.orders()) == 3
        result = strategy.process_signals(
            (fixture_signal("v18", "exit", BASE_NS + 10 * SECOND, "flat"),)
        )
        assert len(result.selected) == 1
        advance(engine, instrument, BASE_NS + 12 * SECOND)
        final = strategy.snapshot()
        assert final.total_base == D("0.00000100") and final.total_quote == D("499.30060")
        assert final.risk_latched and len(engine.cache.orders()) == 4
        fixture_account_evidence(strategy)  # recheck full lineage/fees, including new venue IDs
        return {
            "status": "passed",
            "scope": "synthetic_native_process_recovery",
            "distinct_processes": observed["producer_pid"] != os.getpid(),
            "abrupt_exit_code": 23,
            "account_evidence_agrees": checked.checks_passed,
            "real_account_verified": False,
            "runtime_ready": False,
            "native_order_count": 4,
            "total_quote_usdt": str(final.total_quote),
            "residual_btc": str(final.total_base),
            "risk_latched": final.risk_latched,
            "partial_order_resumed_without_resubmit": True,
        }
    finally:
        engine.end()
        engine.dispose()


def run_acceptance(directory):
    module = "apps.strategies_nautilus.runners.portfolio_recovery_acceptance"
    produced = subprocess.run(
        [sys.executable, "-m", module, "--worker", "produce", str(directory)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if produced.returncode != 23:
        raise RuntimeError(f"recovery producer failed: {produced.stderr}")
    recovered = subprocess.run(
        [sys.executable, "-m", module, "--worker", "resume", str(directory)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if recovered.returncode:
        raise RuntimeError(f"recovery consumer failed: {recovered.stderr}")
    report = json.loads(recovered.stdout)
    if not report["distinct_processes"]:
        raise RuntimeError("new process not verified")
    return report


def main():
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("produce", "resume"), help=argparse.SUPPRESS)
    parser.add_argument("directory", nargs="?", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if args.directory is None:
            parser.error("worker directory required")
        if args.worker == "produce":
            produce(args.directory)
        else:
            print(json.dumps(resume(args.directory)))
    else:
        with tempfile.TemporaryDirectory(prefix="portfolio-recovery-") as directory:
            print(json.dumps(run_acceptance(Path(directory)), indent=2))


if __name__ == "__main__":
    main()

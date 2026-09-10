"""Reconcile a detached numeric-venue checkpoint; never resume execution.

Every result still needs downtime risk review. Native reconciliation mutates only
a disposable cache; original checkpoint bytes and opaque strategy state stay intact.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import LiveExecEngineConfig, StrategyConfig
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.trading.strategy import Strategy

from apps.strategies_nautilus.portfolio_account import reconcile_account
from apps.strategies_nautilus.portfolio_adapter_recovery import (
    EvidenceOnlyExecutionEngine,
    reconcile_binance_reports,
)
from apps.strategies_nautilus.portfolio_recovery import (
    RecoveryError,
    capture_native,
    reconstruct_native,
    verify_checkpoint,
)
from apps.strategies_nautilus.portfolio_stream import StreamFence, canonical
from apps.strategies_nautilus.portfolio_venue import _fresh, _unique_object

NUMERIC_MODE = "binance_numeric_offline_v1"


def checkpoint_bytes(state, native):
    return canonical(
        {
            "state": state,
            "native": native,
            "sha256": hashlib.sha256(canonical(state)).hexdigest(),
            "native_sha256": hashlib.sha256(canonical(native)).hexdigest(),
            "generation_sha256": hashlib.sha256(
                canonical({"state": state, "native": native})
            ).hexdigest(),
        }
    )


def write_new_checkpoint(path: Path, raw: bytes):
    """Publish a durable new artifact without replacing any existing checkpoint."""
    verify_checkpoint(raw)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.link(temporary, path)  # atomic, exclusive publish; existing path must fail
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class AdapterCheckpointResult:
    checkpoint: bytes
    input_sha256: str
    output_sha256: str
    account_evidence_sha256: tuple[tuple[str, str], ...]
    risk_latched: bool
    stream_fence: StreamFence
    wire_sha256: tuple[tuple[str, str], ...]
    checks_passed: bool = True
    runtime_ready: bool = False
    real_account_verified: bool = False
    downtime_risk_review_required: bool = True


def reconcile_adapter_checkpoint(
    raw,
    *,
    expected_sha256,
    anchor,
    collected,
    stream,
    now_ns,
    loop,
    max_age_ns=60_000_000_000,
):
    """Source-fenced evidence -> native reports -> exact complete account check.

    This is synchronous on the stream's owner loop. The supplied input hash binds
    the caller's chosen checkpoint; hashes do not independently prove provenance.
    Opaque strategy state is preserved, not policy-qualified or started.
    """
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise RecoveryError("selected checkpoint digest changed")
    wrapped = verify_checkpoint(raw)
    native, state = wrapped["native"], wrapped["state"]
    if type(state.get("risk_latched")) is not bool or not isinstance(state.get("orders"), dict):
        raise RecoveryError("persisted order/risk state required")
    if state.get("halt_reason"):
        raise RecoveryError("persisted halt requires explicit incident resolution")
    anchor_fields = {**asdict(anchor), "quote": str(anchor.quote), "base": str(anchor.base)}
    if native["anchor"] != anchor_fields:
        raise RecoveryError("checkpoint account anchor mismatch")
    if type(now_ns) is not int or not anchor.start_ns <= native["ts_ns"] < now_ns:
        raise RecoveryError("recovery must advance beyond checkpoint cursor")
    if (
        collected.stream_fence is None
        or collected.stream_fence.binding.account_uid != anchor.venue_uid
    ):
        raise RecoveryError("source-bound collected account fence required")
    stream.assert_fence(collected.stream_fence)
    evidence = collected.evidence
    if evidence.start_ns != anchor.start_ns or not native["ts_ns"] <= evidence.end_ns <= now_ns:
        raise RecoveryError("account evidence does not cover checkpoint downtime")
    # Reject stale or mismatched captures before entering native mutation.
    for name in ("account", "orders", "trades", "open_orders"):
        response = getattr(evidence, name)
        _fresh(response.received_ns, now_ns, max_age_ns)
        if response.account_id != anchor.venue_uid:
            raise RecoveryError("account evidence source mismatch")
    orders = json.loads(evidence.orders.body, object_pairs_hook=_unique_object)
    trades = json.loads(evidence.trades.body, object_pairs_hook=_unique_object)
    instrument, account, native_orders, positions = reconstruct_native(
        native,
        venue_id_mode=NUMERIC_MODE,
        calculate_account_state=True,
    )
    if set(state["orders"]) != {str(order.client_order_id) for order, _ in native_orders}:
        raise RecoveryError("unknown prepared or native order")
    clock = TestClock()
    clock.set_time(now_ns)
    cache = Cache()
    cache.add_instrument(instrument)
    cache.add_account(account)
    for order, position_id in native_orders:
        cache.add_order(order, position_id=position_id)
    for position in positions:
        cache.add_position(position, OmsType.HEDGING)
    cache.build_index()
    bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
    portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
    engine = EvidenceOnlyExecutionEngine(
        loop=loop,
        msgbus=bus,
        cache=cache,
        clock=clock,
        config=LiveExecEngineConfig(filter_unclaimed_external_orders=False),
    )
    try:
        engine.register_oms_type(
            Strategy(
                StrategyConfig(
                    strategy_id="PORTFOLIO-FIXTURE",
                    order_id_tag="PF",
                    oms_type="HEDGING",
                )
            )
        )
        portfolio.initialize_orders()
        portfolio.initialize_positions()
        stream.assert_fence(collected.stream_fence)
        reconcile_binance_reports(
            engine,
            cache,
            account_id=account.id,
            orders=orders,
            trades=trades,
            now_ns=now_ns,
        )
        result = reconcile_account(
            evidence,
            anchor=anchor,
            native=(
                account,
                [(o, cache.position_id(o.client_order_id)) for o in cache.orders()],
                cache.positions(),
            ),
            intents=state["orders"],
            now_ns=now_ns,
            max_age_ns=max_age_ns,
        )
        if not result.checks_passed:
            raise RecoveryError("; ".join(result.reasons))
        updated = checkpoint_bytes(
            state,
            capture_native(
                SimpleNamespace(cache=cache, clock=clock),
                venue_id_mode=NUMERIC_MODE,
                anchor=anchor,
            ),
        )
        stream.assert_fence(collected.stream_fence)
        return AdapterCheckpointResult(
            updated,
            expected_sha256,
            hashlib.sha256(updated).hexdigest(),
            result.response_sha256,
            state["risk_latched"],
            collected.stream_fence,
            collected.wire_sha256,
        )
    finally:
        engine.dispose()

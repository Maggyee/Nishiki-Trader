"""NautilusTrader `Strategy` wrapper around `BaselineSignalStrategy`.

This is the Phase 2 bridge between the pure-Python decision layer
(`apps/strategies_nautilus/baseline_strategy.py`) and the real NautilusTrader
runtime. Order submission goes through `self.submit_order(...)`, which routes
into the live `RiskEngine` and `ExecutionEngine`; nothing here bypasses
NautilusTrader's risk controls.

The strategy:

1. On `on_start`, subscribes to the configured `BarType`. The full list of
   `SignalEvent`s for the run is loaded into memory at construction time,
   sorted by `(ts_event, signal_id)` for determinism.
2. On each `Bar`, pops every signal whose `ts_event` is at-or-before the bar
   time, asks `BaselineSignalStrategy.decide(...)` for an `OrderIntent`, and
   either submits a market order (`target_long` / `target_short`) or closes
   positions (`target_flat`). `skip` is a no-op.
3. Tracks `lineage` (one record per `SignalEvent`) including the
   `client_order_id` of any submitted order, so the runner can write
   `signal_lineage.parquet` per ADR-004 §2.3 and join `signal_id` back
   through `orders / fills / positions`.

The order-vs-position policy is idempotent: a `target_long` while already
long is a no-op; a `target_long` while short closes the short first
(`close_all_positions`) and then sends the new BUY. This keeps state
recoverable when signals repeat without forcing the strategy to track its
own position book in parallel with `self.portfolio`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.strategy import Strategy

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_nautilus.baseline_strategy import (
    BaselineSignalStrategy,
    BaselineStrategyConfig,
    OrderIntent,
)


class SignalSource(Protocol):
    """Pluggable signal feed consumed by ``BaselineNautilusStrategy.on_bar``.

    Implementations must return every signal whose ``ts_event`` is ≤
    ``until_ns`` and that has not been popped before, in
    ``(ts_event, signal_id)`` order. A source must never re-emit a signal.
    """

    def pop_due(self, until_ns: int) -> list[SignalEvent]: ...


@dataclass
class StaticSignalSource:
    """Default in-memory ``SignalSource``. Used by backtests and tests.

    The full event list is provided at construction, sorted by
    ``(ts_event, signal_id)`` once, and consumed via an advancing index.
    """

    events: list[SignalEvent] = field(default_factory=list)
    _sorted: list[SignalEvent] = field(default_factory=list, init=False, repr=False)
    _idx: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._sorted = sorted(self.events, key=lambda e: (e.ts_event, e.signal_id))

    def pop_due(self, until_ns: int) -> list[SignalEvent]:
        out: list[SignalEvent] = []
        while (
            self._idx < len(self._sorted)
            and int(self._sorted[self._idx].ts_event) <= until_ns
        ):
            out.append(self._sorted[self._idx])
            self._idx += 1
        return out


@dataclass
class SignalStorePollingSource:
    """Incremental ``SignalStore`` poller for testnet / live runtime.

    Each ``pop_due(until_ns)`` issues
    ``store.replay(source=..., model_version=..., since_ns=cursor_ns,
    until_ns=until_ns)`` and advances ``cursor_ns`` to one nanosecond past
    the largest ``ts_event`` seen. ``cursor_ns`` should be initialised to
    the runner start time so historical backfills are not re-consumed on
    every restart — the operator launcher is responsible for picking that
    value (typically ``time.time_ns()`` at startup, or
    ``previous_processed_until_ns + 1`` for a restart).
    """

    store: SignalStore
    source: str
    model_version: str
    cursor_ns: int

    def pop_due(self, until_ns: int) -> list[SignalEvent]:
        if until_ns < self.cursor_ns:
            return []
        events = self.store.replay(
            source=self.source,
            model_version=self.model_version,
            since_ns=self.cursor_ns,
            until_ns=until_ns,
        )
        if events:
            self.cursor_ns = max(int(e.ts_event) for e in events) + 1
        return events

SIGNAL_TAG_PREFIX = "signal_id:"


@dataclass
class LineageRecord:
    signal_id: str
    source: str
    model_version: str
    ts_event: int
    decision: str
    reason: str | None
    client_order_ids: list[str]
    ts_decision: int


@dataclass
class BaselineNautilusStrategyParams:
    instrument_id: InstrumentId
    bar_type: BarType
    baseline_config: BaselineStrategyConfig
    trade_size: Decimal
    equity_currency: Currency
    signals: list[SignalEvent] = field(default_factory=list)
    signal_source: SignalSource | None = None
    lineage: list[LineageRecord] = field(default_factory=list)


class BaselineNautilusStrategy(Strategy):
    def __init__(self, params: BaselineNautilusStrategyParams) -> None:
        super().__init__()
        self._params = params
        self._baseline = BaselineSignalStrategy(config=params.baseline_config)
        if params.signal_source is not None:
            self._signal_source: SignalSource = params.signal_source
        else:
            self._signal_source = StaticSignalSource(events=list(params.signals))
        self.lineage = params.lineage  # shared with runner
        self._current_day: date | None = None
        self._day_open_equity: float | None = None

    @property
    def instrument_id(self) -> InstrumentId:
        return self._params.instrument_id

    def on_start(self) -> None:
        self.subscribe_bars(self._params.bar_type)

    def on_bar(self, bar: Bar) -> None:
        bar_ns = int(bar.ts_event)
        self._update_daily_risk_state(bar_ns)
        for event in self._signal_source.pop_due(bar_ns):
            intent = self._baseline.decide(event, now_ns=bar_ns)
            client_order_ids = self._apply_intent(intent)
            self.lineage.append(
                LineageRecord(
                    signal_id=event.signal_id,
                    source=event.source,
                    model_version=event.model_version,
                    ts_event=int(event.ts_event),
                    decision=intent.action,
                    reason=intent.reason,
                    client_order_ids=client_order_ids,
                    ts_decision=bar_ns,
                )
            )

    def _apply_intent(self, intent: OrderIntent) -> list[str]:
        action = intent.action
        if action == "skip":
            return []

        # ADR-006 §2.5: dry-run intents must produce no orders. The lineage
        # row still records the action + target_position_pct via the caller,
        # so audits can reconstruct what the strategy would have submitted.
        if intent.dry_run:
            return []

        instrument = self.cache.instrument(self._params.instrument_id)
        if instrument is None:
            return []

        tags = [_signal_tag(intent.signal_id)]

        if action == "target_long":
            if self.portfolio.is_net_long(self._params.instrument_id):
                return []
            if self.portfolio.is_net_short(self._params.instrument_id):
                self.close_all_positions(self._params.instrument_id, tags=tags)
            order = self.order_factory.market(
                instrument_id=self._params.instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(self._params.trade_size),
                tags=tags,
            )
            self.submit_order(order)
            return [order.client_order_id.value]

        if action == "target_short":
            if self.portfolio.is_net_short(self._params.instrument_id):
                return []
            if self.portfolio.is_net_long(self._params.instrument_id):
                self.close_all_positions(self._params.instrument_id, tags=tags)
            order = self.order_factory.market(
                instrument_id=self._params.instrument_id,
                order_side=OrderSide.SELL,
                quantity=instrument.make_qty(self._params.trade_size),
                tags=tags,
            )
            self.submit_order(order)
            return [order.client_order_id.value]

        if action == "target_flat":
            if self.portfolio.is_flat(self._params.instrument_id):
                return []
            self.close_all_positions(self._params.instrument_id, tags=tags)
            return []

        raise ValueError(f"unknown OrderIntent.action={action!r}")

    def _update_daily_risk_state(self, now_ns: int) -> None:
        current_day = datetime.fromtimestamp(now_ns / 1_000_000_000, tz=UTC).date()
        equity = self._current_equity()
        if self._current_day != current_day:
            self._current_day = current_day
            self._day_open_equity = equity
            self._baseline.on_day_start()
        if self._day_open_equity is not None and equity is not None:
            self._baseline.on_account_update(
                equity_open=self._day_open_equity,
                equity_now=equity,
            )

    def _current_equity(self) -> float | None:
        equities = self.portfolio.equity(venue=self._params.instrument_id.venue)
        if not equities:
            return None
        money = equities.get(self._params.equity_currency)
        if money is not None:
            return float(money.as_double())
        if len(equities) == 1:
            return float(next(iter(equities.values())).as_double())
        return None

    def on_stop(self) -> None:
        self.close_all_positions(self._params.instrument_id)
        self.unsubscribe_bars(self._params.bar_type)


__all__ = [
    "BaselineNautilusStrategy",
    "BaselineNautilusStrategyParams",
    "LineageRecord",
    "SIGNAL_TAG_PREFIX",
    "SignalSource",
    "SignalStorePollingSource",
    "StaticSignalSource",
]


def _signal_tag(signal_id: str) -> str:
    return f"{SIGNAL_TAG_PREFIX}{signal_id}"

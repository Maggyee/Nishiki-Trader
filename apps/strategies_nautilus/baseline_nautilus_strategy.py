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

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.strategy import Strategy

from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.baseline_strategy import (
    BaselineSignalStrategy,
    BaselineStrategyConfig,
    OrderIntent,
)

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
    signals: list[SignalEvent]
    baseline_config: BaselineStrategyConfig
    trade_size: Decimal
    equity_currency: Currency
    lineage: list[LineageRecord] = field(default_factory=list)


class BaselineNautilusStrategy(Strategy):
    def __init__(self, params: BaselineNautilusStrategyParams) -> None:
        super().__init__()
        self._params = params
        self._baseline = BaselineSignalStrategy(config=params.baseline_config)
        self._signals = sorted(
            params.signals,
            key=lambda e: (e.ts_event, e.signal_id),
        )
        self._signal_idx = 0
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
        while (
            self._signal_idx < len(self._signals)
            and int(self._signals[self._signal_idx].ts_event) <= bar_ns
        ):
            event = self._signals[self._signal_idx]
            self._signal_idx += 1
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
]


def _signal_tag(signal_id: str) -> str:
    return f"{SIGNAL_TAG_PREFIX}{signal_id}"

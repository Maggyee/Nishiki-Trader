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
   time, rejects events for a different instrument, asks
   `BaselineSignalStrategy.decide(...)` for an `OrderIntent`, and
   either submits a market order (`target_long` / `target_short`) or closes
   positions (`target_flat`). `skip` is a no-op. If multiple executable
   signals are due on the same bar, only the first order-submitting intent is
   sent to NautilusTrader; later same-bar intents are preserved in lineage but
   suppressed so the next bar can observe the updated portfolio state.
3. Tracks `lineage` (one record per `SignalEvent`) including the
   `client_order_id` of any submitted order, so the runner can write
   `signal_lineage.parquet` per ADR-004 §2.3 and join `signal_id` back
   through `orders / fills / positions`.

The order-vs-position policy is idempotent: a `target_long` while already
long is a no-op; a `target_long` while short closes the short first
(`close_all_positions`) and then sends the new BUY. This keeps state
recoverable when signals repeat without forcing the strategy to track its
own position book in parallel with `self.portfolio`.

On a CASH (spot) account a `sell` signal is evaluated as `flat`: spot cannot
short, so it only closes a long. Doing this before the decision keeps the
kill-switch rule that closing is never blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Quantity
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

    Each ``pop_due(until_ns)`` replays from the run's initial lower bound and
    deduplicates by globally unique ``signal_id``. Keeping the lower bound
    stable prevents a signal committed late with an older or identical
    ``ts_event`` from being skipped after the high-water cursor advances.
    ``cursor_ns`` remains the observable high-water mark and should be
    initialised to the runner start time so historical backfills are not
    re-consumed on every restart — the operator launcher is responsible for
    picking that value (typically ``time.time_ns()`` at startup, or
    ``previous_processed_until_ns + 1`` for a restart).
    """

    store: SignalStore
    source: str
    model_version: str
    cursor_ns: int
    last_popped_ns: int | None = None
    _replay_floor_ns: int = field(init=False, repr=False)
    _seen_signal_ids: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._replay_floor_ns = self.cursor_ns

    def reset_cursor(self, cursor_ns: int) -> None:
        """Reset the run lower bound without permitting signal re-emission."""
        self.cursor_ns = cursor_ns
        self._replay_floor_ns = cursor_ns

    def pop_due(self, until_ns: int) -> list[SignalEvent]:
        if until_ns < self._replay_floor_ns:
            return []
        events = self.store.replay(
            source=self.source,
            model_version=self.model_version,
            since_ns=self._replay_floor_ns,
            until_ns=until_ns,
        )
        new_events = [
            event for event in events if event.signal_id not in self._seen_signal_ids
        ]
        if new_events:
            self._seen_signal_ids.update(event.signal_id for event in new_events)
            last_ts = max(int(event.ts_event) for event in new_events)
            self.cursor_ns = max(self.cursor_ns, last_ts + 1)
            self.last_popped_ns = max(self.last_popped_ns or last_ts, last_ts)
        return new_events

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
    # When set, each order is sized as trade_notional / latest bar close
    # (quote currency) instead of the fixed trade_size quantity.
    trade_notional: Decimal | None = None
    signals: list[SignalEvent] = field(default_factory=list)
    signal_source: SignalSource | None = None
    lineage: list[LineageRecord] = field(default_factory=list)
    target_equity_fraction: Decimal | None = None
    rebalance_weekday: int | None = None
    allocated_capital: Decimal | None = None

    def __post_init__(self) -> None:
        _validate_equity_sizing(
            self.target_equity_fraction,
            self.trade_notional,
            self.rebalance_weekday,
            self.allocated_capital,
        )


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
        self._last_close: Decimal | None = None
        self._last_signal: SignalEvent | None = None
        self._rebalance_intent: OrderIntent | None = None
        self._next_rebalance_ns: int | None = None
        self._sleeve_cash: Decimal | None = None
        self._warned_commission_currency = False

    @property
    def instrument_id(self) -> InstrumentId:
        return self._params.instrument_id

    @property
    def sleeve_cash(self) -> Decimal | None:
        """Quote cash in the allocation; None until its first bar or if disabled."""
        return self._sleeve_cash

    @property
    def sleeve_equity(self) -> Decimal | None:
        """Allocation marked at the latest bar close, including this strategy's holdings."""
        if self._sleeve_cash is None or self._last_close is None:
            return None
        return self._sleeve_cash + self._net_position() * self._last_close

    def _net_position(self) -> Decimal:
        if self._params.allocated_capital is None:
            return self.portfolio.net_position(self.instrument_id)
        return sum(
            (
                position.signed_decimal_qty()
                for position in self.cache.positions_open(
                    instrument_id=self.instrument_id, strategy_id=self.id
                )
            ),
            Decimal(0),
        )

    def on_start(self) -> None:
        self.subscribe_bars(self._params.bar_type)

    def on_bar(self, bar: Bar) -> None:
        bar_ns = int(bar.ts_event)
        if (
            self._params.trade_notional is not None
            or self._params.target_equity_fraction is not None
        ):
            self._last_close = bar.close.as_decimal()
        if self._params.allocated_capital is not None and self._sleeve_cash is None:
            self._sleeve_cash = (
                self._params.allocated_capital - self._net_position() * self._last_close
            )
        self._update_daily_risk_state(bar_ns)
        submitted_order_this_bar = False
        for event in self._signal_source.pop_due(bar_ns):
            expected_symbol = self._params.instrument_id.symbol.value
            expected_venue = self._params.instrument_id.venue.value
            if event.symbol != expected_symbol or event.venue != expected_venue:
                self.lineage.append(
                    LineageRecord(
                        signal_id=event.signal_id,
                        source=event.source,
                        model_version=event.model_version,
                        ts_event=int(event.ts_event),
                        decision="skip",
                        reason=(
                            "instrument_mismatch:"
                            f"{event.symbol}.{event.venue}!="
                            f"{expected_symbol}.{expected_venue}"
                        ),
                        client_order_ids=[],
                        ts_decision=bar_ns,
                    )
                )
                continue
            self._last_signal = event
            spot_note = None
            if event.side == "sell" and self._is_cash_account():
                event = event.model_copy(update={"side": "flat", "score": 0.0})
                spot_note = "spot_cash_account_sell_as_flat"
            intent = self._baseline.decide(event, now_ns=bar_ns)
            lineage_reason = intent.reason or spot_note
            if (
                submitted_order_this_bar
                and intent.action != "skip"
                and not intent.dry_run
            ):
                client_order_ids = []
                lineage_reason = "suppressed_after_same_bar_order_submission"
            else:
                if intent.action != "skip":
                    self._rebalance_intent = intent
                client_order_ids = self._apply_intent(intent)
                if client_order_ids:
                    submitted_order_this_bar = True
            self.lineage.append(
                LineageRecord(
                    signal_id=event.signal_id,
                    source=event.source,
                    model_version=event.model_version,
                    ts_event=int(event.ts_event),
                    decision=intent.action,
                    reason=lineage_reason,
                    client_order_ids=client_order_ids,
                    ts_decision=bar_ns,
                )
            )
        self._rebalance(bar_ns, submitted_order_this_bar)

    def on_order_filled(self, event: OrderFilled) -> None:
        # Fills before the first bar form part of the opening position, marked
        # at that first close. After initialization, book each fill at its price.
        if (
            self._sleeve_cash is None
            or event.strategy_id != self.id
            or event.instrument_id != self.instrument_id
        ):
            return
        price = event.last_px.as_decimal()
        value = event.last_qty.as_decimal() * price
        self._sleeve_cash += value if event.order_side == OrderSide.SELL else -value
        instrument = self.cache.instrument(self.instrument_id)
        commission = event.commission
        if commission.currency == instrument.quote_currency:
            self._sleeve_cash -= commission.as_decimal()
        elif commission.currency == instrument.base_currency:
            self._sleeve_cash -= commission.as_decimal() * price
        elif not self._warned_commission_currency:
            self.log.warning(
                f"Sleeve ignores commission in {commission.currency}: "
                f"no conversion to {instrument.quote_currency}"
            )
            self._warned_commission_currency = True

    def _apply_intent(self, intent: OrderIntent) -> list[str]:
        action = intent.action
        if action == "skip":
            return []

        # ADR-006 §2.5: dry-run intents must produce no orders. The lineage
        # row still records the action so audits retain the decision outcome.
        if intent.dry_run:
            return []

        instrument = self.cache.instrument(self._params.instrument_id)
        if instrument is None:
            return []

        tags = [_signal_tag(intent.signal_id)]

        if action == "target_long":
            if self._params.target_equity_fraction is not None and self._net_position() > 0:
                return []
            quantity = self._scaled_trade_size(intent)
            if quantity <= 0:
                return []
            if self._net_position() > 0:
                return []
            order_qty = self._order_quantity(instrument, quantity, OrderSide.BUY)
            if order_qty is None:
                return []
            if self._net_position() < 0:
                self.close_all_positions(self._params.instrument_id, tags=tags)
            order = self.order_factory.market(
                instrument_id=self._params.instrument_id,
                order_side=OrderSide.BUY,
                quantity=order_qty,
                tags=tags,
            )
            self.submit_order(order)
            return [order.client_order_id.value]

        if action == "target_short":
            quantity = self._scaled_trade_size(intent)
            if quantity <= 0:
                return []
            if self._net_position() < 0:
                return []
            order_qty = self._order_quantity(instrument, quantity, OrderSide.SELL)
            if order_qty is None:
                return []
            if self._net_position() > 0:
                self.close_all_positions(self._params.instrument_id, tags=tags)
            order = self.order_factory.market(
                instrument_id=self._params.instrument_id,
                order_side=OrderSide.SELL,
                quantity=order_qty,
                tags=tags,
            )
            self.submit_order(order)
            return [order.client_order_id.value]

        if action == "target_flat":
            if self._net_position() == 0:
                return []
            return self._close_positions(tags)

        raise ValueError(f"unknown OrderIntent.action={action!r}")

    def _close_positions(self, tags: list[str]) -> list[str]:
        """Close open positions and return the closing orders' client ids.

        Returning the ids makes a close count as this bar's submission, so a
        second same-bar close is suppressed instead of sent and rejected.
        """
        instrument_id = self._params.instrument_id
        before = {
            o.client_order_id
            for o in self.cache.orders(instrument_id=instrument_id, strategy_id=self.id)
        }
        self.close_all_positions(instrument_id, tags=tags)
        return sorted(
            o.client_order_id.value
            for o in self.cache.orders(instrument_id=instrument_id, strategy_id=self.id)
            if o.client_order_id not in before
        )

    def _order_quantity(
        self, instrument: Instrument, quantity: Decimal, side: OrderSide
    ) -> Quantity | None:
        if self._params.trade_notional is None and self._params.target_equity_fraction is None:
            return instrument.make_qty(quantity)
        if side == OrderSide.BUY:
            quantity = min(quantity, self._affordable_buy_quantity(instrument))
            if self._params.allocated_capital is not None:
                if self._sleeve_cash is None or self._last_close is None or self._last_close <= 0:
                    return None
                quantity = min(
                    quantity,
                    self._sleeve_cash / (self._last_close * (1 + instrument.taker_fee)),
                )
        # Below one lot: place nothing rather than let make_qty round to zero.
        if quantity < instrument.size_increment.as_decimal():
            return None
        return instrument.make_qty(quantity, round_down=True)

    def _is_cash_account(self) -> bool:
        account = self.portfolio.account(self._params.instrument_id.venue)
        return account is not None and account.type == AccountType.CASH

    def _affordable_buy_quantity(self, instrument: Instrument) -> Decimal:
        """Cash accounts: the most the free quote balance buys after the taker fee."""
        account = self.portfolio.account(self._params.instrument_id.venue)
        if account is None or account.type != AccountType.CASH:
            return Decimal("Infinity")
        free = account.balance_free(instrument.quote_currency)
        if free is None or self._last_close is None:
            return Decimal(0)
        return free.as_decimal() / (self._last_close * (1 + instrument.taker_fee))

    def _scaled_trade_size(self, intent: OrderIntent) -> Decimal:
        max_position_pct = Decimal(str(self._params.baseline_config.max_position_pct))
        target_position_pct = Decimal(str(abs(intent.target_position_pct)))
        if max_position_pct <= 0 or target_position_pct <= 0:
            return Decimal(0)
        base_size = self._params.trade_size
        if self._params.target_equity_fraction is not None:
            if self._last_close is None or self._last_close <= 0:
                return Decimal(0)
            instrument = self.cache.instrument(self._params.instrument_id)
            if instrument is None:
                return Decimal(0)
            base_size = (
                self._params.target_equity_fraction
                * self._sizing_equity(instrument)
                / self._last_close
            )
        elif self._params.trade_notional is not None:
            if self._last_close is None or self._last_close <= 0:
                return Decimal(0)
            base_size = self._params.trade_notional / self._last_close
        return base_size * target_position_pct / max_position_pct

    def _sizing_equity(self, instrument: Instrument) -> Decimal:
        if self._params.allocated_capital is not None:
            equity = self.sleeve_equity
            return equity if equity is not None else Decimal(0)
        account = self.portfolio.account(self._params.instrument_id.venue)
        if account is None:
            return Decimal(0)
        if account.type != AccountType.CASH:
            equity = self._current_equity()
            return Decimal(str(equity)) if equity is not None else Decimal(0)
        quote = account.balance_total(instrument.quote_currency)
        base = account.balance_total(instrument.base_currency)
        return (quote.as_decimal() if quote is not None else Decimal(0)) + (
            base.as_decimal() * self._last_close
            if base is not None and self._last_close is not None
            else Decimal(0)
        )

    def _rebalance(self, bar_ns: int, submitted_order_this_bar: bool) -> None:
        weekday = self._params.rebalance_weekday
        if weekday is None:
            return
        week_ns = 7 * 24 * 60 * 60 * 1_000_000_000
        if self._next_rebalance_ns is None:
            day = datetime.fromtimestamp(bar_ns // 1_000_000_000, tz=UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            boundary = day + timedelta(days=(weekday + 1 - day.weekday()) % 7)
            self._next_rebalance_ns = int(boundary.timestamp()) * 1_000_000_000
            if self._next_rebalance_ns < bar_ns:
                self._next_rebalance_ns += week_ns
        if bar_ns < self._next_rebalance_ns:
            return
        # A gap spanning several weeks causes one reset at the latest boundary.
        boundary_ns = (
            self._next_rebalance_ns + ((bar_ns - self._next_rebalance_ns) // week_ns) * week_ns
        )
        self._next_rebalance_ns = boundary_ns + week_ns
        if submitted_order_this_bar or self._net_position() <= 0:
            return
        intent = self._rebalance_intent
        if intent is not None and intent.dry_run:
            return
        instrument = self.cache.instrument(self.instrument_id)
        if instrument is None or self._last_close is None or self._last_close <= 0:
            return
        boundary_iso = datetime.fromtimestamp(boundary_ns // 1_000_000_000, tz=UTC).isoformat()
        signal_id = f"rebalance:{boundary_iso}"
        if intent is None:
            intent = OrderIntent(
                signal_id,
                str(self.instrument_id),
                "target_long",
                self._params.baseline_config.max_position_pct,
            )
        increment = instrument.size_increment.as_decimal()
        desired = (self._scaled_trade_size(intent) / increment).to_integral_value(
            rounding=ROUND_DOWN
        ) * increment
        difference = desired - self._net_position()
        side = OrderSide.BUY if difference > 0 else OrderSide.SELL
        if side == OrderSide.BUY and self._baseline.kill_switch_engaged:
            return
        quantity = self._order_quantity(instrument, abs(difference), side)
        if quantity is None:
            return
        if (
            instrument.min_notional is not None
            and quantity.as_decimal() * self._last_close < instrument.min_notional.as_decimal()
        ):
            return
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=quantity,
            reduce_only=side == OrderSide.SELL,
            tags=[signal_id, _signal_tag(signal_id)],
        )
        self.submit_order(order)
        self.lineage.append(
            LineageRecord(
                signal_id=signal_id,
                source=self._last_signal.source if self._last_signal is not None else "",
                model_version=(
                    self._last_signal.model_version if self._last_signal is not None else ""
                ),
                ts_event=boundary_ns,
                decision="rebalance",
                reason=None,
                client_order_ids=[order.client_order_id.value],
                ts_decision=bar_ns,
            )
        )

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


def _validate_equity_sizing(
    fraction: Decimal | None,
    notional: Decimal | None,
    weekday: int | None,
    allocated_capital: Decimal | None = None,
) -> None:
    if fraction is not None:
        if not fraction.is_finite() or not 0 < fraction <= 1:
            raise ValueError("target_equity_fraction must be in (0, 1]")
        if notional is not None:
            raise ValueError("target_equity_fraction and trade_notional are mutually exclusive")
    if weekday is not None:
        if fraction is None:
            raise ValueError("rebalance_weekday requires target_equity_fraction")
        if type(weekday) is not int or not 0 <= weekday <= 6:
            raise ValueError("rebalance_weekday must be an integer in [0, 6]")
    if allocated_capital is not None:
        if fraction is None:
            raise ValueError("allocated_capital requires target_equity_fraction")
        if not allocated_capital.is_finite() or allocated_capital <= 0:
            raise ValueError("allocated_capital must be finite and positive")

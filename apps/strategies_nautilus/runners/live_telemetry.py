"""Live telemetry reader for the ADR-008 §6.6 testnet runner.

Default :class:`testnet_runner.TelemetryReader` returns hardcoded constants
(``daily_pnl=0``, ``open_positions=0``, ``last_bar_ns=None`` …) and therefore
silently disarms the §5.2 kill-switch and three of the §5.4 advisory alerts
(``signal_lag_exceeded_threshold``, ``data_gap_exceeded_tolerance``,
``ws_disconnected``) for live testnet runs. This module reads from
``node.portfolio`` / ``node.cache``, the kernel's ``DataEngine`` /
``ExecutionEngine`` ``check_connected()``, and the launcher's
``SignalStorePollingSource`` so those checks observe real state.

The reader is constructed pre-build and bound to the node post-build via
:meth:`LiveTelemetryReader.bind_node`. ``testnet_runner.run_long_running_testnet``
calls ``bind_node`` automatically when the injected ``telemetry_reader``
exposes it. Every read is wrapped in ``try / except`` and falls back to a
safe constant sample so a transient cache hiccup never crashes the monitor
loop.

``ws_connected`` is the conjunction of
``node.kernel.data_engine.check_connected()`` and
``node.kernel.exec_engine.check_connected()`` — both public ``cpdef bint``
methods that walk each registered client's ``is_connected`` flag.
``ws_reconnect_count`` is the count of ``False → True`` transitions of the
combined connection state observed across telemetry samples; sub-poll-window
blips are invisible, but any drop long enough to be observed at the
``telemetry_poll_seconds`` cadence (default 1 s) is counted on recovery.

Known gap left for follow-up:

- ``exchange_error_count`` stays at zero because the Binance live data /
  exec clients catch errors internally (retry loops, log-only warnings) and
  do not publish a counter or message-bus event we can subscribe to without
  monkey-patching adapter internals. ``data_gap_exceeded_tolerance`` and
  ``ws_disconnected`` together cover the user-visible failure modes; the
  ``exchange_error_burst`` trigger remains inert until upstream exposes a
  counter we can read non-invasively.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Currency

from apps.strategies_nautilus.baseline_nautilus_strategy import (
    SignalStorePollingSource,
)
from apps.strategies_nautilus.runners.testnet_runner import (
    TestnetRuntimeTelemetry,
)

ClockFn = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class LiveTelemetryReader:
    """Read live telemetry from a Nautilus ``TradingNode``.

    Construct in the launcher (before ``node.build()``), pass to
    ``testnet_runner.main(..., telemetry_reader=reader)``, and the runner
    will call :meth:`bind_node` for you. After ``bind_node`` the reader
    becomes a no-arg callable returning :class:`TestnetRuntimeTelemetry`.

    Parameters
    ----------
    venue, bar_type, base_currency : the Nautilus identifiers the reader
        uses to query portfolio / cache facades. They mirror the strategy's
        own params.
    starting_balance : authoritative ``account_total_usdt`` for the runner's
        daily-loss budget. Used as the day-anchor for the first heartbeat
        and as the fallback when the cache has not produced an account yet.
    signal_source : optional reference to the launcher's
        ``SignalStorePollingSource``. The reader reads
        ``signal_source.last_popped_ns`` for ``last_signal_ns``. If omitted,
        ``last_signal_ns`` stays ``None`` and ``signal_lag_exceeded_threshold``
        cannot fire.
    """

    venue: Venue
    bar_type: BarType
    base_currency: Currency
    starting_balance: float
    signal_source: SignalStorePollingSource | None = None
    _node_holder: dict[str, Any] = field(default_factory=dict, repr=False)
    _day_anchor_total: float | None = field(default=None, repr=False)
    _day_anchor_date: date | None = field(default=None, repr=False)
    _clock: ClockFn = field(default=_utc_now, repr=False)
    _ws_connected_prev: bool = field(default=True, repr=False)
    _ws_reconnect_count: int = field(default=0, repr=False)

    def bind_node(self, node: Any) -> None:
        """Attach a built ``TradingNode``. Idempotent; safe to call again."""
        self._node_holder["node"] = node

    def __call__(self) -> TestnetRuntimeTelemetry:
        ts = self._clock()
        node = self._node_holder.get("node")
        if node is None:
            return self._defaults(ts, self.starting_balance, daily_pnl=0.0)
        try:
            total = self._read_account_total(node)
            daily_pnl = self._apply_day_anchor(total, ts)
            ws_connected = self._read_ws_connected(node)
            return TestnetRuntimeTelemetry(
                ts=ts,
                daily_pnl=daily_pnl,
                exchange_error_count=0,
                ws_reconnect_count=self._ws_reconnect_count,
                account_total_usdt=total,
                open_orders=_safe_len(
                    lambda: node.cache.orders_open(venue=self.venue)
                ),
                open_positions=_safe_len(
                    lambda: node.cache.positions_open(venue=self.venue)
                ),
                last_bar_ns=_read_last_bar_ns(node, self.bar_type),
                last_signal_ns=self._read_last_signal_ns(),
                ws_connected=ws_connected,
            )
        except Exception:  # noqa: BLE001 — telemetry must never crash the loop
            return self._defaults(ts, self.starting_balance, daily_pnl=0.0)

    def _defaults(
        self, ts: datetime, total: float, *, daily_pnl: float
    ) -> TestnetRuntimeTelemetry:
        return TestnetRuntimeTelemetry(
            ts=ts,
            daily_pnl=daily_pnl,
            exchange_error_count=0,
            ws_reconnect_count=self._ws_reconnect_count,
            account_total_usdt=total,
            open_orders=0,
            open_positions=0,
            last_bar_ns=None,
            last_signal_ns=self._read_last_signal_ns(),
            ws_connected=True,
        )

    def _read_account_total(self, node: Any) -> float:
        equity_by_currency = node.portfolio.equity(venue=self.venue)
        if not equity_by_currency:
            return self.starting_balance
        money = equity_by_currency.get(self.base_currency)
        if money is None:
            return self.starting_balance
        return float(money.as_double())

    def _apply_day_anchor(self, total: float, ts: datetime) -> float:
        today = ts.astimezone(UTC).date()
        if self._day_anchor_date != today:
            self._day_anchor_date = today
            self._day_anchor_total = total
            return 0.0
        if self._day_anchor_total is None:
            self._day_anchor_total = total
            return 0.0
        return total - self._day_anchor_total

    def _read_last_signal_ns(self) -> int | None:
        if self.signal_source is None:
            return None
        return self.signal_source.last_popped_ns

    def _read_ws_connected(self, node: Any) -> bool:
        """Return whether every kernel client is currently connected.

        Reads ``node.kernel.data_engine.check_connected()`` AND
        ``node.kernel.exec_engine.check_connected()`` — both ``cpdef bint``
        methods that walk each registered client's ``is_connected`` flag.
        Increments ``_ws_reconnect_count`` on a ``False → True`` edge so
        the §5.4 ``ws_disconnected`` and §5.2 ``ws_reconnect_burst`` paths
        observe live state. Treats any read error as "no information"
        without changing prev/count state.
        """
        try:
            data_ok = bool(node.kernel.data_engine.check_connected())
            exec_ok = bool(node.kernel.exec_engine.check_connected())
        except Exception:  # noqa: BLE001 — never crash the monitor loop
            return self._ws_connected_prev
        connected = data_ok and exec_ok
        if connected and not self._ws_connected_prev:
            self._ws_reconnect_count += 1
        self._ws_connected_prev = connected
        return connected


def _safe_len(fn: Callable[[], Any]) -> int:
    try:
        value = fn()
    except Exception:  # noqa: BLE001
        return 0
    try:
        return len(value) if value is not None else 0
    except TypeError:
        return 0


def _read_last_bar_ns(node: Any, bar_type: BarType) -> int | None:
    try:
        bar = node.cache.bar(bar_type)
    except Exception:  # noqa: BLE001
        return None
    if bar is None:
        return None
    ts_event = getattr(bar, "ts_event", None)
    if ts_event is None:
        return None
    try:
        return int(ts_event)
    except (TypeError, ValueError):
        return None


__all__ = ["LiveTelemetryReader"]

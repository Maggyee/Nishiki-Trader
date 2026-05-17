"""Wall-clock bar feed for ADR-008 Phase 3a paper runtime.

Streams closed 1m klines from Binance public spot WS via NautilusTrader's
``BinanceWebSocketClient``. Public streams require no API key / secret; this
module deliberately reads no ``BINANCE_*`` environment variables.

The runner consumes bars through a small ``BarFeed`` interface so tests can
inject a fake feed without touching the network.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_BINANCE_PUBLIC_WS_URL = "wss://stream.binance.com:9443"


@dataclass(frozen=True)
class BarSample:
    """Minimal bar shape consumed by the paper simulation."""

    ts_event: int
    ts_init: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarFeed(Protocol):
    """Pull-style bar feed used by the wall-clock paper loop."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def next_bar(self, timeout: float) -> BarSample | None: ...

    @property
    def reconnect_count(self) -> int: ...

    @property
    def duplicate_bars_dropped(self) -> int: ...

    @property
    def endpoint(self) -> str: ...

    @property
    def stream_name(self) -> str: ...

    @property
    def source_name(self) -> str: ...


class BinancePublicBarFeed:
    """Public ``<symbol>@kline_<interval>`` consumer via NautilusTrader WS client.

    No credentials. Drops un-closed kline updates (``k.x == false``) and dedups
    closed bars by their close-time so WS retransmissions never enter the
    simulation twice.
    """

    def __init__(
        self,
        *,
        symbol: str,
        interval: str = "1m",
        base_url: str = DEFAULT_BINANCE_PUBLIC_WS_URL,
        queue_max: int = 10_000,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must be a non-empty string")
        if not interval:
            raise ValueError("interval must be a non-empty string")
        self._symbol = symbol
        self._interval = interval
        self._base_url = base_url
        self._stream = f"{symbol.lower()}@kline_{interval}"
        self._queue: queue.Queue[BarSample] = queue.Queue(maxsize=queue_max)
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._failure: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws_client: Any = None
        self._reconnect_count = 0
        self._duplicate_bars_dropped = 0
        self._last_emitted_ns: int | None = None

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def duplicate_bars_dropped(self) -> int:
        return self._duplicate_bars_dropped

    @property
    def endpoint(self) -> str:
        return self._base_url

    @property
    def stream_name(self) -> str:
        return self._stream

    @property
    def source_name(self) -> str:
        return "binance_public_ws"

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("bar feed already started")
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"binance-ws-{self._stream}",
            daemon=True,
        )
        self._thread.start()
        if not self._started_event.wait(timeout=30.0):
            self.stop()
            raise TimeoutError("Binance WS feed failed to start within 30s")
        if self._failure is not None:
            raise RuntimeError(f"Binance WS feed failed: {self._failure!r}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15.0)
            self._thread = None

    def next_bar(self, timeout: float) -> BarSample | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _run_loop(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_main())
        except BaseException as exc:
            self._failure = exc
            self._started_event.set()
        finally:
            if self._loop is not None:
                self._loop.close()
                self._loop = None

    async def _async_main(self) -> None:
        from nautilus_trader.adapters.binance.websocket.client import (
            BinanceWebSocketClient,
        )
        from nautilus_trader.common.component import LiveClock

        loop = asyncio.get_running_loop()
        self._ws_client = BinanceWebSocketClient(
            clock=LiveClock(),
            base_url=self._base_url,
            handler=self._handle_message,
            handler_reconnect=self._handle_reconnect,
            loop=loop,
        )
        await self._ws_client.subscribe_bars(
            symbol=self._symbol,
            interval=self._interval,
        )
        await self._ws_client.connect()
        self._started_event.set()
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(0.1)
        finally:
            await self._ws_client.disconnect()

    def _handle_message(self, raw: bytes) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        data = msg.get("data") if isinstance(msg, dict) else None
        if data is None:
            data = msg
        if not isinstance(data, dict) or data.get("e") != "kline":
            return
        k = data.get("k")
        if not isinstance(k, dict) or not k.get("x"):
            return
        try:
            close_time_ms = int(k["T"])
            sample = BarSample(
                ts_event=close_time_ms * 1_000_000,
                ts_init=close_time_ms * 1_000_000,
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
                volume=float(k["v"]),
            )
        except (KeyError, TypeError, ValueError):
            return
        if self._last_emitted_ns is not None and sample.ts_event <= self._last_emitted_ns:
            self._duplicate_bars_dropped += 1
            return
        self._last_emitted_ns = sample.ts_event
        try:
            self._queue.put_nowait(sample)
        except queue.Full:
            self._duplicate_bars_dropped += 1

    async def _handle_reconnect(self) -> None:
        self._reconnect_count += 1


__all__ = [
    "BarFeed",
    "BarSample",
    "BinancePublicBarFeed",
    "DEFAULT_BINANCE_PUBLIC_WS_URL",
]

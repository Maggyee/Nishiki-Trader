"""Daily ADR-019 B2 signals: BTC and ETH long while above their 200-day SMA.

    uv run python -m apps.strategies_freqtrade.beta_signals

Reads the last closed daily candles from Binance's public market-data API (no
credentials), applies the same `sma_filter` rule and `weights_to_signals`
encoding as the B2 backtest, and writes one `SignalEvent` per coin for the
latest closed UTC day. Idempotent: rerunning the same day writes duplicates
that the store ignores.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from apps.bridge.store import DEFAULT_DB_PATH, SignalStore
from apps.strategies_freqtrade.research import trend_vol
from apps.strategies_freqtrade.research.export_signals import weights_to_signals

SOURCE = "rule_beta_sma200_v1"
MODEL_VERSION = "btc-eth-sma200-v1"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
PARAMS = {"sma_days": 200, "weight_per_symbol": 0.5}
KLINES_URL = "https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=260"


def _http_json(url: str) -> list:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - public market data
        return json.loads(response.read())


def closed_daily_closes(
    symbol: str, *, now: datetime, get: Callable[[str], list] = _http_json
) -> pd.Series:
    """Daily closes indexed by UTC open day, without the still-open candle."""
    rows = get(KLINES_URL.format(symbol=symbol))
    now_ms = int(now.timestamp() * 1000)
    closed = [row for row in rows if int(row[6]) < now_ms]
    index = pd.DatetimeIndex(pd.to_datetime([int(row[0]) for row in closed], unit="ms", utc=True))
    return pd.Series([float(row[4]) for row in closed], index=index, name=symbol)


def build_signals(now: datetime, get: Callable[[str], list] = _http_json) -> list:
    day = (pd.Timestamp(now).tz_convert("UTC").normalize() - pd.Timedelta(days=1)).date()
    prices = {}
    for symbol in SYMBOLS:
        closes = closed_daily_closes(symbol, now=now, get=get)
        if len(closes) <= PARAMS["sma_days"] or closes.index[-1].date() != day:
            raise ValueError(
                f"{symbol}: need more than {PARAMS['sma_days']} closed days ending {day}, "
                f"got {len(closes)} ending {closes.index[-1].date() if len(closes) else None}"
            )
        prices[symbol] = closes.to_frame("close")
    weights = trend_vol.target_weights({trend_vol.PRICE_DATASET: prices}, "sma_filter", PARAMS)
    return weights_to_signals(
        weights,
        source=SOURCE,
        model_version=MODEL_VERSION,
        start=day.isoformat(),
        end=day.isoformat(),
        emit_weekday=None,
        long_only=True,
        horizon="1d",
        ttl_seconds=2 * 86_400,
        metadata={"adr": "019", "producer": "beta_signals"},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--signal-store-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args(argv)
    events = build_signals(datetime.now(UTC))
    written, duplicates = SignalStore(args.signal_store_path).write_many(events)
    print(
        json.dumps(
            {
                "day": events[0].signal_id.rsplit(":", 1)[-1],
                "written": written,
                "duplicates": duplicates,
                "sides": {event.symbol: event.side for event in events},
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

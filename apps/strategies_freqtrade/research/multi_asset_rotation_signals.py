"""Pre-registered BTC/ETH/SOL rotation and breadth research signals."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.breakout_rule_signals import (
    resample_ohlcv_15m,
)
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    _load_bars_from_catalog,
    _make_signal_id,
)

UNIVERSE = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
STRATEGY_IDENTITIES = {
    "xs_momentum": (
        "rule_xs_momentum_rotation_v1",
        "btc-eth-sol-ret90-monthly-cash-v1",
    ),
    "market_breadth": (
        "rule_market_breadth_v1",
        "breadth2of3-sma100-btc20-v1",
    ),
    "relative_value": (
        "rule_relative_value_rotation_v1",
        "ethbtc-z20x1.5-weekly-cash-v1",
    ),
}


def _aligned_daily(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if set(bars_by_symbol) != set(UNIVERSE):
        raise ValueError(f"bars_by_symbol must contain exactly {UNIVERSE}")
    closes: dict[str, pd.Series] = {}
    timestamps: dict[str, pd.Series] = {}
    for symbol in UNIVERSE:
        daily = resample_ohlcv_15m(bars_by_symbol[symbol], timeframe_minutes=1440)
        days = pd.to_datetime(daily["ts_event"], unit="ns", utc=True).dt.floor("D")
        closes[symbol] = pd.Series(daily["close"].astype(float).to_numpy(), index=days)
        timestamps[symbol] = pd.Series(daily["ts_event"].astype("int64").to_numpy(), index=days)
    close_frame = pd.DataFrame(closes).dropna()
    timestamp_frame = pd.DataFrame(timestamps).loc[close_frame.index]
    if close_frame.empty:
        raise ValueError("aligned daily universe is empty")
    if timestamp_frame.isna().any().any():
        raise ValueError("aligned daily timestamps are incomplete")
    return close_frame, timestamp_frame.astype("int64")


def _event(
    *,
    symbol: str,
    ts_event: int,
    side: str,
    source: str,
    model_version: str,
    metadata: dict[str, object],
) -> SignalEvent:
    return SignalEvent.model_validate(
        {
            "schema_version": "signal.v1",
            "signal_id": _make_signal_id(
                source=source,
                model_version=model_version,
                symbol=symbol,
                venue="BINANCE",
                ts_event_ns=ts_event,
                side=side,
            ),
            "symbol": symbol,
            "venue": "BINANCE",
            "ts_event": ts_event,
            "horizon": "1d",
            "side": side,
            "score": 0.75 if side == "buy" else 0.0,
            "confidence": 0.75,
            "source": source,
            "model_version": model_version,
            "ttl_seconds": 86_400,
            "features_hash": None,
            "metadata": metadata,
        }
    )


def _transition(
    *,
    previous: str | None,
    selected: str | None,
    day: pd.Timestamp,
    timestamps: pd.DataFrame,
    source: str,
    model_version: str,
    trigger: str,
    metadata: dict[str, object],
) -> list[SignalEvent]:
    if previous == selected:
        return []
    events: list[SignalEvent] = []
    common = {
        "algorithm": trigger,
        "selection_day": day.isoformat(),
        "previous_asset": previous,
        "selected_asset": selected,
        **metadata,
    }
    if previous is not None:
        events.append(
            _event(
                symbol=previous,
                ts_event=int(timestamps.loc[day, previous]),
                side="flat",
                source=source,
                model_version=model_version,
                metadata={**common, "spot_target": "flat", "trigger": f"{trigger}_exit"},
            )
        )
    if selected is not None:
        events.append(
            _event(
                symbol=selected,
                ts_event=int(timestamps.loc[day, selected]),
                side="buy",
                source=source,
                model_version=model_version,
                metadata={**common, "spot_target": "long", "trigger": f"{trigger}_entry"},
            )
        )
    return events


def _within_decision_window(
    index: pd.DatetimeIndex,
    *,
    start_date: str | None,
    end_date: str | None,
) -> np.ndarray:
    mask = np.ones(len(index), dtype=bool)
    if start_date is not None:
        mask &= index >= pd.Timestamp(start_date, tz="UTC")
    if end_date is not None:
        end = pd.Timestamp(end_date, tz="UTC")
        if end == end.normalize():
            mask &= index < end + pd.Timedelta(days=1)
        else:
            mask &= index <= end
    return mask


def generate_xs_momentum_from_daily(
    closes: pd.DataFrame,
    timestamps: pd.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["xs_momentum"]
    previous_close = closes.shift(1)
    returns = previous_close / closes.shift(91) - 1.0
    month = pd.Series(closes.index.tz_localize(None).to_period("M"), index=closes.index)
    rebalance = month.ne(month.shift(1)).to_numpy()
    rebalance &= _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    selected: str | None = None
    events: list[SignalEvent] = []
    for day in closes.index[rebalance]:
        row = returns.loc[day]
        if row.isna().any():
            continue
        winner = str(row.idxmax())
        next_asset = winner if float(row[winner]) > 0.0 else None
        events.extend(
            _transition(
                previous=selected,
                selected=next_asset,
                day=day,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="monthly_relative_strength_rotation",
                metadata={
                    "lookback_days": 90,
                    "returns": {symbol: round(float(row[symbol]), 10) for symbol in UNIVERSE},
                    "cash_if_top_nonpositive": True,
                },
            )
        )
        selected = next_asset
    return events


def generate_market_breadth_from_daily(
    closes: pd.DataFrame,
    timestamps: pd.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["market_breadth"]
    previous_close = closes.shift(1)
    previous_sma = closes.shift(1).rolling(100, min_periods=100).mean()
    breadth = (previous_close > previous_sma).sum(axis=1)
    btc_return = previous_close["BTCUSDT"] / closes["BTCUSDT"].shift(21) - 1.0
    state = False
    events: list[SignalEvent] = []
    decision_days = closes.index[
        _within_decision_window(
            closes.index,
            start_date=start_date,
            end_date=end_date,
        )
    ]
    for day in decision_days:
        if pd.isna(btc_return.loc[day]) or previous_sma.loc[day].isna().any():
            continue
        risk_on = int(breadth.loc[day]) >= 2 and float(btc_return.loc[day]) > 0.0
        if risk_on == state:
            continue
        events.extend(
            _transition(
                previous="BTCUSDT" if state else None,
                selected="BTCUSDT" if risk_on else None,
                day=day,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="multi_asset_breadth_btc_allocation",
                metadata={
                    "breadth_count": int(breadth.loc[day]),
                    "breadth_required": 2,
                    "sma_days": 100,
                    "btc_return_days": 20,
                    "btc_return": round(float(btc_return.loc[day]), 10),
                },
            )
        )
        state = risk_on
    return events


def generate_relative_value_from_daily(
    closes: pd.DataFrame,
    timestamps: pd.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["relative_value"]
    ratio = closes["ETHUSDT"] / closes["BTCUSDT"]
    previous_ratio = ratio.shift(1)
    mean = previous_ratio.rolling(20, min_periods=20).mean()
    std = previous_ratio.rolling(20, min_periods=20).std(ddof=0)
    zscore = (previous_ratio - mean) / std.replace(0.0, np.nan)
    selected: str | None = None
    events: list[SignalEvent] = []
    decision_mask = closes.index.weekday == 0
    decision_mask &= _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    for day in closes.index[decision_mask]:
        z = zscore.loc[day]
        if pd.isna(z):
            continue
        next_asset = selected
        if float(z) <= -1.5:
            next_asset = "ETHUSDT"
        elif float(z) >= 1.5:
            next_asset = "BTCUSDT"
        elif (selected == "ETHUSDT" and float(z) >= 0.0) or (
            selected == "BTCUSDT" and float(z) <= 0.0
        ):
            next_asset = None
        events.extend(
            _transition(
                previous=selected,
                selected=next_asset,
                day=day,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="weekly_ethbtc_relative_value_rotation",
                metadata={
                    "ratio_lookback_days": 20,
                    "entry_zscore": 1.5,
                    "exit_zscore": 0.0,
                    "eth_btc_ratio": round(float(previous_ratio.loc[day]), 12),
                    "zscore": round(float(z), 10),
                },
            )
        )
        selected = next_asset
    return events


GENERATORS = {
    "xs_momentum": generate_xs_momentum_from_daily,
    "market_breadth": generate_market_breadth_from_daily,
    "relative_value": generate_relative_value_from_daily,
}


def generate_multi_asset_signals(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    strategy: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    if strategy not in GENERATORS:
        raise ValueError(f"unknown strategy {strategy!r}")
    closes, timestamps = _aligned_daily(bars_by_symbol)
    return GENERATORS[strategy](
        closes,
        timestamps,
        start_date=start_date,
        end_date=end_date,
    )


def _parse_asset(value: str) -> tuple[str, str]:
    symbol, separator, bar_type = value.partition("=")
    symbol = symbol.strip().upper()
    if not separator or symbol not in UNIVERSE or not bar_type.strip():
        raise argparse.ArgumentTypeError("asset must be SYMBOL=bar_type for BTCUSDT/ETHUSDT/SOLUSDT")
    return symbol, bar_type.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(GENERATORS), required=True)
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--asset", action="append", type=_parse_asset, default=[])
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--start-date", help="First UTC decision date, with prior data as warm-up")
    parser.add_argument("--end-date", help="Last UTC decision date")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    asset_map = dict(args.asset)
    if set(asset_map) != set(UNIVERSE):
        raise SystemExit(f"provide exactly one --asset for each of {UNIVERSE}")
    bars = {
        symbol: _load_bars_from_catalog(args.catalog_path, asset_map[symbol])
        for symbol in UNIVERSE
    }
    events = generate_multi_asset_signals(
        bars,
        strategy=args.strategy,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    source, model_version = STRATEGY_IDENTITIES[args.strategy]
    print(f"generated {len(events)} signals for {source} / {model_version}")
    if args.dry_run:
        for event in events[:10]:
            print(f"  {event.signal_id} side={event.side}")
        return 0
    written, duplicates = SignalStore(args.signal_store_path).write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

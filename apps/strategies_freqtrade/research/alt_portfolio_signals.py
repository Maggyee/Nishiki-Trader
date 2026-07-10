"""Pre-registered independent-universe diversified momentum research signals."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.flow_positioning_signals import (
    load_spot_aggregates,
)
from apps.strategies_freqtrade.research.multi_asset_rotation_signals import (
    _event,
    _transition,
    _within_decision_window,
)

ALT_UNIVERSE = ("BNBUSDT", "XRPUSDT", "ADAUSDT")
STRATEGY_IDENTITIES = {
    "diversified_momentum": (
        "rule_alt_diversified_momentum_v1",
        "bnb-xrp-ada-ret90-weekly-equal16-v1",
    ),
    "low_vol_rotation": (
        "rule_alt_low_vol_rotation_v1",
        "bnb-xrp-ada-ret90-lowvol30-weekly-cash-v1",
    ),
}


def _field(frames: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    if set(frames) != set(ALT_UNIVERSE):
        raise ValueError(f"daily frames must contain exactly {ALT_UNIVERSE}")
    result = pd.DataFrame({symbol: frames[symbol][name] for symbol in ALT_UNIVERSE})
    if result.empty or result.isna().any().any():
        raise ValueError(f"aligned {name} is empty or incomplete")
    return result


def generate_diversified_momentum(
    daily: dict[str, pd.DataFrame],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["diversified_momentum"]
    closes = _field(daily, "close")
    timestamps = _field(daily, "ts_event").astype("int64")
    returns = closes.shift(1) / closes.shift(91) - 1.0
    decision_mask = closes.index.weekday == 0
    decision_mask &= _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    held = {symbol: False for symbol in ALT_UNIVERSE}
    events: list[SignalEvent] = []
    for ts in closes.index[decision_mask]:
        row = returns.loc[ts]
        if row.isna().any():
            continue
        for symbol in ALT_UNIVERSE:
            desired = float(row[symbol]) > 0.0
            if desired == held[symbol]:
                continue
            events.append(
                _event(
                    symbol=symbol,
                    ts_event=int(timestamps.loc[ts, symbol]),
                    side="buy" if desired else "flat",
                    source=source,
                    model_version=model_version,
                    metadata={
                        "algorithm": "weekly_independent_absolute_momentum",
                        "selection_day": ts.isoformat(),
                        "return_days": 90,
                        "return": round(float(row[symbol]), 10),
                        "spot_target": "long" if desired else "flat",
                        "portfolio_target_notional_usdt": 16.0,
                        "maximum_concurrent_assets": 3,
                    },
                )
            )
            held[symbol] = desired
    return events


def generate_low_vol_rotation(
    daily: dict[str, pd.DataFrame],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["low_vol_rotation"]
    closes = _field(daily, "close")
    timestamps = _field(daily, "ts_event").astype("int64")
    returns_90 = closes.shift(1) / closes.shift(91) - 1.0
    daily_returns = closes.pct_change()
    volatility_30 = daily_returns.shift(1).rolling(30, min_periods=30).std(ddof=0)
    decision_mask = closes.index.weekday == 0
    decision_mask &= _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    selected: str | None = None
    events: list[SignalEvent] = []
    for ts in closes.index[decision_mask]:
        rets = returns_90.loc[ts]
        vols = volatility_30.loc[ts]
        if rets.isna().any() or vols.isna().any():
            continue
        eligible = [symbol for symbol in ALT_UNIVERSE if float(rets[symbol]) > 0.0]
        next_asset = min(eligible, key=lambda symbol: float(vols[symbol])) if eligible else None
        events.extend(
            _transition(
                previous=selected,
                selected=next_asset,
                day=ts,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="weekly_positive_momentum_low_vol_rotation",
                metadata={
                    "return_days": 90,
                    "volatility_days": 30,
                    "returns": {
                        symbol: round(float(rets[symbol]), 10) for symbol in ALT_UNIVERSE
                    },
                    "volatilities": {
                        symbol: round(float(vols[symbol]), 10) for symbol in ALT_UNIVERSE
                    },
                },
            )
        )
        selected = next_asset
    return events


GENERATORS = {
    "diversified_momentum": generate_diversified_momentum,
    "low_vol_rotation": generate_low_vol_rotation,
}


def _parse_directory(value: str) -> tuple[str, Path]:
    symbol, separator, path = value.partition("=")
    symbol = symbol.strip().upper()
    if not separator or symbol not in ALT_UNIVERSE or not path.strip():
        raise argparse.ArgumentTypeError("daily directory must be SYMBOL=PATH")
    return symbol, Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(GENERATORS), required=True)
    parser.add_argument("--daily-dir", action="append", type=_parse_directory, default=[])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    directories = dict(args.daily_dir)
    if set(directories) != set(ALT_UNIVERSE):
        raise SystemExit(f"provide exactly one --daily-dir for each of {ALT_UNIVERSE}")
    daily = {
        symbol: load_spot_aggregates(
            directories[symbol],
            symbol,
            "1D",
            source_interval="1d",
        )
        for symbol in ALT_UNIVERSE
    }
    events = GENERATORS[args.strategy](
        daily,
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

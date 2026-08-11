"""SignalEvent generators for the frozen Cboe Research Protocol v7 batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    audit_point_in_time_frame,
    load_point_in_time_csv,
)

PROTOCOL_VERSION = "research.protocol.v7"
STRATEGY_IDENTITIES = {
    "equity_vol_relief": ("rule_equity_vol_relief_v3", "cboe-vix5obs-negative-1d-v1", "VIX"),
    "energy_vol_relief": ("rule_energy_vol_relief_v1", "cboe-ovx5obs-negative-1d-v1", "OVX"),
    "gold_vol_relief": ("rule_gold_vol_relief_v1", "cboe-gvz5obs-negative-1d-v1", "GVZ"),
}


@dataclass(frozen=True)
class VolatilityReliefParams:
    change_observations: int = 5
    maximum_change: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.change_observations != 5:
            raise ValueError("Protocol v7 fixes the change lookback at five observations")
        if self.maximum_change != 0.0:
            raise ValueError("Protocol v7 fixes the change threshold at exactly zero")
        if self.ttl_seconds != 86_400:
            raise ValueError("Protocol v7 fixes the signal TTL at one day")
        if self.confidence != 0.75:
            raise ValueError("Protocol v7 fixes confidence at 0.75")


def _feature_hash(strategy: str, params: VolatilityReliefParams) -> str:
    payload = {
        "protocol": PROTOCOL_VERSION,
        "strategy": strategy,
        "params": asdict(params),
        "fields": ["vol_close"],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def generate_volatility_relief_signals(
    factors: pd.DataFrame,
    *,
    strategy: str,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: VolatilityReliefParams | None = None,
) -> list[SignalEvent]:
    if strategy not in STRATEGY_IDENTITIES:
        raise ValueError(f"unsupported Protocol v7 strategy {strategy!r}")
    cfg = params or VolatilityReliefParams()
    frame = audit_point_in_time_frame(factors, required_numeric={"vol_close"})
    if (frame["vol_close"] <= 0.0).any():
        raise ValueError("volatility index closes must be strictly positive")
    change = frame["vol_close"].pct_change(cfg.change_observations)
    states = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    ready = change.notna()
    states.loc[ready] = change.loc[ready] < cfg.maximum_change

    source, model_version, index_name = STRATEGY_IDENTITIES[strategy]
    feature_hash = _feature_hash(strategy, cfg)
    start = pd.Timestamp(start_date, tz="UTC") if start_date else None
    end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) if end_date else None
    current_long = False
    events: list[SignalEvent] = []
    for timestamp, desired in states.items():
        if pd.isna(desired):
            continue
        if start is not None and timestamp < start:
            continue
        if end is not None and timestamp >= end:
            break
        desired_long = bool(desired)
        if desired_long == current_long:
            continue
        row = frame.loc[timestamp]
        change_value = float(change.loc[timestamp])
        side = "buy" if desired_long else "flat"
        ts_event = int(timestamp.value)
        score = math.tanh(max(0.0, -change_value)) if desired_long else 0.0
        metadata: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "strategy": strategy,
            "index": index_name,
            "available_at": pd.Timestamp(row["available_at"]).isoformat(),
            "vintage_id": str(row["vintage_id"]),
            "snapshot_sha256": str(row["snapshot_sha256"]),
            "point_in_time": True,
            "trigger": f"{index_name.lower()}_5obs_negative"
            if desired_long
            else f"{index_name.lower()}_not_relieving",
            "inputs": {
                "vol_close": round(float(row["vol_close"]), 12),
                "change_5obs": round(change_value, 12),
            },
            **asdict(cfg),
        }
        events.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": _make_signal_id(
                        source=source,
                        model_version=model_version,
                        symbol=symbol,
                        venue=venue,
                        ts_event_ns=ts_event,
                        side=side,
                    ),
                    "symbol": symbol,
                    "venue": venue,
                    "ts_event": ts_event,
                    "horizon": "1d",
                    "side": side,
                    "score": score,
                    "confidence": cfg.confidence,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": feature_hash,
                    "metadata": metadata,
                }
            )
        )
        current_long = desired_long
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(STRATEGY_IDENTITIES), required=True)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2022-12-31")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--signal-store-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and args.signal_store_path is None:
        raise SystemExit("--signal-store-path is required unless --dry-run is set")
    events = generate_volatility_relief_signals(
        load_point_in_time_csv(args.input_csv),
        strategy=args.strategy,
        symbol=args.symbol,
        venue=args.venue,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    source, model_version, _ = STRATEGY_IDENTITIES[args.strategy]
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

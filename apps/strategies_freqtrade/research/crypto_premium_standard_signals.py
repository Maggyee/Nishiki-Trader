"""Generate SignalEvent v1 signals for Protocol v46 (Binance Perpetual Premium Index Standard Relief)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v46 import IDENTITIES, PARAMETERS, SCHEMA_VERSION
from apps.strategies_freqtrade.research.crypto_trend_volume_signals import audit_factor_frame
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)


def generate_premium_standard_signals(
    factors: pd.DataFrame,
    *,
    candidate: str,
    start_date: str = "2020-01-01",
    end_date: str = "2022-12-31",
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
) -> list[SignalEvent]:
    if candidate not in IDENTITIES:
        raise ValueError(f"unsupported candidate {candidate!r}")
    params = PARAMETERS[candidate]
    frame = audit_factor_frame(factors)
    values = frame["index_value"]

    states = (values > 0.0)

    source, model = IDENTITIES[candidate]
    feature_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "protocol": SCHEMA_VERSION,
                    "candidate": candidate,
                    "parameters": params,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
    current_long = False
    events: list[SignalEvent] = []

    for timestamp, desired in states.items():
        if pd.isna(desired) or timestamp < start:
            continue
        if timestamp >= end:
            break
        desired_long = bool(desired)
        if desired_long == current_long:
            continue
        row = frame.loc[timestamp]
        val = float(values.loc[timestamp])
        side = "buy" if desired_long else "flat"
        ts_event = int(timestamp.value)
        events.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": _make_signal_id(
                        source=source,
                        model_version=model,
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
                    "score": 1.0 if desired_long else 0.0,
                    "confidence": params["confidence"],
                    "source": source,
                    "model_version": model,
                    "ttl_seconds": params["ttl_seconds"],
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": SCHEMA_VERSION,
                        "candidate": candidate,
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "observation_date": pd.Timestamp(row["observation_date"]).date().isoformat(),
                        "vintage_id": str(row["vintage_id"]),
                        "snapshot_sha256": str(row["snapshot_sha256"]),
                        "historical_vintage_claim": False,
                        "point_in_time_interpretation": "binance_vision_premium_index_closed_daily_bars_lagged_1_calendar_day",
                        "trigger": f"{candidate}_active" if desired_long else f"{candidate}_inactive",
                        "inputs": {
                            "index_value": round(val, 12),
                        },
                        **params,
                    },
                }
            )
        )
        current_long = desired_long
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=sorted(IDENTITIES), required=True)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2022-12-31")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--signal-store-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and args.signal_store_path is None:
        parser.error("--signal-store-path is required unless --dry-run")
    events = generate_premium_standard_signals(
        load_point_in_time_csv(args.input_csv),
        candidate=args.candidate,
        start_date=args.start_date,
        end_date=args.end_date,
        symbol=args.symbol,
        venue=args.venue,
    )
    source, model = IDENTITIES[args.candidate]
    print(f"generated {len(events)} signals for {source} / {model}")
    if args.dry_run:
        for event in events[:10]:
            print(f"  {event.signal_id} side={event.side}")
        return 0
    written, duplicates = SignalStore(args.signal_store_path).write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

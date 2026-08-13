"""SignalEvent generator for Protocol v21 U.S. net-liquidity expansion."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v21 import CANDIDATE, IDENTITIES, PARAMETERS
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)

PROTOCOL_VERSION = "research.protocol.v21"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


def audit_factor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "available_at",
        "observation_date",
        "vintage_id",
        "snapshot_sha256",
        "walcl_millions",
        "wdtgal_millions",
        "rrpontsyd_billions",
        "net_liquidity_millions",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Protocol v21 factor frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Protocol v21 factor timestamps must be timezone-aware")
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Protocol v21 factor timestamps must be unique and increasing")
    audited = frame.copy()
    available = pd.to_datetime(audited["available_at"], utc=True, errors="raise")
    if (available.array.asi8 > audited.index.asi8).any():
        raise ValueError("Protocol v21 available_at after ts_event would introduce lookahead")
    observed = pd.to_datetime(audited["observation_date"], utc=True, errors="raise")
    if not ((available - observed) == pd.Timedelta(days=7)).all():
        raise ValueError("Protocol v21 requires the frozen seven-day publication lag")
    hashes = audited["snapshot_sha256"].astype(str)
    if not hashes.map(lambda value: bool(_SHA256_RE.fullmatch(value))).all():
        raise ValueError("Protocol v21 snapshot hashes are invalid")
    if audited["vintage_id"].astype(str).str.strip().eq("").any():
        raise ValueError("Protocol v21 vintage identifiers cannot be empty")
    for column in (
        "walcl_millions",
        "wdtgal_millions",
        "rrpontsyd_billions",
        "net_liquidity_millions",
    ):
        values = pd.to_numeric(audited[column], errors="raise").astype("float64")
        if not values.map(math.isfinite).all():
            raise ValueError(f"Protocol v21 {column} contains NaN or Infinity")
        audited[column] = values
    reconstructed = (
        audited["walcl_millions"]
        - audited["wdtgal_millions"]
        - 1000.0 * audited["rrpontsyd_billions"]
    )
    if not (reconstructed - audited["net_liquidity_millions"]).abs().le(1e-5).all():
        raise ValueError("Protocol v21 net-liquidity formula drifted")
    audited["available_at"] = available
    audited["observation_date"] = observed
    return audited


def generate_net_liquidity_signals(
    factors: pd.DataFrame,
    *,
    start_date: str = "2020-01-01",
    end_date: str = "2022-12-31",
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
) -> list[SignalEvent]:
    frame = audit_factor_frame(factors)
    values = frame["net_liquidity_millions"]
    change = values.diff(int(PARAMETERS["change_observations"]))
    ready = change.notna()
    states = (change > float(PARAMETERS["minimum_change_millions_usd"])).where(ready)
    source, model = IDENTITIES[CANDIDATE]
    feature_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "protocol": PROTOCOL_VERSION,
                    "candidate": CANDIDATE,
                    "formula": "WALCL-WDTGAL-1000*RRPONTSYD",
                    "parameters": PARAMETERS,
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
        change_value = float(change.loc[timestamp])
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
                    "score": (
                        math.tanh(max(0.0, change_value) / 1_000_000.0) if desired_long else 0.0
                    ),
                    "confidence": PARAMETERS["confidence"],
                    "source": source,
                    "model_version": model,
                    "ttl_seconds": PARAMETERS["ttl_seconds"],
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "candidate": CANDIDATE,
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "observation_date": pd.Timestamp(row["observation_date"])
                        .date()
                        .isoformat(),
                        "vintage_id": str(row["vintage_id"]),
                        "snapshot_sha256": str(row["snapshot_sha256"]),
                        "historical_vintage_claim": False,
                        "point_in_time_interpretation": "fred_current_history_reconstruction_lagged_7_calendar_days",
                        "trigger": "net_liquidity_expanding_4w"
                        if desired_long
                        else "net_liquidity_not_expanding_4w",
                        "inputs": {
                            "net_liquidity_millions": round(float(values.loc[timestamp]), 6),
                            "change_4_observations_millions": round(change_value, 6),
                        },
                        **PARAMETERS,
                    },
                }
            )
        )
        current_long = desired_long
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
    events = generate_net_liquidity_signals(
        load_point_in_time_csv(args.input_csv),
        start_date=args.start_date,
        end_date=args.end_date,
        symbol=args.symbol,
        venue=args.venue,
    )
    source, model = IDENTITIES[CANDIDATE]
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

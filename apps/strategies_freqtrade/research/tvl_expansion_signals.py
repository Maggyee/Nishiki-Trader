"""SignalEvent generators for Protocol v25 DefiLlama TVL-expansion mechanisms."""

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
from apps.ops.research_protocol_v25 import (
    COMMON_PARAMETERS,
    IDENTITIES,
    KIND_BY_CANDIDATE,
)
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)

PROTOCOL_VERSION = "research.protocol.v25"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


def audit_factor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "available_at",
        "observation_date",
        "vintage_id",
        "snapshot_sha256",
        "tvl",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Protocol v25 factor frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Protocol v25 factor timestamps must be timezone-aware")
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Protocol v25 factor timestamps must be unique and increasing")
    audited = frame.copy()
    available = pd.to_datetime(audited["available_at"], utc=True, errors="raise")
    observed = pd.to_datetime(audited["observation_date"], utc=True, errors="raise")
    if (available.array.asi8 > audited.index.asi8).any():
        raise ValueError("Protocol v25 available_at after ts_event would introduce lookahead")
    if not ((available - observed) == pd.Timedelta(days=2)).all():
        raise ValueError("Protocol v25 requires the frozen two-day publication lag")
    hashes = audited["snapshot_sha256"].astype(str)
    if not hashes.map(lambda value: bool(_SHA256_RE.fullmatch(value))).all():
        raise ValueError("Protocol v25 snapshot hashes are invalid")
    if audited["vintage_id"].astype(str).str.strip().eq("").any():
        raise ValueError("Protocol v25 vintage identifiers cannot be empty")
    values = pd.to_numeric(audited["tvl"], errors="raise").astype("float64")
    if not values.map(math.isfinite).all() or (values < 0).any():
        raise ValueError("Protocol v25 TVL values must be finite and non-negative")
    audited["available_at"] = available
    audited["observation_date"] = observed
    audited["tvl"] = values
    return audited


def generate_tvl_expansion_signals(
    factors: pd.DataFrame,
    *,
    candidate: str,
    start_date: str = "2020-01-01",
    end_date: str = "2022-12-31",
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
) -> list[SignalEvent]:
    if candidate not in IDENTITIES:
        raise ValueError(f"unsupported Protocol v25 candidate {candidate!r}")
    frame = audit_factor_frame(factors)
    values = frame["tvl"]
    change = values.diff(int(COMMON_PARAMETERS["change_observations"]))
    ready = change.notna()
    states = (change > float(COMMON_PARAMETERS["threshold"])).where(ready)
    source, model = IDENTITIES[candidate]
    feature_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "protocol": PROTOCOL_VERSION,
                    "candidate": candidate,
                    "kind": KIND_BY_CANDIDATE[candidate],
                    "parameters": COMMON_PARAMETERS,
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
                    "score": math.tanh(max(0.0, change_value) / 1_000_000_000.0)
                    if desired_long
                    else 0.0,
                    "confidence": COMMON_PARAMETERS["confidence"],
                    "source": source,
                    "model_version": model,
                    "ttl_seconds": COMMON_PARAMETERS["ttl_seconds"],
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "candidate": candidate,
                        "kind": KIND_BY_CANDIDATE[candidate],
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "observation_date": pd.Timestamp(row["observation_date"])
                        .date()
                        .isoformat(),
                        "vintage_id": str(row["vintage_id"]),
                        "snapshot_sha256": str(row["snapshot_sha256"]),
                        "historical_vintage_claim": False,
                        "point_in_time_interpretation": (
                            "defillama_current_tvl_lagged_2_calendar_days"
                        ),
                        "trigger": (
                            f"{candidate}_5obs_positive"
                            if desired_long
                            else f"{candidate}_not_positive"
                        ),
                        "inputs": {
                            "tvl": round(float(values.loc[timestamp]), 12),
                            "change_5_observations": round(change_value, 12),
                        },
                        **COMMON_PARAMETERS,
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
    events = generate_tvl_expansion_signals(
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

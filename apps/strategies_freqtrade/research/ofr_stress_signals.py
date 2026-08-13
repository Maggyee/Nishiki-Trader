"""SignalEvent generators for Protocol v20 OFR financial-stress relief."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v20 import IDENTITIES, PARAMETERS, SERIES_KEYS
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id
from apps.strategies_freqtrade.research.independent_mechanism_signals import (
    load_point_in_time_csv,
)

PROTOCOL_VERSION = "research.protocol.v20"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
METRIC_COLUMNS = {
    "systemic_stress_relief": "ofr_fsi",
    "credit_stress_relief": "credit_stress",
    "safe_asset_stress_relief": "safe_asset_stress",
}


@dataclass(frozen=True)
class StressReliefParams:
    change_observations: int = 5
    maximum_change: float = 0.0
    publication_lag_calendar_days: int = 5
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if asdict(self) != PARAMETERS:
            raise ValueError("Protocol v20 stress-relief parameters cannot be tuned")


def _feature_hash(candidate: str, params: StressReliefParams) -> str:
    payload = {
        "protocol": PROTOCOL_VERSION,
        "candidate": candidate,
        "series_key": SERIES_KEYS[candidate],
        "metric_column": METRIC_COLUMNS[candidate],
        "parameters": asdict(params),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def audit_point_in_time_frame(frame: pd.DataFrame, metric_column: str) -> pd.DataFrame:
    required = {"available_at", "vintage_id", "snapshot_sha256", metric_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"point-in-time frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("point-in-time frame must use a DatetimeIndex")
    if frame.index.tz is None or str(frame.index.tz) != "UTC":
        raise ValueError("point-in-time timestamps must be UTC")
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("point-in-time timestamps must be non-empty, unique, and increasing")
    available = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    if available.isna().any() or (available.array.asi8 > frame.index.asi8).any():
        raise ValueError("available_at after ts_event would introduce lookahead")
    vintages = frame["vintage_id"].astype(str).str.strip()
    if frame["vintage_id"].isna().any() or (vintages == "").any():
        raise ValueError("every observation requires a non-empty vintage_id")
    hashes = frame["snapshot_sha256"].astype(str)
    if not hashes.map(lambda value: bool(_SHA256_RE.fullmatch(value))).all():
        raise ValueError("every observation requires sha256:<64 lowercase hex>")
    values = pd.to_numeric(frame[metric_column], errors="raise").astype("float64")
    if not values.map(math.isfinite).all():
        raise ValueError(f"{metric_column} contains NaN or Infinity")
    audited = frame.copy()
    audited["available_at"] = available
    audited[metric_column] = values
    return audited


def generate_ofr_stress_signals(
    factors: pd.DataFrame,
    *,
    candidate: str,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str = "2020-01-01",
    end_date: str = "2022-12-31",
    params: StressReliefParams | None = None,
) -> list[SignalEvent]:
    if candidate not in IDENTITIES:
        raise ValueError(f"unsupported Protocol v20 candidate {candidate!r}")
    cfg = params or StressReliefParams()
    metric_column = METRIC_COLUMNS[candidate]
    frame = audit_point_in_time_frame(factors, metric_column)
    values = frame[metric_column]
    change = values.diff(cfg.change_observations)
    states = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    ready = change.notna()
    states.loc[ready] = change.loc[ready] < cfg.maximum_change
    source, model_version = IDENTITIES[candidate]
    feature_hash = _feature_hash(candidate, cfg)
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
                    "score": (math.tanh(max(0.0, -change_value)) if desired_long else 0.0),
                    "confidence": cfg.confidence,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "candidate": candidate,
                        "series_key": SERIES_KEYS[candidate],
                        "metric_column": metric_column,
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "vintage_id": str(row["vintage_id"]),
                        "snapshot_sha256": str(row["snapshot_sha256"]),
                        "point_in_time_interpretation": (
                            "immutable_current_history_reconstruction_lagged_5_calendar_days"
                        ),
                        "historical_vintage_claim": False,
                        "trigger": (
                            f"{candidate}_5obs_negative"
                            if desired_long
                            else f"{candidate}_not_relieving"
                        ),
                        "inputs": {
                            "value": round(float(values.loc[timestamp]), 12),
                            "change_5obs": round(change_value, 12),
                        },
                        **asdict(cfg),
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
    events = generate_ofr_stress_signals(
        load_point_in_time_csv(args.input_csv),
        candidate=args.candidate,
        symbol=args.symbol,
        venue=args.venue,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    source, model_version = IDENTITIES[args.candidate]
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

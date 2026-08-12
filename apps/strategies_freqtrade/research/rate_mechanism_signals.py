"""Signal generators for Protocol v15 U.S. rate mechanisms."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v15 import IDENTITIES, PARAMETERS, load_and_validate
from apps.ops.research_v15_snapshot import parse_and_audit, verify_snapshot
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id

PROTOCOL_VERSION = "research.protocol.v15"
METRIC_COLUMNS = {
    "real_yield_relief": "DFII10",
    "yield_curve_steepening": "T10Y2Y",
    "treasury_volatility_relief": "DGS10",
}


def build_factor_frame(snapshot_path: Path) -> pd.DataFrame:
    load_and_validate()
    verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit(raw)
    records = []
    for row in rows:
        if any(row[metric] is None for metric in METRIC_COLUMNS.values()):
            continue
        observed = pd.Timestamp(row["observation_date"], tz="UTC")
        decision = observed + pd.Timedelta(days=4)
        records.append(
            {
                "ts_event": decision,
                **{metric: float(row[metric]) for metric in METRIC_COLUMNS.values()},
                "available_at": decision,
                "snapshot_sha256": envelope["snapshot_sha256"],
                "vintage_id": envelope["vintage_id"],
            }
        )
    return pd.DataFrame(records).set_index("ts_event").sort_index()


def generate_rate_signals(
    frame: pd.DataFrame,
    *,
    candidate: str,
    start_date: str = "2020-01-01",
    end_date: str = "2022-12-31",
) -> list[SignalEvent]:
    if candidate not in IDENTITIES:
        raise ValueError(f"unsupported Protocol v15 candidate {candidate!r}")
    metric_name = METRIC_COLUMNS[candidate]
    if frame.empty or frame.index.has_duplicates or metric_name not in frame:
        raise ValueError("Protocol v15 factor frame is invalid")
    values = pd.to_numeric(frame[metric_name], errors="raise")
    if not values.map(math.isfinite).all():
        raise ValueError("Protocol v15 metric values must be finite")
    params = PARAMETERS[candidate]
    factor = values.diff().abs() if candidate == "treasury_volatility_relief" else values
    short = factor.rolling(
        int(params["short_observations"]), min_periods=int(params["short_observations"])
    ).mean()
    long = factor.rolling(
        int(params["long_observations"]), min_periods=int(params["long_observations"])
    ).mean()
    valid = short.notna() & long.notna()
    if candidate == "yield_curve_steepening":
        comparison = short - long
        states = (short > long).where(valid)
    else:
        comparison = long - short
        states = (short < long).where(valid)
    source, model = IDENTITIES[candidate]
    feature_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {"protocol": PROTOCOL_VERSION, "candidate": candidate, "parameters": params},
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
        side = "buy" if desired_long else "flat"
        score = math.tanh(max(0.0, float(comparison.loc[timestamp]))) if desired_long else 0.0
        ts_event = int(timestamp.value)
        row = frame.loc[timestamp]
        events.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": _make_signal_id(
                        source=source,
                        model_version=model,
                        symbol="BTCUSDT",
                        venue="BINANCE",
                        ts_event_ns=ts_event,
                        side=side,
                    ),
                    "symbol": "BTCUSDT",
                    "venue": "BINANCE",
                    "ts_event": ts_event,
                    "horizon": "1d",
                    "side": side,
                    "score": score,
                    "confidence": 0.75,
                    "source": source,
                    "model_version": model,
                    "ttl_seconds": 86400,
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "candidate": candidate,
                        "metric": metric_name,
                        "metric_value": round(float(values.loc[timestamp]), 12),
                        "comparison_value": round(float(comparison.loc[timestamp]), 12),
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "snapshot_sha256": row["snapshot_sha256"],
                        "vintage_id": row["vintage_id"],
                        "point_in_time_interpretation": "fred_reconstruction_lag4_calendar_days",
                        **params,
                    },
                }
            )
        )
        current_long = desired_long
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--candidate", choices=sorted(IDENTITIES), required=True)
    parser.add_argument("--signal-store-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    events = generate_rate_signals(build_factor_frame(args.snapshot), candidate=args.candidate)
    print(f"generated {len(events)} signals for {args.candidate}")
    if not args.dry_run:
        if args.signal_store_path is None:
            parser.error("--signal-store-path is required unless --dry-run")
        written, duplicates = SignalStore(args.signal_store_path).write_many(events)
        print(f"wrote {written}, skipped {duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

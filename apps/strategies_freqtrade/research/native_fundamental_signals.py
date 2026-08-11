"""SignalEvent generators for Protocol v11 crypto-native fundamentals."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v11 import IDENTITIES, PARAMETERS, load_and_validate
from apps.ops.research_v10_snapshot import verify_snapshot
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id

PROTOCOL_VERSION = "research.protocol.v11"
SOURCES_PATH = Path("docs/progress/phase-2-research-v10-data-sources.json")


@dataclass(frozen=True)
class MeanExpansionParams:
    short_days: int = 7
    long_days: int = 30
    ttl_seconds: int = 86_400
    confidence: float = 0.75


@dataclass(frozen=True)
class SupplyExpansionParams:
    change_days: int = 30
    maximum_change: float = 0.0
    assets: tuple[str, str] = ("usdt", "usdc")
    ttl_seconds: int = 86_400
    confidence: float = 0.75


def _load_sources(path: Path = SOURCES_PATH) -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(path.read_text())
    if payload.get("status") != "qualification_complete_all_routes_blocked_missing_status_time":
        raise ValueError("Protocol v10 source qualification status drifted")
    if (
        payload.get("values_reported")
        or payload.get("signals_generated")
        or payload.get("pnl_opened")
    ):
        raise ValueError("Protocol v10 source boundaries drifted")
    return payload


def _snapshot_rows(kind: str, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(spec["path"])
    verification = verify_snapshot(path)
    if verification["snapshot_sha256"] != spec["snapshot_sha256"]:
        raise ValueError(f"Protocol v11 {kind} snapshot hash mismatch")
    envelope = json.loads(path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    payload = json.loads(raw)
    return payload["data"], envelope


def _decision_time(value: str) -> pd.Timestamp:
    observed = pd.Timestamp(value)
    if observed.tz is None:
        raise ValueError("Coin Metrics observation time must be timezone-aware")
    observed = observed.tz_convert("UTC")
    if observed != observed.normalize():
        raise ValueError("Coin Metrics observation must identify a UTC day")
    return observed + pd.Timedelta(days=2)


def build_factor_frames(path: Path = SOURCES_PATH) -> dict[str, pd.DataFrame]:
    sources = _load_sources(path)
    snapshots = sources["snapshots"]
    frames: dict[str, pd.DataFrame] = {}
    for candidate, kind, metric, value_name in (
        ("miner_hashrate_recovery", "hashrate", "HashRate", "hashrate"),
        ("btc_fee_demand", "btc_fees", "FeeTotNtv", "fee_total_ntv"),
    ):
        rows, envelope = _snapshot_rows(kind, snapshots[kind])
        records = [
            {"ts_event": _decision_time(row["time"]), value_name: float(row[metric])}
            for row in rows
        ]
        frame = pd.DataFrame(records).set_index("ts_event").sort_index()
        frame["available_at"] = frame.index
        frame["snapshot_sha256"] = envelope["snapshot_sha256"]
        frame["vintage_id"] = envelope["vintage_id"]
        frames[candidate] = frame

    rows, envelope = _snapshot_rows("stablecoin_supply", snapshots["stablecoin_supply"])
    stable = pd.DataFrame(
        {
            "asset": str(row["asset"]),
            "ts_event": _decision_time(row["time"]),
            "supply": float(row["SplyCur"]),
        }
        for row in rows
    )
    counts = stable.groupby("ts_event")["asset"].nunique()
    if not (counts == 2).all():
        raise ValueError("every stablecoin day must contain exactly USDT and USDC")
    supply = stable.groupby("ts_event", sort=True)["supply"].sum().to_frame("stablecoin_supply")
    supply["available_at"] = supply.index
    supply["snapshot_sha256"] = envelope["snapshot_sha256"]
    supply["vintage_id"] = envelope["vintage_id"]
    frames["stablecoin_liquidity_expansion"] = supply
    return frames


def _audit(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    required = {value_column, "available_at", "snapshot_sha256", "vintage_id"}
    if missing := sorted(required - set(frame.columns)):
        raise ValueError(f"Protocol v11 factor frame is missing {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Protocol v11 factor index must be timezone-aware")
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Protocol v11 factor index must be non-empty, unique, and increasing")
    result = frame.copy()
    values = pd.to_numeric(result[value_column], errors="raise").astype("float64")
    if not values.map(math.isfinite).all() or (values < 0.0).any():
        raise ValueError("Protocol v11 factor values must be finite and non-negative")
    available = pd.to_datetime(result["available_at"], utc=True, errors="raise")
    if (available.array.asi8 > frame.index.asi8).any():
        raise ValueError("Protocol v11 available_at introduces lookahead")
    result[value_column] = values
    result["available_at"] = available
    return result


def _feature_hash(candidate: str, params: dict[str, Any]) -> str:
    body = {"protocol": PROTOCOL_VERSION, "candidate": candidate, "parameters": params}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def generate_native_fundamental_signals(
    frame: pd.DataFrame,
    *,
    candidate: str,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    if candidate not in IDENTITIES:
        raise ValueError(f"unsupported Protocol v11 candidate {candidate!r}")
    if candidate == "stablecoin_liquidity_expansion":
        cfg: MeanExpansionParams | SupplyExpansionParams = SupplyExpansionParams()
        value_column = "stablecoin_supply"
        audited = _audit(frame, value_column)
        metric = audited[value_column].pct_change(cfg.change_days)
        states = (metric > cfg.maximum_change).where(metric.notna())
    else:
        cfg = MeanExpansionParams()
        value_column = "hashrate" if candidate == "miner_hashrate_recovery" else "fee_total_ntv"
        audited = _audit(frame, value_column)
        short = audited[value_column].rolling(cfg.short_days, min_periods=cfg.short_days).mean()
        long = audited[value_column].rolling(cfg.long_days, min_periods=cfg.long_days).mean()
        metric = short / long - 1.0
        states = (short > long).where(short.notna() & long.notna())
    params = PARAMETERS[candidate]
    source, model_version = IDENTITIES[candidate]
    feature_hash = _feature_hash(candidate, params)
    start = pd.Timestamp(start_date, tz="UTC") if start_date else None
    end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) if end_date else None
    current_long = False
    events: list[SignalEvent] = []
    for timestamp, desired in states.items():
        if pd.isna(desired) or (start is not None and timestamp < start):
            continue
        if end is not None and timestamp >= end:
            break
        desired_long = bool(desired)
        if desired_long == current_long:
            continue
        row = audited.loc[timestamp]
        side = "buy" if desired_long else "flat"
        metric_value = float(metric.loc[timestamp])
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
                    "score": math.tanh(max(0.0, metric_value)) if desired_long else 0.0,
                    "confidence": float(params["confidence"]),
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": int(params["ttl_seconds"]),
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "candidate": candidate,
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "snapshot_sha256": str(row["snapshot_sha256"]),
                        "vintage_id": str(row["vintage_id"]),
                        "point_in_time_interpretation": "finalized_ledger_reconstruction_d_plus_2",
                        "provider_vintage_claimed": False,
                        "metric_value": round(metric_value, 12),
                        "factor_value": round(float(row[value_column]), 12),
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
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2022-12-31")
    parser.add_argument("--signal-store-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and args.signal_store_path is None:
        parser.error("--signal-store-path is required unless --dry-run is set")
    frames = build_factor_frames()
    events = generate_native_fundamental_signals(
        frames[args.candidate],
        candidate=args.candidate,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    source, model = IDENTITIES[args.candidate]
    print(f"generated {len(events)} signals for {source} / {model}")
    if args.dry_run:
        return 0
    written, duplicates = SignalStore(args.signal_store_path).write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

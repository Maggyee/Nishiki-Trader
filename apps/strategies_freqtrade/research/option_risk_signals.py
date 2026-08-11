"""SignalEvent generators for the frozen Protocol v9 option-risk batch."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.research_protocol_v9 import load_and_validate
from apps.ops.research_v7_snapshot import verify_snapshot as verify_v7_snapshot
from apps.ops.research_v9_snapshot import verify_snapshot as verify_v9_snapshot
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id

PROTOCOL_VERSION = "research.protocol.v9"
SOURCES_PATH = Path("docs/progress/phase-2-research-v9-data-sources.json")
IDENTITIES = {
    "equity_vol_curve": ("rule_equity_vol_curve_v1", "cboe-vix9d-below-vix-1d-v1"),
    "vol_of_vol_relief": ("rule_vol_of_vol_relief_v1", "cboe-vvix5obs-negative-1d-v1"),
}


@dataclass(frozen=True)
class CurveParams:
    curve_ratio_threshold: float = 1.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.curve_ratio_threshold != 1.0:
            raise ValueError("Protocol v9 fixes the curve threshold at one")
        if self.ttl_seconds != 86_400 or self.confidence != 0.75:
            raise ValueError("Protocol v9 curve TTL/confidence drifted")


@dataclass(frozen=True)
class ReliefParams:
    change_observations: int = 5
    maximum_change: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.change_observations != 5 or self.maximum_change != 0.0:
            raise ValueError("Protocol v9 fixes VVIX relief at five observations below zero")
        if self.ttl_seconds != 86_400 or self.confidence != 0.75:
            raise ValueError("Protocol v9 VVIX TTL/confidence drifted")


def load_sources(path: Path = SOURCES_PATH) -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or payload.get("schema_version") != "research.data_sources.v9":
        raise ValueError("Protocol v9 data-source schema drifted")
    if payload.get("status") != "locked_after_qualification_before_strategy_value_and_pnl_access":
        raise ValueError("Protocol v9 data sources are not locked")
    if any(payload.get("boundaries", {}).values()):
        raise ValueError("Protocol v9 data-source boundaries must remain false")
    snapshots = payload.get("snapshots", {})
    expected = {
        "vix9d": "sha256:81e1df251f4a4ff7e4e1ccf1e7413a3f1edf11fec5891b94712f7df8dc808e72",
        "vvix": "sha256:155f8576a077bb7092ae1f2609a794754f77b1b5022bb330962688724a3629fb",
        "vix": "sha256:b2cffe2c74b4b03cab1cf47759a4be741af17cd87853f1817ba03c6aea30d368",
    }
    if {key: row.get("snapshot_sha256") for key, row in snapshots.items()} != expected:
        raise ValueError("Protocol v9 snapshot hashes drifted")
    return payload


def _snapshot_rows(kind: str, spec: dict[str, Any]) -> list[tuple[date, float]]:
    path = Path(spec["path"])
    verification = verify_v7_snapshot(path) if kind == "vix" else verify_v9_snapshot(path)
    if verification["snapshot_sha256"] != spec["snapshot_sha256"]:
        raise ValueError(f"Protocol v9 {kind} snapshot hash mismatch")
    envelope = json.loads(path.read_text())
    if envelope["vintage_id"] != spec["vintage_id"]:
        raise ValueError(f"Protocol v9 {kind} vintage mismatch")
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != spec["columns"]:
        raise ValueError(f"Protocol v9 {kind} columns drifted")
    rows: list[tuple[date, float]] = []
    for row in reader:
        session: date | None = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                session = datetime.strptime(row["DATE"].strip(), fmt).date()
                break
            except ValueError:
                pass
        if session is None:
            raise ValueError(f"Protocol v9 {kind} has invalid DATE")
        value = float(row[spec["value_column"]])
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"Protocol v9 {kind} value must be finite and positive")
        rows.append((session, value))
    return rows


def build_factor_frames(sources_path: Path = SOURCES_PATH) -> dict[str, pd.DataFrame]:
    sources = load_sources(sources_path)
    snapshots = sources["snapshots"]
    values = {
        kind: pd.Series(dict(_snapshot_rows(kind, spec)), name=f"{kind}_close")
        for kind, spec in snapshots.items()
    }
    curve = pd.concat([values["vix9d"], values["vix"]], axis=1, join="inner").dropna()
    curve.index = pd.DatetimeIndex(
        [datetime.combine(session + timedelta(days=1), datetime.min.time(), UTC) for session in curve.index]
    )
    curve["available_at"] = curve.index
    curve["snapshot_hashes"] = json.dumps(
        {kind: snapshots[kind]["snapshot_sha256"] for kind in ("vix9d", "vix")},
        sort_keys=True,
    )
    curve["vintage_ids"] = json.dumps(
        {kind: snapshots[kind]["vintage_id"] for kind in ("vix9d", "vix")},
        sort_keys=True,
    )
    vvix = values["vvix"].to_frame()
    vvix.index = pd.DatetimeIndex(
        [datetime.combine(session + timedelta(days=1), datetime.min.time(), UTC) for session in vvix.index]
    )
    vvix["available_at"] = vvix.index
    vvix["snapshot_hashes"] = json.dumps(
        {"vvix": snapshots["vvix"]["snapshot_sha256"]}, sort_keys=True
    )
    vvix["vintage_ids"] = json.dumps(
        {"vvix": snapshots["vvix"]["vintage_id"]}, sort_keys=True
    )
    return {"equity_vol_curve": curve, "vol_of_vol_relief": vvix}


def _audit_frame(frame: pd.DataFrame, required: set[str]) -> pd.DataFrame:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Protocol v9 factor frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Protocol v9 factor timestamps must be timezone-aware")
    if str(frame.index.tz) != "UTC":
        raise ValueError("Protocol v9 factor timestamps must use UTC")
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Protocol v9 factor timestamps must be non-empty, unique, and increasing")
    available = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    if (available.array.asi8 > frame.index.asi8).any():
        raise ValueError("Protocol v9 available_at after ts_event would introduce lookahead")
    result = frame.copy()
    result["available_at"] = available
    for column in required - {"available_at", "snapshot_hashes", "vintage_ids"}:
        values = pd.to_numeric(result[column], errors="raise").astype("float64")
        if not values.map(math.isfinite).all() or (values <= 0.0).any():
            raise ValueError(f"Protocol v9 {column} values must be finite and positive")
        result[column] = values
    return result


def _feature_hash(candidate: str, params: dict[str, Any]) -> str:
    payload = {"protocol": PROTOCOL_VERSION, "candidate": candidate, "params": params}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def generate_option_risk_signals(
    frame: pd.DataFrame,
    *,
    candidate: str,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    if candidate not in IDENTITIES:
        raise ValueError(f"unsupported Protocol v9 candidate {candidate!r}")
    common = {"available_at", "snapshot_hashes", "vintage_ids"}
    if candidate == "equity_vol_curve":
        cfg: CurveParams | ReliefParams = CurveParams()
        audited = _audit_frame(frame, common | {"vix9d_close", "vix_close"})
        ratio = audited["vix9d_close"] / audited["vix_close"]
        metric = ratio
        states = ratio < cfg.curve_ratio_threshold
    else:
        cfg = ReliefParams()
        audited = _audit_frame(frame, common | {"vvix_close"})
        change = audited["vvix_close"].pct_change(cfg.change_observations)
        metric = change
        states = change < cfg.maximum_change
        states = states.where(change.notna())
    source, model_version = IDENTITIES[candidate]
    params = asdict(cfg)
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
        metric_value = float(metric.loc[timestamp])
        side = "buy" if desired_long else "flat"
        if candidate == "equity_vol_curve":
            inputs = {
                "vix9d_close": round(float(row["vix9d_close"]), 12),
                "vix_close": round(float(row["vix_close"]), 12),
                "curve_ratio": round(metric_value, 12),
            }
            trigger = "vix9d_below_vix" if desired_long else "vix9d_not_below_vix"
            score = math.tanh(max(0.0, 1.0 - metric_value)) if desired_long else 0.0
        else:
            inputs = {
                "vvix_close": round(float(row["vvix_close"]), 12),
                "change_5obs": round(metric_value, 12),
            }
            trigger = "vvix_5obs_negative" if desired_long else "vvix_not_relieving"
            score = math.tanh(max(0.0, -metric_value)) if desired_long else 0.0
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
                    "score": score,
                    "confidence": cfg.confidence,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": feature_hash,
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "candidate": candidate,
                        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
                        "snapshot_hashes": json.loads(str(row["snapshot_hashes"])),
                        "vintage_ids": json.loads(str(row["vintage_ids"])),
                        "point_in_time": True,
                        "trigger": trigger,
                        "inputs": inputs,
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
    events = generate_option_risk_signals(
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

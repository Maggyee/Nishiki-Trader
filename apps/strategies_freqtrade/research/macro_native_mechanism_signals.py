"""Point-in-time generators for the pre-registered Research Protocol v3 candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Callable, Mapping
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

PROTOCOL_VERSION = "research.protocol.v3"
STRATEGY_IDENTITIES = {
    "miner_hashrate_recovery": (
        "rule_miner_hashrate_recovery_v1",
        "hashrate7-30-positive-1d-v1",
    ),
    "usd_weakness_impulse": (
        "rule_usd_weakness_v1",
        "dxy20d-negative-1d-v1",
    ),
    "equity_vol_relief": (
        "rule_equity_vol_relief_v1",
        "vix5d-negative-1d-v1",
    ),
}

PREREGISTERED_PARAMETERS = {
    "miner_hashrate_recovery": {
        "short_hashrate_days": 7,
        "long_hashrate_days": 30,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
    "usd_weakness_impulse": {
        "dxy_return_days": 20,
        "maximum_dxy_return": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
    "equity_vol_relief": {
        "vix_change_days": 5,
        "maximum_vix_change": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
}

REQUIRED_FACTORS = {
    "miner_hashrate_recovery": ["hashrate_eh_s"],
    "usd_weakness_impulse": ["dxy_close"],
    "equity_vol_relief": ["vix_close"],
}


@dataclass(frozen=True)
class MinerHashrateRecoveryParams:
    short_hashrate_days: int = 7
    long_hashrate_days: int = 30
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.short_hashrate_days != 7 or self.long_hashrate_days != 30:
            raise ValueError("hashrate lookbacks are pre-registered at 7 and 30 days")
        _validate_shared_params(self.ttl_seconds, self.confidence)


@dataclass(frozen=True)
class UsdWeaknessImpulseParams:
    dxy_return_days: int = 20
    maximum_dxy_return: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.dxy_return_days != 20:
            raise ValueError("DXY lookback is pre-registered at 20 days")
        if self.maximum_dxy_return != 0.0:
            raise ValueError("the pre-registered DXY return ceiling is exactly zero")
        _validate_shared_params(self.ttl_seconds, self.confidence)


@dataclass(frozen=True)
class EquityVolReliefParams:
    vix_change_days: int = 5
    maximum_vix_change: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.vix_change_days != 5:
            raise ValueError("VIX lookback is pre-registered at 5 days")
        if self.maximum_vix_change != 0.0:
            raise ValueError("the pre-registered VIX change ceiling is exactly zero")
        _validate_shared_params(self.ttl_seconds, self.confidence)


def _validate_shared_params(ttl_seconds: int, confidence: float) -> None:
    if ttl_seconds != 86_400:
        raise ValueError("Research Protocol v3 fixes the signal TTL at one day")
    if confidence != 0.75:
        raise ValueError("Research Protocol v3 fixes confidence at 0.75")


def _features_hash(strategy: str, params: Mapping[str, Any], fields: list[str]) -> str:
    payload = {
        "protocol": PROTOCOL_VERSION,
        "strategy": strategy,
        "params": dict(params),
        "fields": fields,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def _metadata_base(row: pd.Series, *, strategy: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "strategy": strategy,
        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
        "vintage_id": str(row["vintage_id"]),
        "snapshot_sha256": str(row["snapshot_sha256"]),
        "point_in_time": True,
        "inputs": inputs,
    }


def _state_events(
    frame: pd.DataFrame,
    *,
    strategy: str,
    states: pd.Series,
    score_for: Callable[[pd.Timestamp, bool], float],
    metadata_for: Callable[[pd.Timestamp, bool], dict[str, Any]],
    params: Mapping[str, Any],
    fields: list[str],
    symbol: str,
    venue: str,
    start_date: str | None,
    end_date: str | None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES[strategy]
    feature_hash = _features_hash(strategy, params, fields)
    start = pd.Timestamp(start_date, tz="UTC") if start_date else None
    end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) if end_date else None
    current_long = False
    events: list[SignalEvent] = []
    for timestamp, desired in states.items():
        if pd.isna(desired):
            continue
        desired_long = bool(desired)
        if start is not None and timestamp < start:
            continue
        if end is not None and timestamp >= end:
            break
        if desired_long == current_long:
            continue
        side = "buy" if desired_long else "flat"
        ts_event = int(timestamp.value)
        score = score_for(timestamp, desired_long)
        if not math.isfinite(score):
            raise ValueError("signal score must be finite")
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
                    "score": max(-1.0, min(1.0, score if desired_long else 0.0)),
                    "confidence": float(params["confidence"]),
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": int(params["ttl_seconds"]),
                    "features_hash": feature_hash,
                    "metadata": metadata_for(timestamp, desired_long),
                }
            )
        )
        current_long = desired_long
    return events


def generate_miner_hashrate_recovery_signals(
    factors: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: MinerHashrateRecoveryParams | None = None,
) -> list[SignalEvent]:
    cfg = params or MinerHashrateRecoveryParams()
    numeric = {"hashrate_eh_s"}
    frame = audit_point_in_time_frame(factors, required_numeric=numeric)
    if (frame["hashrate_eh_s"] <= 0.0).any():
        raise ValueError("hashrate must be strictly positive")
    short_mean = frame["hashrate_eh_s"].rolling(
        cfg.short_hashrate_days, min_periods=cfg.short_hashrate_days
    ).mean()
    long_mean = frame["hashrate_eh_s"].rolling(
        cfg.long_hashrate_days, min_periods=cfg.long_hashrate_days
    ).mean()
    ready = short_mean.notna() & long_mean.notna()
    states = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    states.loc[ready] = short_mean.loc[ready] > long_mean.loc[ready]
    params_dict = asdict(cfg)

    def metadata(timestamp: pd.Timestamp, desired: bool) -> dict[str, Any]:
        row = frame.loc[timestamp]
        inputs = {
            "hashrate_eh_s": round(float(row["hashrate_eh_s"]), 12),
            "hashrate_mean_7d": round(float(short_mean.loc[timestamp]), 12),
            "hashrate_mean_30d": round(float(long_mean.loc[timestamp]), 12),
            "hashrate_spread": round(
                float(short_mean.loc[timestamp] - long_mean.loc[timestamp]), 12
            ),
        }
        return {
            **_metadata_base(row, strategy="miner_hashrate_recovery", inputs=inputs),
            "trigger": "hashrate_short_above_long" if desired else "hashrate_not_recovering",
            **params_dict,
        }

    return _state_events(
        frame,
        strategy="miner_hashrate_recovery",
        states=states,
        score_for=lambda timestamp, desired: math.tanh(
            max(
                0.0,
                float(
                    (short_mean.loc[timestamp] / long_mean.loc[timestamp]) - 1.0
                ),
            )
        ),
        metadata_for=metadata,
        params=params_dict,
        fields=sorted(numeric),
        symbol=symbol,
        venue=venue,
        start_date=start_date,
        end_date=end_date,
    )


def generate_usd_weakness_impulse_signals(
    factors: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: UsdWeaknessImpulseParams | None = None,
) -> list[SignalEvent]:
    cfg = params or UsdWeaknessImpulseParams()
    numeric = {"dxy_close"}
    frame = audit_point_in_time_frame(factors, required_numeric=numeric)
    if (frame["dxy_close"] <= 0.0).any():
        raise ValueError("DXY close must be strictly positive")
    dxy_return = frame["dxy_close"].pct_change(cfg.dxy_return_days)
    ready = dxy_return.notna()
    states = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    states.loc[ready] = dxy_return.loc[ready] < cfg.maximum_dxy_return
    params_dict = asdict(cfg)

    def metadata(timestamp: pd.Timestamp, desired: bool) -> dict[str, Any]:
        row = frame.loc[timestamp]
        inputs = {
            "dxy_close": round(float(row["dxy_close"]), 12),
            "dxy_return_20d": round(float(dxy_return.loc[timestamp]), 12),
        }
        return {
            **_metadata_base(row, strategy="usd_weakness_impulse", inputs=inputs),
            "trigger": "dxy_20d_negative" if desired else "dxy_not_weak",
            **params_dict,
        }

    return _state_events(
        frame,
        strategy="usd_weakness_impulse",
        states=states,
        score_for=lambda timestamp, desired: math.tanh(
            max(0.0, -float(dxy_return.loc[timestamp]))
        ),
        metadata_for=metadata,
        params=params_dict,
        fields=sorted(numeric),
        symbol=symbol,
        venue=venue,
        start_date=start_date,
        end_date=end_date,
    )


def generate_equity_vol_relief_signals(
    factors: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: EquityVolReliefParams | None = None,
) -> list[SignalEvent]:
    cfg = params or EquityVolReliefParams()
    numeric = {"vix_close"}
    frame = audit_point_in_time_frame(factors, required_numeric=numeric)
    if (frame["vix_close"] <= 0.0).any():
        raise ValueError("VIX close must be strictly positive")
    vix_change = frame["vix_close"].pct_change(cfg.vix_change_days)
    ready = vix_change.notna()
    states = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    states.loc[ready] = vix_change.loc[ready] < cfg.maximum_vix_change
    params_dict = asdict(cfg)

    def metadata(timestamp: pd.Timestamp, desired: bool) -> dict[str, Any]:
        row = frame.loc[timestamp]
        inputs = {
            "vix_close": round(float(row["vix_close"]), 12),
            "vix_change_5d": round(float(vix_change.loc[timestamp]), 12),
        }
        return {
            **_metadata_base(row, strategy="equity_vol_relief", inputs=inputs),
            "trigger": "vix_5d_negative" if desired else "vix_not_relieving",
            **params_dict,
        }

    return _state_events(
        frame,
        strategy="equity_vol_relief",
        states=states,
        score_for=lambda timestamp, desired: math.tanh(
            max(0.0, -float(vix_change.loc[timestamp]))
        ),
        metadata_for=metadata,
        params=params_dict,
        fields=sorted(numeric),
        symbol=symbol,
        venue=venue,
        start_date=start_date,
        end_date=end_date,
    )


GENERATORS: dict[str, Callable[..., list[SignalEvent]]] = {
    "miner_hashrate_recovery": generate_miner_hashrate_recovery_signals,
    "usd_weakness_impulse": generate_usd_weakness_impulse_signals,
    "equity_vol_relief": generate_equity_vol_relief_signals,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(GENERATORS), required=True)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--signal-store-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.dry_run and args.signal_store_path is None:
        raise SystemExit("--signal-store-path is required unless --dry-run is set")
    frame = load_point_in_time_csv(args.input_csv)
    events = GENERATORS[args.strategy](
        frame,
        symbol=args.symbol,
        venue=args.venue,
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

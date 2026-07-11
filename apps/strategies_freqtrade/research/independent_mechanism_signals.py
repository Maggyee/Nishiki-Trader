"""Point-in-time generators for the pre-registered Research Protocol v2 candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id

PROTOCOL_VERSION = "research.protocol.v2"
STRATEGY_IDENTITIES = {
    "option_risk_premium": (
        "rule_option_risk_premium_v1",
        "structural-rn-excessret30d-sign-v1",
    ),
    "futures_basis_curve": (
        "rule_futures_basis_curve_v1",
        "front-next-contango-sign-1d-v1",
    ),
    "stablecoin_liquidity": (
        "rule_stablecoin_liquidity_v1",
        "supply30d-transfer7d-positive-1d-v1",
    ),
}

PREREGISTERED_PARAMETERS = {
    "option_risk_premium": {
        "expected_excess_return_floor": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
    "futures_basis_curve": {
        "minimum_annualized_basis": 0.0,
        "minimum_curve_slope": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
    "stablecoin_liquidity": {
        "supply_change_days": 30,
        "transfer_sum_days": 7,
        "minimum_supply_change": 0.0,
        "minimum_transfer_change": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
}

REQUIRED_FACTORS = {
    "option_risk_premium": [
        "expected_excess_return_30d",
        "intercept_contribution",
        "variance_contribution",
        "higher_moment_contribution",
        "vol_of_vol_contribution",
        "replication_spec_hash",
    ],
    "futures_basis_curve": [
        "spot_price",
        "front_futures_price",
        "next_futures_price",
        "front_days_to_expiry",
        "next_days_to_expiry",
    ],
    "stablecoin_liquidity": [
        "stablecoin_supply_total",
        "stablecoin_transfer_volume",
    ],
}

_BASE_COLUMNS = {"available_at", "vintage_id", "snapshot_sha256"}
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class OptionRiskPremiumParams:
    expected_excess_return_floor: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.expected_excess_return_floor != 0.0:
            raise ValueError("the pre-registered excess-return floor is exactly zero")
        _validate_shared_params(self.ttl_seconds, self.confidence)


@dataclass(frozen=True)
class FuturesBasisCurveParams:
    minimum_annualized_basis: float = 0.0
    minimum_curve_slope: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.minimum_annualized_basis != 0.0 or self.minimum_curve_slope != 0.0:
            raise ValueError("the pre-registered basis and curve floors are exactly zero")
        _validate_shared_params(self.ttl_seconds, self.confidence)


@dataclass(frozen=True)
class StablecoinLiquidityParams:
    supply_change_days: int = 30
    transfer_sum_days: int = 7
    minimum_supply_change: float = 0.0
    minimum_transfer_change: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.supply_change_days != 30 or self.transfer_sum_days != 7:
            raise ValueError("stablecoin lookbacks are pre-registered at 30 and 7 days")
        if self.minimum_supply_change != 0.0 or self.minimum_transfer_change != 0.0:
            raise ValueError("the pre-registered stablecoin impulse floors are exactly zero")
        _validate_shared_params(self.ttl_seconds, self.confidence)


def _validate_shared_params(ttl_seconds: int, confidence: float) -> None:
    if ttl_seconds != 86_400:
        raise ValueError("Research Protocol v2 fixes the signal TTL at one day")
    if confidence != 0.75:
        raise ValueError("Research Protocol v2 fixes confidence at 0.75")


def load_point_in_time_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "ts_event" not in frame:
        raise ValueError("factor CSV is missing ts_event")
    timestamps = pd.to_datetime(frame.pop("ts_event"), utc=True, errors="raise")
    frame.index = pd.DatetimeIndex(timestamps, name="ts_event")
    return frame


def audit_point_in_time_frame(
    frame: pd.DataFrame,
    *,
    required_numeric: set[str],
    required_text: set[str] | None = None,
) -> pd.DataFrame:
    """Fail closed on publication lag, revisions, duplicates, gaps, and invalid values."""

    required_text = required_text or set()
    required = _BASE_COLUMNS | required_numeric | required_text
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"point-in-time frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("point-in-time frame must use a DatetimeIndex")
    if frame.index.tz is None or str(frame.index.tz) != "UTC":
        raise ValueError("point-in-time timestamps must be UTC")
    if frame.empty:
        raise ValueError("point-in-time frame must not be empty")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("point-in-time timestamps must be unique and strictly increasing")
    if len(frame.index) > 1:
        steps = frame.index.to_series().diff().dropna()
        if not (steps == pd.Timedelta(days=1)).all():
            raise ValueError("point-in-time frame must contain every daily observation")

    available = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    if available.isna().any():
        raise ValueError("available_at must not be missing")
    if (available.array.asi8 > frame.index.asi8).any():
        raise ValueError("available_at after ts_event would introduce lookahead")

    vintages = frame["vintage_id"].astype(str).str.strip()
    if (vintages == "").any() or frame["vintage_id"].isna().any():
        raise ValueError("every observation requires a non-empty vintage_id")
    hashes = frame["snapshot_sha256"].astype(str)
    if not hashes.map(lambda value: bool(_SHA256_RE.fullmatch(value))).all():
        raise ValueError("every observation requires sha256:<64 lowercase hex>")

    for column in sorted(required_text):
        values = frame[column].astype(str).str.strip()
        if frame[column].isna().any() or (values == "").any():
            raise ValueError(f"{column} must contain non-empty text")
    for column in sorted(required_numeric):
        values = pd.to_numeric(frame[column], errors="raise").astype("float64")
        if not np.isfinite(values.to_numpy()).all():
            raise ValueError(f"{column} contains NaN or Infinity")

    audited = frame.copy()
    audited["available_at"] = available
    for column in required_numeric:
        audited[column] = pd.to_numeric(audited[column], errors="raise").astype("float64")
    return audited


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


def generate_option_risk_premium_signals(
    factors: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: OptionRiskPremiumParams | None = None,
) -> list[SignalEvent]:
    cfg = params or OptionRiskPremiumParams()
    numeric = {
        "expected_excess_return_30d",
        "intercept_contribution",
        "variance_contribution",
        "higher_moment_contribution",
        "vol_of_vol_contribution",
    }
    frame = audit_point_in_time_frame(
        factors,
        required_numeric=numeric,
        required_text={"replication_spec_hash"},
    )
    if not frame["replication_spec_hash"].astype(str).map(_SHA256_RE.fullmatch).all():
        raise ValueError("replication_spec_hash must be sha256:<64 lowercase hex>")
    decomposition = frame[
        [
            "intercept_contribution",
            "variance_contribution",
            "higher_moment_contribution",
            "vol_of_vol_contribution",
        ]
    ].sum(axis=1)
    if not np.allclose(
        decomposition.to_numpy(),
        frame["expected_excess_return_30d"].to_numpy(),
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("option factor decomposition does not equal expected excess return")
    states = frame["expected_excess_return_30d"] > cfg.expected_excess_return_floor
    params_dict = asdict(cfg)

    def metadata(timestamp: pd.Timestamp, desired: bool) -> dict[str, Any]:
        row = frame.loc[timestamp]
        inputs = {column: round(float(row[column]), 12) for column in sorted(numeric)}
        inputs["replication_spec_hash"] = str(row["replication_spec_hash"])
        return {
            **_metadata_base(row, strategy="option_risk_premium", inputs=inputs),
            "trigger": "positive_structural_expected_excess_return" if desired else "non_positive_structural_expected_excess_return",
            **params_dict,
        }

    return _state_events(
        frame,
        strategy="option_risk_premium",
        states=states,
        score_for=lambda timestamp, desired: math.tanh(
            max(0.0, float(frame.loc[timestamp, "expected_excess_return_30d"]))
        ),
        metadata_for=metadata,
        params=params_dict,
        fields=sorted(numeric | {"replication_spec_hash"}),
        symbol=symbol,
        venue=venue,
        start_date=start_date,
        end_date=end_date,
    )


def generate_futures_basis_curve_signals(
    factors: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: FuturesBasisCurveParams | None = None,
) -> list[SignalEvent]:
    cfg = params or FuturesBasisCurveParams()
    numeric = {
        "spot_price",
        "front_futures_price",
        "next_futures_price",
        "front_days_to_expiry",
        "next_days_to_expiry",
    }
    frame = audit_point_in_time_frame(factors, required_numeric=numeric)
    prices = frame[["spot_price", "front_futures_price", "next_futures_price"]]
    if (prices <= 0.0).any().any():
        raise ValueError("spot and futures prices must be positive")
    front_days = frame["front_days_to_expiry"]
    next_days = frame["next_days_to_expiry"]
    if (front_days <= 0.0).any() or (next_days <= front_days).any():
        raise ValueError("expiry days must satisfy 0 < front < next")
    front_basis = (frame["front_futures_price"] / frame["spot_price"] - 1.0) * (
        365.0 / front_days
    )
    next_basis = (frame["next_futures_price"] / frame["spot_price"] - 1.0) * (
        365.0 / next_days
    )
    curve_slope = next_basis - front_basis
    states = (
        (front_basis > cfg.minimum_annualized_basis)
        & (next_basis > cfg.minimum_annualized_basis)
        & (curve_slope >= cfg.minimum_curve_slope)
    )
    params_dict = asdict(cfg)

    def metadata(timestamp: pd.Timestamp, desired: bool) -> dict[str, Any]:
        row = frame.loc[timestamp]
        inputs = {column: round(float(row[column]), 12) for column in sorted(numeric)}
        inputs.update(
            {
                "front_annualized_basis": round(float(front_basis.loc[timestamp]), 12),
                "next_annualized_basis": round(float(next_basis.loc[timestamp]), 12),
                "curve_slope": round(float(curve_slope.loc[timestamp]), 12),
            }
        )
        return {
            **_metadata_base(row, strategy="futures_basis_curve", inputs=inputs),
            "trigger": "positive_upward_basis_curve" if desired else "basis_curve_not_eligible",
            **params_dict,
        }

    return _state_events(
        frame,
        strategy="futures_basis_curve",
        states=states,
        score_for=lambda timestamp, desired: math.tanh(
            max(0.0, float(next_basis.loc[timestamp]))
        ),
        metadata_for=metadata,
        params=params_dict,
        fields=sorted(numeric),
        symbol=symbol,
        venue=venue,
        start_date=start_date,
        end_date=end_date,
    )


def generate_stablecoin_liquidity_signals(
    factors: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    start_date: str | None = None,
    end_date: str | None = None,
    params: StablecoinLiquidityParams | None = None,
) -> list[SignalEvent]:
    cfg = params or StablecoinLiquidityParams()
    numeric = {"stablecoin_supply_total", "stablecoin_transfer_volume"}
    frame = audit_point_in_time_frame(factors, required_numeric=numeric)
    if (frame[list(numeric)] <= 0.0).any().any():
        raise ValueError("stablecoin supply and transfer volume must be positive")
    supply_change = frame["stablecoin_supply_total"].pct_change(cfg.supply_change_days)
    current_transfer = frame["stablecoin_transfer_volume"].rolling(
        cfg.transfer_sum_days, min_periods=cfg.transfer_sum_days
    ).sum()
    previous_transfer = current_transfer.shift(cfg.transfer_sum_days)
    transfer_change = current_transfer / previous_transfer - 1.0
    ready = supply_change.notna() & transfer_change.notna()
    states = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    states.loc[ready] = (
        (supply_change.loc[ready] > cfg.minimum_supply_change)
        & (transfer_change.loc[ready] > cfg.minimum_transfer_change)
    )
    params_dict = asdict(cfg)

    def metadata(timestamp: pd.Timestamp, desired: bool) -> dict[str, Any]:
        row = frame.loc[timestamp]
        inputs = {
            "stablecoin_supply_total": round(float(row["stablecoin_supply_total"]), 12),
            "stablecoin_transfer_volume": round(float(row["stablecoin_transfer_volume"]), 12),
            "supply_change": round(float(supply_change.loc[timestamp]), 12),
            "transfer_change": round(float(transfer_change.loc[timestamp]), 12),
        }
        return {
            **_metadata_base(row, strategy="stablecoin_liquidity", inputs=inputs),
            "trigger": "positive_supply_and_transfer_impulse" if desired else "liquidity_impulse_not_eligible",
            **params_dict,
        }

    return _state_events(
        frame,
        strategy="stablecoin_liquidity",
        states=states,
        score_for=lambda timestamp, desired: math.tanh(
            max(
                0.0,
                min(
                    float(supply_change.loc[timestamp]),
                    float(transfer_change.loc[timestamp]),
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


GENERATORS: dict[str, Callable[..., list[SignalEvent]]] = {
    "option_risk_premium": generate_option_risk_premium_signals,
    "futures_basis_curve": generate_futures_basis_curve_signals,
    "stablecoin_liquidity": generate_stablecoin_liquidity_signals,
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

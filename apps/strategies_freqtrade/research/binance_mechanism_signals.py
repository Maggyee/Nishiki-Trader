"""Fail-closed SignalEvent generators for Research Protocol v5.

The module consumes normalized, immutable Binance snapshot rows.  It never
downloads data, sizes orders, starts NautilusTrader, or touches SourcePolicy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import _make_signal_id

PROTOCOL_VERSION = "research.protocol.v5"
ASSETS = ("BTCUSDT", "ETHUSDT")
STRATEGY_IDENTITIES = {
    "curve_carry": (
        "rule_binance_curve_carry_v1",
        "btc-eth-front-next-positive-steep-daily-v1",
    ),
    "bvol_relief": (
        "rule_binance_bvol_relief_v1",
        "btc-eth-bvol5d-negative-daily-lag2-v1",
    ),
}
REQUIRED_FACTORS = {
    "curve_carry": [
        "index_close",
        "front_futures_close",
        "next_futures_close",
        "front_days_to_expiry",
        "next_days_to_expiry",
        "front_contract",
        "next_contract",
        "front_expiry",
        "next_expiry",
    ],
    "bvol_relief": ["bvol_index"],
}

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class CurveCarryParams:
    minimum_annualized_basis: float = 0.0
    minimum_curve_slope: float = 0.0
    expiry_hour_utc: int = 8
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.minimum_annualized_basis != 0.0 or self.minimum_curve_slope != 0.0:
            raise ValueError("curve floors are frozen at exactly zero")
        if self.expiry_hour_utc != 8:
            raise ValueError("quarterly delivery is frozen at 08:00 UTC")
        _validate_shared(self.ttl_seconds, self.confidence)


@dataclass(frozen=True)
class BvolReliefParams:
    change_observations: int = 5
    historical_publication_lag_days: int = 2
    maximum_change: float = 0.0
    ttl_seconds: int = 86_400
    confidence: float = 0.75

    def __post_init__(self) -> None:
        if self.change_observations != 5:
            raise ValueError("BVOL lookback is frozen at five valid observations")
        if self.historical_publication_lag_days != 2:
            raise ValueError("historical BVOL publication lag is frozen at two days")
        if self.maximum_change != 0.0:
            raise ValueError("BVOL change ceiling is frozen at exactly zero")
        _validate_shared(self.ttl_seconds, self.confidence)


def _validate_shared(ttl_seconds: int, confidence: float) -> None:
    if ttl_seconds != 86_400:
        raise ValueError("Research Protocol v5 fixes the SignalEvent TTL at one day")
    if confidence != 0.75:
        raise ValueError("Research Protocol v5 fixes confidence at 0.75")


PREREGISTERED_PARAMETERS = {
    "curve_carry": asdict(CurveCarryParams()),
    "bvol_relief": asdict(BvolReliefParams()),
}


def candidate_features_hash(candidate: str) -> str:
    if candidate not in STRATEGY_IDENTITIES:
        raise ValueError(f"unknown v5 candidate {candidate!r}")
    payload = {
        "protocol": PROTOCOL_VERSION,
        "candidate": candidate,
        "identity": STRATEGY_IDENTITIES[candidate],
        "parameters": PREREGISTERED_PARAMETERS[candidate],
        "required_factors": REQUIRED_FACTORS[candidate],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(encoded.encode()).hexdigest()}"


def candidate_fingerprint(candidate: str) -> dict[str, Any]:
    source, model_version = STRATEGY_IDENTITIES[candidate]
    core = {
        "candidate": candidate,
        "source": source,
        "model_version": model_version,
        "parameters": PREREGISTERED_PARAMETERS[candidate],
        "required_factors": REQUIRED_FACTORS[candidate],
        "features_hash": candidate_features_hash(candidate),
    }
    encoded = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return {
        **core,
        "candidate_sha256": f"sha256:{hashlib.sha256(encoded.encode()).hexdigest()}",
    }


def _parse_utc(series: pd.Series, field: str) -> pd.Series:
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{field} contains a missing or invalid timestamp")
    return parsed


def _parse_raw_hashes(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("raw_file_hashes must be canonical JSON or an object") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("raw_file_hashes must be a non-empty object")
    result = {str(key): str(item) for key, item in value.items()}
    if any(not key or not _SHA256_RE.fullmatch(item) for key, item in result.items()):
        raise ValueError("raw_file_hashes contains an invalid name or SHA-256")
    return dict(sorted(result.items()))


def audit_normalized_frame(
    frame: pd.DataFrame,
    *,
    candidate: str,
    asset: str,
) -> pd.DataFrame:
    """Validate normalized v5 rows without forward-filling gaps or values."""

    asset = asset.upper()
    if asset not in ASSETS:
        raise ValueError(f"asset must be one of {ASSETS}")
    required = {
        "asset",
        "data_date",
        "available_at",
        "retrieved_at",
        "vintage_id",
        "snapshot_sha256",
        "raw_file_hashes",
        *REQUIRED_FACTORS[candidate],
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"normalized {candidate} frame is missing columns: {missing}")
    if frame.empty:
        raise ValueError("normalized v5 frame must not be empty")
    if set(frame["asset"].astype(str).str.upper()) != {asset}:
        raise ValueError("normalized frame contains the wrong or mixed asset")

    audited = frame.copy()
    days = pd.to_datetime(audited["data_date"], format="%Y-%m-%d", errors="coerce")
    if days.isna().any():
        raise ValueError("data_date must use YYYY-MM-DD")
    audited["data_date"] = days.dt.date
    if audited["data_date"].duplicated().any():
        raise ValueError("normalized data_date rows must be unique; vintage comparison is blocked")
    audited = audited.sort_values("data_date", kind="mergesort").reset_index(drop=True)
    audited["available_at"] = _parse_utc(audited["available_at"], "available_at")
    audited["retrieved_at"] = _parse_utc(audited["retrieved_at"], "retrieved_at")
    if audited["available_at"].duplicated().any():
        raise ValueError("available_at decision timestamps must be unique")

    if audited["vintage_id"].isna().any() or (
        audited["vintage_id"].astype(str).str.strip() == ""
    ).any():
        raise ValueError("every normalized row requires a vintage_id")
    if not audited["snapshot_sha256"].astype(str).map(_SHA256_RE.fullmatch).all():
        raise ValueError("every normalized row requires snapshot_sha256")
    audited["raw_file_hashes"] = audited["raw_file_hashes"].map(_parse_raw_hashes)

    if candidate == "curve_carry":
        numeric = [
            "index_close",
            "front_futures_close",
            "next_futures_close",
            "front_days_to_expiry",
            "next_days_to_expiry",
        ]
        for column in numeric:
            audited[column] = pd.to_numeric(audited[column], errors="coerce")
            if audited[column].isna().any() or not audited[column].map(math.isfinite).all():
                raise ValueError(f"{column} contains NaN or Infinity")
        if (audited[["index_close", "front_futures_close", "next_futures_close"]] <= 0).any().any():
            raise ValueError("curve prices must be strictly positive")
        if (audited["front_days_to_expiry"] <= 0).any() or (
            audited["next_days_to_expiry"] <= audited["front_days_to_expiry"]
        ).any():
            raise ValueError("curve expiries must satisfy 0 < front < next")
        front_expiry = _parse_utc(audited["front_expiry"], "front_expiry")
        next_expiry = _parse_utc(audited["next_expiry"], "next_expiry")
        if not (front_expiry.dt.hour == 8).all() or not (next_expiry.dt.hour == 8).all():
            raise ValueError("quarterly expiries must use the frozen 08:00 UTC rule")
        if (next_expiry <= front_expiry).any():
            raise ValueError("front and next contract expiry order is invalid")
        audited["front_expiry"] = front_expiry
        audited["next_expiry"] = next_expiry
    else:
        audited["bvol_index"] = pd.to_numeric(audited["bvol_index"], errors="coerce")
        if audited["bvol_index"].isna().any() or not audited["bvol_index"].map(
            math.isfinite
        ).all():
            raise ValueError("bvol_index contains NaN or Infinity")
        if (audited["bvol_index"] <= 0).any():
            raise ValueError("bvol_index must be strictly positive")
        for row in audited.itertuples(index=False):
            data_day = row.data_date
            expected_historical = datetime.combine(
                data_day + timedelta(days=2), datetime.min.time(), UTC
            )
            if data_day < date(2026, 7, 1):
                if row.available_at.to_pydatetime() != expected_historical:
                    raise ValueError("historical BVOL rows must use the fixed two-day lag")
            else:
                retrieved = row.retrieved_at.to_pydatetime().astimezone(UTC)
                next_boundary = datetime.combine(
                    retrieved.date() + timedelta(days=1), datetime.min.time(), UTC
                )
                if row.available_at.to_pydatetime() < next_boundary:
                    raise ValueError("future BVOL signal precedes the UTC day after retrieval")
    return audited


def _missing_metadata(candidate: str, asset: str, data_day: date) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "candidate": candidate,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "quality_status": "missing_no_forward_fill",
        "raw_file_hashes": {},
        "parameters": PREREGISTERED_PARAMETERS[candidate],
        "features_hash": candidate_features_hash(candidate),
        "point_in_time": True,
    }


def _row_metadata(
    row: pd.Series,
    *,
    candidate: str,
    asset: str,
    factor: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = {
        "protocol_version": PROTOCOL_VERSION,
        "candidate": candidate,
        "asset": asset,
        "data_date": row["data_date"].isoformat(),
        "available_at": pd.Timestamp(row["available_at"]).isoformat(),
        "retrieved_at": pd.Timestamp(row["retrieved_at"]).isoformat(),
        "vintage_id": str(row["vintage_id"]),
        "snapshot_sha256": str(row["snapshot_sha256"]),
        "raw_file_hashes": dict(row["raw_file_hashes"]),
        "factor": dict(factor),
        "parameters": PREREGISTERED_PARAMETERS[candidate],
        "features_hash": candidate_features_hash(candidate),
        "quality_status": "valid",
        "point_in_time": True,
    }
    if candidate == "curve_carry":
        metadata["contracts"] = {
            "front": str(row["front_contract"]),
            "next": str(row["next_contract"]),
            "front_expiry": pd.Timestamp(row["front_expiry"]).isoformat(),
            "next_expiry": pd.Timestamp(row["next_expiry"]).isoformat(),
        }
    return metadata


def _events_from_states(
    states: list[tuple[datetime, bool, dict[str, Any]]],
    *,
    candidate: str,
    asset: str,
    start_date: str | None,
    end_date: str | None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES[candidate]
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    current_long = False
    events: list[SignalEvent] = []
    for decision_at, desired_long, metadata in sorted(states, key=lambda item: item[0]):
        decision_day = decision_at.astimezone(UTC).date()
        if start is not None and decision_day < start:
            continue
        if end is not None and decision_day > end:
            continue
        if desired_long == current_long:
            continue
        side = "buy" if desired_long else "flat"
        ts_event = int(pd.Timestamp(decision_at).value)
        events.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": _make_signal_id(
                        source=source,
                        model_version=model_version,
                        symbol=asset,
                        venue="BINANCE",
                        ts_event_ns=ts_event,
                        side=side,
                    ),
                    "symbol": asset,
                    "venue": "BINANCE",
                    "ts_event": ts_event,
                    "horizon": "1d",
                    "side": side,
                    "score": 1.0 if desired_long else 0.0,
                    "confidence": 0.75,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": 86_400,
                    "features_hash": candidate_features_hash(candidate),
                    "metadata": metadata,
                }
            )
        )
        current_long = desired_long
    return events


def generate_curve_carry_signals(
    factors: pd.DataFrame,
    *,
    asset: str,
    start_date: str | None = None,
    end_date: str | None = None,
    params: CurveCarryParams | None = None,
) -> list[SignalEvent]:
    cfg = params or CurveCarryParams()
    asset = asset.upper()
    frame = audit_normalized_frame(factors, candidate="curve_carry", asset=asset)
    rows = {row["data_date"]: row for _, row in frame.iterrows()}
    first, last = min(rows), max(rows)
    states: list[tuple[datetime, bool, dict[str, Any]]] = []
    data_day = first
    while data_day <= last:
        row = rows.get(data_day)
        if row is None:
            decision = datetime.combine(data_day + timedelta(days=1), datetime.min.time(), UTC)
            states.append((decision, False, _missing_metadata("curve_carry", asset, data_day)))
        else:
            front = (row["front_futures_close"] / row["index_close"] - 1.0) * 365.0 / row[
                "front_days_to_expiry"
            ]
            next_basis = (row["next_futures_close"] / row["index_close"] - 1.0) * 365.0 / row[
                "next_days_to_expiry"
            ]
            desired = bool(
                front > cfg.minimum_annualized_basis
                and next_basis > cfg.minimum_annualized_basis
                and next_basis >= front + cfg.minimum_curve_slope
            )
            factor = {
                "index_close": float(row["index_close"]),
                "front_futures_close": float(row["front_futures_close"]),
                "next_futures_close": float(row["next_futures_close"]),
                "front_days_to_expiry": float(row["front_days_to_expiry"]),
                "next_days_to_expiry": float(row["next_days_to_expiry"]),
                "front_annualized_basis": round(float(front), 12),
                "next_annualized_basis": round(float(next_basis), 12),
                "curve_slope": round(float(next_basis - front), 12),
            }
            states.append(
                (
                    pd.Timestamp(row["available_at"]).to_pydatetime(),
                    desired,
                    _row_metadata(row, candidate="curve_carry", asset=asset, factor=factor),
                )
            )
        data_day += timedelta(days=1)
    return _events_from_states(
        states,
        candidate="curve_carry",
        asset=asset,
        start_date=start_date,
        end_date=end_date,
    )


def generate_bvol_relief_signals(
    factors: pd.DataFrame,
    *,
    asset: str,
    start_date: str | None = None,
    end_date: str | None = None,
    params: BvolReliefParams | None = None,
) -> list[SignalEvent]:
    cfg = params or BvolReliefParams()
    asset = asset.upper()
    frame = audit_normalized_frame(factors, candidate="bvol_relief", asset=asset)
    rows = {row["data_date"]: row for _, row in frame.iterrows()}
    valid_history: list[float] = []
    states: list[tuple[datetime, bool, dict[str, Any]]] = []
    data_day = min(rows)
    last = max(rows)
    while data_day <= last:
        row = rows.get(data_day)
        if row is None:
            decision = datetime.combine(
                data_day + timedelta(days=cfg.historical_publication_lag_days),
                datetime.min.time(),
                UTC,
            )
            states.append((decision, False, _missing_metadata("bvol_relief", asset, data_day)))
        else:
            current = float(row["bvol_index"])
            change = (
                current - valid_history[-cfg.change_observations]
                if len(valid_history) >= cfg.change_observations
                else None
            )
            desired = change is not None and change < cfg.maximum_change
            factor = {
                "bvol_index": current,
                "change_observations": cfg.change_observations,
                "bvol_change": round(change, 12) if change is not None else None,
            }
            states.append(
                (
                    pd.Timestamp(row["available_at"]).to_pydatetime(),
                    desired,
                    _row_metadata(row, candidate="bvol_relief", asset=asset, factor=factor),
                )
            )
            valid_history.append(current)
        data_day += timedelta(days=1)
    return _events_from_states(
        states,
        candidate="bvol_relief",
        asset=asset,
        start_date=start_date,
        end_date=end_date,
    )


GENERATORS = {
    "curve_carry": generate_curve_carry_signals,
    "bvol_relief": generate_bvol_relief_signals,
}


def load_normalized_rows(root: Path, candidate: str, asset: str) -> pd.DataFrame:
    kind = "delivery_curve" if candidate == "curve_carry" else "bvol"
    directory = root / kind / asset
    paths = sorted(directory.rglob("*.parquet")) if directory.exists() else []
    if not paths:
        raise FileNotFoundError(f"no normalized snapshots found under {directory}")
    return pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=sorted(GENERATORS), required=True)
    parser.add_argument(
        "--asset",
        choices=ASSETS,
        help="generate one isolated asset sleeve; omit only for a combined two-asset store",
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--signal-db", type=Path)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("data/research-v5/normalized"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.dry_run and args.signal_db is None:
        raise SystemExit("--signal-db is required unless --dry-run is used")
    events: list[SignalEvent] = []
    selected_assets = (args.asset,) if args.asset else ASSETS
    for asset in selected_assets:
        frame = load_normalized_rows(args.input_root, args.candidate, asset)
        events.extend(
            GENERATORS[args.candidate](
                frame,
                asset=asset,
                start_date=args.start_date,
                end_date=args.end_date,
            )
        )
    events.sort(key=lambda event: (event.ts_event, event.symbol, event.signal_id))
    source, model_version = STRATEGY_IDENTITIES[args.candidate]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "candidate": args.candidate,
                    "source": source,
                    "model_version": model_version,
                    "assets": list(selected_assets),
                    "features_hash": candidate_features_hash(args.candidate),
                    "signal_count": len(events),
                    "signals": [event.model_dump(mode="json") for event in events[:10]],
                    "signal_store_written": False,
                },
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 0
    written, duplicates = SignalStore(args.signal_db).write_many(events)
    print(
        json.dumps(
            {
                "candidate": args.candidate,
                "source": source,
                "model_version": model_version,
                "assets": list(selected_assets),
                "features_hash": candidate_features_hash(args.candidate),
                "generated": len(events),
                "written": written,
                "duplicates": duplicates,
                "signal_db": str(args.signal_db),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

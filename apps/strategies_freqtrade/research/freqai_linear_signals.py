"""FreqAI-family linear momentum `SignalEvent v1` exporter.

Phase 2 model-driven smoke path. Reads OHLCV bars from a NautilusTrader
`ParquetDataCatalog`, fits a deterministic ridge-linear model on historical
bar features, and exports out-of-sample predictions as `SignalEvent`s.

This module intentionally does not import freqtrade or FreqAI runtime code yet:
ADR-005 classifies `freqai_*` as FreqAI / classic ML model outputs, and this
file is the first lightweight classic-ML export that exercises the same bridge
contract before the full FreqAI training loop is wired up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore

DEFAULT_SOURCE = "freqai_linear_v1"
DEFAULT_MODEL_VERSION = "linear-mom-train20240105"

FEATURE_COLUMNS: tuple[str, ...] = (
    "ret_1",
    "ret_5",
    "ret_15",
    "ema_5_20",
    "volatility_15",
    "volume_z_20",
)


@dataclass(frozen=True)
class LinearFreqaiParams:
    horizon_bars: int = 15
    min_train_rows: int = 1440
    emit_every_bars: int = 15
    prediction_threshold: float = 0.00035
    score_scale: float = 0.002
    confidence_scale: float = 0.002
    ridge_alpha: float = 0.0001
    ttl_seconds: int = 900

    def __post_init__(self) -> None:
        if self.horizon_bars <= 0:
            raise ValueError(f"horizon_bars must be positive, got {self.horizon_bars}")
        if self.min_train_rows <= len(FEATURE_COLUMNS):
            raise ValueError(
                f"min_train_rows must be > {len(FEATURE_COLUMNS)}, "
                f"got {self.min_train_rows}"
            )
        if self.emit_every_bars <= 0:
            raise ValueError(
                f"emit_every_bars must be positive, got {self.emit_every_bars}"
            )
        if self.prediction_threshold < 0.0:
            raise ValueError(
                f"prediction_threshold must be >= 0, got {self.prediction_threshold}"
            )
        if self.score_scale <= 0.0:
            raise ValueError(f"score_scale must be positive, got {self.score_scale}")
        if self.confidence_scale <= self.prediction_threshold:
            raise ValueError(
                "confidence_scale must be greater than prediction_threshold, "
                f"got confidence_scale={self.confidence_scale} "
                f"threshold={self.prediction_threshold}"
            )
        if self.ridge_alpha < 0.0:
            raise ValueError(f"ridge_alpha must be >= 0, got {self.ridge_alpha}")
        if self.ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {self.ttl_seconds}")


@dataclass(frozen=True)
class LinearModel:
    coefficients: tuple[float, ...]
    feature_means: tuple[float, ...]
    feature_stds: tuple[float, ...]
    train_rows: int
    train_start_ns: int
    train_until_ns: int
    features_hash: str


def generate_freqai_linear_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    train_until_ns: int,
    horizon: str = "15m",
    params: LinearFreqaiParams | None = None,
    source: str = DEFAULT_SOURCE,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[SignalEvent]:
    """Fit a deterministic linear model and export post-train predictions.

    Training rows are limited to `ts_event <= train_until_ns`. Signals are only
    emitted for rows after that boundary, which keeps this baseline
    out-of-sample on the existing 7-day BTCUSDT fixture.
    """
    cfg = params or LinearFreqaiParams()
    df = _normalize_bar_frame(bars)
    if df.empty:
        return []

    features = _build_feature_frame(df, cfg)
    model = _fit_linear_model(features, train_until_ns=train_until_ns, params=cfg)
    predictions = _predict(features, model)

    signals: list[SignalEvent] = []
    predictable = features.loc[features["ts_event"] > train_until_ns].copy()
    predictable["prediction"] = predictions.loc[predictable.index]
    predictable = predictable.dropna(subset=["prediction", *FEATURE_COLUMNS])

    for row_number, row in predictable.iterrows():
        if int(row_number) % cfg.emit_every_bars != 0:
            continue
        prediction = float(row["prediction"])
        if abs(prediction) < cfg.prediction_threshold:
            continue

        side = "buy" if prediction > 0.0 else "sell"
        score = _clamp(prediction / cfg.score_scale, -1.0, 1.0)
        confidence = _confidence_from_prediction(prediction, cfg)
        ts_event = int(row["ts_event"])
        signal_id = _make_signal_id(
            source=source,
            model_version=model_version,
            symbol=symbol,
            venue=venue,
            ts_event_ns=ts_event,
            side=side,
        )
        signals.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "venue": venue,
                    "ts_event": ts_event,
                    "horizon": horizon,
                    "side": side,
                    "score": score,
                    "confidence": confidence,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": model.features_hash,
                    "metadata": {
                        "algorithm": "ridge_linear_momentum",
                        "prediction": round(prediction, 10),
                        "prediction_threshold": cfg.prediction_threshold,
                        "horizon_bars": cfg.horizon_bars,
                        "emit_every_bars": cfg.emit_every_bars,
                        "train_rows": model.train_rows,
                        "train_start": _ns_to_iso(model.train_start_ns),
                        "train_until": _ns_to_iso(model.train_until_ns),
                    },
                }
            )
        )
    return signals


def _normalize_bar_frame(bars: pd.DataFrame) -> pd.DataFrame:
    if "ts_event" in bars.columns:
        df = bars.copy()
    elif pd.api.types.is_datetime64_any_dtype(bars.index):
        df = bars.reset_index()
        df = df.rename(columns={bars.index.name or "index": "ts_event"})
    else:
        raise ValueError("bars must have a 'ts_event' column or a DatetimeIndex")

    if (
        pd.api.types.is_datetime64_any_dtype(df["ts_event"])
        or df["ts_event"].dtype == "object"
    ):
        df["ts_event"] = pd.to_datetime(
            df["ts_event"], utc=True, errors="coerce"
        ).astype("int64")

    missing = [c for c in ("close", "volume") if c not in df.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {missing}")

    df = df.sort_values("ts_event", kind="mergesort").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="raise").astype(float)
    df["volume"] = pd.to_numeric(df["volume"], errors="raise").astype(float)
    return df


def _build_feature_frame(
    bars: pd.DataFrame,
    params: LinearFreqaiParams,
) -> pd.DataFrame:
    close = bars["close"].astype(float)
    volume = bars["volume"].astype(float)
    returns = close.pct_change()

    features = pd.DataFrame(
        {
            "ts_event": bars["ts_event"].astype("int64"),
            "ret_1": close.pct_change(1),
            "ret_5": close.pct_change(5),
            "ret_15": close.pct_change(15),
            "ema_5_20": (
                close.ewm(span=5, adjust=False).mean()
                - close.ewm(span=20, adjust=False).mean()
            )
            / close,
            "volatility_15": returns.rolling(15, min_periods=15).std(),
            "volume_z_20": volume / volume.rolling(20, min_periods=20).mean() - 1.0,
            "target": close.shift(-params.horizon_bars) / close - 1.0,
        },
        index=bars.index,
    )
    return features


def _fit_linear_model(
    features: pd.DataFrame,
    *,
    train_until_ns: int,
    params: LinearFreqaiParams,
) -> LinearModel:
    train = features.loc[features["ts_event"] <= train_until_ns].dropna(
        subset=[*FEATURE_COLUMNS, "target"]
    )
    if len(train) < params.min_train_rows:
        raise ValueError(
            f"not enough training rows before train_until_ns={train_until_ns}: "
            f"need {params.min_train_rows}, got {len(train)}"
        )

    means = train.loc[:, FEATURE_COLUMNS].mean()
    stds = train.loc[:, FEATURE_COLUMNS].std(ddof=0).replace(0.0, 1.0)
    x = ((train.loc[:, FEATURE_COLUMNS] - means) / stds).to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(x)), x])
    y = train["target"].to_numpy(dtype=float)

    penalty = np.eye(x.shape[1]) * params.ridge_alpha
    penalty[0, 0] = 0.0
    lhs = x.T @ x + penalty
    rhs = x.T @ y
    try:
        coef = np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:
        coef = np.linalg.lstsq(lhs, rhs, rcond=None)[0]

    train_start_ns = int(train["ts_event"].iloc[0])
    model = LinearModel(
        coefficients=tuple(float(v) for v in coef),
        feature_means=tuple(float(v) for v in means.to_numpy()),
        feature_stds=tuple(float(v) for v in stds.to_numpy()),
        train_rows=len(train),
        train_start_ns=train_start_ns,
        train_until_ns=train_until_ns,
        features_hash="",
    )
    return LinearModel(
        coefficients=model.coefficients,
        feature_means=model.feature_means,
        feature_stds=model.feature_stds,
        train_rows=model.train_rows,
        train_start_ns=model.train_start_ns,
        train_until_ns=model.train_until_ns,
        features_hash=_features_hash(model, params),
    )


def _predict(features: pd.DataFrame, model: LinearModel) -> pd.Series:
    frame = features.loc[:, FEATURE_COLUMNS].copy()
    means = pd.Series(model.feature_means, index=FEATURE_COLUMNS)
    stds = pd.Series(model.feature_stds, index=FEATURE_COLUMNS).replace(0.0, 1.0)
    x = ((frame - means) / stds).to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(x)), x])
    pred = x @ np.asarray(model.coefficients, dtype=float)
    return pd.Series(pred, index=features.index)


def _features_hash(model: LinearModel, params: LinearFreqaiParams) -> str:
    payload: dict[str, Any] = {
        "feature_columns": FEATURE_COLUMNS,
        "params": asdict(params),
        "coefficients": [round(v, 16) for v in model.coefficients],
        "feature_means": [round(v, 16) for v in model.feature_means],
        "feature_stds": [round(v, 16) for v in model.feature_stds],
        "train_rows": model.train_rows,
        "train_start_ns": model.train_start_ns,
        "train_until_ns": model.train_until_ns,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def _confidence_from_prediction(
    prediction: float,
    params: LinearFreqaiParams,
) -> float:
    margin = abs(prediction) - params.prediction_threshold
    span = params.confidence_scale - params.prediction_threshold
    return _clamp(0.5 + 0.5 * (margin / span), 0.5, 1.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, value)))


def _make_signal_id(
    *,
    source: str,
    model_version: str,
    symbol: str,
    venue: str,
    ts_event_ns: int,
    side: str,
) -> str:
    return f"{source}:{model_version}:{symbol}:{venue}:{ts_event_ns}:{side}"


def _load_bars_from_catalog(catalog_path: Path, bar_type: str) -> pd.DataFrame:
    from nautilus_trader.model.data import BarType
    from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    bars = catalog.bars(bar_types=[BarType.from_str(bar_type)])
    if not bars:
        raise SystemExit(f"no bars found in {catalog_path} for bar_type={bar_type}")
    rows = [
        {
            "ts_event": int(b.ts_event),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
        }
        for b in bars
    ]
    return pd.DataFrame(rows)


def _parse_time_ns(value: str) -> int:
    if value.isdigit():
        return int(value)
    return int(pd.Timestamp(value, tz="UTC").value)


def _ns_to_iso(ns: int) -> str:
    return pd.Timestamp(ns, unit="ns", tz="UTC").isoformat()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--train-until", required=True, help="ISO UTC time or ns")
    parser.add_argument("--horizon", default="15m")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--horizon-bars", type=int, default=15)
    parser.add_argument("--min-train-rows", type=int, default=1440)
    parser.add_argument("--emit-every-bars", type=int, default=15)
    parser.add_argument("--prediction-threshold", type=float, default=0.00035)
    parser.add_argument("--score-scale", type=float, default=0.002)
    parser.add_argument("--confidence-scale", type=float, default=0.002)
    parser.add_argument("--ridge-alpha", type=float, default=0.0001)
    parser.add_argument("--ttl-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    params = LinearFreqaiParams(
        horizon_bars=args.horizon_bars,
        min_train_rows=args.min_train_rows,
        emit_every_bars=args.emit_every_bars,
        prediction_threshold=args.prediction_threshold,
        score_scale=args.score_scale,
        confidence_scale=args.confidence_scale,
        ridge_alpha=args.ridge_alpha,
        ttl_seconds=args.ttl_seconds,
    )
    bars = _load_bars_from_catalog(args.catalog_path, args.bar_type)
    events = generate_freqai_linear_signals(
        bars,
        symbol=args.symbol,
        venue=args.venue,
        train_until_ns=_parse_time_ns(args.train_until),
        horizon=args.horizon,
        params=params,
        source=args.source,
        model_version=args.model_version,
    )

    print(f"generated {len(events)} signals from {len(bars)} bars")
    if args.dry_run:
        for ev in events[:10]:
            print(
                f"  {ev.signal_id} side={ev.side} "
                f"score={ev.score:.3f} conf={ev.confidence:.3f}"
            )
        if len(events) > 10:
            print(f"  ... +{len(events) - 10} more")
        return 0

    store = SignalStore(args.signal_store_path)
    written, skipped = store.write_many(events)
    print(f"wrote {written}, skipped {skipped} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_SOURCE",
    "FEATURE_COLUMNS",
    "LinearFreqaiParams",
    "generate_freqai_linear_signals",
    "main",
]

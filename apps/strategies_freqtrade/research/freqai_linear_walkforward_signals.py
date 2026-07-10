"""Monthly walk-forward ridge signals for cost-aware Spot research.

The generator is research-only. It emits long/flat ``SignalEvent v1`` rows,
never orders, and refits at each UTC month boundary using only the preceding
60 calendar days. The final target rows are purged from training so a 15-bar
label can never cross into the prediction month.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    LinearFreqaiParams,
    _build_feature_frame,
    _clamp,
    _confidence_from_prediction,
    _fit_linear_model,
    _load_bars_from_catalog,
    _make_signal_id,
    _normalize_bar_frame,
    _ns_to_iso,
    _predict,
)

DEFAULT_SOURCE = "freqai_linear_walkforward_v1"
DEFAULT_MODEL_VERSION = "ridge-wf60d-cost30bp-v1"
ONE_MINUTE_NS = 60_000_000_000


@dataclass(frozen=True)
class WalkForwardLinearParams:
    training_window_days: int = 60
    horizon_bars: int = 15
    min_train_rows: int = 1440
    emit_every_bars: int = 15
    prediction_threshold: float = 0.003
    score_scale: float = 0.006
    confidence_scale: float = 0.006
    ridge_alpha: float = 0.0001
    ttl_seconds: int = 900

    def __post_init__(self) -> None:
        if self.training_window_days <= 0:
            raise ValueError("training_window_days must be positive")
        # Reuse the canonical linear parameter validation.
        self.linear_params()

    def linear_params(self) -> LinearFreqaiParams:
        return LinearFreqaiParams(
            horizon_bars=self.horizon_bars,
            min_train_rows=self.min_train_rows,
            emit_every_bars=self.emit_every_bars,
            prediction_threshold=self.prediction_threshold,
            score_scale=self.score_scale,
            confidence_scale=self.confidence_scale,
            ridge_alpha=self.ridge_alpha,
            ttl_seconds=self.ttl_seconds,
        )


def generate_walkforward_linear_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    horizon: str = "15m",
    params: WalkForwardLinearParams | None = None,
    source: str = DEFAULT_SOURCE,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[SignalEvent]:
    cfg = params or WalkForwardLinearParams()
    linear = cfg.linear_params()
    df = _normalize_bar_frame(bars)
    if df.empty:
        return []

    features = _build_feature_frame(df, linear)
    first_ts = pd.Timestamp(int(features["ts_event"].min()), unit="ns", tz="UTC")
    last_ts = pd.Timestamp(int(features["ts_event"].max()), unit="ns", tz="UTC")
    earliest = first_ts + pd.Timedelta(days=cfg.training_window_days)
    month_start = pd.Timestamp(
        year=earliest.year,
        month=earliest.month,
        day=1,
        tz="UTC",
    )
    if month_start < earliest:
        month_start += pd.offsets.MonthBegin(1)

    events: list[SignalEvent] = []
    while month_start <= last_ts:
        month_end = month_start + pd.offsets.MonthBegin(1)
        training_start = month_start - pd.Timedelta(days=cfg.training_window_days)
        # Purge label rows whose forward horizon reaches into the prediction month.
        fit_until_ns = int(month_start.value) - cfg.horizon_bars * ONE_MINUTE_NS - 1
        training = features.loc[
            (features["ts_event"] >= int(training_start.value))
            & (features["ts_event"] <= fit_until_ns)
        ]
        model = _fit_linear_model(
            training,
            train_until_ns=fit_until_ns,
            params=linear,
        )
        predictions = _predict(features, model)
        predictable = features.loc[
            (features["ts_event"] >= int(month_start.value))
            & (features["ts_event"] < int(month_end.value))
        ].copy()
        predictable["prediction"] = predictions.loc[predictable.index]
        predictable = predictable.dropna(subset=["prediction"])

        for row_number, row in predictable.iterrows():
            if int(row_number) % cfg.emit_every_bars != 0:
                continue
            prediction = float(row["prediction"])
            if prediction >= cfg.prediction_threshold:
                side = "buy"
            elif prediction <= -cfg.prediction_threshold:
                side = "flat"
            else:
                continue
            ts_event = int(row["ts_event"])
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
                        "horizon": horizon,
                        "side": side,
                        "score": (
                            _clamp(prediction / cfg.score_scale, 0.0, 1.0)
                            if side == "buy"
                            else 0.0
                        ),
                        "confidence": _confidence_from_prediction(prediction, linear),
                        "source": source,
                        "model_version": model_version,
                        "ttl_seconds": cfg.ttl_seconds,
                        "features_hash": model.features_hash,
                        "metadata": {
                            "algorithm": "ridge_linear_momentum_walkforward",
                            "prediction": round(prediction, 10),
                            "prediction_threshold": cfg.prediction_threshold,
                            "training_window_days": cfg.training_window_days,
                            "prediction_month": month_start.strftime("%Y-%m"),
                            "train_rows": model.train_rows,
                            "train_start": _ns_to_iso(model.train_start_ns),
                            "train_until": _ns_to_iso(model.train_until_ns),
                            "horizon_bars": cfg.horizon_bars,
                            "emit_every_bars": cfg.emit_every_bars,
                            "spot_target": "long" if side == "buy" else "flat",
                        },
                    }
                )
            )
        month_start = month_end
    return events


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    bars = _load_bars_from_catalog(args.catalog_path, args.bar_type)
    events = generate_walkforward_linear_signals(
        bars,
        symbol=args.symbol,
        venue=args.venue,
        source=args.source,
        model_version=args.model_version,
    )
    print(f"generated {len(events)} signals from {len(bars)} bars")
    if args.dry_run:
        for event in events[:10]:
            print(
                f"  {event.signal_id} side={event.side} "
                f"score={event.score:.3f} conf={event.confidence:.3f}"
            )
        return 0

    store = SignalStore(args.signal_store_path)
    written, duplicates = store.write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


__all__ = [
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_SOURCE",
    "WalkForwardLinearParams",
    "generate_walkforward_linear_signals",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

"""Export research weights as SignalEvent v1 for learning simulations."""

from __future__ import annotations

import argparse
import importlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import DEFAULT_DB_PATH, SignalStore
from apps.research import data


def weights_to_signals(
    weights: pd.DataFrame,
    *,
    source: str,
    model_version: str,
    start: str,
    end: str,
    emit_weekday: int | None,
    long_only: bool,
    venue: str = "BINANCE",
    horizon: str = "7d",
    ttl_seconds: int = 8 * 86_400,
    confidence: float = 0.75,
) -> list[SignalEvent]:
    """Emit each selected row at the next UTC midnight, including refreshes."""
    events: list[SignalEvent] = []
    for stamp, row in weights.loc[start:end].iterrows():
        if emit_weekday is not None and stamp.weekday() != emit_weekday:
            continue
        for symbol, value in row.items():
            weight = float(value)
            if not math.isfinite(weight):
                raise ValueError(f"Non-finite weight for {symbol} on {stamp.date()}")
            side = "buy" if weight > 0 else "sell" if weight < 0 and not long_only else "flat"
            score = max(-1.0, min(weight, 1.0)) if side != "flat" else 0.0
            events.append(
                SignalEvent(
                    signal_id=f"{source}:{model_version}:{symbol}:{stamp.date().isoformat()}",
                    symbol=symbol,
                    venue=venue,
                    ts_event=(stamp + pd.Timedelta(days=1)).value,
                    horizon=horizon,
                    side=side,
                    score=score,
                    confidence=confidence,
                    source=source,
                    model_version=model_version,
                    ttl_seconds=ttl_seconds,
                    metadata={"weight": weight, "learning_simulation": True},
                )
            )
    return events


def main(argv: list[str] | None = None) -> int:
    """Load cached research data and write an idempotent signal batch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--model-version-suffix", default="")
    parser.add_argument("--signal-store-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--data-root", type=Path, default=data.DATA_ROOT)
    args = parser.parse_args(argv)
    if args.end >= data.BLIND_START:
        parser.error(f"--end reaches the sealed blind starting {data.BLIND_START}")
    if args.start > args.end:
        parser.error("--start must be on or before --end")
    contract = json.loads(args.contract.read_text())
    if args.candidate not in contract["candidates"]:
        parser.error(f"Unknown candidate: {args.candidate}")
    candidate = contract["candidates"][args.candidate]
    params, spec = candidate["params"], contract["data"]
    datasets = spec.get("datasets") or [spec["dataset"]]
    frames = data.load_frames(datasets, spec["symbols"], root=args.data_root)
    module = importlib.import_module(contract["mechanism_module"])
    weights = module.target_weights(frames, args.candidate, params)
    model = candidate["model_version"]
    if args.model_version_suffix:
        model += "-" + args.model_version_suffix
    events = weights_to_signals(
        weights,
        source=candidate["source"],
        model_version=model,
        start=args.start.isoformat(),
        end=args.end.isoformat(),
        emit_weekday=params.get("rebalance_weekday"),
        long_only=args.long_only,
    )
    written, duplicates = SignalStore(args.signal_store_path).write_many(events)
    print(
        json.dumps(
            {
                "written": written,
                "duplicates": duplicates,
                "by_symbol": dict(Counter(event.symbol for event in events)),
                "by_side": dict(Counter(event.side for event in events)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

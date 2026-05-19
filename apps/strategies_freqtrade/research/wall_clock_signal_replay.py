"""Restamp reviewed historical SignalEvents into wall-clock time.

This helper is for ADR-008 testnet canaries that need a small stream of
current-time `SignalEvent v1` rows while the real online FreqAI producer is
not wired yet. It copies existing SignalStore rows, preserves source/model
authorization, records the original lineage in metadata, and writes only back
to SignalStore. It does not import trading, exchange, or network APIs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from apps.bridge.signal_event import Side, SignalEvent
from apps.bridge.store import DEFAULT_DB_PATH, DuplicateSignalError, SignalStore
from apps.bridge.time_utils import ensure_ns
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    DEFAULT_MODEL_VERSION,
    DEFAULT_SOURCE,
)

NS_PER_SECOND = 1_000_000_000
DEFAULT_START_DELAY_SECONDS = 180.0
DEFAULT_INTERVAL_SECONDS = 60.0
DEFAULT_MIN_CONFIDENCE = 0.55


@dataclass(frozen=True)
class WallClockReplayConfig:
    input_store_path: Path = DEFAULT_DB_PATH
    output_store_path: Path = DEFAULT_DB_PATH
    source: str = DEFAULT_SOURCE
    model_version: str = DEFAULT_MODEL_VERSION
    start_ns: int = 0
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    max_signals: int = 1
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    side: Side | None = None
    ttl_seconds: int | None = None
    input_since_ns: int | None = None
    input_until_ns: int | None = None

    def __post_init__(self) -> None:
        ensure_ns(self.start_ns)
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.max_signals <= 0:
            raise ValueError("max_signals must be positive")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        if self.ttl_seconds is not None and self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive when provided")


@dataclass(frozen=True)
class ReplayWriteSummary:
    input_count: int
    eligible_count: int
    generated_count: int
    written_count: int
    skipped_duplicates: int
    first_ts_event: int | None
    last_ts_event: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "input_count": self.input_count,
            "eligible_count": self.eligible_count,
            "generated_count": self.generated_count,
            "written_count": self.written_count,
            "skipped_duplicates": self.skipped_duplicates,
            "first_ts_event": self.first_ts_event,
            "last_ts_event": self.last_ts_event,
        }


def build_wall_clock_replay_events(
    events: list[SignalEvent],
    config: WallClockReplayConfig,
) -> tuple[list[SignalEvent], int]:
    """Return restamped events and the number of eligible source rows."""

    eligible = _eligible_events(events, config)
    selected = eligible[: config.max_signals]
    interval_ns = int(round(config.interval_seconds * NS_PER_SECOND))
    out: list[SignalEvent] = []
    for idx, event in enumerate(selected):
        out.append(
            _restamp_event(
                event,
                new_ts_event=config.start_ns + idx * interval_ns,
                ttl_seconds=config.ttl_seconds,
            )
        )
    return out, len(eligible)


def write_wall_clock_replay(
    config: WallClockReplayConfig,
    *,
    dry_run: bool = False,
) -> tuple[ReplayWriteSummary, list[SignalEvent]]:
    """Build and optionally write restamped SignalEvents to SignalStore."""

    input_store = SignalStore(config.input_store_path)
    source_events = input_store.replay(
        source=config.source,
        model_version=config.model_version,
        since_ns=config.input_since_ns,
        until_ns=config.input_until_ns,
    )
    replay_events, eligible_count = build_wall_clock_replay_events(
        source_events,
        config,
    )

    written = 0
    skipped = 0
    if not dry_run:
        output_store = SignalStore(config.output_store_path)
        for event in replay_events:
            try:
                output_store.write(event)
                written += 1
            except DuplicateSignalError:
                skipped += 1

    first_ts = replay_events[0].ts_event if replay_events else None
    last_ts = replay_events[-1].ts_event if replay_events else None
    summary = ReplayWriteSummary(
        input_count=len(source_events),
        eligible_count=eligible_count,
        generated_count=len(replay_events),
        written_count=written,
        skipped_duplicates=skipped,
        first_ts_event=first_ts,
        last_ts_event=last_ts,
    )
    return summary, replay_events


def _eligible_events(
    events: list[SignalEvent],
    config: WallClockReplayConfig,
) -> list[SignalEvent]:
    filtered = [
        event
        for event in events
        if not _is_wall_clock_replay(event)
        and event.confidence >= config.min_confidence
        and (config.side is None or event.side == config.side)
    ]
    return sorted(filtered, key=lambda event: (event.ts_event, event.signal_id))


def _is_wall_clock_replay(event: SignalEvent) -> bool:
    marker = event.metadata.get("wall_clock_replay")
    return isinstance(marker, dict)


def _restamp_event(
    event: SignalEvent,
    *,
    new_ts_event: int,
    ttl_seconds: int | None,
) -> SignalEvent:
    ensure_ns(new_ts_event)
    original_metadata = dict(event.metadata)
    original_metadata["wall_clock_replay"] = {
        "kind": "historical_signal_restamp",
        "original_signal_id": event.signal_id,
        "original_ts_event": event.ts_event,
        "original_ttl_seconds": event.ttl_seconds,
    }
    return SignalEvent.model_validate(
        {
            **event.model_dump(),
            "signal_id": _replay_signal_id(event, new_ts_event),
            "ts_event": new_ts_event,
            "ttl_seconds": event.ttl_seconds if ttl_seconds is None else ttl_seconds,
            "metadata": original_metadata,
        }
    )


def _replay_signal_id(event: SignalEvent, new_ts_event: int) -> str:
    digest = hashlib.sha256(
        f"{event.signal_id}|{new_ts_event}".encode()
    ).hexdigest()[:12]
    return (
        f"{event.source}:{event.model_version}:wall_clock_replay:"
        f"{event.symbol}:{event.venue}:{new_ts_event}:{event.side}:{digest}"
    )


def _parse_time_ns(value: str) -> int:
    text = value.strip()
    if text.isdigit():
        return ensure_ns(int(text))
    if text.lower() == "now":
        return time.time_ns()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return ensure_ns(int(dt.timestamp() * NS_PER_SECOND))


def _start_ns_from_args(args: argparse.Namespace) -> int:
    if args.start_at is not None:
        return _parse_time_ns(args.start_at)
    return ensure_ns(
        time.time_ns() + int(round(args.start_delay_seconds * NS_PER_SECOND))
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input-store-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-store-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--start-at", help="ISO UTC time, ns, or 'now'.")
    parser.add_argument(
        "--start-delay-seconds",
        type=float,
        default=DEFAULT_START_DELAY_SECONDS,
        help=(
            "When --start-at is omitted, begin this many seconds in the future "
            f"(default: {DEFAULT_START_DELAY_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Spacing between restamped signals (default: {DEFAULT_INTERVAL_SECONDS:g}).",
    )
    parser.add_argument("--max-signals", type=int, default=1)
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    parser.add_argument("--side", choices=("buy", "sell", "flat"))
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        help="Override ttl_seconds on restamped events. Defaults to source TTL.",
    )
    parser.add_argument("--input-since", help="Optional source replay lower bound.")
    parser.add_argument("--input-until", help="Optional source replay upper bound.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    config = WallClockReplayConfig(
        input_store_path=args.input_store_path,
        output_store_path=args.output_store_path,
        source=args.source,
        model_version=args.model_version,
        start_ns=_start_ns_from_args(args),
        interval_seconds=args.interval_seconds,
        max_signals=args.max_signals,
        min_confidence=args.min_confidence,
        side=args.side,
        ttl_seconds=args.ttl_seconds,
        input_since_ns=None if args.input_since is None else _parse_time_ns(args.input_since),
        input_until_ns=None if args.input_until is None else _parse_time_ns(args.input_until),
    )
    summary, events = write_wall_clock_replay(config, dry_run=args.dry_run)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    if args.dry_run:
        for event in events[:10]:
            print(
                f"  {event.signal_id} ts_event={event.ts_event} "
                f"side={event.side} confidence={event.confidence:.3f}"
            )
        if len(events) > 10:
            print(f"  ... +{len(events) - 10} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ReplayWriteSummary",
    "WallClockReplayConfig",
    "build_wall_clock_replay_events",
    "main",
    "write_wall_clock_replay",
]

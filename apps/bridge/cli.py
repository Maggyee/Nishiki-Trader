from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import DEFAULT_DB_PATH, DuplicateSignalError, SignalStore
from apps.bridge.validators import (
    Authorization,
    ValidationError,
    is_expired,
    validate,
)


def _load_authorization(args: argparse.Namespace) -> Authorization:
    sources = frozenset(s for s in (args.allowed_sources or "").split(",") if s)
    models = frozenset(m for m in (args.allowed_models or "").split(",") if m)
    return Authorization(allowed_sources=sources, allowed_model_versions=models)


def _read_events(path: Path) -> list[SignalEvent]:
    text = path.read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        items = json.loads(text)
        return [SignalEvent.model_validate(item) for item in items]
    events: list[SignalEvent] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(SignalEvent.model_validate_json(line))
        except Exception as exc:
            raise SystemExit(f"{path}:{line_no}: invalid SignalEvent: {exc}") from exc
    return events


def _cmd_write(args: argparse.Namespace) -> int:
    store = SignalStore(args.db)
    events = _read_events(Path(args.input))
    auth = _load_authorization(args) if _enforce_consumer_policy(args) else None
    now_ns = time.time_ns() if args.now_ns is None else args.now_ns
    accepted = 0
    duplicates = 0
    rejected = 0
    for event in events:
        if auth is not None:
            try:
                validate(
                    event,
                    auth,
                    now_ns=now_ns,
                    venue=args.venue,
                )
            except ValidationError as exc:
                rejected += 1
                print(f"{event.signal_id}: REJECT {exc.code}: {exc}")
                continue
        try:
            store.write(event)
            accepted += 1
        except DuplicateSignalError:
            duplicates += 1
    print(
        f"wrote {accepted} accepted, {duplicates} duplicates (skipped), "
        f"{rejected} rejected"
    )
    return 1 if rejected else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    auth = _load_authorization(args)
    events = _read_events(Path(args.input))
    now_ns = time.time_ns() if args.now_ns is None else args.now_ns
    failures = 0
    for event in events:
        try:
            validate(event, auth, now_ns=now_ns, venue=args.venue or None)
        except ValidationError as exc:
            failures += 1
            print(f"{event.signal_id}: REJECT {exc.code}: {exc}")
        else:
            print(f"{event.signal_id}: OK")
    print(f"validated {len(events) - failures}/{len(events)}")
    return 1 if failures else 0


def _cmd_replay(args: argparse.Namespace) -> int:
    store = SignalStore(args.db)
    events = store.replay(
        source=args.source,
        model_version=args.model_version,
        since_ns=args.since_ns,
        until_ns=args.until_ns,
    )
    skip_expired = not args.include_expired
    for event in events:
        if skip_expired and is_expired(event, now_ns=args.now_ns):
            continue
        sys.stdout.write(event.model_dump_json() + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridge", description="SignalEvent v1 CLI")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="Write SignalEvents from a JSON/JSONL file to SQLite")
    write.add_argument("input", help="Path to JSON array or JSONL file")
    write.add_argument(
        "--enforce-consumer-policy",
        action="store_true",
        help=(
            "Apply ADR-002 consumer checks before persisting. Requires "
            "--allowed-sources and --allowed-models."
        ),
    )
    write.add_argument(
        "--allowed-sources",
        default="",
        help="Comma-separated source allowlist used with --enforce-consumer-policy",
    )
    write.add_argument(
        "--allowed-models",
        default="",
        help="Comma-separated model_version allowlist used with --enforce-consumer-policy",
    )
    write.add_argument(
        "--venue",
        default="BINANCE",
        help="Expected venue when --enforce-consumer-policy is set (default: BINANCE)",
    )
    write.add_argument(
        "--now-ns",
        type=int,
        default=None,
        help="Override current time for ttl checks during write validation",
    )
    write.set_defaults(func=_cmd_write)

    validate_p = sub.add_parser("validate", help="Validate a JSON/JSONL file without writing")
    validate_p.add_argument("input", help="Path to JSON array or JSONL file")
    validate_p.add_argument("--allowed-sources", default="", help="Comma-separated source allowlist")
    validate_p.add_argument(
        "--allowed-models", default="", help="Comma-separated model_version allowlist"
    )
    validate_p.add_argument(
        "--venue",
        default="BINANCE",
        help="Expected consumer venue (default: BINANCE)",
    )
    validate_p.add_argument(
        "--now-ns",
        type=int,
        default=None,
        help="Override current time for ttl checks",
    )
    validate_p.set_defaults(func=_cmd_validate)

    replay = sub.add_parser("replay", help="Replay stored SignalEvents as JSONL on stdout")
    replay.add_argument("--source", default=None)
    replay.add_argument("--model-version", default=None)
    replay.add_argument("--since-ns", type=int, default=None)
    replay.add_argument("--until-ns", type=int, default=None)
    replay.add_argument("--include-expired", action="store_true")
    replay.add_argument("--now-ns", type=int, default=None, help="Override current time for ttl check")
    replay.set_defaults(func=_cmd_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())



def _enforce_consumer_policy(args: argparse.Namespace) -> bool:
    if not args.enforce_consumer_policy:
        return False
    if not args.allowed_sources.strip() or not args.allowed_models.strip():
        raise SystemExit(
            "bridge write: --enforce-consumer-policy requires "
            "--allowed-sources and --allowed-models"
        )
    return True

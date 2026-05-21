"""One-shot SQLite SignalStore -> PostgresSignalStore mirror.

`PostgresSignalStore` (added 2026-05-21) has the same surface as the
SQLite `SignalStore`. The bridge default backend remains SQLite; this
helper copies all existing rows into the Postgres `signal_events`
hypertable so Grafana dashboards (`signals-overview` and friends) can
query them through the read-only `postgres-trader` datasource.

Idempotent: rows already present in Postgres are skipped via
`DuplicateSignalError`. The bridge SQLite path is not modified.

Re-run after each canary / paper run if you want fresh rows in Postgres
until ADR-010 / a real bridge-side mirroring decision lands.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import (
    DEFAULT_DB_PATH,
    DuplicateSignalError,
    PostgresConnInfo,
    PostgresSignalStore,
    SignalStore,
)


def _coerce_event(row: Any) -> SignalEvent:
    payload = json.loads(row["raw_json"])
    return SignalEvent.model_validate(payload)


def sync(
    *,
    sqlite_path: Path,
    pg_conn: PostgresConnInfo,
    dry_run: bool,
    sources: list[str] | None,
    since_ns: int | None,
) -> dict[str, int]:
    src = SignalStore(sqlite_path)
    dst = PostgresSignalStore(pg_conn)
    counts = {
        "read": 0,
        "written": 0,
        "skipped_duplicate": 0,
        "skipped_filter": 0,
        "errored": 0,
    }
    with src._connect() as conn:
        cur = conn.execute(
            "SELECT raw_json, created_at, source, ts_event "
            "FROM signals ORDER BY ts_event ASC"
        )
        for row in cur:
            counts["read"] += 1
            if sources is not None and row["source"] not in sources:
                counts["skipped_filter"] += 1
                continue
            if since_ns is not None and row["ts_event"] < since_ns:
                counts["skipped_filter"] += 1
                continue
            event = _coerce_event(row)
            if dry_run:
                continue
            try:
                dst.write(event, now_ns=row["created_at"])
                counts["written"] += 1
            except DuplicateSignalError:
                counts["skipped_duplicate"] += 1
            except Exception as exc:
                counts["errored"] += 1
                print(
                    f"ERROR writing {event.signal_id}: {exc!r}",
                    file=sys.stderr,
                )
    return counts


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy SignalStore (SQLite) rows into PostgresSignalStore "
            "(`signal_events` hypertable). Idempotent."
        )
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Source SQLite path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--pg-host",
        default="127.0.0.1",
        help="Postgres host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--pg-port",
        type=int,
        default=5433,
        help="Postgres host port (default: 5433)",
    )
    parser.add_argument(
        "--pg-user",
        default="trader",
        help="Postgres user (default: trader; bridge dev role)",
    )
    parser.add_argument(
        "--pg-password",
        default="trader_local_pg",
        help="Postgres password (default loopback dev only)",
    )
    parser.add_argument(
        "--pg-dbname",
        default="trader",
        help="Postgres database (default: trader)",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Restrict to one source (repeatable). Default: all.",
    )
    parser.add_argument(
        "--since-ns",
        type=int,
        default=None,
        help="Only sync rows with ts_event >= this nanosecond timestamp.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read SQLite + filter only; do not write to Postgres.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    pg_conn = PostgresConnInfo(
        host=args.pg_host,
        port=args.pg_port,
        user=args.pg_user,
        password=args.pg_password,
        dbname=args.pg_dbname,
    )
    counts = sync(
        sqlite_path=args.sqlite_path,
        pg_conn=pg_conn,
        dry_run=args.dry_run,
        sources=args.sources,
        since_ns=args.since_ns,
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0 if counts["errored"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the credential-free Research Protocol v2 paired snapshot collection."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import tempfile
import urllib.error
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_v2_snapshot import collect_snapshot, verify_snapshot
from apps.ops.research_v2_snapshot_review import MIN_CONTIGUOUS_DAYS, review_snapshots

SCHEMA_VERSION = "research.snapshot.daily.v1"
LEDGER_SCHEMA_VERSION = "research.snapshot.ledger.v1"
REQUIRED_KINDS = ("options", "basis")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

Collector = Callable[..., tuple[Path, dict[str, Any]]]


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} must be a JSON object")
        rows.append(row)
    return rows


def _validate_git_sha(git_sha: str) -> None:
    if not _GIT_SHA_RE.fullmatch(git_sha):
        raise ValueError("TRADER_GIT_SHA must be exactly 40 lowercase hexadecimal characters")


def _ledger_path(data_dir: Path) -> Path:
    return data_dir / "qualification-ledger.jsonl"


def _snapshot_path(data_dir: Path, row: dict[str, Any]) -> Path:
    relative = Path(str(row.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("ledger snapshot path must be a non-empty relative path")
    path = data_dir / relative
    if not path.is_relative_to(data_dir):
        raise ValueError("ledger snapshot path escapes the data directory")
    return path


def _validate_ledger(data_dir: Path, git_sha: str) -> list[dict[str, Any]]:
    rows = _read_jsonl(_ledger_path(data_dir))
    identities: set[tuple[str, str, str]] = set()
    paths: set[str] = set()
    hashes: set[str] = set()
    by_attempt_day: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        if row.get("schema_version") != LEDGER_SCHEMA_VERSION:
            raise ValueError("ledger schema version is invalid")
        if row.get("git_sha") != git_sha:
            raise ValueError("ledger git SHA differs from the locked collector image")
        attempt_id = str(row.get("attempt_id", ""))
        day = str(row.get("retrieved_day", ""))
        kind = str(row.get("kind", ""))
        if kind not in REQUIRED_KINDS or not attempt_id:
            raise ValueError("ledger attempt or kind is invalid")
        date.fromisoformat(day)
        identity = (attempt_id, day, kind)
        if identity in identities:
            raise ValueError(f"duplicate ledger kind/day in {attempt_id}: {day} {kind}")
        identities.add(identity)
        if str(row.get("path")) in paths or str(row.get("snapshot_sha256")) in hashes:
            raise ValueError("ledger snapshot path or hash is duplicated")
        paths.add(str(row["path"]))
        hashes.add(str(row["snapshot_sha256"]))
        review = verify_snapshot(_snapshot_path(data_dir, row))
        if review["kind"] != kind or str(review["retrieved_at"])[:10] != day:
            raise ValueError("ledger identity differs from the verified snapshot")
        if review["snapshot_sha256"] != row.get("snapshot_sha256"):
            raise ValueError("ledger snapshot hash differs from the verified snapshot")
        by_attempt_day.setdefault((attempt_id, day), set()).add(kind)
    for (attempt_id, day), kinds in by_attempt_day.items():
        if kinds != set(REQUIRED_KINDS):
            raise ValueError(f"unpaired ledger day in {attempt_id}: {day}")
    return rows


def _attempt_id(day: date, attempts: list[dict[str, Any]]) -> str:
    prefix = f"attempt-{day.strftime('%Y%m%d')}-"
    sequence = sum(str(row.get("attempt_id", "")).startswith(prefix) for row in attempts) + 1
    return f"{prefix}{sequence:03d}"


def _start_attempt(data_dir: Path, git_sha: str, day: date, now: datetime) -> dict[str, Any]:
    attempts_path = data_dir / "attempts.jsonl"
    attempts = _read_jsonl(attempts_path)
    attempt_id = _attempt_id(day, attempts)
    _append_jsonl(
        attempts_path,
        {
            "schema_version": SCHEMA_VERSION,
            "event": "attempt_started",
            "attempt_id": attempt_id,
            "git_sha": git_sha,
            "day": day.isoformat(),
            "recorded_at": _utc_text(now),
            "reason": "fresh_cloud_collection" if not attempts else "restart_after_operational_gap",
        },
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "collecting",
        "git_sha": git_sha,
        "attempt_id": attempt_id,
        "attempt_started_on": day.isoformat(),
        "last_paired_date": None,
        "paired_day_count": 0,
        "updated_at": _utc_text(now),
    }


def _close_for_gap(data_dir: Path, state: dict[str, Any], day: date, now: datetime) -> None:
    _append_jsonl(
        data_dir / "attempts.jsonl",
        {
            "schema_version": SCHEMA_VERSION,
            "event": "attempt_closed",
            "attempt_id": state["attempt_id"],
            "git_sha": state["git_sha"],
            "day": day.isoformat(),
            "recorded_at": _utc_text(now),
            "reason": "failed_operational_gap",
            "paired_day_count": state["paired_day_count"],
        },
    )


def _pending_by_kind(pending_dir: Path, day: date) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not pending_dir.exists():
        return found
    for path in sorted(pending_dir.glob("*.json")):
        if path.name == "transaction.json":
            continue
        review = verify_snapshot(path)
        kind = str(review["kind"])
        if kind not in REQUIRED_KINDS or str(review["retrieved_at"])[:10] != day.isoformat():
            raise ValueError("pending snapshot has the wrong kind or UTC day")
        if kind in found:
            raise ValueError(f"duplicate pending snapshot for {kind} on {day}")
        found[kind] = path
    return found


def _commit_pair(
    data_dir: Path,
    pending_dir: Path,
    attempt_id: str,
    git_sha: str,
    day: date,
    now: datetime,
) -> None:
    snapshots = _pending_by_kind(pending_dir, day)
    if set(snapshots) != set(REQUIRED_KINDS):
        raise ValueError("cannot commit an incomplete snapshot pair")
    records: list[dict[str, Any]] = []
    for kind in REQUIRED_KINDS:
        review = verify_snapshot(snapshots[kind])
        destination = Path("raw") / snapshots[kind].name
        records.append(
            {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "git_sha": git_sha,
                "retrieved_day": day.isoformat(),
                "kind": kind,
                "path": str(destination),
                "snapshot_sha256": review["snapshot_sha256"],
                "recorded_at": _utc_text(now),
            }
        )
    transaction = {
        "schema_version": SCHEMA_VERSION,
        "status": "prepared",
        "attempt_id": attempt_id,
        "git_sha": git_sha,
        "retrieved_day": day.isoformat(),
        "records": records,
    }
    transaction_path = pending_dir / "transaction.json"
    _atomic_json(transaction_path, transaction)
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        source = snapshots[str(record["kind"])]
        destination = data_dir / str(record["path"])
        if destination.exists():
            existing = verify_snapshot(destination)
            if existing["snapshot_sha256"] != record["snapshot_sha256"]:
                raise ValueError("transaction destination conflicts with an existing snapshot")
            source.unlink(missing_ok=True)
        else:
            source.replace(destination)
    existing_rows = _read_jsonl(_ledger_path(data_dir))
    existing_ids = {
        (str(row.get("attempt_id")), str(row.get("retrieved_day")), str(row.get("kind")))
        for row in existing_rows
    }
    for record in records:
        identity = (attempt_id, day.isoformat(), str(record["kind"]))
        if identity not in existing_ids:
            _append_jsonl(_ledger_path(data_dir), record)
    transaction["status"] = "committed"
    transaction["committed_at"] = _utc_text(now)
    archive = data_dir / "transactions" / f"{attempt_id}-{day.isoformat()}.json"
    _atomic_json(archive, transaction)
    transaction_path.unlink()


def _recover_transactions(data_dir: Path, git_sha: str, now: datetime) -> None:
    pending_root = data_dir / "pending"
    if not pending_root.exists():
        return
    for transaction_path in sorted(pending_root.glob("*/transaction.json")):
        transaction = _read_json(transaction_path)
        if transaction.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("pending transaction schema is invalid")
        if transaction.get("git_sha") != git_sha or transaction.get("status") != "prepared":
            raise ValueError("pending transaction identity is invalid")
        day = date.fromisoformat(str(transaction["retrieved_day"]))
        records = transaction.get("records")
        if not isinstance(records, list) or len(records) != len(REQUIRED_KINDS):
            raise ValueError("pending transaction records are invalid")
        pending_dir = transaction_path.parent
        # If a crash happened after a move, put the verified file back long enough
        # to reuse the single pair-commit path.
        for record in records:
            kind = str(record.get("kind"))
            final_path = _snapshot_path(data_dir, record)
            candidates = list(pending_dir.glob(f"{kind}-*.json"))
            if not candidates and final_path.exists():
                final_path.replace(pending_dir / final_path.name)
        _commit_pair(
            data_dir,
            pending_dir,
            str(transaction["attempt_id"]),
            git_sha,
            day,
            now,
        )


def _attempt_rows(rows: list[dict[str, Any]], attempt_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("attempt_id") == attempt_id]


def _write_review(data_dir: Path, state: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    current = _attempt_rows(rows, str(state["attempt_id"]))
    if not current:
        return {
            "schema_version": "research.snapshot.coverage.v1",
            "status": "collecting_insufficient_days",
            "minimum_contiguous_days": MIN_CONTIGUOUS_DAYS,
            "paired_day_count": 0,
            "paired_dates": [],
            "blockers": [],
            "recommendation": "continue_daily_snapshot_collection",
            "boundaries": {
                "prices_summarized": False,
                "returns_loaded": False,
                "pnl_computed": False,
                "signals_generated": False,
                "signal_store_written": False,
                "nautilus_run": False,
                "source_policy_mutated": False,
            },
        }
    review = review_snapshots([_snapshot_path(data_dir, row) for row in current])
    _atomic_json(data_dir / "latest-review.json", review)
    return review


def preflight(data_dir: Path, git_sha: str) -> dict[str, Any]:
    """Validate configuration and existing evidence without network or writes."""
    _validate_git_sha(git_sha)
    if data_dir.exists() and not data_dir.is_dir():
        raise ValueError("data directory path exists but is not a directory")
    existing_rows = _validate_ledger(data_dir, git_sha) if data_dir.exists() else []
    state_path = data_dir / "state.json"
    if state_path.exists() and _read_json(state_path).get("git_sha") != git_sha:
        raise ValueError("state git SHA differs from the locked collector image")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "preflight_pass",
        "git_sha": git_sha,
        "data_dir": str(data_dir),
        "existing_ledger_rows": len(existing_rows),
        "network_accessed": False,
        "data_written": False,
    }


def review_only(data_dir: Path, git_sha: str) -> dict[str, Any]:
    """Verify and summarize existing evidence without network or writes."""
    _validate_git_sha(git_sha)
    state = _read_json(data_dir / "state.json")
    if state.get("git_sha") != git_sha:
        raise ValueError("state git SHA differs from the locked collector image")
    rows = _validate_ledger(data_dir, git_sha)
    current = _attempt_rows(rows, str(state["attempt_id"]))
    if not current:
        raise ValueError("current attempt has no committed snapshot pair")
    review = review_snapshots([_snapshot_path(data_dir, row) for row in current])
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "review_only",
        "git_sha": git_sha,
        "attempt_id": state["attempt_id"],
        "review": review,
        "network_accessed": False,
        "data_written": False,
    }


def run_daily(
    data_dir: Path,
    git_sha: str,
    *,
    now: datetime | None = None,
    collector: Collector = collect_snapshot,
) -> dict[str, Any]:
    """Collect at most one verified options/basis pair for the current UTC day."""
    _validate_git_sha(git_sha)
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    current_day = current_time.date()
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / ".collector.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another collector process holds the data-directory lock") from exc

        _recover_transactions(data_dir, git_sha, current_time)
        rows = _validate_ledger(data_dir, git_sha)
        state_path = data_dir / "state.json"
        if state_path.exists():
            state = _read_json(state_path)
            if state.get("schema_version") != SCHEMA_VERSION or state.get("git_sha") != git_sha:
                raise ValueError("collector state schema or git SHA is invalid")
        elif rows:
            raise ValueError("ledger exists without collector state")
        else:
            state = _start_attempt(data_dir, git_sha, current_day, current_time)
            _atomic_json(state_path, state)

        current_rows = _attempt_rows(rows, str(state["attempt_id"]))
        if current_rows:
            recovered_review = _write_review(data_dir, state, rows)
            recovered_count = int(recovered_review["paired_day_count"])
            recovered_dates = list(recovered_review["paired_dates"])
            if recovered_count > MIN_CONTIGUOUS_DAYS:
                raise ValueError("collector exceeded the locked seven-day target")
            claimed_count = int(state.get("paired_day_count", 0))
            claimed_last = state.get("last_paired_date")
            if claimed_count > recovered_count or (
                claimed_last is not None and claimed_last not in recovered_dates
            ):
                raise ValueError("collector state is ahead of or conflicts with the verified ledger")
            if claimed_count != recovered_count or claimed_last != recovered_dates[-1]:
                state.update(
                    {
                        "last_paired_date": recovered_dates[-1],
                        "paired_day_count": recovered_count,
                        "updated_at": _utc_text(current_time),
                    }
                )
                _atomic_json(state_path, state)
            if recovered_count == MIN_CONTIGUOUS_DAYS and not (data_dir / "COMPLETE").exists():
                if recovered_review["status"] != "qualification_coverage_pass":
                    raise ValueError("recovered seven-day ledger did not pass coverage review")
                state["status"] = "complete"
                _atomic_json(state_path, state)
                _atomic_json(
                    data_dir / "COMPLETE",
                    {
                        "schema_version": SCHEMA_VERSION,
                        "status": "complete",
                        "git_sha": git_sha,
                        "attempt_id": state["attempt_id"],
                        "paired_day_count": recovered_count,
                        "paired_dates": recovered_dates,
                        "completed_at": _utc_text(current_time),
                        "recommendation": recovered_review["recommendation"],
                        "boundaries": recovered_review["boundaries"],
                    },
                )

        if (data_dir / "COMPLETE").exists():
            complete = _read_json(data_dir / "COMPLETE")
            if state.get("status") != "complete" or complete.get("git_sha") != git_sha:
                raise ValueError("completion marker conflicts with collector state")
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "already_complete",
                "git_sha": git_sha,
                "attempt_id": state["attempt_id"],
                "paired_day_count": state["paired_day_count"],
                "network_accessed": False,
            }

        last_text = state.get("last_paired_date")
        started_day = date.fromisoformat(str(state["attempt_started_on"]))
        if not last_text and current_day > started_day:
            _close_for_gap(data_dir, state, current_day, current_time)
            state = _start_attempt(data_dir, git_sha, current_day, current_time)
            _atomic_json(state_path, state)
            rows = _validate_ledger(data_dir, git_sha)
        if last_text:
            last_day = date.fromisoformat(str(last_text))
            if current_day < last_day:
                raise ValueError("server UTC date moved backwards")
            if current_day > last_day + timedelta(days=1):
                _close_for_gap(data_dir, state, current_day, current_time)
                state = _start_attempt(data_dir, git_sha, current_day, current_time)
                _atomic_json(state_path, state)
                rows = _validate_ledger(data_dir, git_sha)
            elif current_day == last_day:
                review = _write_review(data_dir, state, rows)
                return {
                    "schema_version": SCHEMA_VERSION,
                    "status": "already_collected_today",
                    "git_sha": git_sha,
                    "attempt_id": state["attempt_id"],
                    "paired_day_count": review["paired_day_count"],
                    "network_accessed": False,
                }

        pending_dir = data_dir / "pending" / current_day.isoformat()
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending = _pending_by_kind(pending_dir, current_day)
        fetched: list[str] = []
        for kind in REQUIRED_KINDS:
            if kind in pending:
                continue
            collector(kind, output_dir=pending_dir, now=current_time)
            fetched.append(kind)
        _commit_pair(
            data_dir,
            pending_dir,
            str(state["attempt_id"]),
            git_sha,
            current_day,
            current_time,
        )
        rows = _validate_ledger(data_dir, git_sha)
        review = _write_review(data_dir, state, rows)
        paired_count = int(review["paired_day_count"])
        if paired_count > MIN_CONTIGUOUS_DAYS:
            raise ValueError("collector exceeded the locked seven-day target")
        state.update(
            {
                "last_paired_date": current_day.isoformat(),
                "paired_day_count": paired_count,
                "updated_at": _utc_text(current_time),
            }
        )
        if paired_count == MIN_CONTIGUOUS_DAYS:
            if review["status"] != "qualification_coverage_pass":
                raise ValueError("seven-day completion did not pass coverage review")
            state["status"] = "complete"
            _atomic_json(state_path, state)
            complete = {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "git_sha": git_sha,
                "attempt_id": state["attempt_id"],
                "paired_day_count": paired_count,
                "paired_dates": review["paired_dates"],
                "completed_at": _utc_text(current_time),
                "recommendation": review["recommendation"],
                "boundaries": review["boundaries"],
            }
            _atomic_json(data_dir / "COMPLETE", complete)
            status = "collection_complete"
        else:
            _atomic_json(state_path, state)
            status = "pair_collected"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "git_sha": git_sha,
            "attempt_id": state["attempt_id"],
            "retrieved_day": current_day.isoformat(),
            "paired_day_count": paired_count,
            "fetched_kinds": fetched,
            "network_accessed": bool(fetched),
            "review_status": review["status"],
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("RESEARCH_V2_DATA_DIR", "data/research-v2-cloud")),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--review-only", action="store_true")
    return parser


def _write_last_error(data_dir: Path, git_sha: str, exc: Exception, exit_code: int) -> None:
    with suppress(OSError):
        _atomic_json(
            data_dir / "last-error.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": "error",
                "git_sha": git_sha,
                "recorded_at": _utc_text(datetime.now(UTC)),
                "exit_code": exit_code,
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    git_sha = os.environ.get("TRADER_GIT_SHA", "")
    try:
        if args.preflight:
            result = preflight(args.data_dir, git_sha)
        elif args.review_only:
            result = review_only(args.data_dir, git_sha)
        else:
            result = run_daily(args.data_dir, git_sha)
    except urllib.error.HTTPError as exc:
        exit_code = 75 if exc.code == 429 or exc.code >= 500 else 2
        if not args.preflight and not args.review_only:
            _write_last_error(args.data_dir, git_sha, exc, exit_code)
        status = "transient_error" if exit_code == 75 else "blocked_error"
        print(json.dumps({"status": status, "message": str(exc)}, sort_keys=True))
        return exit_code
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        if not args.preflight and not args.review_only:
            _write_last_error(args.data_dir, git_sha, exc, 75)
        print(json.dumps({"status": "transient_error", "message": str(exc)}, sort_keys=True))
        return 75
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        if not args.preflight and not args.review_only:
            _write_last_error(args.data_dir, git_sha, exc, 2)
        print(json.dumps({"status": "blocked_error", "message": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

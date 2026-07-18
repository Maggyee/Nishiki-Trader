"""Build a read-only status artifact for the Protocol v5 cloud collector."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.v5.collector_status.v1"
DAILY_SCHEMA_VERSION = "research.v5.daily_collection.v1"
DEFAULT_SERVICE_UNIT = "nishiki-research-v5-collector.service"
DEFAULT_TIMER_UNIT = "nishiki-research-v5-collector.timer"
EXPECTED_STREAMS = (
    ("delivery_curve", "BTCUSDT"),
    ("delivery_curve", "ETHUSDT"),
    ("bvol", "BTCUSDT"),
    ("bvol", "ETHUSDT"),
)

CommandRunner = Callable[[Sequence[str]], tuple[int, str, str]]


def _run_command(command: Sequence[str]) -> tuple[int, str, str]:
    result = subprocess.run(  # noqa: S603 - fixed read-only operator commands
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _required_command(runner: CommandRunner, command: Sequence[str]) -> str:
    returncode, stdout, stderr = runner(command)
    if returncode != 0:
        detail = stderr or stdout or f"exit {returncode}"
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
    return stdout


def _state_command(runner: CommandRunner, command: Sequence[str]) -> str:
    _returncode, stdout, _stderr = runner(command)
    return stdout or "unknown"


def _ssh_runner(host: str, runner: CommandRunner) -> CommandRunner:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", host):
        raise ValueError("--ssh-host must be a plain SSH host or configured alias")

    def run_remote(command: Sequence[str]) -> tuple[int, str, str]:
        return runner(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                host,
                shlex.join(str(part) for part in command),
            ]
        )

    return run_remote


def _find_count(
    runner: CommandRunner,
    root: Path,
    *,
    name: str,
) -> int:
    output = _required_command(
        runner,
        [
            "find",
            str(root),
            "-type",
            "f",
            "-name",
            name,
            "-printf",
            ".",
        ],
    )
    return len(output)


def _systemctl_show(
    runner: CommandRunner,
    unit: str,
    properties: Sequence[str],
) -> dict[str, str]:
    output = _required_command(
        runner,
        [
            "systemctl",
            "show",
            unit,
            "--no-pager",
            *[f"--property={name}" for name in properties],
        ],
    )
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def _systemd_timestamp_ns(value: str | None) -> int | None:
    if not value or value in {"n/a", "never"}:
        return None
    try:
        parsed = datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S %Z").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None
    return int(parsed.timestamp() * 1_000_000_000)


def parse_latest_daily_report(journal_text: str) -> dict[str, Any] | None:
    """Return the last strict daily report embedded in systemd journal text."""

    decoder = json.JSONDecoder(
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        )
    )
    reports: list[dict[str, Any]] = []
    for index, char in enumerate(journal_text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(journal_text[index:])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == DAILY_SCHEMA_VERSION
        ):
            reports.append(payload)
    return reports[-1] if reports else None


def _failure_type(error: str | None) -> str | None:
    lowered = str(error or "").lower()
    if not lowered:
        return None
    if "http error 404" in lowered or "404: not found" in lowered:
        return "http_404_not_published"
    if "checksum" in lowered:
        return "checksum_failure"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    if "must contain" in lowered or "grid" in lowered or "duplicate" in lowered:
        return "validation_failure"
    return "collector_error"


def _stream_rows(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    snapshots = {
        (str(row.get("kind")), str(row.get("asset"))): row
        for row in (report or {}).get("snapshots") or []
        if isinstance(row, dict)
    }
    failures = {
        (str(row.get("kind")), str(row.get("asset"))): row
        for row in (report or {}).get("failures") or []
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for kind, asset in EXPECTED_STREAMS:
        key = (kind, asset)
        if key in failures:
            failure = failures[key]
            error = str(failure.get("error") or "unknown collector failure")
            rows.append(
                {
                    "kind": kind,
                    "asset": asset,
                    "status": "failed",
                    "snapshot_written": failure.get("snapshot_written") is True,
                    "desired_state": str(failure.get("desired_state") or "flat"),
                    "failure_type": _failure_type(error),
                    "error": error,
                }
            )
        elif key in snapshots:
            snapshot = snapshots[key]
            rows.append(
                {
                    "kind": kind,
                    "asset": asset,
                    "status": "success",
                    "snapshot_written": snapshot.get("valid") is True,
                    "desired_state": None,
                    "failure_type": None,
                    "error": None,
                }
            )
        else:
            rows.append(
                {
                    "kind": kind,
                    "asset": asset,
                    "status": "missing",
                    "snapshot_written": False,
                    "desired_state": "flat",
                    "failure_type": "missing_stream_evidence",
                    "error": "stream is absent from the latest daily report",
                }
            )
    return rows


def _report_has_exact_streams(report: dict[str, Any] | None) -> bool:
    evidence = [
        row
        for group in ("snapshots", "failures")
        for row in (report or {}).get(group) or []
        if isinstance(row, dict)
    ]
    keys = [(str(row.get("kind")), str(row.get("asset"))) for row in evidence]
    return len(keys) == len(EXPECTED_STREAMS) and set(keys) == set(EXPECTED_STREAMS)


def build_collector_status(
    *,
    observed_at_ns: int,
    source: dict[str, str],
    service: dict[str, Any],
    timer: dict[str, Any],
    deployment: dict[str, Any],
    storage: dict[str, int],
    daily_report: dict[str, Any] | None,
) -> dict[str, Any]:
    streams = _stream_rows(daily_report)
    failure_counts = Counter(
        str(row["failure_type"])
        for row in streams
        if row.get("failure_type") is not None
    )
    report_found = daily_report is not None
    expected_stream_count = _report_has_exact_streams(daily_report)
    timer_ready = timer.get("active") == "active" and timer.get("enabled") == "enabled"
    identity_match = (
        bool(deployment.get("git_commit"))
        and deployment.get("git_commit") == deployment.get("image_revision")
    )
    checkout_clean = deployment.get("checkout_clean") is True
    no_conflicts = (
        int(storage.get("vintage_conflict_count", 0)) == 0
        and int(storage.get("comparison_marker_count", 0)) == 0
    )
    batch_complete = bool(daily_report and daily_report.get("complete") is True)
    blockers: list[str] = []
    if not timer_ready:
        blockers.append("timer_not_ready")
    if not identity_match:
        blockers.append("deployment_identity_mismatch")
    if not checkout_clean:
        blockers.append("deployment_checkout_dirty")
    if not no_conflicts:
        blockers.append("immutable_vintage_conflict")
    if not report_found:
        blockers.append("daily_report_not_found")
    elif not batch_complete:
        blockers.append("last_batch_incomplete")
    if not expected_stream_count:
        blockers.append("expected_stream_count_mismatch")

    if not identity_match or not checkout_clean or not no_conflicts:
        state = "breach"
    elif not report_found:
        state = "unknown"
    elif not timer_ready or not batch_complete or not expected_stream_count:
        state = "attention"
    else:
        state = "healthy"

    if not no_conflicts:
        next_action = "stop_result_comparison"
    elif not timer_ready:
        next_action = "review_timer_state"
    elif not report_found:
        next_action = "capture_first_scheduled_batch"
    elif (not batch_complete or not expected_stream_count) and timer.get(
        "next_trigger_at"
    ):
        next_action = "await_scheduled_retry"
    elif not batch_complete or not expected_stream_count:
        next_action = "review_incomplete_batch"
    else:
        next_action = "monitor_next_daily_batch"

    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at_ns": observed_at_ns,
        "state": state,
        "next_action": next_action,
        "source": source,
        "service": service,
        "timer": timer,
        "deployment": deployment,
        "storage": storage,
        "last_run": {
            "report_found": report_found,
            "schema_version": (
                daily_report.get("schema_version") if daily_report else None
            ),
            "data_date": daily_report.get("data_date") if daily_report else None,
            "complete": daily_report.get("complete") is True if daily_report else False,
            "valid_snapshot_count": int(
                (daily_report or {}).get("valid_snapshot_count") or 0
            ),
            "failed_snapshot_count": int(
                (daily_report or {}).get("failed_snapshot_count") or 0
            ),
            "vintage_conflict_count": int(
                (daily_report or {}).get("vintage_conflict_count") or 0
            ),
            "signals_generated": (daily_report or {}).get("signals_generated") is True,
            "pnl_computed": (daily_report or {}).get("pnl_computed") is True,
            "streams": streams,
            "failure_types": [
                {"type": key, "count": failure_counts[key]}
                for key in sorted(failure_counts)
            ],
        },
        "gates": {
            "timer_ready": timer_ready,
            "deployment_identity_match": identity_match,
            "checkout_clean": checkout_clean,
            "no_vintage_conflicts": no_conflicts,
            "daily_report_found": report_found,
            "expected_stream_count": expected_stream_count,
            "last_batch_complete": batch_complete,
        },
        "blockers": blockers,
        "boundaries": {
            "read_only": True,
            "network_accessed": False,
            "loads_credentials": False,
            "writes_signal_event": False,
            "computes_pnl": False,
            "mutates_source_policy": False,
            "starts_nautilus": False,
            "resumes_testnet": False,
            "touches_live_path": False,
        },
    }


def collect_collector_status(
    *,
    service_unit: str,
    timer_unit: str,
    data_root: Path,
    checkout: Path,
    image: str,
    observed_at_ns: int | None = None,
    runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    service_show = _systemctl_show(
        runner,
        service_unit,
        (
            "Result",
            "ExecMainStatus",
            "ExecMainStartTimestamp",
            "ExecMainExitTimestamp",
        ),
    )
    timer_show = _systemctl_show(
        runner,
        timer_unit,
        ("LastTriggerUSec", "NextElapseUSecRealtime"),
    )
    journal = _required_command(
        runner,
        ["journalctl", "-u", service_unit, "--no-pager", "-o", "cat", "-n", "2000"],
    )
    git_commit = _required_command(
        runner, ["git", "-C", str(checkout), "rev-parse", "HEAD"]
    )
    git_status = _required_command(
        runner, ["git", "-C", str(checkout), "status", "--porcelain"]
    )
    image_line = _required_command(
        runner,
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{.Id}}\t{{index .Config.Labels "org.opencontainers.image.revision"}}',
            image,
        ],
    )
    image_id, separator, image_revision = image_line.partition("\t")
    if not separator:
        raise ValueError("docker image inspection did not return id and revision")

    storage = {
        "snapshot_count": _find_count(runner, data_root / "raw", name="snapshot.json"),
        "normalized_parquet_count": _find_count(
            runner,
            data_root / "normalized",
            name="*.parquet",
        ),
        "vintage_conflict_count": _find_count(
            runner,
            data_root,
            name="comparison-blocked-*.json",
        ),
        "comparison_marker_count": _find_count(
            runner,
            data_root,
            name="RESULT_COMPARISON_BLOCKED",
        ),
    }
    started_at = service_show.get("ExecMainStartTimestamp") or None
    finished_at = service_show.get("ExecMainExitTimestamp") or None
    last_trigger_at = timer_show.get("LastTriggerUSec") or None
    next_trigger_at = timer_show.get("NextElapseUSecRealtime") or None
    return build_collector_status(
        observed_at_ns=observed_at_ns if observed_at_ns is not None else time.time_ns(),
        source={
            "service_unit": service_unit,
            "timer_unit": timer_unit,
            "data_root": str(data_root),
            "checkout": str(checkout),
            "image": image,
        },
        service={
            "active": _state_command(runner, ["systemctl", "is-active", service_unit]),
            "result": service_show.get("Result") or "unknown",
            "exit_status": int(service_show.get("ExecMainStatus") or 0),
            "started_at": started_at,
            "started_at_ns": _systemd_timestamp_ns(started_at),
            "finished_at": finished_at,
            "finished_at_ns": _systemd_timestamp_ns(finished_at),
        },
        timer={
            "active": _state_command(runner, ["systemctl", "is-active", timer_unit]),
            "enabled": _state_command(runner, ["systemctl", "is-enabled", timer_unit]),
            "last_trigger_at": last_trigger_at,
            "last_trigger_at_ns": _systemd_timestamp_ns(last_trigger_at),
            "next_trigger_at": next_trigger_at,
            "next_trigger_at_ns": _systemd_timestamp_ns(next_trigger_at),
        },
        deployment={
            "git_commit": git_commit,
            "checkout_clean": not git_status,
            "image_id": image_id,
            "image_revision": image_revision,
        },
        storage=storage,
        daily_report=parse_latest_daily_report(journal),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-unit", default=DEFAULT_SERVICE_UNIT)
    parser.add_argument("--timer-unit", default=DEFAULT_TIMER_UNIT)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--ssh-host",
        help="Optional SSH host/alias; all collector evidence remains read-only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = _ssh_runner(args.ssh_host, _run_command) if args.ssh_host else _run_command
    report = collect_collector_status(
        service_unit=args.service_unit,
        timer_unit=args.timer_unit,
        data_root=args.data_root,
        checkout=args.checkout,
        image=args.image,
        runner=runner,
    )
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DAILY_SCHEMA_VERSION",
    "EXPECTED_STREAMS",
    "SCHEMA_VERSION",
    "build_collector_status",
    "collect_collector_status",
    "parse_latest_daily_report",
]

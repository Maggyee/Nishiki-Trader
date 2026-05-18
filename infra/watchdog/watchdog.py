"""Minimal ADR-008 §5.5 heartbeat watchdog for testnet runs.

The watchdog deliberately does not read exchange credentials. It only reads a
runner heartbeat file, records its own state, and invokes the existing
``emergency_flatten`` CLI if the heartbeat is stale. The flatten path owns all
credential loading and exchange interaction.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KIND_TESTNET = "testnet"
DEFAULT_TESTNET_ROOT = Path("data/testnet")
DEFAULT_STATE_PATH = Path("infra/watchdog/state.json")
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 90.0
EXIT_OK = 0
EXIT_FLATTEN_SUCCESS = 4
EXIT_FLATTEN_FAILED = 5


@dataclass(frozen=True)
class WatchdogSettings:
    active_run_id: str
    instrument_ids: tuple[str, ...]
    testnet_root: Path = DEFAULT_TESTNET_ROOT
    state_path: Path = DEFAULT_STATE_PATH
    heartbeat_timeout_seconds: float = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
    operator: str = "watchdog"
    reason: str = "heartbeat_lost"
    runner_pid: int | None = None
    python_executable: str = sys.executable

    def __post_init__(self) -> None:
        if not self.active_run_id:
            raise ValueError("active_run_id is required")
        if not self.instrument_ids:
            raise ValueError("at least one instrument_id is required")
        if self.heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds must be positive")


@dataclass(frozen=True)
class WatchdogResult:
    active_run_id: str
    heartbeat_path: Path
    state_path: Path
    status: str
    checked_at: str
    last_heartbeat_at: str | None
    heartbeat_age_seconds: float | None
    heartbeat_timeout_seconds: float
    flatten_invoked: bool
    flatten_returncode: int | None = None
    alert_path: Path | None = None

    @property
    def exit_code(self) -> int:
        if not self.flatten_invoked:
            return EXIT_OK
        return (
            EXIT_FLATTEN_SUCCESS
            if self.flatten_returncode == 0
            else EXIT_FLATTEN_FAILED
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["heartbeat_path"] = str(self.heartbeat_path)
        payload["state_path"] = str(self.state_path)
        if self.alert_path is not None:
            payload["alert_path"] = str(self.alert_path)
        payload["exit_code"] = self.exit_code
        return payload


ClockFn = Callable[[], datetime]
FlattenInvoker = Callable[[WatchdogSettings], int]


def check_once(
    settings: WatchdogSettings,
    *,
    clock: ClockFn | None = None,
    flatten_invoker: FlattenInvoker | None = None,
) -> WatchdogResult:
    now = clock() if clock is not None else datetime.now(UTC)
    checked_at = _iso_ms_utc(now)
    heartbeat_path = (
        settings.testnet_root / settings.active_run_id / "logs" / "heartbeat.jsonl"
    )
    alert_path = settings.testnet_root / settings.active_run_id / "logs" / "alerts.log"
    last_heartbeat_at = _last_heartbeat_ts(heartbeat_path)
    heartbeat_age = None
    status = "heartbeat_missing"
    flatten_invoked = False
    flatten_returncode = None

    if last_heartbeat_at is not None:
        heartbeat_age = max(0.0, (now - last_heartbeat_at).total_seconds())
        status = (
            "heartbeat_stale"
            if heartbeat_age > settings.heartbeat_timeout_seconds
            else "healthy"
        )

    if status != "healthy":
        _append_alert(
            alert_path,
            ts=checked_at,
            run_id=settings.active_run_id,
            msg="heartbeat_lost",
            context={
                "last_heartbeat_at": (
                    None if last_heartbeat_at is None else _iso_ms_utc(last_heartbeat_at)
                ),
                "heartbeat_age_seconds": heartbeat_age,
                "heartbeat_timeout_seconds": settings.heartbeat_timeout_seconds,
                "watchdog_status": status,
            },
        )
        invoker = flatten_invoker if flatten_invoker is not None else _invoke_flatten
        flatten_returncode = invoker(settings)
        flatten_invoked = True

    result = WatchdogResult(
        active_run_id=settings.active_run_id,
        heartbeat_path=heartbeat_path,
        state_path=settings.state_path,
        status=status,
        checked_at=checked_at,
        last_heartbeat_at=None
        if last_heartbeat_at is None
        else _iso_ms_utc(last_heartbeat_at),
        heartbeat_age_seconds=heartbeat_age,
        heartbeat_timeout_seconds=settings.heartbeat_timeout_seconds,
        flatten_invoked=flatten_invoked,
        flatten_returncode=flatten_returncode,
        alert_path=alert_path if status != "healthy" else None,
    )
    _write_state(settings.state_path, result)
    return result


def _last_heartbeat_ts(path: Path) -> datetime | None:
    if not path.exists():
        return None
    last_payload: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            last_payload = payload
    if last_payload is None:
        return None
    raw_ts = last_payload.get("ts")
    return _parse_iso_ms_utc(str(raw_ts)) if raw_ts else None


def _invoke_flatten(settings: WatchdogSettings) -> int:
    command = [
        settings.python_executable,
        "-m",
        "apps.strategies_nautilus.runners.emergency_flatten",
        "--kind",
        KIND_TESTNET,
        "--run-id",
        settings.active_run_id,
        "--operator",
        settings.operator,
        "--reason",
        settings.reason,
        "--output-root",
        str(settings.testnet_root),
    ]
    for instrument_id in settings.instrument_ids:
        command.extend(["--instrument-id", instrument_id])
    if settings.runner_pid is not None:
        command.extend(["--runner-pid", str(settings.runner_pid)])
    completed = subprocess.run(command, check=False)  # noqa: S603
    return int(completed.returncode)


def _append_alert(
    path: Path,
    *,
    ts: str,
    run_id: str,
    msg: str,
    context: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": ts,
                    "severity": "critical",
                    "kind": KIND_TESTNET,
                    "run_id": run_id,
                    "msg": msg,
                    "context": context,
                },
                sort_keys=True,
            )
        )
        fh.write("\n")


def _write_state(path: Path, result: WatchdogResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_iso_ms_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _iso_ms_utc(dt: datetime) -> str:
    aware = dt.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%S.") + f"{aware.microsecond // 1000:03d}Z"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a testnet runner heartbeat and flatten on timeout.",
    )
    parser.add_argument("--active-run-id", required=True)
    parser.add_argument("--instrument-id", action="append", required=True)
    parser.add_argument("--testnet-root", type=Path, default=DEFAULT_TESTNET_ROOT)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument(
        "--heartbeat-timeout-seconds",
        type=float,
        default=DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--operator", default="watchdog")
    parser.add_argument("--reason", default="heartbeat_lost")
    parser.add_argument("--runner-pid", type=int)
    return parser


def _settings_from_args(args: argparse.Namespace) -> WatchdogSettings:
    return WatchdogSettings(
        active_run_id=args.active_run_id,
        instrument_ids=tuple(args.instrument_id),
        testnet_root=args.testnet_root,
        state_path=args.state_path,
        heartbeat_timeout_seconds=args.heartbeat_timeout_seconds,
        operator=args.operator,
        reason=args.reason,
        runner_pid=args.runner_pid,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: ClockFn | None = None,
    flatten_invoker: FlattenInvoker | None = None,
) -> int:
    parser = _build_parser()
    try:
        settings = _settings_from_args(parser.parse_args(argv))
    except ValueError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    result = check_once(settings, clock=clock, flatten_invoker=flatten_invoker)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return result.exit_code


__all__ = [
    "WatchdogResult",
    "WatchdogSettings",
    "check_once",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

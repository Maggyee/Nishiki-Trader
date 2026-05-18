"""ADR-008 §5.1 / §6.3 emergency flatten CLI.

Stand-alone seven-step shutdown path. Given a running ``(kind, run_id)``
bundle on disk, signal the runner process, cancel every open order on the
target instruments via the injected exchange client, flatten every open
position with reduce-only market orders, wait for fills (with a timeout
budget), snapshot the account, and write ``data/<kind>/<run_id>/emergency_flatten.json``
plus two ``logs/alerts.log`` lines (``emergency_flatten_started`` /
``emergency_flatten_completed``).

The orchestration is exchange-agnostic: callers supply an object that
implements the :class:`ExchangeClient` protocol. Unit tests pass a fake
client to drive every step deterministically. For ``--kind testnet`` the
CLI default factory now wires the real Binance Spot testnet REST driver;
paper and live still require an injected factory.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

DEFAULT_FILL_TIMEOUT_SECONDS = 60.0
DEFAULT_CANCEL_TIMEOUT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_SIGKILL_DELAY_SECONDS = 5.0
ALLOWED_KINDS = ("paper", "testnet", "live")
TERMINAL_ORDER_STATUSES = frozenset(
    {"FILLED", "CANCELED", "REJECTED", "EXPIRED"},
)


class FlattenValidationError(ValueError):
    """Raised when CLI / settings validation fails before any side effect."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class OpenOrder:
    order_id: str
    instrument_id: str
    side: str  # "BUY" | "SELL"
    quantity: Decimal
    submitted_at: str | None = None


@dataclass(frozen=True)
class OpenPosition:
    instrument_id: str
    side: str  # "LONG" | "SHORT" | "FLAT"
    quantity: Decimal  # always positive; FLAT carries Decimal("0")


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: str
    instrument_id: str
    status: str  # NEW | PARTIALLY_FILLED | FILLED | CANCELED | REJECTED | EXPIRED
    filled_quantity: Decimal
    avg_price: Decimal | None = None


@dataclass(frozen=True)
class AccountBalance:
    asset: str
    free: Decimal
    locked: Decimal


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    fetched_at: str
    balances: tuple[AccountBalance, ...]


class ExchangeClient(Protocol):
    """Minimal exchange surface needed for emergency flatten.

    The real Binance Spot testnet implementation is deferred to a
    follow-up §6.3b commit. The probe-stage testnet runner does not
    rely on this protocol — it only connects, never trades.
    """

    def list_open_orders(self, instrument_id: str) -> Sequence[OpenOrder]: ...

    def cancel_order(
        self, *, order_id: str, instrument_id: str
    ) -> bool: ...

    def list_open_positions(
        self, instrument_id: str
    ) -> Sequence[OpenPosition]: ...

    def submit_reduce_only_market_order(
        self,
        *,
        instrument_id: str,
        side: str,
        quantity: Decimal,
        client_order_id: str,
    ) -> str: ...

    def query_order(
        self, *, order_id: str, instrument_id: str
    ) -> OrderSnapshot: ...

    def get_account_snapshot(self) -> AccountSnapshot: ...


@dataclass(frozen=True)
class EmergencyFlattenSettings:
    kind: str
    run_id: str
    operator: str
    reason: str
    instrument_ids: tuple[str, ...]
    output_root: Path
    cancel_only: bool = False
    fill_timeout_seconds: float = DEFAULT_FILL_TIMEOUT_SECONDS
    cancel_timeout_seconds: float = DEFAULT_CANCEL_TIMEOUT_SECONDS
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    sigkill_delay_seconds: float = DEFAULT_SIGKILL_DELAY_SECONDS
    runner_pid: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in ALLOWED_KINDS:
            raise FlattenValidationError(
                "invalid_kind",
                f"--kind must be one of {ALLOWED_KINDS}, got {self.kind!r}",
            )
        if not self.run_id:
            raise FlattenValidationError("run_id_required", "--run-id is required")
        if not self.operator:
            raise FlattenValidationError(
                "operator_required", "--operator is required"
            )
        if not self.reason:
            raise FlattenValidationError("reason_required", "--reason is required")
        if not self.instrument_ids:
            raise FlattenValidationError(
                "instruments_required",
                "at least one --instrument-id must be provided",
            )
        if self.fill_timeout_seconds <= 0:
            raise FlattenValidationError(
                "fill_timeout_must_be_positive",
                f"--fill-timeout-seconds must be > 0, got {self.fill_timeout_seconds}",
            )
        if self.cancel_timeout_seconds <= 0:
            raise FlattenValidationError(
                "cancel_timeout_must_be_positive",
                f"--cancel-timeout-seconds must be > 0, got {self.cancel_timeout_seconds}",
            )
        if self.poll_interval_seconds <= 0:
            raise FlattenValidationError(
                "poll_interval_must_be_positive",
                f"--poll-interval-seconds must be > 0, got {self.poll_interval_seconds}",
            )


@dataclass(frozen=True)
class CancelledOrderRecord:
    order_id: str
    instrument_id: str
    side: str
    quantity: str
    cancelled_at: str


@dataclass(frozen=True)
class ResidualOrderRecord:
    order_id: str
    instrument_id: str
    side: str
    quantity: str
    reason: str  # "cancel_rejected" | "cancel_exception"


@dataclass(frozen=True)
class ClosedPositionRecord:
    instrument_id: str
    side_before: str
    quantity_before: str
    reduce_order_id: str
    close_side: str
    filled_quantity: str
    avg_price: str | None
    closed_at: str


@dataclass(frozen=True)
class ResidualPositionRecord:
    instrument_id: str
    side: str
    quantity: str
    reduce_order_id: str | None
    last_status: str | None
    last_filled_quantity: str | None
    reason: str  # "submit_exception" | "fill_timeout" | "rejected"


@dataclass(frozen=True)
class EmergencyFlattenResult:
    triggered_at: str
    triggered_by: str
    reason: str
    cancel_only: bool
    kind: str
    run_id: str
    instrument_ids: tuple[str, ...]
    runner_pid: int | None
    runner_sigterm_sent: bool
    runner_sigkill_sent: bool
    cancelled_orders: tuple[CancelledOrderRecord, ...]
    residual_orders: tuple[ResidualOrderRecord, ...]
    closed_positions: tuple[ClosedPositionRecord, ...]
    residual_positions: tuple[ResidualPositionRecord, ...]
    final_account: dict[str, Any]
    success: bool
    elapsed_seconds: float
    audit_path: Path
    alerts_path: Path

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["audit_path"] = str(self.audit_path)
        payload["alerts_path"] = str(self.alerts_path)
        payload["instrument_ids"] = list(self.instrument_ids)
        payload["cancelled_orders"] = [asdict(o) for o in self.cancelled_orders]
        payload["residual_orders"] = [asdict(o) for o in self.residual_orders]
        payload["closed_positions"] = [asdict(p) for p in self.closed_positions]
        payload["residual_positions"] = [
            asdict(p) for p in self.residual_positions
        ]
        return payload


Signaller = Callable[[int, int], None]
ClockFn = Callable[[], datetime]
MonoClockFn = Callable[[], float]
SleeperFn = Callable[[float], None]


def run_emergency_flatten(
    settings: EmergencyFlattenSettings,
    *,
    exchange: ExchangeClient,
    clock: ClockFn | None = None,
    monotonic: MonoClockFn | None = None,
    sleeper: SleeperFn | None = None,
    signaller: Signaller | None = None,
) -> EmergencyFlattenResult:
    """Execute the ADR-008 §5.1 seven-step flatten path.

    The orchestration always writes ``emergency_flatten.json`` and
    ``logs/alerts.log`` — even when every step fails — so the operator
    has an audit trail. ``success`` is true only when all listed orders
    were cancelled and all listed positions reached ``FILLED``.
    """

    now: ClockFn = clock if clock is not None else _utc_now
    mono: MonoClockFn = monotonic if monotonic is not None else time.monotonic
    sleep: SleeperFn = sleeper if sleeper is not None else time.sleep
    sig: Signaller = signaller if signaller is not None else os.kill

    started = now()
    triggered_at = _iso_ms_utc(started)
    mono_start = mono()

    bundle_root = settings.output_root / settings.run_id
    logs_dir = bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    alerts_path = logs_dir / "alerts.log"
    audit_path = bundle_root / "emergency_flatten.json"

    _append_alert(
        alerts_path,
        severity="critical",
        kind=settings.kind,
        run_id=settings.run_id,
        msg="emergency_flatten_started",
        ts=triggered_at,
        context={
            "operator": settings.operator,
            "reason": settings.reason,
            "cancel_only": settings.cancel_only,
            "instrument_ids": list(settings.instrument_ids),
        },
    )

    runner_sigterm_sent = _send_signal(sig, settings.runner_pid, signal.SIGTERM)

    cancelled: list[CancelledOrderRecord] = []
    residual_orders: list[ResidualOrderRecord] = []
    closed: list[ClosedPositionRecord] = []
    residual_positions: list[ResidualPositionRecord] = []

    for instrument_id in settings.instrument_ids:
        _cancel_orders_for_instrument(
            exchange=exchange,
            instrument_id=instrument_id,
            cancelled=cancelled,
            residual=residual_orders,
            now=now,
        )

        if settings.cancel_only:
            continue

        _flatten_positions_for_instrument(
            exchange=exchange,
            settings=settings,
            instrument_id=instrument_id,
            closed=closed,
            residual=residual_positions,
            now=now,
            mono=mono,
            sleep=sleep,
        )

    final_account_snapshot = exchange.get_account_snapshot()
    final_account_dict = _account_to_dict(final_account_snapshot)

    runner_sigkill_sent = False
    if runner_sigterm_sent:
        sleep(settings.sigkill_delay_seconds)
        runner_sigkill_sent = _send_signal(
            sig, settings.runner_pid, signal.SIGKILL
        )

    finished = now()
    elapsed = max(0.0, mono() - mono_start)
    success = not residual_orders and (
        settings.cancel_only or not residual_positions
    )

    result = EmergencyFlattenResult(
        triggered_at=triggered_at,
        triggered_by=settings.operator,
        reason=settings.reason,
        cancel_only=settings.cancel_only,
        kind=settings.kind,
        run_id=settings.run_id,
        instrument_ids=settings.instrument_ids,
        runner_pid=settings.runner_pid,
        runner_sigterm_sent=runner_sigterm_sent,
        runner_sigkill_sent=runner_sigkill_sent,
        cancelled_orders=tuple(cancelled),
        residual_orders=tuple(residual_orders),
        closed_positions=tuple(closed),
        residual_positions=tuple(residual_positions),
        final_account=final_account_dict,
        success=success,
        elapsed_seconds=elapsed,
        audit_path=audit_path,
        alerts_path=alerts_path,
    )

    audit_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    _append_alert(
        alerts_path,
        severity="critical",
        kind=settings.kind,
        run_id=settings.run_id,
        msg="emergency_flatten_completed",
        ts=_iso_ms_utc(finished),
        context={
            "operator": settings.operator,
            "success": success,
            "cancelled_orders": len(cancelled),
            "residual_orders": len(residual_orders),
            "closed_positions": len(closed),
            "residual_positions": len(residual_positions),
            "elapsed_seconds": elapsed,
        },
    )

    return result


def _cancel_orders_for_instrument(
    *,
    exchange: ExchangeClient,
    instrument_id: str,
    cancelled: list[CancelledOrderRecord],
    residual: list[ResidualOrderRecord],
    now: ClockFn,
) -> None:
    try:
        open_orders = list(exchange.list_open_orders(instrument_id))
    except Exception as exc:  # noqa: BLE001 — audit failures, never raise
        residual.append(
            ResidualOrderRecord(
                order_id="<unknown>",
                instrument_id=instrument_id,
                side="<unknown>",
                quantity="<unknown>",
                reason=f"list_orders_exception:{type(exc).__name__}",
            )
        )
        return

    for order in open_orders:
        try:
            ok = exchange.cancel_order(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
            )
        except Exception as exc:  # noqa: BLE001
            residual.append(
                ResidualOrderRecord(
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    side=order.side,
                    quantity=str(order.quantity),
                    reason=f"cancel_exception:{type(exc).__name__}",
                )
            )
            continue

        if ok:
            cancelled.append(
                CancelledOrderRecord(
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    side=order.side,
                    quantity=str(order.quantity),
                    cancelled_at=_iso_ms_utc(now()),
                )
            )
        else:
            residual.append(
                ResidualOrderRecord(
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    side=order.side,
                    quantity=str(order.quantity),
                    reason="cancel_rejected",
                )
            )


def _flatten_positions_for_instrument(
    *,
    exchange: ExchangeClient,
    settings: EmergencyFlattenSettings,
    instrument_id: str,
    closed: list[ClosedPositionRecord],
    residual: list[ResidualPositionRecord],
    now: ClockFn,
    mono: MonoClockFn,
    sleep: SleeperFn,
) -> None:
    try:
        positions = list(exchange.list_open_positions(instrument_id))
    except Exception as exc:  # noqa: BLE001
        residual.append(
            ResidualPositionRecord(
                instrument_id=instrument_id,
                side="<unknown>",
                quantity="<unknown>",
                reduce_order_id=None,
                last_status=None,
                last_filled_quantity=None,
                reason=f"list_positions_exception:{type(exc).__name__}",
            )
        )
        return

    for pos in positions:
        if pos.side == "FLAT" or pos.quantity == 0:
            continue

        close_side = "SELL" if pos.side == "LONG" else "BUY"
        client_order_id = _build_client_order_id(settings.run_id, instrument_id)

        try:
            order_id = exchange.submit_reduce_only_market_order(
                instrument_id=pos.instrument_id,
                side=close_side,
                quantity=pos.quantity,
                client_order_id=client_order_id,
            )
        except Exception as exc:  # noqa: BLE001
            residual.append(
                ResidualPositionRecord(
                    instrument_id=pos.instrument_id,
                    side=pos.side,
                    quantity=str(pos.quantity),
                    reduce_order_id=None,
                    last_status=None,
                    last_filled_quantity=None,
                    reason=f"submit_exception:{type(exc).__name__}",
                )
            )
            continue

        snapshot = _wait_for_terminal(
            exchange=exchange,
            order_id=order_id,
            instrument_id=pos.instrument_id,
            timeout_seconds=settings.fill_timeout_seconds,
            poll_seconds=settings.poll_interval_seconds,
            mono=mono,
            sleep=sleep,
        )

        if snapshot is not None and snapshot.status == "FILLED":
            closed.append(
                ClosedPositionRecord(
                    instrument_id=pos.instrument_id,
                    side_before=pos.side,
                    quantity_before=str(pos.quantity),
                    reduce_order_id=order_id,
                    close_side=close_side,
                    filled_quantity=str(snapshot.filled_quantity),
                    avg_price=(
                        None if snapshot.avg_price is None else str(snapshot.avg_price)
                    ),
                    closed_at=_iso_ms_utc(now()),
                )
            )
            continue

        if snapshot is None:
            reason = "fill_timeout"
            status = None
            filled = None
        elif snapshot.status in ("CANCELED", "REJECTED", "EXPIRED"):
            reason = "rejected"
            status = snapshot.status
            filled = str(snapshot.filled_quantity)
        else:
            # Reached the deadline while status was still NEW / PARTIALLY_FILLED.
            reason = "fill_timeout"
            status = snapshot.status
            filled = str(snapshot.filled_quantity)

        residual.append(
            ResidualPositionRecord(
                instrument_id=pos.instrument_id,
                side=pos.side,
                quantity=str(pos.quantity),
                reduce_order_id=order_id,
                last_status=status,
                last_filled_quantity=filled,
                reason=reason,
            )
        )


def _wait_for_terminal(
    *,
    exchange: ExchangeClient,
    order_id: str,
    instrument_id: str,
    timeout_seconds: float,
    poll_seconds: float,
    mono: MonoClockFn,
    sleep: SleeperFn,
) -> OrderSnapshot | None:
    deadline = mono() + timeout_seconds
    snapshot: OrderSnapshot | None = None
    while True:
        try:
            snapshot = exchange.query_order(
                order_id=order_id, instrument_id=instrument_id
            )
        except Exception:  # noqa: BLE001
            snapshot = None
        if snapshot is not None and snapshot.status in TERMINAL_ORDER_STATUSES:
            return snapshot
        remaining = deadline - mono()
        if remaining <= 0:
            return snapshot
        sleep(min(poll_seconds, remaining))


def _send_signal(
    signaller: Signaller, pid: int | None, sig: signal.Signals
) -> bool:
    if pid is None:
        return False
    try:
        signaller(pid, int(sig))
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    except OSError:
        return False
    return True


def _build_client_order_id(run_id: str, instrument_id: str) -> str:
    # Binance Spot accepts up to 36 chars; keep deterministic enough for audit.
    ns = time.time_ns()
    base = f"EF-{run_id}-{instrument_id}-{ns}"
    return base[:36]


def _account_to_dict(snapshot: AccountSnapshot) -> dict[str, Any]:
    return {
        "account_id": snapshot.account_id,
        "fetched_at": snapshot.fetched_at,
        "balances": [
            {
                "asset": b.asset,
                "free": str(b.free),
                "locked": str(b.locked),
            }
            for b in snapshot.balances
        ],
    }


def _append_alert(
    path: Path,
    *,
    severity: str,
    kind: str,
    run_id: str,
    msg: str,
    ts: str,
    context: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": ts,
                    "severity": severity,
                    "kind": kind,
                    "run_id": run_id,
                    "msg": msg,
                    "context": dict(context),
                },
                sort_keys=True,
            )
        )
        fh.write("\n")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_ms_utc(dt: datetime) -> str:
    aware = dt.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%S.") + f"{aware.microsecond // 1000:03d}Z"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the ADR-008 §5.1 emergency flatten sequence against an "
            "exchange. Defaults assume a Binance Spot testnet bundle."
        ),
    )
    parser.add_argument(
        "--kind",
        required=True,
        choices=ALLOWED_KINDS,
        help="Bundle kind: paper | testnet | live",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Target run_id (bundle directory name under data/<kind>/).",
    )
    parser.add_argument(
        "--operator",
        required=True,
        help="Operator name; recorded in the audit JSON triggered_by field.",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Free-text reason recorded in the audit JSON and alerts.log.",
    )
    parser.add_argument(
        "--instrument-id",
        action="append",
        required=True,
        help=(
            "Instrument ID to flatten (repeat for multiple). Each maps to "
            "open orders + open positions on that market."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Bundle root (defaults to data/<kind>/).",
    )
    parser.add_argument(
        "--cancel-only",
        action="store_true",
        help="Cancel open orders but do not flatten positions.",
    )
    parser.add_argument(
        "--fill-timeout-seconds",
        type=float,
        default=DEFAULT_FILL_TIMEOUT_SECONDS,
        help=f"Fill wait timeout per position (default {DEFAULT_FILL_TIMEOUT_SECONDS}s).",
    )
    parser.add_argument(
        "--cancel-timeout-seconds",
        type=float,
        default=DEFAULT_CANCEL_TIMEOUT_SECONDS,
        help=f"Cancel wait timeout reserve (default {DEFAULT_CANCEL_TIMEOUT_SECONDS}s).",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=(
            "Polling interval when waiting for order fills "
            f"(default {DEFAULT_POLL_INTERVAL_SECONDS}s)."
        ),
    )
    parser.add_argument(
        "--sigkill-delay-seconds",
        type=float,
        default=DEFAULT_SIGKILL_DELAY_SECONDS,
        help=(
            "Delay between SIGTERM and SIGKILL when a --runner-pid is "
            f"provided (default {DEFAULT_SIGKILL_DELAY_SECONDS}s)."
        ),
    )
    parser.add_argument(
        "--runner-pid",
        type=int,
        default=None,
        help="Optional runner PID to receive SIGTERM/SIGKILL bracket.",
    )
    return parser


def _settings_from_args(args: argparse.Namespace) -> EmergencyFlattenSettings:
    output_root = args.output_root or Path("data") / args.kind
    return EmergencyFlattenSettings(
        kind=args.kind,
        run_id=args.run_id,
        operator=args.operator,
        reason=args.reason,
        instrument_ids=tuple(args.instrument_id),
        output_root=output_root,
        cancel_only=bool(args.cancel_only),
        fill_timeout_seconds=args.fill_timeout_seconds,
        cancel_timeout_seconds=args.cancel_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        sigkill_delay_seconds=args.sigkill_delay_seconds,
        runner_pid=args.runner_pid,
    )


ExchangeFactory = Callable[[EmergencyFlattenSettings], ExchangeClient]


def main(
    argv: list[str] | None = None,
    *,
    exchange_factory: ExchangeFactory | None = None,
    env: Mapping[str, str] | None = None,
    clock: ClockFn | None = None,
    monotonic: MonoClockFn | None = None,
    sleeper: SleeperFn | None = None,
    signaller: Signaller | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        settings = _settings_from_args(args)
    except FlattenValidationError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")

    factory = exchange_factory or (lambda s: _default_exchange_factory(s, env=env))
    try:
        exchange = factory(settings)
    except FlattenValidationError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    result = run_emergency_flatten(
        settings,
        exchange=exchange,
        clock=clock,
        monotonic=monotonic,
        sleeper=sleeper,
        signaller=signaller,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.success else 1


def _default_exchange_factory(
    settings: EmergencyFlattenSettings,
    *,
    env: Mapping[str, str] | None = None,
) -> ExchangeClient:
    if settings.kind == "testnet":
        from apps.strategies_nautilus.runners.binance_testnet_exchange import (
            build_binance_spot_testnet_exchange,
        )

        return build_binance_spot_testnet_exchange(
            settings,
            env=env if env is not None else os.environ,
        )
    raise FlattenValidationError(
        "exchange_driver_unavailable",
        f"no default exchange driver is wired for kind={settings.kind!r}",
    )


__all__ = [
    "ALLOWED_KINDS",
    "AccountBalance",
    "AccountSnapshot",
    "CancelledOrderRecord",
    "ClosedPositionRecord",
    "EmergencyFlattenResult",
    "EmergencyFlattenSettings",
    "ExchangeClient",
    "ExchangeFactory",
    "FlattenValidationError",
    "OpenOrder",
    "OpenPosition",
    "OrderSnapshot",
    "ResidualOrderRecord",
    "ResidualPositionRecord",
    "main",
    "run_emergency_flatten",
]


if __name__ == "__main__":
    raise SystemExit(main())

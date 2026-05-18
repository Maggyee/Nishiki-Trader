"""Tests for ADR-008 §5.1 / §6.3 emergency flatten orchestration."""

from __future__ import annotations

import json
import signal
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from apps.strategies_nautilus.runners.emergency_flatten import (
    AccountBalance,
    AccountSnapshot,
    EmergencyFlattenSettings,
    FlattenValidationError,
    OpenOrder,
    OpenPosition,
    OrderSnapshot,
    main,
    run_emergency_flatten,
)


class _FakeExchange:
    """Records every API call and produces scripted responses."""

    def __init__(
        self,
        *,
        open_orders: dict[str, list[OpenOrder]] | None = None,
        open_positions: dict[str, list[OpenPosition]] | None = None,
        cancel_outcomes: dict[str, bool | type[Exception]] | None = None,
        submit_outcomes: dict[str, str | type[Exception]] | None = None,
        query_script: dict[str, list[OrderSnapshot]] | None = None,
        account: AccountSnapshot | None = None,
    ) -> None:
        self._open_orders = open_orders or {}
        self._open_positions = open_positions or {}
        self._cancel_outcomes = cancel_outcomes or {}
        self._submit_outcomes = submit_outcomes or {}
        self._query_script = {
            key: deque(value) for key, value in (query_script or {}).items()
        }
        self._account = account or AccountSnapshot(
            account_id="BINANCE-SPOT-master",
            fetched_at="2026-05-18T12:34:56.000Z",
            balances=(AccountBalance("USDT", Decimal("10000"), Decimal("0")),),
        )
        self.calls: list[tuple[str, dict]] = []
        self.submitted_orders: list[dict] = []

    def list_open_orders(self, instrument_id):
        self.calls.append(("list_open_orders", {"instrument_id": instrument_id}))
        return list(self._open_orders.get(instrument_id, []))

    def cancel_order(self, *, order_id, instrument_id):
        self.calls.append(
            ("cancel_order", {"order_id": order_id, "instrument_id": instrument_id})
        )
        outcome = self._cancel_outcomes.get(order_id, True)
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome("scripted cancel failure")
        return bool(outcome)

    def list_open_positions(self, instrument_id):
        self.calls.append(
            ("list_open_positions", {"instrument_id": instrument_id})
        )
        return list(self._open_positions.get(instrument_id, []))

    def submit_reduce_only_market_order(
        self, *, instrument_id, side, quantity, client_order_id
    ):
        self.calls.append(
            (
                "submit_reduce_only_market_order",
                {
                    "instrument_id": instrument_id,
                    "side": side,
                    "quantity": str(quantity),
                    "client_order_id": client_order_id,
                },
            )
        )
        outcome = self._submit_outcomes.get(instrument_id, f"EXCH-{instrument_id}")
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome("scripted submit failure")
        order_id = str(outcome)
        self.submitted_orders.append(
            {
                "order_id": order_id,
                "instrument_id": instrument_id,
                "side": side,
                "quantity": str(quantity),
            }
        )
        return order_id

    def query_order(self, *, order_id, instrument_id):
        self.calls.append(
            ("query_order", {"order_id": order_id, "instrument_id": instrument_id})
        )
        script = self._query_script.get(order_id)
        if not script:
            # Default: never-terminal NEW so callers can verify timeout paths.
            return OrderSnapshot(
                order_id=order_id,
                instrument_id=instrument_id,
                status="NEW",
                filled_quantity=Decimal("0"),
                avg_price=None,
            )
        return script.popleft() if len(script) > 1 else script[0]

    def get_account_snapshot(self):
        self.calls.append(("get_account_snapshot", {}))
        return self._account


def _frozen_clock(base: datetime, step_seconds: float = 0.5):
    state = {"t": base}

    def _now() -> datetime:
        current = state["t"]
        state["t"] = current + timedelta(seconds=step_seconds)
        return current

    return _now


def _frozen_monotonic(step_seconds: float = 0.5):
    state = {"t": 0.0}

    def _now() -> float:
        current = state["t"]
        state["t"] = current + step_seconds
        return current

    return _now


def _settings(
    tmp_path: Path, **overrides
) -> EmergencyFlattenSettings:
    values = {
        "kind": "testnet",
        "run_id": "20260518-122839Z-24bf3db2",
        "operator": "pytest",
        "reason": "unit test",
        "instrument_ids": ("BTCUSDT.BINANCE",),
        "output_root": tmp_path / "data" / "testnet",
        "cancel_only": False,
        "fill_timeout_seconds": 2.0,
        "cancel_timeout_seconds": 2.0,
        "poll_interval_seconds": 0.5,
        "sigkill_delay_seconds": 0.0,
    }
    values.update(overrides)
    return EmergencyFlattenSettings(**values)


def _no_op_sleeper(_: float) -> None:
    return None


# ---- validation ----


def test_settings_rejects_invalid_kind(tmp_path):
    with pytest.raises(FlattenValidationError, match="invalid_kind"):
        _settings(tmp_path, kind="mainnet")


def test_settings_requires_run_id(tmp_path):
    with pytest.raises(FlattenValidationError, match="run_id_required"):
        _settings(tmp_path, run_id="")


def test_settings_requires_operator(tmp_path):
    with pytest.raises(FlattenValidationError, match="operator_required"):
        _settings(tmp_path, operator="")


def test_settings_requires_reason(tmp_path):
    with pytest.raises(FlattenValidationError, match="reason_required"):
        _settings(tmp_path, reason="")


def test_settings_requires_instruments(tmp_path):
    with pytest.raises(FlattenValidationError, match="instruments_required"):
        _settings(tmp_path, instrument_ids=())


# ---- happy path ----


def test_full_path_cancels_orders_flattens_positions_and_writes_audit(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_orders={
            instrument: [
                OpenOrder(
                    order_id="O1",
                    instrument_id=instrument,
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
                OpenOrder(
                    order_id="O2",
                    instrument_id=instrument,
                    side="SELL",
                    quantity=Decimal("0.02"),
                ),
            ],
        },
        open_positions={
            instrument: [
                OpenPosition(
                    instrument_id=instrument,
                    side="LONG",
                    quantity=Decimal("0.05"),
                ),
            ],
        },
        cancel_outcomes={"O1": True, "O2": True},
        submit_outcomes={instrument: "EXCH-REDUCE-1"},
        query_script={
            "EXCH-REDUCE-1": [
                OrderSnapshot(
                    order_id="EXCH-REDUCE-1",
                    instrument_id=instrument,
                    status="FILLED",
                    filled_quantity=Decimal("0.05"),
                    avg_price=Decimal("30000"),
                ),
            ],
        },
        account=AccountSnapshot(
            account_id="BINANCE-SPOT-master",
            fetched_at="2026-05-18T12:34:56.000Z",
            balances=(
                AccountBalance("USDT", Decimal("11500"), Decimal("0")),
                AccountBalance("BTC", Decimal("0"), Decimal("0")),
            ),
        ),
    )

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is True
    assert len(result.cancelled_orders) == 2
    assert {o.order_id for o in result.cancelled_orders} == {"O1", "O2"}
    assert result.residual_orders == ()
    assert len(result.closed_positions) == 1
    closed = result.closed_positions[0]
    assert closed.instrument_id == instrument
    assert closed.side_before == "LONG"
    assert closed.close_side == "SELL"
    assert closed.filled_quantity == "0.05"
    assert closed.avg_price == "30000"
    assert result.residual_positions == ()
    assert result.runner_sigterm_sent is False  # runner_pid not set
    assert result.runner_sigkill_sent is False
    assert result.audit_path.exists()
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
    assert audit["success"] is True
    assert audit["triggered_by"] == "pytest"
    assert audit["reason"] == "unit test"
    assert audit["cancel_only"] is False
    assert audit["final_account"]["account_id"] == "BINANCE-SPOT-master"
    assert audit["final_account"]["balances"][0]["asset"] == "USDT"
    # Order matters for §5.1 §2-§4: cancel before submit.
    call_names = [c[0] for c in exchange.calls]
    assert call_names.index("cancel_order") < call_names.index(
        "submit_reduce_only_market_order"
    )


def test_cancel_only_skips_position_steps(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_orders={
            instrument: [
                OpenOrder(
                    order_id="O1",
                    instrument_id=instrument,
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
            ],
        },
        open_positions={
            instrument: [
                OpenPosition(
                    instrument_id=instrument,
                    side="LONG",
                    quantity=Decimal("0.05"),
                ),
            ],
        },
    )

    result = run_emergency_flatten(
        _settings(tmp_path, cancel_only=True),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.cancel_only is True
    assert len(result.cancelled_orders) == 1
    assert result.closed_positions == ()
    assert result.residual_positions == ()
    assert result.success is True
    call_names = [c[0] for c in exchange.calls]
    assert "submit_reduce_only_market_order" not in call_names
    assert "list_open_positions" not in call_names


# ---- residual paths ----


def test_cancel_rejected_recorded_as_residual_order(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_orders={
            instrument: [
                OpenOrder(
                    order_id="O_OK",
                    instrument_id=instrument,
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
                OpenOrder(
                    order_id="O_FAIL",
                    instrument_id=instrument,
                    side="SELL",
                    quantity=Decimal("0.02"),
                ),
            ],
        },
        cancel_outcomes={"O_OK": True, "O_FAIL": False},
    )

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is False
    assert {o.order_id for o in result.cancelled_orders} == {"O_OK"}
    assert len(result.residual_orders) == 1
    residual = result.residual_orders[0]
    assert residual.order_id == "O_FAIL"
    assert residual.reason == "cancel_rejected"


def test_cancel_exception_recorded_as_residual_order(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_orders={
            instrument: [
                OpenOrder(
                    order_id="O_RAISE",
                    instrument_id=instrument,
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
            ],
        },
        cancel_outcomes={"O_RAISE": RuntimeError},
    )

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is False
    assert result.cancelled_orders == ()
    assert len(result.residual_orders) == 1
    assert result.residual_orders[0].reason.startswith("cancel_exception:")


def test_fill_timeout_recorded_as_residual_position(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_positions={
            instrument: [
                OpenPosition(
                    instrument_id=instrument,
                    side="LONG",
                    quantity=Decimal("0.05"),
                ),
            ],
        },
        submit_outcomes={instrument: "EXCH-REDUCE-X"},
        # query_order falls back to a NEW status forever — caller must time out.
    )

    result = run_emergency_flatten(
        _settings(
            tmp_path,
            fill_timeout_seconds=1.0,
            poll_interval_seconds=0.5,
        ),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(step_seconds=0.4),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is False
    assert result.closed_positions == ()
    assert len(result.residual_positions) == 1
    residual = result.residual_positions[0]
    assert residual.reduce_order_id == "EXCH-REDUCE-X"
    assert residual.reason == "fill_timeout"
    assert residual.last_status == "NEW"


def test_submit_exception_recorded_as_residual_position(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_positions={
            instrument: [
                OpenPosition(
                    instrument_id=instrument,
                    side="SHORT",
                    quantity=Decimal("0.03"),
                ),
            ],
        },
        submit_outcomes={instrument: RuntimeError},
    )

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is False
    assert len(result.residual_positions) == 1
    residual = result.residual_positions[0]
    assert residual.reduce_order_id is None
    assert residual.reason.startswith("submit_exception:")
    assert residual.last_status is None


def test_rejected_close_order_recorded_as_residual_position(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_positions={
            instrument: [
                OpenPosition(
                    instrument_id=instrument,
                    side="LONG",
                    quantity=Decimal("0.05"),
                ),
            ],
        },
        submit_outcomes={instrument: "EXCH-REJECTED"},
        query_script={
            "EXCH-REJECTED": [
                OrderSnapshot(
                    order_id="EXCH-REJECTED",
                    instrument_id=instrument,
                    status="REJECTED",
                    filled_quantity=Decimal("0"),
                ),
            ],
        },
    )

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is False
    residual = result.residual_positions[0]
    assert residual.last_status == "REJECTED"
    assert residual.reason == "rejected"


def test_no_orders_no_positions_returns_success(tmp_path):
    exchange = _FakeExchange()

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is True
    assert result.cancelled_orders == ()
    assert result.residual_orders == ()
    assert result.closed_positions == ()
    assert result.residual_positions == ()


def test_flat_position_is_ignored(tmp_path):
    instrument = "BTCUSDT.BINANCE"
    exchange = _FakeExchange(
        open_positions={
            instrument: [
                OpenPosition(
                    instrument_id=instrument,
                    side="FLAT",
                    quantity=Decimal("0"),
                ),
            ],
        },
    )

    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.success is True
    assert result.closed_positions == ()
    assert result.residual_positions == ()
    # No submit should have been attempted.
    call_names = [c[0] for c in exchange.calls]
    assert "submit_reduce_only_market_order" not in call_names


# ---- signalling ----


def test_runner_sigterm_then_sigkill_when_pid_provided(tmp_path):
    signals_sent: list[tuple[int, int]] = []

    def _signaller(pid: int, sig: int) -> None:
        signals_sent.append((pid, sig))

    exchange = _FakeExchange()
    result = run_emergency_flatten(
        _settings(tmp_path, runner_pid=12345),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=_signaller,
    )

    assert result.runner_sigterm_sent is True
    assert result.runner_sigkill_sent is True
    assert signals_sent == [(12345, int(signal.SIGTERM)), (12345, int(signal.SIGKILL))]


def test_runner_sigterm_failure_skips_sigkill(tmp_path):
    def _signaller(pid: int, sig: int) -> None:
        raise ProcessLookupError(f"no such pid {pid}")

    exchange = _FakeExchange()
    result = run_emergency_flatten(
        _settings(tmp_path, runner_pid=99999),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=_signaller,
    )

    # Runner not present → sigterm reported false, no sigkill attempted.
    assert result.runner_sigterm_sent is False
    assert result.runner_sigkill_sent is False


# ---- alerts ----


def test_alerts_log_records_started_and_completed(tmp_path):
    exchange = _FakeExchange()
    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert result.alerts_path.exists()
    lines = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    msgs = [line["msg"] for line in lines]
    assert msgs == ["emergency_flatten_started", "emergency_flatten_completed"]
    assert all(line["severity"] == "critical" for line in lines)
    assert all(line["kind"] == "testnet" for line in lines)
    assert lines[1]["context"]["success"] is True


def test_alerts_log_appends_to_existing_file(tmp_path):
    # Pre-existing alerts.log should be appended to, never truncated.
    bundle = tmp_path / "data" / "testnet" / "20260518-122839Z-24bf3db2"
    (bundle / "logs").mkdir(parents=True, exist_ok=True)
    alerts_path = bundle / "logs" / "alerts.log"
    alerts_path.write_text(
        json.dumps(
            {
                "ts": "2026-05-18T12:00:00.000Z",
                "severity": "warning",
                "kind": "testnet",
                "run_id": "20260518-122839Z-24bf3db2",
                "msg": "ws_disconnected",
                "context": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exchange = _FakeExchange()
    result = run_emergency_flatten(
        _settings(tmp_path),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    lines = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [line["msg"] for line in lines] == [
        "ws_disconnected",
        "emergency_flatten_started",
        "emergency_flatten_completed",
    ]


# ---- audit shape ----


def test_audit_json_carries_all_required_fields(tmp_path):
    exchange = _FakeExchange(
        open_orders={
            "BTCUSDT.BINANCE": [
                OpenOrder(
                    order_id="O1",
                    instrument_id="BTCUSDT.BINANCE",
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
            ],
        },
        open_positions={
            "BTCUSDT.BINANCE": [
                OpenPosition(
                    instrument_id="BTCUSDT.BINANCE",
                    side="LONG",
                    quantity=Decimal("0.05"),
                ),
            ],
        },
        submit_outcomes={"BTCUSDT.BINANCE": "EXCH-R1"},
        query_script={
            "EXCH-R1": [
                OrderSnapshot(
                    order_id="EXCH-R1",
                    instrument_id="BTCUSDT.BINANCE",
                    status="FILLED",
                    filled_quantity=Decimal("0.05"),
                    avg_price=Decimal("30000"),
                ),
            ],
        },
    )

    result = run_emergency_flatten(
        _settings(tmp_path, runner_pid=12345),
        exchange=exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    payload = json.loads(result.audit_path.read_text(encoding="utf-8"))
    required = {
        "triggered_at",
        "triggered_by",
        "reason",
        "cancel_only",
        "kind",
        "run_id",
        "instrument_ids",
        "runner_pid",
        "runner_sigterm_sent",
        "runner_sigkill_sent",
        "cancelled_orders",
        "residual_orders",
        "closed_positions",
        "residual_positions",
        "final_account",
        "success",
        "elapsed_seconds",
        "audit_path",
        "alerts_path",
    }
    missing = required - set(payload)
    assert missing == set(), f"audit JSON missing fields: {missing}"
    assert payload["runner_pid"] == 12345
    assert payload["kind"] == "testnet"
    assert payload["instrument_ids"] == ["BTCUSDT.BINANCE"]


# ---- CLI dispatch ----


def test_cli_dispatches_through_main_with_injected_factory(tmp_path, capsys):
    exchange = _FakeExchange(
        open_orders={
            "BTCUSDT.BINANCE": [
                OpenOrder(
                    order_id="O1",
                    instrument_id="BTCUSDT.BINANCE",
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
            ],
        },
    )

    rc = main(
        [
            "--kind",
            "testnet",
            "--run-id",
            "20260518-122839Z-24bf3db2",
            "--operator",
            "pytest",
            "--reason",
            "cli-test",
            "--instrument-id",
            "BTCUSDT.BINANCE",
            "--output-root",
            str(tmp_path / "data" / "testnet"),
            "--cancel-only",
            "--fill-timeout-seconds",
            "1",
            "--cancel-timeout-seconds",
            "1",
            "--poll-interval-seconds",
            "0.1",
            "--sigkill-delay-seconds",
            "0",
        ],
        exchange_factory=lambda settings: exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cancel_only"] is True
    assert out["success"] is True
    assert len(out["cancelled_orders"]) == 1
    assert Path(out["audit_path"]).is_file()
    assert Path(out["alerts_path"]).is_file()


def test_cli_returns_1_when_residual_present(tmp_path):
    exchange = _FakeExchange(
        open_orders={
            "BTCUSDT.BINANCE": [
                OpenOrder(
                    order_id="O_FAIL",
                    instrument_id="BTCUSDT.BINANCE",
                    side="BUY",
                    quantity=Decimal("0.01"),
                ),
            ],
        },
        cancel_outcomes={"O_FAIL": False},
    )

    rc = main(
        [
            "--kind",
            "testnet",
            "--run-id",
            "20260518-122839Z-24bf3db2",
            "--operator",
            "pytest",
            "--reason",
            "cli-test",
            "--instrument-id",
            "BTCUSDT.BINANCE",
            "--output-root",
            str(tmp_path / "data" / "testnet"),
            "--cancel-only",
            "--fill-timeout-seconds",
            "1",
            "--poll-interval-seconds",
            "0.1",
            "--sigkill-delay-seconds",
            "0",
        ],
        exchange_factory=lambda settings: exchange,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 30, 0, tzinfo=UTC)),
        monotonic=_frozen_monotonic(),
        sleeper=_no_op_sleeper,
        signaller=lambda pid, sig: None,
    )

    assert rc == 1

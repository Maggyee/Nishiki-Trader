"""Unit tests for the ADR-008 §6.6 live-sidecar writer wiring."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from apps.strategies_nautilus.baseline_nautilus_strategy import LineageRecord
from apps.strategies_nautilus.runners.first_testnet_canary import (
    FirstCanaryStrategySpec,
    build_sidecar_recording,
)
from apps.strategies_nautilus.runners.sidecar_writer import (
    SidecarRecording,
    SidecarWriteResult,
    write_live_sidecars,
)
from apps.strategies_nautilus.runners.testnet_runner import (
    GitState,
    LongRunningTestnetSettings,
    StartupSettings,
    StartupValidationError,
    TestnetRuntimeTelemetry,
    run_long_running_testnet,
)

SOURCE = "freqai_linear_v1"
MODEL_VERSION = "linear-mom-train20240105"
VALID_KEY = "K" * 40
VALID_SECRET = "S" * 40
VALID_ENV = {
    "BINANCE_TESTNET_API_KEY": VALID_KEY,
    "BINANCE_TESTNET_API_SECRET": VALID_SECRET,
}
GIT_CLEAN = GitState(commit="a" * 40, dirty=False)


def _write_retro(retros_dir: Path) -> Path:
    retros_dir.mkdir(parents=True, exist_ok=True)
    path = retros_dir / "2026-05-17-freqai-linear-v1-hold-paper-simulated.md"
    path.write_text(
        "\n".join(
            [
                f"# Promotion review — {SOURCE} / {MODEL_VERSION}",
                "",
                "## 1. Source / model",
                "",
                f"- source: `{SOURCE}`",
                f"- model_version: `{MODEL_VERSION}`",
                "",
                "## 2. Current vs target policy",
                "",
                "- current_stage: `paper_simulated`",
                "- target_stage: `paper_simulated`",
                "",
                "## 7. Conclusion",
                "",
                "- decision: **HOLD**",
                "- decision_allowed: **yes**",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _startup(tmp_path: Path) -> StartupSettings:
    return StartupSettings(
        mode="testnet",
        kind="testnet",
        allow_real_credentials=True,
        source=SOURCE,
        model_version=MODEL_VERSION,
        policy_position_pct_multiplier=0.1,
        retros_dir=tmp_path / "retros",
        repo_root=tmp_path,
        operator="pytest",
    )


def _long_run_settings(tmp_path: Path, **overrides) -> LongRunningTestnetSettings:
    values = {
        "output_root": tmp_path / "data" / "testnet",
        "instrument_ids": ("BTCUSDT.BINANCE",),
        "starting_balance": 10_000.0,
        "max_run_seconds": 0.05,
        "telemetry_poll_seconds": 0.001,
        "heartbeat_interval_seconds": 30.0,
        "emergency_fill_timeout_seconds": 1.0,
        "emergency_poll_interval_seconds": 0.1,
    }
    values.update(overrides)
    return LongRunningTestnetSettings(**values)


def _frozen_clock(base: datetime, step_seconds: float = 1.0):
    state = {"t": base}

    def _now() -> datetime:
        current = state["t"]
        state["t"] = current + timedelta(seconds=step_seconds)
        return current

    return _now


class _FakeTrader:
    def __init__(self) -> None:
        self.strategies: list[object] = []
        self.actors: list[object] = []


class _BlockingFakeNode:
    def __init__(self, node_config: Any) -> None:
        self.node_config = node_config
        self.trader = _FakeTrader()
        self.build_called = False
        self.run_called = False
        self.stop_called = False
        self.dispose_called = False

    def add_data_client_factory(self, name: str, factory: type) -> None:
        return None

    def add_exec_client_factory(self, name: str, factory: type) -> None:
        return None

    def build(self) -> None:
        self.build_called = True

    def run(self, raise_exception: bool = False) -> None:
        self.run_called = True
        while not self.stop_called:
            time.sleep(0.001)

    def stop(self) -> None:
        self.stop_called = True

    def dispose(self) -> None:
        self.dispose_called = True


def _register_one_strategy(node: Any) -> None:
    node.trader.strategies.append(object())


# ---------------------------------------------------------------------------
# LongRunningTestnetSettings invariants
# ---------------------------------------------------------------------------


def test_settings_default_write_live_sidecars_is_false(tmp_path: Path) -> None:
    settings = _long_run_settings(tmp_path)
    assert settings.write_live_sidecars is False


def test_settings_rejects_write_live_sidecars_without_strategy_execution(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="write_live_sidecars=True requires enable_strategy_execution=True",
    ):
        _long_run_settings(
            tmp_path,
            write_live_sidecars=True,
            enable_strategy_execution=False,
        )


# ---------------------------------------------------------------------------
# run_long_running_testnet flag/recording cross-check
# ---------------------------------------------------------------------------


def test_long_run_rejects_flag_without_recording(tmp_path: Path) -> None:
    _write_retro(tmp_path / "retros")
    settings = _startup(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        enable_strategy_execution=True,
        write_live_sidecars=True,
    )

    with pytest.raises(StartupValidationError, match="sidecar_recording_required"):
        run_long_running_testnet(
            settings,
            run_settings,
            env=VALID_ENV,
            git_state=GIT_CLEAN,
            node_factory=lambda cfg: _BlockingFakeNode(cfg),
            register_strategies=_register_one_strategy,
            run_id="20260519-150000Z-aaaaaaaa",
        )


def test_long_run_rejects_recording_without_flag(tmp_path: Path) -> None:
    _write_retro(tmp_path / "retros")
    settings = _startup(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        enable_strategy_execution=True,
        write_live_sidecars=False,
    )
    recording = SidecarRecording(venue_name="BINANCE", lineage=[])

    with pytest.raises(
        StartupValidationError, match="write_live_sidecars_flag_required"
    ):
        run_long_running_testnet(
            settings,
            run_settings,
            env=VALID_ENV,
            git_state=GIT_CLEAN,
            node_factory=lambda cfg: _BlockingFakeNode(cfg),
            register_strategies=_register_one_strategy,
            sidecar_recording=recording,
            run_id="20260519-150000Z-bbbbbbbb",
        )


# ---------------------------------------------------------------------------
# Happy path + writer injection
# ---------------------------------------------------------------------------


def _make_dummy_result(bundle_root: Path) -> SidecarWriteResult:
    paths = {
        "orders": bundle_root / "orders.parquet",
        "fills": bundle_root / "fills.parquet",
        "positions": bundle_root / "positions.parquet",
        "account_balances": bundle_root / "account_balances.parquet",
        "signal_lineage": bundle_root / "signal_lineage.parquet",
    }
    for path in paths.values():
        path.write_bytes(b"parquet-stub")
    return SidecarWriteResult(
        paths=paths,
        orders_count=2,
        fills_count=2,
        positions_count=1,
        account_rows=3,
        lineage_rows=1,
    )


def test_long_run_invokes_sidecar_writer_with_recording(tmp_path: Path) -> None:
    _write_retro(tmp_path / "retros")
    settings = _startup(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        enable_strategy_execution=True,
        write_live_sidecars=True,
    )
    lineage = [
        LineageRecord(
            signal_id="sig-001",
            source=SOURCE,
            model_version=MODEL_VERSION,
            ts_event=1714521540000000000,
            decision="target_long",
            reason=None,
            client_order_ids=["O-001"],
            ts_decision=1714521540000000000,
        )
    ]
    recording = SidecarRecording(venue_name="BINANCE", lineage=lineage)
    base = datetime(2026, 5, 19, 15, 0, 0, tzinfo=UTC)
    captured: dict[str, Any] = {}

    def fake_writer(**kwargs: Any) -> SidecarWriteResult:
        captured.update(kwargs)
        bundle_root = kwargs["bundle_root"]
        return _make_dummy_result(bundle_root)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        clock_ns=lambda: 1714521540123456789,
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        register_strategies=_register_one_strategy,
        sidecar_recording=recording,
        live_sidecar_writer=fake_writer,
        run_id="20260519-150000Z-cccccccc",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert result.sidecar_error is None
    assert result.sidecar_write_result is not None
    assert result.sidecar_write_result.orders_count == 2
    assert captured["trader"] is not None
    assert captured["venue_name"] == "BINANCE"
    assert captured["lineage"] is lineage
    assert captured["bundle_root"] == result.bundle_root
    assert captured["report_ts_event_ns"] == 1714521540123456789

    runtime = result.runtime
    assert runtime["write_live_sidecars"] is True
    assert runtime["sidecar"]["success"] is True
    assert runtime["sidecar"]["error"] is None
    assert runtime["sidecar"]["result"]["fills_count"] == 2
    assert runtime["sidecar"]["result"]["lineage_rows"] == 1

    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["runtime"]["sidecar"]["success"] is True
    assert payload["runtime"]["sidecar"]["result"]["orders_count"] == 2

    runtime_log = [
        json.loads(line)
        for line in result.runtime_log_path.read_text(encoding="utf-8").splitlines()
    ]
    sidecar_events = [row for row in runtime_log if row.get("event") == "sidecar_write"]
    assert len(sidecar_events) == 1
    assert sidecar_events[0]["success"] is True

    payload_dict = result.to_dict()
    assert payload_dict["sidecar_write_result"]["orders_count"] == 2
    assert payload_dict["sidecar_write_result"]["paths"]["orders"].endswith(
        "orders.parquet"
    )


def test_long_run_records_sidecar_writer_exception(tmp_path: Path) -> None:
    _write_retro(tmp_path / "retros")
    settings = _startup(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        enable_strategy_execution=True,
        write_live_sidecars=True,
    )
    recording = SidecarRecording(venue_name="BINANCE", lineage=[])
    base = datetime(2026, 5, 19, 15, 0, 0, tzinfo=UTC)

    def failing_writer(**kwargs: Any) -> SidecarWriteResult:
        raise RuntimeError("trader cache empty")

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        clock_ns=lambda: 1714521540123456789,
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        register_strategies=_register_one_strategy,
        sidecar_recording=recording,
        live_sidecar_writer=failing_writer,
        run_id="20260519-150000Z-dddddddd",
    )

    assert result.exit_code == 0  # sidecar failure must not change exit code
    assert result.stop_reason == "max_duration"
    assert result.sidecar_write_result is None
    assert result.sidecar_error is not None
    assert "trader cache empty" in result.sidecar_error
    assert result.runtime["sidecar"]["success"] is False
    assert "trader cache empty" in result.runtime["sidecar"]["error"]


def test_long_run_skips_writer_when_flag_off(tmp_path: Path) -> None:
    _write_retro(tmp_path / "retros")
    settings = _startup(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        enable_strategy_execution=True,
        write_live_sidecars=False,
    )
    base = datetime(2026, 5, 19, 15, 0, 0, tzinfo=UTC)

    def boom(**kwargs: Any) -> SidecarWriteResult:
        raise AssertionError("writer must not run when flag is off")

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        register_strategies=_register_one_strategy,
        live_sidecar_writer=boom,
        run_id="20260519-150000Z-eeeeeeee",
    )

    assert result.exit_code == 0
    assert result.sidecar_write_result is None
    assert result.sidecar_error is None
    assert result.runtime["write_live_sidecars"] is False
    assert "sidecar" not in result.runtime


# ---------------------------------------------------------------------------
# write_live_sidecars (direct)
# ---------------------------------------------------------------------------


class _FakeReportTrader:
    """Reports the bare-minimum DataFrame shape `_prepare_reports` needs."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_orders_report(self) -> pd.DataFrame:
        self.calls.append("orders")
        return pd.DataFrame(
            [
                {
                    "client_order_id": "O-001",
                    "venue_order_id": "V-001",
                    "instrument_id": "BTCUSDT.BINANCE",
                    "side": "BUY",
                    "order_side": "BUY",
                    "quantity": "0.001",
                    "avg_px": "76778.75",
                    "type": "MARKET",
                    "status": "FILLED",
                    "ts_init": 1714521540000000000,
                    "ts_last": 1714521540000000000,
                    "tags": ["signal_id:sig-001"],
                }
            ]
        )

    def generate_fills_report(self) -> pd.DataFrame:
        self.calls.append("fills")
        return pd.DataFrame(
            [
                {
                    "client_order_id": "O-001",
                    "venue_order_id": "V-001",
                    "trade_id": "T-001",
                    "instrument_id": "BTCUSDT.BINANCE",
                    "side": "BUY",
                    "order_side": "BUY",
                    "last_qty": "0.001",
                    "last_px": "76778.75",
                    "commission": "0",
                    "currency": "USDT",
                    "ts_event": 1714521540000000000,
                }
            ]
        )

    def generate_positions_report(self) -> pd.DataFrame:
        self.calls.append("positions")
        return pd.DataFrame(
            [
                {
                    "position_id": "BTCUSDT.BINANCE-strategy-000",
                    "instrument_id": "BTCUSDT.BINANCE",
                    "strategy_id": "BaselineNautilusStrategy",
                    "side": "LONG",
                    "opening_order_id": "O-001",
                    "closing_order_id": "",
                    "quantity": "0.001",
                    "peak_qty": "0.001",
                    "avg_px_open": "76778.75",
                    "avg_px_close": "0",
                    "realized_pnl": "0",
                    "ts_init": 1714521540000000000,
                    "ts_opened": 1714521540000000000,
                    "ts_closed": 0,
                }
            ]
        )

    def generate_account_report(self, venue: Any) -> pd.DataFrame:
        self.calls.append(f"account:{venue}")
        return pd.DataFrame(
            [
                {
                    "account_id": "BINANCE-SPOT-master",
                    "currency": "USDT",
                    "total": "10000.0",
                    "free": "9998.0",
                    "locked": "2.0",
                }
            ]
        )


def test_write_live_sidecars_writes_five_parquet_files(tmp_path: Path) -> None:
    trader = _FakeReportTrader()
    lineage = [
        LineageRecord(
            signal_id="sig-001",
            source=SOURCE,
            model_version=MODEL_VERSION,
            ts_event=1714521540000000000,
            decision="target_long",
            reason=None,
            client_order_ids=["O-001"],
            ts_decision=1714521540000000000,
        )
    ]

    result = write_live_sidecars(
        trader=trader,
        venue_name="BINANCE",
        lineage=lineage,
        bundle_root=tmp_path,
        report_ts_event_ns=1714521540123456789,
    )

    assert trader.calls == ["orders", "fills", "positions", "account:BINANCE"]
    expected = {
        "orders.parquet",
        "fills.parquet",
        "positions.parquet",
        "account_balances.parquet",
        "signal_lineage.parquet",
    }
    actual = {p.name for p in tmp_path.iterdir()}
    assert expected.issubset(actual)
    assert result.orders_count == 1
    assert result.fills_count == 1
    assert result.positions_count == 1
    assert result.account_rows == 1
    assert result.lineage_rows == 1

    orders = pq.read_table(tmp_path / "orders.parquet").to_pandas()
    assert orders.iloc[0]["signal_id"] == "sig-001"
    fills = pq.read_table(tmp_path / "fills.parquet").to_pandas()
    assert fills.iloc[0]["signal_id"] == "sig-001"
    account = pq.read_table(tmp_path / "account_balances.parquet").to_pandas()
    assert int(account.iloc[0]["ts_event"]) == 1714521540123456789
    assert account.iloc[0]["venue"] == "BINANCE"
    lineage_df = pq.read_table(tmp_path / "signal_lineage.parquet").to_pandas()
    assert lineage_df.iloc[0]["signal_id"] == "sig-001"


# ---------------------------------------------------------------------------
# build_sidecar_recording helper
# ---------------------------------------------------------------------------


def test_build_sidecar_recording_shares_same_lineage_list() -> None:
    spec = FirstCanaryStrategySpec(
        source=SOURCE,
        model_version=MODEL_VERSION,
        signal_store_path=Path("data/bridge/signals.db"),
        instrument_id_str="BTCUSDT.BINANCE",
        bar_type_str="BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
        trade_size=__import__("decimal").Decimal("0.001"),
        base_currency_code="USDT",
        venue="BINANCE",
        position_pct_multiplier=0.1,
    )
    lineage: list[LineageRecord] = []

    recording = build_sidecar_recording(spec, lineage=lineage)

    assert recording.venue_name == "BINANCE"
    assert recording.lineage is lineage

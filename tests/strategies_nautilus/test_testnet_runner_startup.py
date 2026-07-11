"""Tests for ADR-008 Phase 3b testnet startup validation + connection probe."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.adapters.binance import (
    BINANCE,
    BinanceAccountType,
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment

from apps.strategies_nautilus.runners.emergency_flatten import (
    OpenOrder,
    OpenPosition,
)
from apps.strategies_nautilus.runners.testnet_runner import (
    EXIT_RUNTIME_ERROR,
    ConnectionProbeResult,
    ConnectionProbeSettings,
    GitState,
    LongRunningTestnetSettings,
    StartupSettings,
    StartupValidationError,
    TestnetRuntimeTelemetry,
    build_testnet_node_config,
    main,
    run_connection_probe,
    run_long_running_testnet,
    validate_startup,
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


def _write_retro(
    retros_dir: Path,
    *,
    source: str = SOURCE,
    model_version: str = MODEL_VERSION,
    decision: str = "HOLD",
    allowed: str = "yes",
    current_stage: str = "paper_simulated",
    target_stage: str = "paper_simulated",
) -> Path:
    retros_dir.mkdir(parents=True, exist_ok=True)
    path = retros_dir / "2026-05-17-freqai-linear-v1-hold-paper-simulated.md"
    path.write_text(
        "\n".join(
            [
                f"# Promotion review — {source} / {model_version}",
                "",
                "## 1. Source / model",
                "",
                f"- source: `{source}`",
                f"- model_version: `{model_version}`",
                "",
                "## 2. Current vs target policy",
                "",
                f"- current_stage: `{current_stage}`",
                f"- target_stage: `{target_stage}`",
                "",
                "## 7. Conclusion",
                "",
                f"- decision: **{decision}**",
                f"- decision_allowed: **{allowed}**",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _config(tmp_path: Path, **overrides) -> StartupSettings:
    values = {
        "mode": "testnet",
        "kind": "testnet",
        "allow_real_credentials": True,
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "policy_position_pct_multiplier": 0.2,
        "retros_dir": tmp_path / "retros",
        "repo_root": tmp_path,
        "operator": "pytest",
    }
    values.update(overrides)
    return StartupSettings(**values)


def test_validate_startup_passes_without_leaking_secret(tmp_path):
    retro_path = _write_retro(tmp_path / "retros")

    result = validate_startup(
        _config(tmp_path),
        env=VALID_ENV,
        git_state=GIT_CLEAN,
    )

    payload = result.to_dict()
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["mode"] == "testnet"
    assert payload["kind"] == "testnet"
    assert payload["runtime_data_mode"] == "exchange_ws"
    assert payload["runtime_order_mode"] == "exchange_testnet"
    assert payload["credentials_key_prefix"] == VALID_KEY[:8]
    assert payload["stage_evidence_path"] == str(retro_path)
    assert payload["adapter_plan"]["exchange"] == "binance"
    assert payload["adapter_plan"]["environment"] == "TESTNET"
    assert payload["adapter_plan"]["account_type"] == "SPOT"
    assert payload["adapter_plan"]["instrument_id"] == "BTCUSDT.BINANCE"
    assert payload["adapter_plan"]["embedded_credentials"] is False
    assert payload["adapter_plan"]["node_config_built"] is True
    assert payload["exchange_connected"] is False
    assert payload["bundle_written"] is False
    assert VALID_SECRET not in rendered
    assert VALID_KEY not in rendered


def test_validate_startup_requires_allow_real_credentials(tmp_path):
    _write_retro(tmp_path / "retros")

    with pytest.raises(StartupValidationError, match="allow_real_credentials"):
        validate_startup(
            _config(tmp_path, allow_real_credentials=False),
            env=VALID_ENV,
            git_state=GIT_CLEAN,
        )


def test_validate_startup_rejects_short_credentials(tmp_path):
    _write_retro(tmp_path / "retros")

    with pytest.raises(StartupValidationError, match="api_key_too_short"):
        validate_startup(
            _config(tmp_path),
            env={
                "BINANCE_TESTNET_API_KEY": "short",
                "BINANCE_TESTNET_API_SECRET": VALID_SECRET,
            },
            git_state=GIT_CLEAN,
        )


def test_validate_startup_rejects_dirty_git(tmp_path):
    _write_retro(tmp_path / "retros")

    with pytest.raises(StartupValidationError, match="git_dirty"):
        validate_startup(
            _config(tmp_path),
            env=VALID_ENV,
            git_state=GitState(commit="a" * 40, dirty=True),
        )


def test_validate_startup_requires_stage_evidence(tmp_path):
    with pytest.raises(StartupValidationError, match="missing_paper_simulated_retro"):
        validate_startup(
            _config(tmp_path),
            env=VALID_ENV,
            git_state=GIT_CLEAN,
        )


def test_validate_startup_rejects_multiplier_above_testnet_cap(tmp_path):
    _write_retro(tmp_path / "retros")

    with pytest.raises(StartupValidationError, match="policy_multiplier"):
        validate_startup(
            _config(tmp_path, policy_position_pct_multiplier=0.21),
            env=VALID_ENV,
            git_state=GIT_CLEAN,
        )


def test_validate_startup_accepts_promote_testnet_evidence(tmp_path):
    _write_retro(
        tmp_path / "retros",
        decision="PROMOTE",
        current_stage="paper_simulated",
        target_stage="testnet_canary",
    )

    result = validate_startup(
        _config(tmp_path),
        env=VALID_ENV,
        git_state=GIT_CLEAN,
    )

    assert result.stage_evidence_path.endswith(".md")


def test_build_testnet_node_config_uses_binance_spot_testnet_without_embedded_keys(
    tmp_path,
):
    config = _config(tmp_path)

    node_config = build_testnet_node_config(config)

    assert str(node_config.trader_id) == "TESTNET_TRADER-001"
    data_config = node_config.data_clients[BINANCE]
    exec_config = node_config.exec_clients[BINANCE]
    assert data_config.account_type == BinanceAccountType.SPOT
    assert exec_config.account_type == BinanceAccountType.SPOT
    assert data_config.environment == BinanceEnvironment.TESTNET
    assert exec_config.environment == BinanceEnvironment.TESTNET
    assert data_config.api_key is None
    assert data_config.api_secret is None
    assert exec_config.api_key is None
    assert exec_config.api_secret is None


def test_validate_startup_rejects_non_binance_instrument(tmp_path):
    _write_retro(tmp_path / "retros")

    with pytest.raises(StartupValidationError, match="instrument_venue_not_binance"):
        validate_startup(
            _config(tmp_path, instrument_id="BTCUSDT.COINBASE"),
            env=VALID_ENV,
            git_state=GIT_CLEAN,
        )


def test_validate_startup_rejects_non_spot_account_type(tmp_path):
    _write_retro(tmp_path / "retros")

    with pytest.raises(StartupValidationError, match="unsupported_account_type"):
        validate_startup(
            _config(tmp_path, account_type="USDT_FUTURES"),
            env=VALID_ENV,
            git_state=GIT_CLEAN,
        )


def test_cli_prints_json_summary(tmp_path, capsys):
    _write_retro(tmp_path / "retros")

    rc = main(
        [
            "--mode",
            "testnet",
            "--kind",
            "testnet",
            "--allow-real-credentials",
            "--source",
            SOURCE,
            "--model-version",
            MODEL_VERSION,
            "--policy-position-pct-multiplier",
            "0.2",
            "--retros-dir",
            str(tmp_path / "retros"),
            "--repo-root",
            str(tmp_path),
        ],
        env=VALID_ENV,
        git_state=GIT_CLEAN,
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["credentials_key_prefix"] == VALID_KEY[:8]
    assert out["adapter_plan"]["exchange_endpoint"] == "https://testnet.binance.vision"
    assert out["adapter_plan"]["embedded_credentials"] is False
    assert out["exchange_connected"] is False


# --- Connection probe (ADR-008 §6.2 controlled testnet connect) ---


class _FakeTrader:
    def __init__(self) -> None:
        self.strategies: list[object] = []
        self.actors: list[object] = []


class _FakeNode:
    """Records driver calls so probe wiring can be asserted without networking."""

    def __init__(self, node_config) -> None:
        self.node_config = node_config
        self.data_factories: list[tuple[str, type]] = []
        self.exec_factories: list[tuple[str, type]] = []
        self.build_called = False
        self.run_called = False
        self.stop_called = False
        self.dispose_called = False
        self.trader = _FakeTrader()

    def add_data_client_factory(self, name: str, factory: type) -> None:
        self.data_factories.append((name, factory))

    def add_exec_client_factory(self, name: str, factory: type) -> None:
        self.exec_factories.append((name, factory))

    def build(self) -> None:
        self.build_called = True

    def run(self, raise_exception: bool = False) -> None:
        self.run_called = True
        # A real node blocks; the probe stops it via a timer. The fake returns
        # immediately, simulating "stop fired right after connect succeeded".

    def stop(self) -> None:  # pragma: no cover — fake never reaches stop()
        self.stop_called = True

    def dispose(self) -> None:
        self.dispose_called = True


class _BlockingFakeNode(_FakeNode):
    """Blocks in run() until the runner calls stop()."""

    def run(self, raise_exception: bool = False) -> None:
        self.run_called = True
        while not self.stop_called:
            time.sleep(0.001)

    def stop(self) -> None:
        self.stop_called = True


@dataclass(frozen=True)
class _FakeFlattenResult:
    success: bool
    audit_path: Path


class _FakeRestartExchange:
    def __init__(
        self,
        *,
        open_orders: dict[str, list[OpenOrder]] | None = None,
        open_positions: dict[str, list[OpenPosition]] | None = None,
    ) -> None:
        self._open_orders = open_orders or {}
        self._open_positions = open_positions or {}

    def list_open_orders(self, instrument_id):
        return list(self._open_orders.get(instrument_id, []))

    def list_open_positions(self, instrument_id):
        return list(self._open_positions.get(instrument_id, []))


def _frozen_clock(base: datetime, step_seconds: float = 1.0):
    state = {"t": base}

    def _now() -> datetime:
        current = state["t"]
        state["t"] = current + timedelta(seconds=step_seconds)
        return current

    return _now


@pytest.fixture
def _probe_setup(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    probe_settings = ConnectionProbeSettings(
        output_root=tmp_path / "data" / "testnet",
        max_connect_seconds=0.1,
    )
    return settings, probe_settings


def _long_run_settings(tmp_path: Path, **overrides) -> LongRunningTestnetSettings:
    values = {
        "output_root": tmp_path / "data" / "testnet",
        "instrument_ids": ("BTCUSDT.BINANCE",),
        "starting_balance": 100000.0,
        "max_run_seconds": 0.2,
        "telemetry_poll_seconds": 0.001,
        "heartbeat_interval_seconds": 30.0,
        "daily_loss_limit_pct": 0.05,
        "exchange_error_burst_threshold": 50,
        "ws_reconnect_burst_threshold": 10,
        "emergency_fill_timeout_seconds": 1.0,
        "emergency_poll_interval_seconds": 0.1,
    }
    values.update(overrides)
    return LongRunningTestnetSettings(**values)


def _sequence_reader(samples: list[TestnetRuntimeTelemetry]):
    state = {"idx": 0}

    def _read() -> TestnetRuntimeTelemetry:
        idx = state["idx"]
        state["idx"] = idx + 1
        return samples[min(idx, len(samples) - 1)]

    return _read


def _write_previous_testnet_bundle(
    output_root: Path,
    *,
    run_id: str = "20260518-120000Z-abcdef12",
    runtime: dict | None = None,
    order_rows: list[dict] | None = None,
    position_rows: list[dict] | None = None,
) -> Path:
    bundle = output_root / run_id
    bundle.mkdir(parents=True)
    manifest = {
        "schema_version": "backtest.v1",
        "kind": "testnet",
        "run_id": run_id,
        "runtime": {
            "mode": "testnet",
            "processed_until_ns": 1_716_038_400_000_000_000,
            "restart_sequence": 1,
            "instrument_ids": ["BTCUSDT.BINANCE"],
            **(runtime or {}),
        },
    }
    (bundle / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if order_rows is not None:
        pd.DataFrame(order_rows).to_parquet(
            bundle / "orders.parquet",
            engine="pyarrow",
            index=False,
        )
    if position_rows is not None:
        pd.DataFrame(position_rows).to_parquet(
            bundle / "positions.parquet",
            engine="pyarrow",
            index=False,
        )
    return bundle


def test_run_connection_probe_writes_redacted_runtime_log(tmp_path, _probe_setup):
    settings, probe_settings = _probe_setup
    captured: dict[str, _FakeNode] = {}

    def _factory(node_config):
        node = _FakeNode(node_config)
        captured["node"] = node
        return node

    result = run_connection_probe(
        settings,
        probe_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=_factory,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)),
    )

    assert isinstance(result, ConnectionProbeResult)
    assert result.bundle_root.is_dir()
    assert result.runtime_log_path.exists()
    assert result.probe_summary_path.exists()
    assert result.stop_reason == "max_duration"
    assert result.error is None
    assert result.node_built is True
    assert result.node_run_invoked is True
    assert result.strategies_registered == 0
    assert result.actors_registered == 0

    log_text = result.runtime_log_path.read_text(encoding="utf-8")
    log_events = [json.loads(line) for line in log_text.splitlines() if line.strip()]
    event_names = [e["event"] for e in log_events]
    assert event_names[0] == "credentials_loaded"
    assert "node_built" in event_names
    assert "node_run_invoked" in event_names
    assert event_names[-1] == "shutdown"
    cred_event = log_events[0]
    assert cred_event["runtime"]["mode"] == "testnet"
    assert cred_event["runtime"]["order_mode"] == "exchange_testnet"
    assert cred_event["runtime"]["credentials_loaded"] is True
    assert cred_event["runtime"]["credentials_key_prefix"] == VALID_KEY[:8]

    summary_text = result.probe_summary_path.read_text(encoding="utf-8")
    summary = json.loads(summary_text)
    assert summary["startup"]["kind"] == "testnet"
    assert summary["startup"]["adapter_plan"]["environment"] == "TESTNET"
    assert summary["startup"]["credentials_key_prefix"] == VALID_KEY[:8]

    # Credentials must never be written to disk.
    assert VALID_KEY not in log_text
    assert VALID_SECRET not in log_text
    assert VALID_KEY not in summary_text
    assert VALID_SECRET not in summary_text

    # The probe must wire the real Binance live factories before connecting.
    node = captured["node"]
    assert node.build_called is True
    assert node.run_called is True
    assert node.dispose_called is True
    assert node.data_factories == [(BINANCE, BinanceLiveDataClientFactory)]
    assert node.exec_factories == [(BINANCE, BinanceLiveExecClientFactory)]
    assert node.trader.strategies == []
    assert node.trader.actors == []


def test_run_connection_probe_injects_credentials_into_node_config_only(
    tmp_path, _probe_setup
):
    settings, probe_settings = _probe_setup
    captured: dict[str, _FakeNode] = {}

    def _factory(node_config):
        node = _FakeNode(node_config)
        captured["node"] = node
        return node

    run_connection_probe(
        settings,
        probe_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=_factory,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)),
    )

    node = captured["node"]
    data_cfg = node.node_config.data_clients[BINANCE]
    exec_cfg = node.node_config.exec_clients[BINANCE]
    # In-memory config sees the real credentials so the adapter can sign requests.
    assert data_cfg.api_key == VALID_KEY
    assert data_cfg.api_secret == VALID_SECRET
    assert exec_cfg.api_key == VALID_KEY
    assert exec_cfg.api_secret == VALID_SECRET
    # But the testnet environment is still locked.
    assert data_cfg.environment == BinanceEnvironment.TESTNET
    assert exec_cfg.environment == BinanceEnvironment.TESTNET
    assert data_cfg.account_type == BinanceAccountType.SPOT


def test_run_connection_probe_runs_through_validation_gates(tmp_path):
    # Missing retro should be caught by validate_startup before any bundle dir
    # is created.
    settings = _config(tmp_path)
    probe_settings = ConnectionProbeSettings(
        output_root=tmp_path / "data" / "testnet",
        max_connect_seconds=0.1,
    )

    with pytest.raises(StartupValidationError, match="missing_paper_simulated_retro"):
        run_connection_probe(
            settings,
            probe_settings,
            env=VALID_ENV,
            git_state=GIT_CLEAN,
            node_factory=lambda cfg: _FakeNode(cfg),
        )

    # No bundle dir was created because validation failed before mkdir.
    assert not (tmp_path / "data" / "testnet").exists()


def test_run_connection_probe_refuses_to_run_with_registered_strategy(
    tmp_path, _probe_setup
):
    settings, probe_settings = _probe_setup

    def _factory_with_strategy(node_config):
        node = _FakeNode(node_config)
        node.trader.strategies.append(object())
        return node

    result = run_connection_probe(
        settings,
        probe_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=_factory_with_strategy,
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)),
    )

    assert result.stop_reason == "exception"
    assert result.error is not None
    assert "strategies" in result.error
    assert result.node_built is True
    assert result.node_run_invoked is False
    log_text = result.runtime_log_path.read_text(encoding="utf-8")
    assert "exception" in log_text


def test_run_connection_probe_raises_on_existing_bundle_dir(tmp_path, _probe_setup):
    settings, probe_settings = _probe_setup
    # Pre-create the expected run_id directory to force a collision.
    fixed_run_id = "20260518-120000Z-deadbeef"
    (probe_settings.output_root / fixed_run_id / "logs").mkdir(parents=True)

    with pytest.raises(FileExistsError):
        run_connection_probe(
            settings,
            probe_settings,
            env=VALID_ENV,
            git_state=GIT_CLEAN,
            node_factory=lambda cfg: _FakeNode(cfg),
            clock=_frozen_clock(datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)),
            run_id=fixed_run_id,
        )


def test_testnet_runner_does_not_reference_live_binance_credentials():
    """The testnet runner must read only BINANCE_TESTNET_* — never live keys."""
    import inspect

    from apps.strategies_nautilus.runners import testnet_runner

    source = inspect.getsource(testnet_runner)
    # Live-mainnet credential names must not appear anywhere in the runner.
    assert "BINANCE_API_KEY" not in source
    assert "BINANCE_API_SECRET" not in source
    # The only Binance environment we touch must be TESTNET.
    assert "BinanceEnvironment.MAINNET" not in source
    assert "BinanceEnvironment.US" not in source


def test_cli_connect_probe_dispatches_to_probe(tmp_path, capsys):
    _write_retro(tmp_path / "retros")
    output_root = tmp_path / "data" / "testnet"

    rc = main(
        [
            "--mode",
            "testnet",
            "--kind",
            "testnet",
            "--allow-real-credentials",
            "--source",
            SOURCE,
            "--model-version",
            MODEL_VERSION,
            "--policy-position-pct-multiplier",
            "0.2",
            "--retros-dir",
            str(tmp_path / "retros"),
            "--repo-root",
            str(tmp_path),
            "--connect-probe",
            "--output-root",
            str(output_root),
            "--max-connect-seconds",
            "0.1",
        ],
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _FakeNode(cfg),
        clock=_frozen_clock(datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)),
    )

    assert rc == 0
    out_text = capsys.readouterr().out
    payload = json.loads(out_text)
    assert payload["stop_reason"] == "max_duration"
    assert payload["startup"]["kind"] == "testnet"
    assert payload["error"] is None
    assert Path(payload["runtime_log_path"]).is_file()
    assert Path(payload["probe_summary_path"]).is_file()
    assert VALID_KEY not in out_text
    assert VALID_SECRET not in out_text


# --- Long-running guarded testnet shell (ADR-008 §6.3c auto-flatten wiring) ---


def test_long_run_auto_flattens_on_daily_loss_limit(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(tmp_path, max_run_seconds=1.0)
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    flatten_calls = []

    def _flatten(flatten_settings):
        flatten_calls.append(flatten_settings)
        audit_path = (
            flatten_settings.output_root
            / flatten_settings.run_id
            / "emergency_flatten.json"
        )
        audit_path.write_text("{}", encoding="utf-8")
        return _FakeFlattenResult(success=True, audit_path=audit_path)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(seconds=1),
                    daily_pnl=-5000.0,
                    account_total_usdt=95000.0,
                ),
            ]
        ),
        flatten_runner=_flatten,
        run_id="20260518-130000Z-feedface",
    )

    assert result.exit_code == 4
    assert result.stop_reason == "emergency_flatten"
    assert result.auto_flatten_trigger == "kill_switch_fired"
    assert result.emergency_flatten_success is True
    assert len(flatten_calls) == 1
    assert flatten_calls[0].kind == "testnet"
    assert flatten_calls[0].instrument_ids == ("BTCUSDT.BINANCE",)
    assert "daily PnL" in flatten_calls[0].reason

    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert alerts[0]["msg"] == "kill_switch_fired"
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["context"]["daily_pnl"] == -5000.0

    manifest_text = result.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    runtime = manifest["runtime"]
    assert runtime["shutdown_reason"] == "emergency_flatten"
    assert runtime["daily_pnl"] == -5000.0
    assert runtime["auto_flatten_trigger"] == "kill_switch_fired"
    assert runtime["credentials_key_prefix"] == VALID_KEY[:8]
    rendered = json.dumps(result.to_dict(), sort_keys=True)
    assert VALID_KEY not in rendered
    assert VALID_SECRET not in rendered
    assert VALID_KEY not in manifest_text
    assert VALID_SECRET not in manifest_text
    runtime_log_text = result.runtime_log_path.read_text(encoding="utf-8")
    assert VALID_KEY not in runtime_log_text
    assert VALID_SECRET not in runtime_log_text


def test_long_run_auto_flattens_on_exchange_error_burst(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(tmp_path, max_run_seconds=1.0)
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    flatten_calls = []

    def _flatten(flatten_settings):
        flatten_calls.append(flatten_settings)
        return _FakeFlattenResult(
            success=True,
            audit_path=flatten_settings.output_root
            / flatten_settings.run_id
            / "emergency_flatten.json",
        )

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(minutes=10),
                    daily_pnl=0.0,
                    exchange_error_count=51,
                ),
            ]
        ),
        flatten_runner=_flatten,
        run_id="20260518-130000Z-bad00001",
    )

    assert result.exit_code == 4
    assert result.auto_flatten_trigger == "exchange_error_burst"
    assert len(flatten_calls) == 1
    assert "exchange_error_count" in flatten_calls[0].reason
    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert alerts[0]["severity"] == "error"
    assert alerts[0]["context"]["exchange_error_count_hour"] == 51


def test_long_run_auto_flattens_on_ws_reconnect_burst(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(tmp_path, max_run_seconds=1.0)
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    flatten_calls = []

    def _flatten(flatten_settings):
        flatten_calls.append(flatten_settings)
        return _FakeFlattenResult(
            success=False,
            audit_path=flatten_settings.output_root
            / flatten_settings.run_id
            / "emergency_flatten.json",
        )

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(minutes=5),
                    daily_pnl=0.0,
                    ws_reconnect_count=11,
                ),
            ]
        ),
        flatten_runner=_flatten,
        run_id="20260518-130000Z-bad00002",
    )

    assert result.exit_code == 5
    assert result.auto_flatten_trigger == "ws_reconnect_burst"
    assert result.emergency_flatten_success is False
    assert len(flatten_calls) == 1
    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert alerts[0]["context"]["ws_reconnect_count_hour"] == 11


def test_long_run_emits_ws_disconnected_on_transition(tmp_path):
    """ADR-008 §5.4 ws_disconnected fires on True→False, re-arms after reconnect,
    and does not block a clean max_duration exit."""
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(tmp_path, max_run_seconds=0.2)
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0, ws_connected=True),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(seconds=1),
                    daily_pnl=0.0,
                    ws_connected=False,
                    ws_reconnect_count=1,
                ),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(seconds=2),
                    daily_pnl=0.0,
                    ws_connected=True,
                    ws_reconnect_count=1,
                ),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(seconds=3),
                    daily_pnl=0.0,
                    ws_connected=False,
                    ws_reconnect_count=2,
                ),
            ]
        ),
        flatten_runner=lambda settings: pytest.fail("flatten must not run"),
        run_id="20260518-130000Z-aaaaaa01",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert result.auto_flatten_trigger is None

    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ws_alerts = [a for a in alerts if a["msg"] == "ws_disconnected"]
    assert len(ws_alerts) == 2
    assert all(a["severity"] == "warning" for a in ws_alerts)
    assert all(a["kind"] == "testnet" for a in ws_alerts)
    assert ws_alerts[0]["context"]["ws_reconnect_count"] == 1
    assert ws_alerts[1]["context"]["ws_reconnect_count"] == 2


def test_long_run_emits_data_gap_exceeded_tolerance(tmp_path):
    """ADR-008 §5.4 data_gap_exceeded_tolerance fires once per gap incident
    and stays deduped while the gap persists."""
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        max_run_seconds=0.2,
        data_gap_tolerance_seconds=1.0,
    )
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    fresh_bar_ns = int(base.timestamp() * 1_000_000_000)
    stale_bar_sample_ts = base + timedelta(seconds=10)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(
                    ts=base,
                    daily_pnl=0.0,
                    last_bar_ns=fresh_bar_ns,
                ),
                TestnetRuntimeTelemetry(
                    ts=stale_bar_sample_ts,
                    daily_pnl=0.0,
                    last_bar_ns=fresh_bar_ns,
                ),
            ]
        ),
        flatten_runner=lambda settings: pytest.fail("flatten must not run"),
        run_id="20260518-130000Z-aaaaaa02",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert result.auto_flatten_trigger is None

    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gap_alerts = [a for a in alerts if a["msg"] == "data_gap_exceeded_tolerance"]
    assert len(gap_alerts) == 1
    assert gap_alerts[0]["severity"] == "error"
    assert gap_alerts[0]["kind"] == "testnet"
    assert gap_alerts[0]["context"]["last_bar_ns"] == fresh_bar_ns
    assert gap_alerts[0]["context"]["tolerance_seconds"] == 1.0
    assert gap_alerts[0]["context"]["gap_seconds"] >= 9.0


def test_long_run_emits_signal_lag_exceeded_threshold(tmp_path):
    """ADR-008 §5.4 signal_lag_exceeded_threshold fires once per lag incident
    and stays deduped while the lag persists."""
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        max_run_seconds=0.2,
        signal_lag_threshold_seconds=1.0,
    )
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    fresh_signal_ns = int(base.timestamp() * 1_000_000_000)
    stale_signal_sample_ts = base + timedelta(seconds=10)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(
                    ts=base,
                    daily_pnl=0.0,
                    last_signal_ns=fresh_signal_ns,
                ),
                TestnetRuntimeTelemetry(
                    ts=stale_signal_sample_ts,
                    daily_pnl=0.0,
                    last_signal_ns=fresh_signal_ns,
                ),
            ]
        ),
        flatten_runner=lambda settings: pytest.fail("flatten must not run"),
        run_id="20260518-130000Z-aaaaaa03",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert result.auto_flatten_trigger is None

    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lag_alerts = [a for a in alerts if a["msg"] == "signal_lag_exceeded_threshold"]
    assert len(lag_alerts) == 1
    assert lag_alerts[0]["severity"] == "warning"
    assert lag_alerts[0]["kind"] == "testnet"
    assert lag_alerts[0]["context"]["last_signal_ns"] == fresh_signal_ns
    assert lag_alerts[0]["context"]["threshold_seconds"] == 1.0
    assert lag_alerts[0]["context"]["lag_seconds"] >= 9.0


def test_adr_008_5_4_alert_kinds_have_runner_or_watchdog_wiring():
    """ADR-008 §5.4 lists 9 mandatory alert msgs. Every one must have a
    triggering code path in the runner or watchdog source."""
    from pathlib import Path as _Path

    project_root = _Path(__file__).resolve().parents[2]
    runner_src = (
        project_root
        / "apps"
        / "strategies_nautilus"
        / "runners"
        / "testnet_runner.py"
    ).read_text(encoding="utf-8")
    flatten_src = (
        project_root
        / "apps"
        / "strategies_nautilus"
        / "runners"
        / "emergency_flatten.py"
    ).read_text(encoding="utf-8")
    watchdog_src = (
        project_root / "infra" / "watchdog" / "watchdog.py"
    ).read_text(encoding="utf-8")

    sources = {
        "kill_switch_fired": runner_src,
        "restart_drift_detected": runner_src,
        "data_gap_exceeded_tolerance": runner_src,
        "signal_lag_exceeded_threshold": runner_src,
        "exchange_error_burst": runner_src,
        "ws_disconnected": runner_src,
        "heartbeat_lost": watchdog_src,
        "emergency_flatten_started": flatten_src,
        "emergency_flatten_completed": flatten_src,
    }
    for kind, src in sources.items():
        assert kind in src, f"§5.4 alert kind {kind!r} has no wiring"


def test_long_run_stops_cleanly_at_max_duration_without_auto_flatten(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(tmp_path, max_run_seconds=0.02)
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        run_id="20260518-130000Z-cafefeed",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert result.auto_flatten_trigger is None
    assert result.emergency_flatten_success is None
    assert result.manifest_path.is_file()
    heartbeat_lines = (
        result.bundle_root / "logs" / "heartbeat.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len([line for line in heartbeat_lines if line.strip()]) >= 1


def test_long_run_restart_reconciliation_allows_clean_restart(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    output_root = tmp_path / "data" / "testnet"
    previous_run_id = "20260518-120000Z-abcdef12"
    previous_bundle = _write_previous_testnet_bundle(output_root, run_id=previous_run_id)
    previous_manifest = previous_bundle / "run_manifest.json"
    run_settings = _long_run_settings(
        tmp_path,
        output_root=output_root,
        max_run_seconds=0.02,
        previous_run_id=previous_run_id,
        restart_reason="planned process restart",
    )
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        restart_exchange_factory=lambda run_id: _FakeRestartExchange(),
        run_id="20260518-130000Z-12345678",
    )

    assert result.exit_code == 0
    runtime = result.runtime
    assert runtime["previous_run_id"] == previous_run_id
    assert runtime["previous_processed_until_ns"] == 1_716_038_400_000_000_000
    assert runtime["previous_manifest_sha256"]
    assert runtime["previous_manifest_sha256"] == hashlib.sha256(
        previous_manifest.read_bytes()
    ).hexdigest()
    assert runtime["restart_sequence"] == 2
    assert runtime["restart_reason"] == "planned process restart"
    assert runtime["restart_drift_detected"] is False
    assert runtime["restart_order_drift"] == {
        "missing_on_exchange": [],
        "unexpected_on_exchange": [],
    }
    assert runtime["restart_position_drift"] == {
        "missing_on_exchange": [],
        "unexpected_on_exchange": [],
    }


def test_long_run_restart_sets_signal_cursor_from_previous_processed_until(tmp_path):
    from decimal import Decimal

    from apps.bridge.store import SignalStore
    from apps.bridge.validators import Authorization
    from apps.strategies_nautilus.baseline_nautilus_strategy import (
        BaselineNautilusStrategy,
        BaselineNautilusStrategyParams,
        SignalStorePollingSource,
    )
    from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig

    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    output_root = tmp_path / "data" / "testnet"
    previous_run_id = "20260518-120000Z-abcdef12"
    _write_previous_testnet_bundle(output_root, run_id=previous_run_id)
    run_settings = _long_run_settings(
        tmp_path,
        output_root=output_root,
        max_run_seconds=0.02,
        previous_run_id=previous_run_id,
        restart_reason="planned process restart",
        enable_strategy_execution=True,
    )
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)

    signal_store = SignalStore(tmp_path / "signals.db")
    source = SignalStorePollingSource(
        store=signal_store,
        source=SOURCE,
        model_version=MODEL_VERSION,
        cursor_ns=9_999,
    )

    def register_one_strategy(node):
        strategy = BaselineNautilusStrategy(
            params=BaselineNautilusStrategyParams(
                instrument_id=__import__("nautilus_trader.model.identifiers", fromlist=["InstrumentId"]).InstrumentId.from_str("BTCUSDT.BINANCE"),
                bar_type=__import__("nautilus_trader.model.data", fromlist=["BarType"]).BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"),
                baseline_config=BaselineStrategyConfig(
                    venue="BINANCE",
                    auth=Authorization(
                        allowed_sources=frozenset({SOURCE}),
                        allowed_model_versions=frozenset({MODEL_VERSION}),
                    ),
                ),
                trade_size=Decimal("0.001"),
                equity_currency=__import__("nautilus_trader.model.objects", fromlist=["Currency"]).Currency.from_str("USDT"),
                signal_source=source,
            )
        )
        node.trader.strategies.append(strategy)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _StrategyBlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        restart_exchange_factory=lambda run_id: _FakeRestartExchange(),
        register_strategies=register_one_strategy,
        run_id="20260518-130000Z-12345678",
    )

    assert result.exit_code == 0
    assert source.cursor_ns == 1_716_038_400_000_000_001
    assert result.runtime["resume_from_ns"] == 1_716_038_400_000_000_001




def test_long_run_restart_drift_exits_3_and_writes_alert(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    output_root = tmp_path / "data" / "testnet"
    previous_run_id = "20260518-120000Z-abcdef12"
    _write_previous_testnet_bundle(output_root, run_id=previous_run_id)
    run_settings = _long_run_settings(
        tmp_path,
        output_root=output_root,
        max_run_seconds=1.0,
        previous_run_id=previous_run_id,
        restart_reason="recover after crash",
    )
    exchange = _FakeRestartExchange(
        open_orders={
            "BTCUSDT.BINANCE": [
                OpenOrder(
                    order_id="EXCH-OPEN-1",
                    instrument_id="BTCUSDT.BINANCE",
                    side="BUY",
                    quantity=Decimal("0.01"),
                )
            ],
        }
    )

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: pytest.fail("node must not build on restart drift"),
        clock=_frozen_clock(datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)),
        telemetry_reader=lambda: pytest.fail("telemetry must not start on drift"),
        restart_exchange_factory=lambda run_id: exchange,
        run_id="20260518-130000Z-12345678",
    )

    assert result.exit_code == 3
    assert result.stop_reason == "restart_drift_detected"
    assert result.node_built is False
    assert result.node_run_invoked is False
    assert result.runtime["restart_drift_detected"] is True
    assert result.runtime["restart_order_drift"]["unexpected_on_exchange"] == [
        {
            "order_id": "EXCH-OPEN-1",
            "instrument_id": "BTCUSDT.BINANCE",
            "side": "BUY",
            "quantity": "0.01",
        }
    ]
    alerts = [
        json.loads(line)
        for line in result.alerts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(alerts) == 1
    assert alerts[0]["msg"] == "restart_drift_detected"
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["kind"] == "testnet"
    assert alerts[0]["context"]["restart_drift_detected"] is True
    assert alerts[0]["context"]["restart_order_drift"][
        "unexpected_on_exchange"
    ] == result.runtime["restart_order_drift"]["unexpected_on_exchange"]


def test_long_run_restart_reconciliation_compares_local_sidecars(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    output_root = tmp_path / "data" / "testnet"
    previous_run_id = "20260518-120000Z-abcdef12"
    _write_previous_testnet_bundle(
        output_root,
        run_id=previous_run_id,
        order_rows=[
            {
                "order_id": "LOCAL-OPEN-1",
                "instrument_id": "BTCUSDT.BINANCE",
                "side": "SELL",
                "quantity": 0.02,
                "status": "NEW",
            },
            {
                "order_id": "LOCAL-FILLED",
                "instrument_id": "BTCUSDT.BINANCE",
                "side": "BUY",
                "quantity": 0.01,
                "status": "FILLED",
            },
        ],
        position_rows=[
            {
                "instrument_id": "BTCUSDT.BINANCE",
                "side": "LONG",
                "quantity": 0.05,
                "closed_ts": 0,
            },
            {
                "instrument_id": "BTCUSDT.BINANCE",
                "side": "LONG",
                "quantity": 0.03,
                "closed_ts": 1,
            },
        ],
    )
    run_settings = _long_run_settings(
        tmp_path,
        output_root=output_root,
        previous_run_id=previous_run_id,
        restart_reason="compare sidecars",
    )
    exchange = _FakeRestartExchange(
        open_orders={
            "BTCUSDT.BINANCE": [
                OpenOrder(
                    order_id="LOCAL-OPEN-1",
                    instrument_id="BTCUSDT.BINANCE",
                    side="SELL",
                    quantity=Decimal("0.0200"),
                )
            ],
        },
        open_positions={
            "BTCUSDT.BINANCE": [
                OpenPosition(
                    instrument_id="BTCUSDT.BINANCE",
                    side="LONG",
                    quantity=Decimal("0.050000"),
                )
            ],
        },
    )

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(
            ts=datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC),
            daily_pnl=0.0,
        ),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        restart_exchange_factory=lambda run_id: exchange,
        run_id="20260518-130000Z-12345678",
    )

    assert result.exit_code == 0
    assert result.runtime["restart_drift_detected"] is False


def test_cli_long_run_dispatches_and_returns_flatten_exit_code(tmp_path, capsys):
    _write_retro(tmp_path / "retros")
    base = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)

    def _flatten(flatten_settings):
        return _FakeFlattenResult(
            success=True,
            audit_path=flatten_settings.output_root
            / flatten_settings.run_id
            / "emergency_flatten.json",
        )

    rc = main(
        [
            "--mode",
            "testnet",
            "--kind",
            "testnet",
            "--allow-real-credentials",
            "--source",
            SOURCE,
            "--model-version",
            MODEL_VERSION,
            "--policy-position-pct-multiplier",
            "0.2",
            "--retros-dir",
            str(tmp_path / "retros"),
            "--repo-root",
            str(tmp_path),
            "--long-run",
            "--output-root",
            str(tmp_path / "data" / "testnet"),
            "--starting-balance",
            "100000",
            "--max-run-seconds",
            "1",
            "--telemetry-poll-seconds",
            "0.001",
        ],
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _BlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=_sequence_reader(
            [
                TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
                TestnetRuntimeTelemetry(
                    ts=base + timedelta(seconds=1),
                    daily_pnl=-5000.0,
                ),
            ]
        ),
        flatten_runner=_flatten,
    )

    assert rc == 4
    out_text = capsys.readouterr().out
    payload = json.loads(out_text)
    assert payload["auto_flatten_trigger"] == "kill_switch_fired"
    assert payload["exit_code"] == 4
    assert Path(payload["manifest_path"]).is_file()
    assert VALID_KEY not in out_text
    assert VALID_SECRET not in out_text


# ---------------------------------------------------------------------------
# ADR-008 §6.6 enable_strategy_execution double-signoff
# ---------------------------------------------------------------------------


class _StrategyBlockingFakeNode(_BlockingFakeNode):
    """Fake node whose trader can record arbitrary strategy/actor objects."""

    def register(self, *, strategy: object | None = None, actor: object | None = None) -> None:
        if strategy is not None:
            self.trader.strategies.append(strategy)
        if actor is not None:
            self.trader.actors.append(actor)


def test_long_run_default_still_rejects_registered_strategy(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(tmp_path, max_run_seconds=0.02)
    base = datetime(2026, 5, 19, 13, 0, 0, tzinfo=UTC)

    node_holder: dict[str, _StrategyBlockingFakeNode] = {}

    def factory(cfg):
        node = _StrategyBlockingFakeNode(cfg)
        node.trader.strategies.append(object())  # operator forgot to opt in
        node_holder["node"] = node
        return node

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=factory,
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        run_id="20260519-130000Z-deadbeef",
    )

    assert result.stop_reason == "exception"
    assert result.error is not None
    assert "refuses to run with registered strategies" in result.error
    assert result.runtime["enable_strategy_execution"] is False
    # The default-mode gate observes the trader's actual count before it
    # raises, so the recorded runtime reflects "fact: 1 strategy was sitting
    # there; we refused to run anyway".
    assert result.runtime["strategies_registered"] == 1


def test_long_run_enable_strategy_execution_requires_callback(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        max_run_seconds=0.02,
        enable_strategy_execution=True,
    )
    base = datetime(2026, 5, 19, 13, 0, 0, tzinfo=UTC)

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _StrategyBlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        run_id="20260519-130000Z-cafef00d",
    )

    assert result.stop_reason == "exception"
    assert result.error is not None
    assert "requires a register_strategies callback" in result.error


def test_long_run_enable_strategy_execution_rejects_zero_strategies(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        max_run_seconds=0.02,
        enable_strategy_execution=True,
    )
    base = datetime(2026, 5, 19, 13, 0, 0, tzinfo=UTC)

    def register_nothing(node):
        return None

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _StrategyBlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        register_strategies=register_nothing,
        run_id="20260519-130000Z-1234abcd",
    )

    assert result.stop_reason == "exception"
    assert result.error is not None
    assert "strategies_registered=0" in result.error


def test_long_run_enable_strategy_execution_records_registered_counts(tmp_path):
    _write_retro(tmp_path / "retros")
    settings = _config(tmp_path)
    run_settings = _long_run_settings(
        tmp_path,
        max_run_seconds=0.02,
        enable_strategy_execution=True,
    )
    base = datetime(2026, 5, 19, 13, 0, 0, tzinfo=UTC)

    register_calls: list[object] = []

    def register_one_strategy(node):
        register_calls.append(node)
        node.trader.strategies.append(object())

    result = run_long_running_testnet(
        settings,
        run_settings,
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _StrategyBlockingFakeNode(cfg),
        clock=_frozen_clock(base),
        telemetry_reader=lambda: TestnetRuntimeTelemetry(ts=base, daily_pnl=0.0),
        flatten_runner=lambda settings: pytest.fail("flatten should not run"),
        register_strategies=register_one_strategy,
        run_id="20260519-130000Z-feedbabe",
    )

    assert result.exit_code == 0
    assert result.stop_reason == "max_duration"
    assert len(register_calls) == 1
    assert result.runtime["enable_strategy_execution"] is True
    assert result.runtime["strategies_registered"] == 1
    assert result.runtime["actors_registered"] == 0
    runtime_log = (
        result.bundle_root / "logs" / "runtime.log"
    ).read_text(encoding="utf-8").splitlines()
    register_events = [
        json.loads(line)
        for line in runtime_log
        if json.loads(line).get("event") == "strategies_registered"
    ]
    assert len(register_events) == 1
    assert register_events[0]["strategies"] == 1
    assert register_events[0]["actors"] == 0


def test_long_run_settings_default_enable_strategy_execution_is_false():
    settings = LongRunningTestnetSettings(
        output_root=Path("/tmp/nonexistent"),
        instrument_ids=("BTCUSDT.BINANCE",),
        starting_balance=10_000.0,
    )
    assert settings.enable_strategy_execution is False


def test_long_run_cli_flag_flows_into_settings(tmp_path):
    """CLI surface acquires --enable-strategy-execution; the CLI itself
    cannot wire a strategy, so a long-run invocation that opts in without
    Python-side register_strategies must still be rejected."""

    _write_retro(tmp_path / "retros")
    output_root = tmp_path / "data" / "testnet"
    retros_dir = tmp_path / "retros"

    rc = main(
        [
            "--mode",
            "testnet",
            "--kind",
            "testnet",
            "--allow-real-credentials",
            "--source",
            "freqai_linear_v1",
            "--model-version",
            "linear-mom-train20240105",
            "--policy-position-pct-multiplier",
            "0.1",
            "--retros-dir",
            str(retros_dir),
            "--repo-root",
            str(tmp_path),
            "--operator",
            "nishiki",
            "--instrument-id",
            "BTCUSDT.BINANCE",
            "--long-run",
            "--starting-balance",
            "10000",
            "--max-run-seconds",
            "0.02",
            "--telemetry-poll-seconds",
            "0.001",
            "--output-root",
            str(output_root),
            "--enable-strategy-execution",
        ],
        env=VALID_ENV,
        git_state=GIT_CLEAN,
        node_factory=lambda cfg: _StrategyBlockingFakeNode(cfg),
    )

    assert rc == EXIT_RUNTIME_ERROR

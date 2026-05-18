"""Tests for ADR-008 Phase 3b testnet startup validation + connection probe."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from nautilus_trader.adapters.binance import (
    BINANCE,
    BinanceAccountType,
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment

from apps.strategies_nautilus.runners.testnet_runner import (
    ConnectionProbeResult,
    ConnectionProbeSettings,
    GitState,
    StartupSettings,
    StartupValidationError,
    build_testnet_node_config,
    main,
    run_connection_probe,
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

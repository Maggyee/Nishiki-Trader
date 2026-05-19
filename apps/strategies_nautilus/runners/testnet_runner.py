"""ADR-008 Phase 3b testnet startup guard + connection probe.

This module guards every step before a real Binance testnet connection. The
``validate_startup`` path enforces ADR-008 §4 and builds a credential-less
adapter config used for audit. The ``run_connection_probe`` path layers on top:
after validation it builds a credentialed Nautilus Binance Spot **testnet**
``TradingNode``, connects it briefly without registering any strategies or
actors, then stops. The probe writes ``data/testnet/<run_id>/logs/runtime.log``
with a redacted ``credentials_loaded`` event and a small
``connection_probe.json`` summary; it never emits a strategy, never submits an
order, and never writes the full API key or secret anywhere on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from nautilus_trader.adapters.binance import (
    BINANCE,
    BinanceAccountType,
    BinanceDataClientConfig,
    BinanceExecClientConfig,
    BinanceInstrumentProviderConfig,
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.common.urls import get_http_base_url
from nautilus_trader.config import (
    CacheConfig,
    LiveDataEngineConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.model.identifiers import InstrumentId, TraderId

MODE_TESTNET = "testnet"
KIND_TESTNET = "testnet"
ORDER_MODE_TESTNET = "exchange_testnet"
DATA_MODE_EXCHANGE_WS = "exchange_ws"
KEY_ENV = "BINANCE_TESTNET_API_KEY"
SECRET_ENV = "BINANCE_TESTNET_API_SECRET"
MIN_CREDENTIAL_LENGTH = 32
TESTNET_MAX_MULTIPLIER = 0.2
DEFAULT_TESTNET_INSTRUMENT_ID = "BTCUSDT.BINANCE"
DEFAULT_TESTNET_ACCOUNT_TYPE = "SPOT"
DEFAULT_TESTNET_TRADER_ID = "TESTNET_TRADER-001"
DEFAULT_LONG_RUN_SECONDS = 3600.0
DEFAULT_TELEMETRY_POLL_SECONDS = 1.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_DAILY_LOSS_LIMIT_PCT = 0.05
DEFAULT_EXCHANGE_ERROR_BURST_THRESHOLD = 50
DEFAULT_WS_RECONNECT_BURST_THRESHOLD = 10
DEFAULT_DATA_GAP_TOLERANCE_SECONDS = 120.0
DEFAULT_SIGNAL_LAG_THRESHOLD_SECONDS = 60.0
EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_STARTUP_VALIDATION = 2
EXIT_RESTART_DRIFT = 3
EXIT_EMERGENCY_FLATTEN_SUCCESS = 4
EXIT_EMERGENCY_FLATTEN_FAILED = 5
TERMINAL_ORDER_STATUSES = frozenset(
    {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
)


class StartupValidationError(ValueError):
    """Raised when ADR-008 §4.2 startup checks fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


@dataclass(frozen=True)
class CredentialAudit:
    credentials_source: str
    credentials_key_prefix: str


@dataclass(frozen=True)
class StageEvidence:
    path: str
    decision: str
    current_stage: str | None
    target_stage: str | None


@dataclass(frozen=True)
class TestnetAdapterPlan:
    exchange: str
    venue: str
    client_id: str
    account_type: str
    environment: str
    exchange_endpoint: str
    instrument_id: str
    trader_id: str
    data_client_factory: str
    exec_client_factory: str
    data_client_config: str
    exec_client_config: str
    credentials_source: str
    credentials_key_prefix: str
    embedded_credentials: bool = False
    node_config_built: bool = True


@dataclass(frozen=True)
class StartupSettings:
    mode: str
    kind: str
    allow_real_credentials: bool
    source: str
    model_version: str
    policy_position_pct_multiplier: float
    retros_dir: Path
    repo_root: Path
    operator: str = "nishiki"
    instrument_id: str = DEFAULT_TESTNET_INSTRUMENT_ID
    account_type: str = DEFAULT_TESTNET_ACCOUNT_TYPE
    trader_id: str = DEFAULT_TESTNET_TRADER_ID


@dataclass(frozen=True)
class StartupCheckResult:
    mode: str
    kind: str
    runtime_mode: str
    runtime_data_mode: str
    runtime_order_mode: str
    source: str
    model_version: str
    policy_position_pct_multiplier: float
    git_commit: str
    git_dirty: bool
    credentials_source: str
    credentials_key_prefix: str
    stage_evidence_path: str
    operator: str
    adapter_plan: TestnetAdapterPlan
    exchange_connected: bool = False
    bundle_written: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectionProbeSettings:
    output_root: Path
    max_connect_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_connect_seconds <= 0:
            raise ValueError(
                f"max_connect_seconds must be positive, got {self.max_connect_seconds}"
            )


@dataclass(frozen=True)
class ConnectionProbeResult:
    startup: StartupCheckResult
    run_id: str
    bundle_root: Path
    runtime_log_path: Path
    probe_summary_path: Path
    started_at: str
    finished_at: str
    elapsed_seconds: float
    max_connect_seconds: float
    stop_reason: str
    error: str | None
    node_built: bool
    node_run_invoked: bool
    strategies_registered: int = 0
    actors_registered: int = 0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["bundle_root"] = str(self.bundle_root)
        payload["runtime_log_path"] = str(self.runtime_log_path)
        payload["probe_summary_path"] = str(self.probe_summary_path)
        return payload


@dataclass(frozen=True)
class TestnetRuntimeTelemetry:
    """One runtime sample for ADR-008 §5.2 auto-flatten checks."""

    __test__ = False

    ts: datetime
    daily_pnl: float
    exchange_error_count: int = 0
    ws_reconnect_count: int = 0
    account_total_usdt: float | None = None
    open_orders: int | None = None
    open_positions: int | None = None
    last_bar_ns: int | None = None
    last_signal_ns: int | None = None
    ws_connected: bool = True

    def __post_init__(self) -> None:
        if self.exchange_error_count < 0:
            raise ValueError("exchange_error_count must be non-negative")
        if self.ws_reconnect_count < 0:
            raise ValueError("ws_reconnect_count must be non-negative")


@dataclass(frozen=True)
class AutoFlattenTrigger:
    msg: str
    severity: str
    reason: str
    context: dict[str, object]


@dataclass
class AdvisoryAlertState:
    """Mutable dedup state for ADR-008 §5.4 warning/error alerts.

    These alerts (``ws_disconnected``, ``data_gap_exceeded_tolerance``,
    ``signal_lag_exceeded_threshold``) only land in ``logs/alerts.log`` — they
    never trigger auto-flatten or change the runner exit code.
    """

    __test__ = False

    ws_connected_prev: bool = True
    data_gap_active: bool = False
    signal_lag_active: bool = False


@dataclass(frozen=True)
class LongRunningTestnetSettings:
    output_root: Path
    instrument_ids: tuple[str, ...]
    starting_balance: float
    max_run_seconds: float = DEFAULT_LONG_RUN_SECONDS
    telemetry_poll_seconds: float = DEFAULT_TELEMETRY_POLL_SECONDS
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    daily_loss_limit_pct: float = DEFAULT_DAILY_LOSS_LIMIT_PCT
    exchange_error_burst_threshold: int = DEFAULT_EXCHANGE_ERROR_BURST_THRESHOLD
    ws_reconnect_burst_threshold: int = DEFAULT_WS_RECONNECT_BURST_THRESHOLD
    data_gap_tolerance_seconds: float = DEFAULT_DATA_GAP_TOLERANCE_SECONDS
    signal_lag_threshold_seconds: float = DEFAULT_SIGNAL_LAG_THRESHOLD_SECONDS
    emergency_fill_timeout_seconds: float = 60.0
    emergency_poll_interval_seconds: float = 1.0
    previous_run_id: str | None = None
    restart_reason: str | None = None
    enable_strategy_execution: bool = False

    def __post_init__(self) -> None:
        if not self.instrument_ids:
            raise ValueError("at least one instrument_id is required")
        if self.starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        if self.max_run_seconds <= 0:
            raise ValueError("max_run_seconds must be positive")
        if self.telemetry_poll_seconds <= 0:
            raise ValueError("telemetry_poll_seconds must be positive")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        if not 0 < self.daily_loss_limit_pct <= 1:
            raise ValueError("daily_loss_limit_pct must be in (0, 1]")
        if self.exchange_error_burst_threshold < 0:
            raise ValueError("exchange_error_burst_threshold must be non-negative")
        if self.ws_reconnect_burst_threshold < 0:
            raise ValueError("ws_reconnect_burst_threshold must be non-negative")
        if self.data_gap_tolerance_seconds <= 0:
            raise ValueError("data_gap_tolerance_seconds must be positive")
        if self.signal_lag_threshold_seconds <= 0:
            raise ValueError("signal_lag_threshold_seconds must be positive")
        if self.emergency_fill_timeout_seconds <= 0:
            raise ValueError("emergency_fill_timeout_seconds must be positive")
        if self.emergency_poll_interval_seconds <= 0:
            raise ValueError("emergency_poll_interval_seconds must be positive")
        if self.previous_run_id and not self.restart_reason:
            raise ValueError("restart_reason is required with previous_run_id")
        if self.restart_reason and not self.previous_run_id:
            raise ValueError("previous_run_id is required with restart_reason")


@dataclass(frozen=True)
class RestartReconciliation:
    previous_run_id: str
    previous_manifest_sha256: str
    previous_processed_until_ns: int | None
    restart_sequence: int
    restart_reason: str
    restart_order_drift: dict[str, list[dict[str, str]]]
    restart_position_drift: dict[str, list[dict[str, str]]]

    @property
    def drift_detected(self) -> bool:
        return bool(
            self.restart_order_drift["missing_on_exchange"]
            or self.restart_order_drift["unexpected_on_exchange"]
            or self.restart_position_drift["missing_on_exchange"]
            or self.restart_position_drift["unexpected_on_exchange"]
        )

    def runtime_fields(self) -> dict[str, object]:
        return {
            "previous_run_id": self.previous_run_id,
            "previous_manifest_sha256": self.previous_manifest_sha256,
            "previous_processed_until_ns": self.previous_processed_until_ns,
            "restart_sequence": self.restart_sequence,
            "restart_reason": self.restart_reason,
            "restart_order_drift": self.restart_order_drift,
            "restart_position_drift": self.restart_position_drift,
            "restart_drift_detected": self.drift_detected,
        }


@dataclass(frozen=True)
class LongRunningTestnetResult:
    startup: StartupCheckResult
    run_id: str
    bundle_root: Path
    runtime_log_path: Path
    alerts_path: Path
    manifest_path: Path
    started_at: str
    finished_at: str
    elapsed_seconds: float
    max_run_seconds: float
    stop_reason: str
    error: str | None
    node_built: bool
    node_run_invoked: bool
    runtime: dict[str, object]
    auto_flatten_trigger: str | None = None
    emergency_flatten_success: bool | None = None
    emergency_flatten_path: Path | None = None

    @property
    def exit_code(self) -> int:
        if self.stop_reason == "restart_drift_detected":
            return EXIT_RESTART_DRIFT
        if self.auto_flatten_trigger is not None:
            return (
                EXIT_EMERGENCY_FLATTEN_SUCCESS
                if self.emergency_flatten_success
                else EXIT_EMERGENCY_FLATTEN_FAILED
            )
        return EXIT_OK if self.error is None else EXIT_RUNTIME_ERROR

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["bundle_root"] = str(self.bundle_root)
        payload["runtime_log_path"] = str(self.runtime_log_path)
        payload["alerts_path"] = str(self.alerts_path)
        payload["manifest_path"] = str(self.manifest_path)
        if self.emergency_flatten_path is not None:
            payload["emergency_flatten_path"] = str(self.emergency_flatten_path)
        payload["exit_code"] = self.exit_code
        return payload


NodeFactory = Callable[[TradingNodeConfig], Any]
ClockFn = Callable[[], datetime]
TelemetryReader = Callable[[], TestnetRuntimeTelemetry]
FlattenRunner = Callable[[Any], Any]
RestartExchangeFactory = Callable[[str], Any]


def validate_startup(
    config: StartupSettings,
    *,
    env: Mapping[str, str] | None = None,
    git_state: GitState | None = None,
) -> StartupCheckResult:
    """Validate ADR-008 §4 startup requirements without connecting anywhere."""

    _check_mode_kind(config.mode, config.kind)
    credential_audit = _credential_audit(env or os.environ)
    if not config.allow_real_credentials:
        raise StartupValidationError(
            "allow_real_credentials_required",
            "--allow-real-credentials is required for testnet startup",
        )

    state = git_state or _git_state(config.repo_root)
    if state.dirty:
        raise StartupValidationError(
            "git_dirty",
            "testnet startup requires a clean git worktree",
        )

    if not config.source:
        raise StartupValidationError("source_required", "--source is required")
    if not config.model_version:
        raise StartupValidationError(
            "model_version_required",
            "--model-version is required",
        )
    if not 0.0 <= config.policy_position_pct_multiplier <= TESTNET_MAX_MULTIPLIER:
        raise StartupValidationError(
            "policy_multiplier_above_testnet_cap",
            "SourcePolicy.position_pct_multiplier must be in "
            f"[0, {TESTNET_MAX_MULTIPLIER}] for testnet_canary, got "
            f"{config.policy_position_pct_multiplier}",
        )

    evidence = _find_stage_evidence(
        retros_dir=config.retros_dir,
        source=config.source,
        model_version=config.model_version,
    )
    if evidence is None:
        raise StartupValidationError(
            "missing_paper_simulated_retro",
            "no decision_allowed paper_simulated hold or testnet_canary promote "
            f"retro found for {config.source} / {config.model_version}",
        )

    node_config = build_testnet_node_config(config)
    adapter_plan = _adapter_plan_from_node_config(
        settings=config,
        node_config=node_config,
        credential_audit=credential_audit,
    )

    return StartupCheckResult(
        mode=config.mode,
        kind=config.kind,
        runtime_mode=MODE_TESTNET,
        runtime_data_mode=DATA_MODE_EXCHANGE_WS,
        runtime_order_mode=ORDER_MODE_TESTNET,
        source=config.source,
        model_version=config.model_version,
        policy_position_pct_multiplier=config.policy_position_pct_multiplier,
        git_commit=state.commit,
        git_dirty=state.dirty,
        credentials_source=f"env:{KEY_ENV},{SECRET_ENV}",
        credentials_key_prefix=credential_audit.credentials_key_prefix,
        stage_evidence_path=evidence.path,
        operator=config.operator,
        adapter_plan=adapter_plan,
    )


def build_testnet_node_config(
    config: StartupSettings,
    *,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> TradingNodeConfig:
    """Build the Nautilus Binance Spot testnet node config.

    ``api_key`` / ``api_secret`` are ``None`` by default — the audit path uses
    that form and asserts no credentials reach the config. The connection
    probe passes real testnet credentials from environment variables; those
    values live in memory only and never appear in any serialized output.
    """

    _check_mode_kind(config.mode, config.kind)
    account_type = _parse_binance_account_type(config.account_type)
    instrument_id = _parse_instrument_id(config.instrument_id)
    if str(instrument_id.venue) != BINANCE:
        raise StartupValidationError(
            "instrument_venue_not_binance",
            f"testnet runner only supports Binance instruments, got {instrument_id}",
        )

    instrument_provider = BinanceInstrumentProviderConfig(
        load_ids=frozenset([instrument_id]),
        query_commission_rates=False,
    )
    return TradingNodeConfig(
        trader_id=TraderId(config.trader_id),
        logging=LoggingConfig(log_level="INFO", use_pyo3=True),
        data_engine=LiveDataEngineConfig(graceful_shutdown_on_exception=True),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            open_check_open_only=False,
            filter_unclaimed_external_orders=True,
            graceful_shutdown_on_exception=True,
        ),
        cache=CacheConfig(timestamps_as_iso8601=True, flush_on_start=False),
        data_clients={
            BINANCE: BinanceDataClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=account_type,
                environment=BinanceEnvironment.TESTNET,
                instrument_provider=instrument_provider,
            ),
        },
        exec_clients={
            BINANCE: BinanceExecClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=account_type,
                environment=BinanceEnvironment.TESTNET,
                instrument_provider=instrument_provider,
                max_retries=3,
                log_rejected_due_post_only_as_warning=False,
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )


def _parse_binance_account_type(value: str) -> BinanceAccountType:
    normalized = value.upper()
    if normalized != BinanceAccountType.SPOT.value:
        raise StartupValidationError(
            "unsupported_account_type",
            "Phase 3b currently supports only Binance Spot testnet "
            f"({BinanceAccountType.SPOT.value}), got {value!r}",
        )
    return BinanceAccountType.SPOT


def _parse_instrument_id(value: str) -> InstrumentId:
    try:
        return InstrumentId.from_str(value)
    except ValueError as exc:
        raise StartupValidationError(
            "invalid_instrument_id",
            f"--instrument-id must be a Nautilus InstrumentId, got {value!r}",
        ) from exc


def _adapter_plan_from_node_config(
    *,
    settings: StartupSettings,
    node_config: TradingNodeConfig,
    credential_audit: CredentialAudit,
) -> TestnetAdapterPlan:
    data_config = node_config.data_clients[BINANCE]
    exec_config = node_config.exec_clients[BINANCE]
    endpoint = get_http_base_url(
        exec_config.account_type,
        BinanceEnvironment.TESTNET,
        False,
    )
    return TestnetAdapterPlan(
        exchange="binance",
        venue=BINANCE,
        client_id=BINANCE,
        account_type=exec_config.account_type.value,
        environment=exec_config.environment.value,
        exchange_endpoint=endpoint,
        instrument_id=settings.instrument_id,
        trader_id=str(node_config.trader_id),
        data_client_factory=(
            f"{BinanceLiveDataClientFactory.__module__}."
            f"{BinanceLiveDataClientFactory.__name__}"
        ),
        exec_client_factory=(
            f"{BinanceLiveExecClientFactory.__module__}."
            f"{BinanceLiveExecClientFactory.__name__}"
        ),
        data_client_config=data_config.__class__.__name__,
        exec_client_config=exec_config.__class__.__name__,
        credentials_source=credential_audit.credentials_source,
        credentials_key_prefix=credential_audit.credentials_key_prefix,
        embedded_credentials=bool(
            data_config.api_key
            or data_config.api_secret
            or exec_config.api_key
            or exec_config.api_secret
        ),
    )

def run_connection_probe(
    settings: StartupSettings,
    probe: ConnectionProbeSettings,
    *,
    env: Mapping[str, str] | None = None,
    git_state: GitState | None = None,
    node_factory: NodeFactory | None = None,
    clock: ClockFn | None = None,
    run_id: str | None = None,
) -> ConnectionProbeResult:
    """Validate, connect, and immediately stop a Binance Spot testnet node.

    The probe never registers a strategy or an actor, so the node cannot
    submit any orders even while connected. Real testnet credentials are
    injected into the in-memory ``TradingNodeConfig`` only; they never reach
    ``runtime.log``, ``connection_probe.json``, or any other on-disk artifact.
    """

    effective_env: Mapping[str, str] = env if env is not None else os.environ
    now: ClockFn = clock if clock is not None else _utc_now
    factory: NodeFactory = (
        node_factory if node_factory is not None else _default_node_factory
    )

    startup = validate_startup(settings, env=effective_env, git_state=git_state)

    started = now()
    rid = run_id or _make_run_id(started)
    bundle_root = probe.output_root / rid
    logs_dir = bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=False)
    runtime_log_path = logs_dir / "runtime.log"
    probe_summary_path = bundle_root / "connection_probe.json"

    started_at = _iso_ms_utc(started)
    _append_runtime_event(
        runtime_log_path,
        {
            "event": "credentials_loaded",
            "ts": started_at,
            "run_id": rid,
            "operator": settings.operator,
            "kind": KIND_TESTNET,
            "runtime": {
                "mode": MODE_TESTNET,
                "data_mode": DATA_MODE_EXCHANGE_WS,
                "order_mode": ORDER_MODE_TESTNET,
                "exchange": "binance",
                "exchange_endpoint": startup.adapter_plan.exchange_endpoint,
                "credentials_source": startup.credentials_source,
                "credentials_key_prefix": startup.credentials_key_prefix,
                "credentials_loaded": True,
            },
        },
    )

    node_config = build_testnet_node_config(
        settings,
        api_key=effective_env[KEY_ENV],
        api_secret=effective_env[SECRET_ENV],
    )

    node_built = False
    node_run_invoked = False
    stop_reason = "max_duration"
    error: str | None = None
    strategies_registered = 0
    actors_registered = 0

    node = factory(node_config)
    try:
        node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
        node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)
        node.build()
        node_built = True
        _append_runtime_event(
            runtime_log_path,
            {"event": "node_built", "ts": _iso_ms_utc(now())},
        )

        strategies_registered, actors_registered = _trader_counts(node)
        if strategies_registered or actors_registered:
            raise RuntimeError(
                "connection probe refuses to run with registered strategies "
                f"({strategies_registered}) or actors ({actors_registered})"
            )

        node_run_invoked = True
        _append_runtime_event(
            runtime_log_path,
            {
                "event": "node_run_invoked",
                "ts": _iso_ms_utc(now()),
                "max_connect_seconds": probe.max_connect_seconds,
            },
        )
        _run_until_timeout(node, probe.max_connect_seconds)
    except Exception as exc:  # noqa: BLE001 — probe must always write summary
        stop_reason = "exception"
        error = repr(exc)
        _append_runtime_event(
            runtime_log_path,
            {"event": "exception", "ts": _iso_ms_utc(now()), "error": error},
        )
    finally:
        _dispose_node(node, runtime_log_path, now)

    finished = now()
    finished_at = _iso_ms_utc(finished)
    elapsed = max(0.0, (finished - started).total_seconds())

    _append_runtime_event(
        runtime_log_path,
        {
            "event": "shutdown",
            "ts": finished_at,
            "elapsed_seconds": elapsed,
            "stop_reason": stop_reason,
            "node_built": node_built,
            "node_run_invoked": node_run_invoked,
            "strategies_registered": strategies_registered,
            "actors_registered": actors_registered,
        },
    )

    result = ConnectionProbeResult(
        startup=startup,
        run_id=rid,
        bundle_root=bundle_root,
        runtime_log_path=runtime_log_path,
        probe_summary_path=probe_summary_path,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=elapsed,
        max_connect_seconds=probe.max_connect_seconds,
        stop_reason=stop_reason,
        error=error,
        node_built=node_built,
        node_run_invoked=node_run_invoked,
        strategies_registered=strategies_registered,
        actors_registered=actors_registered,
    )
    probe_summary_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def run_long_running_testnet(
    settings: StartupSettings,
    run_settings: LongRunningTestnetSettings,
    *,
    env: Mapping[str, str] | None = None,
    git_state: GitState | None = None,
    node_factory: NodeFactory | None = None,
    clock: ClockFn | None = None,
    telemetry_reader: TelemetryReader | None = None,
    flatten_runner: FlattenRunner | None = None,
    restart_exchange_factory: RestartExchangeFactory | None = None,
    register_strategies: Callable[[Any], None] | None = None,
    run_id: str | None = None,
) -> LongRunningTestnetResult:
    """Run the guarded ADR-008 §6.3c testnet shell with auto-flatten triggers.

    This is still a guard-rail runner: it reuses the Phase 3b Binance Spot
    testnet connection path and monitors runtime counters for §5.2 thresholds.
    The automatic stop path calls the same ``run_emergency_flatten`` surface as
    the operator CLI. No LLM, FreqAI, or direct order shortcut is introduced.
    """

    effective_env: Mapping[str, str] = env if env is not None else os.environ
    now: ClockFn = clock if clock is not None else _utc_now
    factory: NodeFactory = (
        node_factory if node_factory is not None else _default_node_factory
    )
    reader: TelemetryReader = (
        telemetry_reader
        if telemetry_reader is not None
        else lambda: TestnetRuntimeTelemetry(
            ts=now(),
            daily_pnl=0.0,
            exchange_error_count=0,
            ws_reconnect_count=0,
            account_total_usdt=run_settings.starting_balance,
            open_orders=0,
            open_positions=0,
            ws_connected=True,
        )
    )
    flatten: FlattenRunner = (
        flatten_runner if flatten_runner is not None else _default_flatten_runner
    )
    exchange_factory: RestartExchangeFactory = (
        restart_exchange_factory
        if restart_exchange_factory is not None
        else lambda current_run_id: _default_restart_exchange(
            settings=settings,
            run_settings=run_settings,
            run_id=current_run_id,
        )
    )

    startup = validate_startup(settings, env=effective_env, git_state=git_state)
    started = now()
    rid = run_id or _make_run_id(started)
    bundle_root = run_settings.output_root / rid
    logs_dir = bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=False)
    runtime_log_path = logs_dir / "runtime.log"
    alerts_path = logs_dir / "alerts.log"
    manifest_path = bundle_root / "run_manifest.json"
    started_at = _iso_ms_utc(started)

    _append_runtime_event(
        runtime_log_path,
        {
            "event": "credentials_loaded",
            "ts": started_at,
            "run_id": rid,
            "operator": settings.operator,
            "kind": KIND_TESTNET,
            "runtime": _base_testnet_runtime(
                startup=startup,
                run_settings=run_settings,
                shutdown_reason="starting",
            ),
        },
    )

    restart_reconciliation: RestartReconciliation | None = None
    if run_settings.previous_run_id is not None:
        restart_reconciliation = _reconcile_restart(
            run_settings=run_settings,
            exchange=exchange_factory(rid),
        )
        _append_runtime_event(
            runtime_log_path,
            {
                "event": "restart_reconciliation",
                "ts": _iso_ms_utc(now()),
                **restart_reconciliation.runtime_fields(),
            },
        )
        if restart_reconciliation.drift_detected:
            _append_alert_event(
                alerts_path,
                severity="critical",
                kind=KIND_TESTNET,
                run_id=rid,
                msg="restart_drift_detected",
                ts=_iso_ms_utc(now()),
                context=restart_reconciliation.runtime_fields(),
            )
            finished = now()
            finished_at = _iso_ms_utc(finished)
            elapsed = max(0.0, (finished - started).total_seconds())
            runtime = _base_testnet_runtime(
                startup=startup,
                run_settings=run_settings,
                shutdown_reason="restart_drift_detected",
                restart=restart_reconciliation,
            )
            _append_runtime_event(
                runtime_log_path,
                {
                    "event": "shutdown",
                    "ts": finished_at,
                    "elapsed_seconds": elapsed,
                    "stop_reason": "restart_drift_detected",
                    "node_built": False,
                    "node_run_invoked": False,
                },
            )
            result = LongRunningTestnetResult(
                startup=startup,
                run_id=rid,
                bundle_root=bundle_root,
                runtime_log_path=runtime_log_path,
                alerts_path=alerts_path,
                manifest_path=manifest_path,
                started_at=started_at,
                finished_at=finished_at,
                elapsed_seconds=elapsed,
                max_run_seconds=run_settings.max_run_seconds,
                stop_reason="restart_drift_detected",
                error=None,
                node_built=False,
                node_run_invoked=False,
                runtime=runtime,
            )
            _write_long_run_manifest(result)
            return result

    node_config = build_testnet_node_config(
        settings,
        api_key=effective_env[KEY_ENV],
        api_secret=effective_env[SECRET_ENV],
    )

    node_built = False
    node_run_invoked = False
    stop_reason = "node_stopped"
    error: str | None = None
    strategies_registered = 0
    actors_registered = 0
    latest_sample: dict[str, TestnetRuntimeTelemetry] = {}
    trigger_box: dict[str, AutoFlattenTrigger] = {}
    stop_reason_box: dict[str, str] = {}
    stop_event = threading.Event()

    node = factory(node_config)
    monitor_thread: threading.Thread | None = None
    timeout_thread: threading.Thread | None = None

    try:
        node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
        node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)
        node.build()
        node_built = True
        _append_runtime_event(
            runtime_log_path,
            {"event": "node_built", "ts": _iso_ms_utc(now())},
        )

        if run_settings.enable_strategy_execution:
            if register_strategies is None:
                raise RuntimeError(
                    "enable_strategy_execution=True requires a register_strategies "
                    "callback; refusing to start the long-running testnet runner "
                    "without an explicit strategy wiring step"
                )
            register_strategies(node)
            strategies_registered, actors_registered = _trader_counts(node)
            if strategies_registered < 1:
                raise RuntimeError(
                    "enable_strategy_execution=True but register_strategies "
                    "callback left strategies_registered="
                    f"{strategies_registered}; refusing to start"
                )
            _append_runtime_event(
                runtime_log_path,
                {
                    "event": "strategies_registered",
                    "ts": _iso_ms_utc(now()),
                    "strategies": strategies_registered,
                    "actors": actors_registered,
                },
            )
        else:
            strategies_registered, actors_registered = _trader_counts(node)
            if strategies_registered or actors_registered:
                raise RuntimeError(
                    "long-running testnet runner refuses to run with registered "
                    f"strategies ({strategies_registered}) or actors "
                    f"({actors_registered}); pass "
                    "enable_strategy_execution=True (and a register_strategies "
                    "callback) to allow strategy execution explicitly"
                )

        monitor_thread = threading.Thread(
            target=_monitor_long_run,
            kwargs={
                "run_settings": run_settings,
                "reader": reader,
                "runtime_log_path": runtime_log_path,
                "alerts_path": alerts_path,
                "kind": KIND_TESTNET,
                "run_id": rid,
                "node": node,
                "stop_event": stop_event,
                "latest_sample": latest_sample,
                "trigger_box": trigger_box,
                "stop_reason_box": stop_reason_box,
            },
            daemon=True,
        )
        timeout_thread = threading.Thread(
            target=_stop_after_max_duration,
            kwargs={
                "node": node,
                "stop_event": stop_event,
                "stop_reason_box": stop_reason_box,
                "max_seconds": run_settings.max_run_seconds,
            },
            daemon=True,
        )
        monitor_thread.start()
        timeout_thread.start()

        node_run_invoked = True
        _append_runtime_event(
            runtime_log_path,
            {
                "event": "node_run_invoked",
                "ts": _iso_ms_utc(now()),
                "max_run_seconds": run_settings.max_run_seconds,
            },
        )
        node.run(raise_exception=False)
    except Exception as exc:  # noqa: BLE001 — runner must always write manifest
        stop_reason = "exception"
        error = repr(exc)
        stop_event.set()
        _append_runtime_event(
            runtime_log_path,
            {"event": "exception", "ts": _iso_ms_utc(now()), "error": error},
        )
    finally:
        stop_event.set()
        if monitor_thread is not None:
            monitor_thread.join(timeout=2.0)
        if timeout_thread is not None:
            timeout_thread.join(timeout=2.0)
        _dispose_node(node, runtime_log_path, now)

    trigger = trigger_box.get("trigger")
    emergency_flatten_success: bool | None = None
    emergency_flatten_path: Path | None = None
    flatten_error: str | None = None
    if trigger is not None:
        stop_reason = "emergency_flatten"
        flatten_settings = _emergency_flatten_settings_for_trigger(
            settings=settings,
            run_settings=run_settings,
            run_id=rid,
            reason=trigger.reason,
        )
        try:
            flatten_result = flatten(flatten_settings)
            emergency_flatten_success = bool(
                getattr(flatten_result, "success", False)
            )
            raw_path = getattr(flatten_result, "audit_path", None)
            if isinstance(raw_path, Path):
                emergency_flatten_path = raw_path
        except Exception as exc:  # noqa: BLE001
            emergency_flatten_success = False
            flatten_error = repr(exc)
            _append_runtime_event(
                runtime_log_path,
                {
                    "event": "emergency_flatten_exception",
                    "ts": _iso_ms_utc(now()),
                    "error": flatten_error,
                },
            )
    elif stop_reason == "node_stopped":
        stop_reason = stop_reason_box.get("stop_reason", stop_reason)

    finished = now()
    finished_at = _iso_ms_utc(finished)
    elapsed = max(0.0, (finished - started).total_seconds())
    sample = latest_sample.get("sample")
    runtime = _base_testnet_runtime(
        startup=startup,
        run_settings=run_settings,
        shutdown_reason=stop_reason,
        sample=sample,
        restart=restart_reconciliation,
    )
    runtime["strategies_registered"] = strategies_registered
    runtime["actors_registered"] = actors_registered
    if trigger is not None:
        runtime["auto_flatten_trigger"] = trigger.msg
        runtime["emergency_flatten_success"] = emergency_flatten_success
        if emergency_flatten_path is not None:
            runtime["emergency_flatten_path"] = str(emergency_flatten_path)
    if flatten_error is not None:
        runtime["emergency_flatten_error"] = flatten_error

    _append_runtime_event(
        runtime_log_path,
        {
            "event": "shutdown",
            "ts": finished_at,
            "elapsed_seconds": elapsed,
            "stop_reason": stop_reason,
            "node_built": node_built,
            "node_run_invoked": node_run_invoked,
            "auto_flatten_trigger": None if trigger is None else trigger.msg,
            "emergency_flatten_success": emergency_flatten_success,
        },
    )

    result = LongRunningTestnetResult(
        startup=startup,
        run_id=rid,
        bundle_root=bundle_root,
        runtime_log_path=runtime_log_path,
        alerts_path=alerts_path,
        manifest_path=manifest_path,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=elapsed,
        max_run_seconds=run_settings.max_run_seconds,
        stop_reason=stop_reason,
        error=error,
        node_built=node_built,
        node_run_invoked=node_run_invoked,
        runtime=runtime,
        auto_flatten_trigger=None if trigger is None else trigger.msg,
        emergency_flatten_success=emergency_flatten_success,
        emergency_flatten_path=emergency_flatten_path,
    )
    _write_long_run_manifest(result)
    return result


def _base_testnet_runtime(
    *,
    startup: StartupCheckResult,
    run_settings: LongRunningTestnetSettings,
    shutdown_reason: str,
    sample: TestnetRuntimeTelemetry | None = None,
    restart: RestartReconciliation | None = None,
) -> dict[str, object]:
    runtime: dict[str, object] = {
        "mode": MODE_TESTNET,
        "data_mode": DATA_MODE_EXCHANGE_WS,
        "order_mode": ORDER_MODE_TESTNET,
        "exchange": "binance",
        "exchange_endpoint": startup.adapter_plan.exchange_endpoint,
        "credentials_source": startup.credentials_source,
        "credentials_key_prefix": startup.credentials_key_prefix,
        "credentials_loaded": True,
        "instrument_ids": list(run_settings.instrument_ids),
        "heartbeat_interval_seconds": run_settings.heartbeat_interval_seconds,
        "exchange_error_count": 0,
        "exchange_error_burst_threshold": (
            run_settings.exchange_error_burst_threshold
        ),
        "ws_reconnect_count": 0,
        "ws_reconnect_burst_threshold": run_settings.ws_reconnect_burst_threshold,
        "data_gap_tolerance_seconds": run_settings.data_gap_tolerance_seconds,
        "signal_lag_threshold_seconds": run_settings.signal_lag_threshold_seconds,
        "daily_pnl": 0.0,
        "starting_balance": run_settings.starting_balance,
        "daily_loss_limit_pct": run_settings.daily_loss_limit_pct,
        "operator": startup.operator,
        "shutdown_reason": shutdown_reason,
        "restart_sequence": 0,
        "restart_drift_detected": False,
        "enable_strategy_execution": run_settings.enable_strategy_execution,
        "strategies_registered": 0,
        "actors_registered": 0,
    }
    if sample is not None:
        runtime.update(
            {
                "exchange_error_count": sample.exchange_error_count,
                "ws_reconnect_count": sample.ws_reconnect_count,
                "daily_pnl": sample.daily_pnl,
                "account_total_usdt": sample.account_total_usdt,
                "open_orders": sample.open_orders,
                "open_positions": sample.open_positions,
                "last_bar_ns": sample.last_bar_ns,
                "last_signal_ns": sample.last_signal_ns,
                "processed_until_ns": sample.last_bar_ns,
                "ws_connected": sample.ws_connected,
            }
        )
    if restart is not None:
        runtime.update(restart.runtime_fields())
    return runtime


def _reconcile_restart(
    *,
    run_settings: LongRunningTestnetSettings,
    exchange: Any,
) -> RestartReconciliation:
    if run_settings.previous_run_id is None or run_settings.restart_reason is None:
        raise StartupValidationError(
            "restart_args_required",
            "previous_run_id and restart_reason are required for restart reconciliation",
        )

    previous_dir = run_settings.output_root / run_settings.previous_run_id
    manifest_path = previous_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise StartupValidationError(
            "previous_manifest_missing",
            f"previous run manifest not found: {manifest_path}",
        )

    manifest_bytes = manifest_path.read_bytes()
    previous_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise StartupValidationError(
            "previous_manifest_invalid_json",
            f"previous run manifest is not valid JSON: {manifest_path}",
        ) from exc

    runtime = manifest.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    previous_processed_until_ns = _optional_int(
        runtime.get("processed_until_ns", runtime.get("last_bar_ns"))
    )
    previous_sequence = _optional_int(runtime.get("restart_sequence")) or 0

    instrument_ids = tuple(run_settings.instrument_ids)
    local_orders = _load_local_open_orders(previous_dir / "orders.parquet")
    local_positions = _load_local_open_positions(previous_dir / "positions.parquet")
    exchange_orders = _exchange_open_orders(exchange, instrument_ids)
    exchange_positions = _exchange_open_positions(exchange, instrument_ids)

    return RestartReconciliation(
        previous_run_id=run_settings.previous_run_id,
        previous_manifest_sha256=previous_manifest_sha256,
        previous_processed_until_ns=previous_processed_until_ns,
        restart_sequence=previous_sequence + 1,
        restart_reason=run_settings.restart_reason,
        restart_order_drift=_record_drift(local_orders, exchange_orders),
        restart_position_drift=_record_drift(local_positions, exchange_positions),
    )


def _load_local_open_orders(path: Path) -> list[dict[str, str]]:
    records = _read_parquet_records(path)
    open_orders: list[dict[str, str]] = []
    for row in records:
        status = str(row.get("status", "")).upper()
        if status in TERMINAL_ORDER_STATUSES:
            continue
        order_id = _text(row.get("order_id") or row.get("venue_order_id"))
        if not order_id:
            continue
        quantity = _decimal_text(row.get("quantity"))
        if quantity is None:
            continue
        open_orders.append(
            {
                "order_id": order_id,
                "instrument_id": _text(row.get("instrument_id")),
                "side": _text(row.get("side")).upper(),
                "quantity": quantity,
            }
        )
    return _sorted_records(open_orders)


def _load_local_open_positions(path: Path) -> list[dict[str, str]]:
    records = _read_parquet_records(path)
    open_positions: list[dict[str, str]] = []
    for row in records:
        side = _text(row.get("side")).upper()
        quantity = _decimal_text(row.get("quantity"))
        if side == "FLAT" or quantity in (None, "0"):
            continue
        closed_ts = _optional_int(row.get("closed_ts"))
        if closed_ts is not None and closed_ts > 0:
            continue
        open_positions.append(
            {
                "instrument_id": _text(row.get("instrument_id")),
                "side": side,
                "quantity": quantity,
            }
        )
    return _sorted_records(open_positions)


def _read_parquet_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    import pandas as pd

    return pd.read_parquet(path).to_dict("records")


def _exchange_open_orders(
    exchange: Any,
    instrument_ids: tuple[str, ...],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for instrument_id in instrument_ids:
        for order in exchange.list_open_orders(instrument_id):
            quantity = _decimal_text(getattr(order, "quantity", None))
            if quantity is None:
                continue
            records.append(
                {
                    "order_id": _text(getattr(order, "order_id", "")),
                    "instrument_id": _text(getattr(order, "instrument_id", instrument_id)),
                    "side": _text(getattr(order, "side", "")).upper(),
                    "quantity": quantity,
                }
            )
    return _sorted_records(records)


def _exchange_open_positions(
    exchange: Any,
    instrument_ids: tuple[str, ...],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for instrument_id in instrument_ids:
        for position in exchange.list_open_positions(instrument_id):
            side = _text(getattr(position, "side", "")).upper()
            quantity = _decimal_text(getattr(position, "quantity", None))
            if side == "FLAT" or quantity in (None, "0"):
                continue
            records.append(
                {
                    "instrument_id": _text(
                        getattr(position, "instrument_id", instrument_id)
                    ),
                    "side": side,
                    "quantity": quantity,
                }
            )
    return _sorted_records(records)


def _record_drift(
    local: list[dict[str, str]],
    exchange: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    local_by_key = {_record_key(row): row for row in local}
    exchange_by_key = {_record_key(row): row for row in exchange}
    missing_on_exchange = [
        local_by_key[key] for key in sorted(local_by_key.keys() - exchange_by_key.keys())
    ]
    unexpected_on_exchange = [
        exchange_by_key[key] for key in sorted(exchange_by_key.keys() - local_by_key.keys())
    ]
    return {
        "missing_on_exchange": missing_on_exchange,
        "unexpected_on_exchange": unexpected_on_exchange,
    }


def _record_key(row: Mapping[str, str]) -> str:
    return json.dumps(dict(row), sort_keys=True, separators=(",", ":"))


def _sorted_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(records, key=_record_key)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal.is_finite():
        return None
    text = format(decimal.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text or "0"


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _monitor_long_run(
    *,
    run_settings: LongRunningTestnetSettings,
    reader: TelemetryReader,
    runtime_log_path: Path,
    alerts_path: Path,
    kind: str,
    run_id: str,
    node: Any,
    stop_event: threading.Event,
    latest_sample: dict[str, TestnetRuntimeTelemetry],
    trigger_box: dict[str, AutoFlattenTrigger],
    stop_reason_box: dict[str, str],
) -> None:
    history: deque[TestnetRuntimeTelemetry] = deque()
    advisory_state = AdvisoryAlertState()
    last_heartbeat_ts: datetime | None = None
    while not stop_event.is_set():
        try:
            sample = reader()
        except Exception as exc:  # noqa: BLE001
            _append_runtime_event(
                runtime_log_path,
                {
                    "event": "telemetry_error",
                    "ts": _iso_ms_utc(_utc_now()),
                    "error": repr(exc),
                },
            )
            stop_event.wait(run_settings.telemetry_poll_seconds)
            continue

        latest_sample["sample"] = sample
        history.append(sample)
        _trim_hourly_history(history, sample.ts)

        if _should_emit_runtime_heartbeat(
            last_heartbeat_ts=last_heartbeat_ts,
            sample_ts=sample.ts,
            interval_seconds=run_settings.heartbeat_interval_seconds,
        ):
            last_heartbeat_ts = sample.ts
            _append_runtime_heartbeat(
                runtime_log_path.parent / "heartbeat.jsonl",
                sample=sample,
                kind=kind,
                run_id=run_id,
            )

        for msg, severity, context in _advisory_alerts(
            sample, settings=run_settings, state=advisory_state
        ):
            _append_alert_event(
                alerts_path,
                severity=severity,
                kind=kind,
                run_id=run_id,
                msg=msg,
                ts=_iso_ms_utc(sample.ts),
                context=context,
            )

        trigger = _auto_flatten_trigger(run_settings, sample, history)
        if trigger is not None:
            trigger_box["trigger"] = trigger
            stop_reason_box["stop_reason"] = "emergency_flatten"
            _append_alert_event(
                alerts_path,
                severity=trigger.severity,
                kind=kind,
                run_id=run_id,
                msg=trigger.msg,
                ts=_iso_ms_utc(sample.ts),
                context=trigger.context,
            )
            _append_runtime_event(
                runtime_log_path,
                {
                    "event": "auto_flatten_triggered",
                    "ts": _iso_ms_utc(sample.ts),
                    "trigger": trigger.msg,
                    "reason": trigger.reason,
                    "context": trigger.context,
                },
            )
            _request_node_stop(node)
            stop_event.set()
            return

        stop_event.wait(run_settings.telemetry_poll_seconds)


def _trim_hourly_history(
    history: deque[TestnetRuntimeTelemetry], now: datetime
) -> None:
    window_start = now - timedelta(hours=1)
    while len(history) > 1 and history[1].ts <= window_start:
        history.popleft()


def _should_emit_runtime_heartbeat(
    *,
    last_heartbeat_ts: datetime | None,
    sample_ts: datetime,
    interval_seconds: float,
) -> bool:
    if last_heartbeat_ts is None:
        return True
    return (sample_ts - last_heartbeat_ts).total_seconds() >= interval_seconds


def _append_runtime_heartbeat(
    path: Path,
    *,
    sample: TestnetRuntimeTelemetry,
    kind: str,
    run_id: str,
) -> None:
    payload = {
        "event": "heartbeat",
        "ts": _iso_ms_utc(sample.ts),
        "kind": kind,
        "run_id": run_id,
        "ws_connected": sample.ws_connected,
        "last_bar_ns": sample.last_bar_ns,
        "account_total_usdt": sample.account_total_usdt,
        "open_orders": sample.open_orders,
        "open_positions": sample.open_positions,
        "daily_pnl": sample.daily_pnl,
        "exchange_error_count": sample.exchange_error_count,
        "ws_reconnect_count": sample.ws_reconnect_count,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True))
        fh.write("\n")


def _auto_flatten_trigger(
    settings: LongRunningTestnetSettings,
    sample: TestnetRuntimeTelemetry,
    history: deque[TestnetRuntimeTelemetry],
) -> AutoFlattenTrigger | None:
    daily_loss_limit = -settings.daily_loss_limit_pct * settings.starting_balance
    if sample.daily_pnl <= daily_loss_limit:
        return AutoFlattenTrigger(
            msg="kill_switch_fired",
            severity="critical",
            reason=(
                "automatic kill-switch: daily PnL "
                f"{sample.daily_pnl:.8g} <= {daily_loss_limit:.8g}"
            ),
            context={
                "daily_pnl": sample.daily_pnl,
                "starting_balance": settings.starting_balance,
                "daily_loss_limit_pct": settings.daily_loss_limit_pct,
                "loss_limit": daily_loss_limit,
            },
        )

    exchange_errors = _window_delta(
        history,
        attr="exchange_error_count",
        latest=sample.exchange_error_count,
    )
    if exchange_errors > settings.exchange_error_burst_threshold:
        return AutoFlattenTrigger(
            msg="exchange_error_burst",
            severity="error",
            reason=(
                "automatic emergency flatten: exchange_error_count "
                f"{exchange_errors} > {settings.exchange_error_burst_threshold}/hour"
            ),
            context={
                "exchange_error_count_hour": exchange_errors,
                "threshold": settings.exchange_error_burst_threshold,
                "runtime_exchange_error_count": sample.exchange_error_count,
            },
        )

    ws_reconnects = _window_delta(
        history,
        attr="ws_reconnect_count",
        latest=sample.ws_reconnect_count,
    )
    if ws_reconnects > settings.ws_reconnect_burst_threshold:
        return AutoFlattenTrigger(
            msg="ws_reconnect_burst",
            severity="error",
            reason=(
                "automatic emergency flatten: ws_reconnect_count "
                f"{ws_reconnects} > {settings.ws_reconnect_burst_threshold}/hour"
            ),
            context={
                "ws_reconnect_count_hour": ws_reconnects,
                "threshold": settings.ws_reconnect_burst_threshold,
                "runtime_ws_reconnect_count": sample.ws_reconnect_count,
            },
        )

    return None


def _advisory_alerts(
    sample: TestnetRuntimeTelemetry,
    *,
    settings: LongRunningTestnetSettings,
    state: AdvisoryAlertState,
) -> list[tuple[str, str, dict[str, object]]]:
    """Return ADR-008 §5.4 warning/error alerts to emit this tick.

    Mutates ``state`` to dedup repeat alerts: ``ws_disconnected`` fires once
    per True→False transition; ``data_gap_exceeded_tolerance`` and
    ``signal_lag_exceeded_threshold`` fire once per incident and re-arm when
    the underlying metric returns inside tolerance.
    """

    pending: list[tuple[str, str, dict[str, object]]] = []

    if state.ws_connected_prev and not sample.ws_connected:
        pending.append(
            (
                "ws_disconnected",
                "warning",
                {
                    "ws_connected": False,
                    "ws_reconnect_count": sample.ws_reconnect_count,
                },
            )
        )
    state.ws_connected_prev = sample.ws_connected

    if sample.last_bar_ns is not None:
        gap_seconds = sample.ts.timestamp() - sample.last_bar_ns / 1_000_000_000
        if gap_seconds > settings.data_gap_tolerance_seconds:
            if not state.data_gap_active:
                pending.append(
                    (
                        "data_gap_exceeded_tolerance",
                        "error",
                        {
                            "last_bar_ns": sample.last_bar_ns,
                            "gap_seconds": gap_seconds,
                            "tolerance_seconds": settings.data_gap_tolerance_seconds,
                        },
                    )
                )
                state.data_gap_active = True
        else:
            state.data_gap_active = False

    if sample.last_signal_ns is not None:
        lag_seconds = sample.ts.timestamp() - sample.last_signal_ns / 1_000_000_000
        if lag_seconds > settings.signal_lag_threshold_seconds:
            if not state.signal_lag_active:
                pending.append(
                    (
                        "signal_lag_exceeded_threshold",
                        "warning",
                        {
                            "last_signal_ns": sample.last_signal_ns,
                            "lag_seconds": lag_seconds,
                            "threshold_seconds": settings.signal_lag_threshold_seconds,
                        },
                    )
                )
                state.signal_lag_active = True
        else:
            state.signal_lag_active = False

    return pending


def _window_delta(
    history: deque[TestnetRuntimeTelemetry],
    *,
    attr: str,
    latest: int,
) -> int:
    if not history:
        return latest
    base = getattr(history[0], attr)
    if latest < base:
        return latest
    return latest - base


def _stop_after_max_duration(
    *,
    node: Any,
    stop_event: threading.Event,
    stop_reason_box: dict[str, str],
    max_seconds: float,
) -> None:
    if stop_event.wait(max_seconds):
        return
    stop_reason_box.setdefault("stop_reason", "max_duration")
    _request_node_stop(node)
    stop_event.set()


def _request_node_stop(node: Any) -> None:
    try:
        loop = node.kernel.loop
    except AttributeError:
        node.stop()
        return
    try:
        loop.call_soon_threadsafe(node.stop)
    except RuntimeError:
        node.stop()


def _emergency_flatten_settings_for_trigger(
    *,
    settings: StartupSettings,
    run_settings: LongRunningTestnetSettings,
    run_id: str,
    reason: str,
) -> Any:
    from apps.strategies_nautilus.runners.emergency_flatten import (
        EmergencyFlattenSettings,
    )

    return EmergencyFlattenSettings(
        kind=KIND_TESTNET,
        run_id=run_id,
        operator=settings.operator,
        reason=reason,
        instrument_ids=run_settings.instrument_ids,
        output_root=run_settings.output_root,
        fill_timeout_seconds=run_settings.emergency_fill_timeout_seconds,
        poll_interval_seconds=run_settings.emergency_poll_interval_seconds,
        runner_pid=None,
    )


def _default_flatten_runner(flatten_settings: Any) -> Any:
    from apps.strategies_nautilus.runners.binance_testnet_exchange import (
        build_binance_spot_testnet_exchange,
    )
    from apps.strategies_nautilus.runners.emergency_flatten import (
        run_emergency_flatten,
    )

    exchange = build_binance_spot_testnet_exchange(flatten_settings)
    return run_emergency_flatten(flatten_settings, exchange=exchange)


def _default_restart_exchange(
    *,
    settings: StartupSettings,
    run_settings: LongRunningTestnetSettings,
    run_id: str,
) -> Any:
    flatten_settings = _emergency_flatten_settings_for_trigger(
        settings=settings,
        run_settings=run_settings,
        run_id=run_id,
        reason="restart reconciliation",
    )
    from apps.strategies_nautilus.runners.binance_testnet_exchange import (
        build_binance_spot_testnet_exchange,
    )

    return build_binance_spot_testnet_exchange(flatten_settings)


def _write_long_run_manifest(result: LongRunningTestnetResult) -> None:
    payload = {
        "schema_version": "backtest.v1",
        "kind": KIND_TESTNET,
        "run_id": result.run_id,
        "trader_id": result.startup.adapter_plan.trader_id,
        "git_commit": result.startup.git_commit,
        "git_dirty": result.startup.git_dirty,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "elapsed_seconds": result.elapsed_seconds,
        "venues": [BINANCE],
        "instruments": list(result.runtime.get("instrument_ids", []))
        or [result.startup.adapter_plan.instrument_id],
        "source": result.startup.source,
        "model_version": result.startup.model_version,
        "stage_evidence_path": result.startup.stage_evidence_path,
        "runtime": result.runtime,
    }
    result.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _append_alert_event(
    path: Path,
    *,
    severity: str,
    kind: str,
    run_id: str,
    msg: str,
    ts: str,
    context: Mapping[str, object],
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


def _default_node_factory(node_config: TradingNodeConfig) -> Any:
    from nautilus_trader.live.node import TradingNode

    return TradingNode(config=node_config)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _make_run_id(started: datetime) -> str:
    stem = started.astimezone(UTC).strftime("%Y%m%d-%H%M%SZ")
    return f"{stem}-{secrets.token_hex(4)}"


def _iso_ms_utc(dt: datetime) -> str:
    aware = dt.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%S.") + f"{aware.microsecond // 1000:03d}Z"


def _append_runtime_event(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(payload), sort_keys=True))
        fh.write("\n")


def _trader_counts(node: Any) -> tuple[int, int]:
    trader = getattr(node, "trader", None)
    if trader is None:
        return 0, 0
    strategies = _safe_len(getattr(trader, "strategies", None))
    actors = _safe_len(getattr(trader, "actors", None))
    return strategies, actors


def _safe_len(value: object) -> int:
    if callable(value):
        try:
            value = value()
        except Exception:
            return 0
    if value is None:
        return 0
    try:
        return len(value)  # type: ignore[arg-type]
    except TypeError:
        return 0


def _run_until_timeout(node: Any, max_connect_seconds: float) -> None:
    stop_called = threading.Event()

    def _stop_later() -> None:
        if stop_called.wait(max_connect_seconds):
            return
        try:
            loop = node.kernel.loop
        except AttributeError:
            node.stop()
            return
        try:
            loop.call_soon_threadsafe(node.stop)
        except RuntimeError:
            node.stop()

    timer = threading.Thread(target=_stop_later, daemon=True)
    timer.start()
    try:
        node.run(raise_exception=False)
    finally:
        stop_called.set()
        timer.join(timeout=1.0)


def _dispose_node(node: Any, runtime_log_path: Path, now: ClockFn) -> None:
    dispose = getattr(node, "dispose", None)
    if dispose is None:
        return
    try:
        dispose()
    except Exception as exc:  # noqa: BLE001 — disposal errors are logged, not raised
        _append_runtime_event(
            runtime_log_path,
            {
                "event": "dispose_failed",
                "ts": _iso_ms_utc(now()),
                "error": repr(exc),
            },
        )


def _check_mode_kind(mode: str, kind: str) -> None:
    if mode != MODE_TESTNET or kind != KIND_TESTNET:
        raise StartupValidationError(
            "mode_kind_mismatch",
            "--mode testnet and --kind testnet must both be explicit",
        )


def _credential_audit(env: Mapping[str, str]) -> CredentialAudit:
    api_key = env.get(KEY_ENV, "")
    secret = env.get(SECRET_ENV, "")
    if not api_key or not secret:
        raise StartupValidationError(
            "missing_credentials",
            f"{KEY_ENV} and {SECRET_ENV} must both be set",
        )
    if len(api_key) < MIN_CREDENTIAL_LENGTH:
        raise StartupValidationError(
            "api_key_too_short",
            f"{KEY_ENV} must be at least {MIN_CREDENTIAL_LENGTH} characters",
        )
    if len(secret) < MIN_CREDENTIAL_LENGTH:
        raise StartupValidationError(
            "api_secret_too_short",
            f"{SECRET_ENV} must be at least {MIN_CREDENTIAL_LENGTH} characters",
        )
    return CredentialAudit(
        credentials_source=f"env:{KEY_ENV},{SECRET_ENV}",
        credentials_key_prefix=api_key[:8],
    )


def _git_state(repo_root: Path) -> GitState:
    root = repo_root.resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
    )
    return GitState(commit=commit, dirty=bool(status.strip()))


def _find_stage_evidence(
    *,
    retros_dir: Path,
    source: str,
    model_version: str,
) -> StageEvidence | None:
    if not retros_dir.exists():
        return None
    for path in sorted(retros_dir.glob("*.md"), reverse=True):
        evidence = _parse_retro(path)
        if evidence is None:
            continue
        if evidence["source"] != source or evidence["model_version"] != model_version:
            continue
        if not evidence["decision_allowed"]:
            continue
        decision = str(evidence["decision"]).upper()
        current_stage = evidence["current_stage"]
        target_stage = evidence["target_stage"]
        if (
            decision == "HOLD"
            and current_stage == "paper_simulated"
            and target_stage == "paper_simulated"
        ) or (decision == "PROMOTE" and target_stage == "testnet_canary"):
            return StageEvidence(
                path=str(path),
                decision=decision,
                current_stage=current_stage,
                target_stage=target_stage,
            )
    return None


def _parse_retro(path: Path) -> dict[str, object] | None:
    text = path.read_text(encoding="utf-8")
    source = _match_backticked(text, r"^- source:\s+`([^`]+)`")
    model_version = _match_backticked(text, r"^- model_version:\s+`([^`]+)`")
    if source is None or model_version is None:
        return None
    return {
        "source": source,
        "model_version": model_version,
        "current_stage": _match_backticked(text, r"^- current_stage:\s+`([^`]+)`"),
        "target_stage": _match_backticked(text, r"^- target_stage:\s+`([^`]+)`"),
        "decision": _match_bold(text, r"^- decision:\s+\*\*([^*]+)\*\*")
        or _match_bold(text, r"^- \*\*Decision\*\*:\s+(.+)$"),
        "decision_allowed": _decision_allowed(text),
    }


def _match_backticked(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _match_bold(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _decision_allowed(text: str) -> bool:
    return bool(
        re.search(r"^- decision_allowed:\s+\*\*yes\*\*", text, flags=re.MULTILINE)
        or re.search(
            r"^- \*\*Decision allowed by gates\*\*:\s+yes",
            text,
            flags=re.MULTILINE,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate ADR-008 testnet startup prerequisites, run a controlled "
            "connection probe, or start the guarded long-running shell."
        ),
    )
    parser.add_argument("--mode", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--allow-real-credentials", action="store_true")
    parser.add_argument("--source", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--policy-position-pct-multiplier", required=True, type=float)
    parser.add_argument("--retros-dir", type=Path, default=Path("docs/retros"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--operator", default="nishiki")
    parser.add_argument("--instrument-id", default=DEFAULT_TESTNET_INSTRUMENT_ID)
    parser.add_argument("--account-type", default=DEFAULT_TESTNET_ACCOUNT_TYPE)
    parser.add_argument("--trader-id", default=DEFAULT_TESTNET_TRADER_ID)
    parser.add_argument(
        "--connect-probe",
        action="store_true",
        help=(
            "After validation passes, build a Binance Spot testnet TradingNode, "
            "connect briefly without registering any strategy, then stop and "
            "write data/testnet/<run_id>/{logs/runtime.log,connection_probe.json}."
        ),
    )
    parser.add_argument(
        "--long-run",
        action="store_true",
        help=(
            "Start the ADR-008 §6.3c guarded long-running testnet shell. "
            "Runtime telemetry thresholds auto-trigger emergency flatten."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/testnet"),
        help="Bundle root for testnet output (default: data/testnet).",
    )
    parser.add_argument(
        "--max-connect-seconds",
        type=float,
        default=30.0,
        help="Stop the connection probe after this many seconds (default: 30).",
    )
    parser.add_argument(
        "--starting-balance",
        type=float,
        help="Required with --long-run; base balance for the 5% daily-loss trigger.",
    )
    parser.add_argument(
        "--max-run-seconds",
        type=float,
        default=DEFAULT_LONG_RUN_SECONDS,
        help=(
            "Stop --long-run after this many seconds "
            f"(default: {DEFAULT_LONG_RUN_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--telemetry-poll-seconds",
        type=float,
        default=DEFAULT_TELEMETRY_POLL_SECONDS,
        help=(
            "Runtime threshold polling interval for --long-run "
            f"(default: {DEFAULT_TELEMETRY_POLL_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=float,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        help=(
            "Heartbeat interval for --long-run logs "
            f"(default: {DEFAULT_HEARTBEAT_INTERVAL_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--daily-loss-limit-pct",
        type=float,
        default=DEFAULT_DAILY_LOSS_LIMIT_PCT,
        help=(
            "Auto-flatten daily loss limit as a fraction of starting balance "
            f"(default: {DEFAULT_DAILY_LOSS_LIMIT_PCT:g})."
        ),
    )
    parser.add_argument(
        "--exchange-error-burst-threshold",
        type=int,
        default=DEFAULT_EXCHANGE_ERROR_BURST_THRESHOLD,
        help=(
            "Auto-flatten when exchange errors exceed this count per hour "
            f"(default: {DEFAULT_EXCHANGE_ERROR_BURST_THRESHOLD})."
        ),
    )
    parser.add_argument(
        "--ws-reconnect-burst-threshold",
        type=int,
        default=DEFAULT_WS_RECONNECT_BURST_THRESHOLD,
        help=(
            "Auto-flatten when WS reconnects exceed this count per hour "
            f"(default: {DEFAULT_WS_RECONNECT_BURST_THRESHOLD})."
        ),
    )
    parser.add_argument(
        "--data-gap-tolerance-seconds",
        type=float,
        default=DEFAULT_DATA_GAP_TOLERANCE_SECONDS,
        help=(
            "Emit data_gap_exceeded_tolerance alert when the latest bar age "
            f"exceeds this many seconds (default: {DEFAULT_DATA_GAP_TOLERANCE_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--signal-lag-threshold-seconds",
        type=float,
        default=DEFAULT_SIGNAL_LAG_THRESHOLD_SECONDS,
        help=(
            "Emit signal_lag_exceeded_threshold alert when the latest signal age "
            f"exceeds this many seconds (default: {DEFAULT_SIGNAL_LAG_THRESHOLD_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--emergency-fill-timeout-seconds",
        type=float,
        default=60.0,
        help="Fill timeout passed to emergency flatten from --long-run.",
    )
    parser.add_argument(
        "--emergency-poll-interval-seconds",
        type=float,
        default=1.0,
        help="Order polling interval passed to emergency flatten from --long-run.",
    )
    parser.add_argument(
        "--previous-run-id",
        help=(
            "Previous testnet run_id for ADR-008 §5.3 restart reconciliation. "
            "Requires --restart-reason."
        ),
    )
    parser.add_argument(
        "--restart-reason",
        help="Operator-supplied restart reason required with --previous-run-id.",
    )
    parser.add_argument(
        "--enable-strategy-execution",
        action="store_true",
        help=(
            "ADR-008 §6.6 double-signoff flag for --long-run. The CLI itself "
            "cannot wire a strategy; with this flag set, callers using "
            "run_long_running_testnet() must also supply a "
            "register_strategies callback. Without this flag the runner "
            "refuses to start whenever any strategy or actor is registered "
            "(stability-soak mode, the Phase 3f default)."
        ),
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> StartupSettings:
    return StartupSettings(
        mode=args.mode,
        kind=args.kind,
        allow_real_credentials=bool(args.allow_real_credentials),
        source=args.source,
        model_version=args.model_version,
        policy_position_pct_multiplier=args.policy_position_pct_multiplier,
        retros_dir=args.retros_dir,
        repo_root=args.repo_root,
        operator=args.operator,
        instrument_id=args.instrument_id,
        account_type=args.account_type,
        trader_id=args.trader_id,
    )


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    git_state: GitState | None = None,
    node_factory: NodeFactory | None = None,
    clock: ClockFn | None = None,
    telemetry_reader: TelemetryReader | None = None,
    flatten_runner: FlattenRunner | None = None,
    restart_exchange_factory: RestartExchangeFactory | None = None,
    register_strategies: Callable[[Any], None] | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = _config_from_args(args)
    if args.connect_probe and args.long_run:
        parser.exit(
            EXIT_STARTUP_VALIDATION,
            f"{parser.prog}: error: choose only one of --connect-probe or --long-run\n",
        )

    if args.long_run:
        if args.starting_balance is None:
            parser.exit(
                EXIT_STARTUP_VALIDATION,
                f"{parser.prog}: error: --starting-balance is required with --long-run\n",
            )
        try:
            run_settings = LongRunningTestnetSettings(
                output_root=args.output_root,
                instrument_ids=(args.instrument_id,),
                starting_balance=args.starting_balance,
                max_run_seconds=args.max_run_seconds,
                telemetry_poll_seconds=args.telemetry_poll_seconds,
                heartbeat_interval_seconds=args.heartbeat_interval_seconds,
                daily_loss_limit_pct=args.daily_loss_limit_pct,
                exchange_error_burst_threshold=args.exchange_error_burst_threshold,
                ws_reconnect_burst_threshold=args.ws_reconnect_burst_threshold,
                data_gap_tolerance_seconds=args.data_gap_tolerance_seconds,
                signal_lag_threshold_seconds=args.signal_lag_threshold_seconds,
                emergency_fill_timeout_seconds=args.emergency_fill_timeout_seconds,
                emergency_poll_interval_seconds=args.emergency_poll_interval_seconds,
                previous_run_id=args.previous_run_id,
                restart_reason=args.restart_reason,
                enable_strategy_execution=bool(args.enable_strategy_execution),
            )
        except ValueError as exc:
            parser.exit(EXIT_STARTUP_VALIDATION, f"{parser.prog}: error: {exc}\n")
        try:
            result = run_long_running_testnet(
                settings,
                run_settings,
                env=env,
                git_state=git_state,
                node_factory=node_factory,
                clock=clock,
                telemetry_reader=telemetry_reader,
                flatten_runner=flatten_runner,
                restart_exchange_factory=restart_exchange_factory,
                register_strategies=register_strategies,
            )
        except StartupValidationError as exc:
            parser.exit(EXIT_STARTUP_VALIDATION, f"{parser.prog}: error: {exc}\n")
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return result.exit_code

    if not args.connect_probe:
        try:
            result = validate_startup(settings, env=env, git_state=git_state)
        except StartupValidationError as exc:
            parser.exit(EXIT_STARTUP_VALIDATION, f"{parser.prog}: error: {exc}\n")
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return EXIT_OK

    probe_settings = ConnectionProbeSettings(
        output_root=args.output_root,
        max_connect_seconds=args.max_connect_seconds,
    )
    try:
        probe = run_connection_probe(
            settings,
            probe_settings,
            env=env,
            git_state=git_state,
            node_factory=node_factory,
            clock=clock,
        )
    except StartupValidationError as exc:
        parser.exit(EXIT_STARTUP_VALIDATION, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(probe.to_dict(), indent=2, sort_keys=True))
    return EXIT_OK if probe.error is None else EXIT_RUNTIME_ERROR


__all__ = [
    "AdvisoryAlertState",
    "AutoFlattenTrigger",
    "ConnectionProbeResult",
    "ConnectionProbeSettings",
    "CredentialAudit",
    "GitState",
    "LongRunningTestnetResult",
    "LongRunningTestnetSettings",
    "RestartReconciliation",
    "TestnetAdapterPlan",
    "TestnetRuntimeTelemetry",
    "StartupCheckResult",
    "StartupValidationError",
    "StartupSettings",
    "build_testnet_node_config",
    "main",
    "run_connection_probe",
    "run_long_running_testnet",
    "validate_startup",
]


if __name__ == "__main__":
    raise SystemExit(main())

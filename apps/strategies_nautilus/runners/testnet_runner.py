"""ADR-008 Phase 3b testnet startup guard.

This module intentionally stops before opening network connections. It verifies
the credential boundary and promotion prerequisites, then builds the Nautilus
Binance testnet adapter configuration that a later runtime will connect.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

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
        config=config,
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


def build_testnet_node_config(config: StartupSettings) -> TradingNodeConfig:
    """Build the Nautilus Binance testnet node config without connecting it."""

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
                account_type=account_type,
                environment=BinanceEnvironment.TESTNET,
                instrument_provider=instrument_provider,
            ),
        },
        exec_clients={
            BINANCE: BinanceExecClientConfig(
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
    config: StartupSettings,
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
        instrument_id=config.instrument_id,
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
        description="Validate ADR-008 Phase 3b testnet startup prerequisites.",
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
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = validate_startup(
            _config_from_args(args),
            env=env,
            git_state=git_state,
        )
    except StartupValidationError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


__all__ = [
    "CredentialAudit",
    "GitState",
    "TestnetAdapterPlan",
    "StartupCheckResult",
    "StartupValidationError",
    "StartupSettings",
    "build_testnet_node_config",
    "validate_startup",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

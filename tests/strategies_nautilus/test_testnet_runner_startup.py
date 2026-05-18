"""Tests for ADR-008 Phase 3b testnet startup validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nautilus_trader.adapters.binance import BINANCE, BinanceAccountType
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment

from apps.strategies_nautilus.runners.testnet_runner import (
    GitState,
    StartupSettings,
    StartupValidationError,
    build_testnet_node_config,
    main,
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

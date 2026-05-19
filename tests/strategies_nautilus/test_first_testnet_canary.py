"""Unit tests for ADR-008 §6.6 first testnet canary launcher helpers."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.bridge.store import SignalStore
from apps.strategies_nautilus.runners.first_testnet_canary import (
    FirstCanaryStrategySpec,
    build_register_strategies,
)

VALID_SPEC_KWARGS = dict(
    source="freqai_linear_v1",
    model_version="linear-mom-train20240105",
    signal_store_path=Path("data/bridge/signals.db"),
    instrument_id_str="BTCUSDT.BINANCE",
    bar_type_str="BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
    trade_size=Decimal("0.001"),
    base_currency_code="USDT",
    venue="BINANCE",
    position_pct_multiplier=0.1,
)


def test_spec_rejects_multiplier_above_testnet_cap():
    with pytest.raises(ValueError, match="caps testnet position_pct_multiplier at 0.2"):
        FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "position_pct_multiplier": 0.3})


def test_spec_rejects_zero_multiplier():
    with pytest.raises(ValueError, match="caps testnet position_pct_multiplier"):
        FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "position_pct_multiplier": 0.0})


def test_spec_rejects_zero_trade_size():
    with pytest.raises(ValueError, match="trade_size must be positive"):
        FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "trade_size": Decimal("0")})


def test_spec_rejects_blank_source_or_model_version():
    with pytest.raises(ValueError, match="source is required"):
        FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "source": ""})
    with pytest.raises(ValueError, match="model_version is required"):
        FirstCanaryStrategySpec(**{**VALID_SPEC_KWARGS, "model_version": ""})


def test_build_authorization_locks_to_single_source_model():
    spec = FirstCanaryStrategySpec(**VALID_SPEC_KWARGS)

    auth = spec.build_authorization()

    assert auth.allowed_sources == frozenset({"freqai_linear_v1"})
    assert auth.allowed_model_versions == frozenset(
        {"linear-mom-train20240105"}
    )
    policy = auth.policies[("freqai_linear_v1", "linear-mom-train20240105")]
    assert policy.position_pct_multiplier == 0.1
    assert policy.dry_run is False
    assert policy.min_confidence_override is None


def test_register_strategies_uses_clock_ns_for_initial_cursor(tmp_path: Path):
    db_path = tmp_path / "signals.db"
    SignalStore(db_path)  # create empty store so SignalStore(...) succeeds
    spec = FirstCanaryStrategySpec(
        **{**VALID_SPEC_KWARGS, "signal_store_path": db_path}
    )
    lineage: list = []
    captured: dict[str, Any] = {}

    def fake_sink(node: Any, strategy: Any) -> None:
        captured["strategy"] = strategy

    register = build_register_strategies(
        spec,
        lineage=lineage,
        clock_ns=lambda: 1_716_038_400_000_000_000,
        store_factory=SignalStore,
        strategy_sink=fake_sink,
    )

    fake_node = MagicMock()
    register(fake_node)

    strategy = captured["strategy"]
    src = strategy._signal_source  # SignalStorePollingSource
    assert src.cursor_ns == 1_716_038_400_000_000_000
    assert src.source == "freqai_linear_v1"
    assert src.model_version == "linear-mom-train20240105"
    assert strategy.lineage is lineage


def test_register_strategies_respects_explicit_initial_cursor(tmp_path: Path):
    db_path = tmp_path / "signals.db"
    SignalStore(db_path)
    spec = FirstCanaryStrategySpec(
        **{
            **VALID_SPEC_KWARGS,
            "signal_store_path": db_path,
            "initial_cursor_ns": 1_704_067_200_000_000_000,
        }
    )
    captured: dict[str, Any] = {}

    def fake_sink(node: Any, strategy: Any) -> None:
        captured["strategy"] = strategy

    register = build_register_strategies(
        spec,
        lineage=[],
        clock_ns=lambda: 1_716_038_400_000_000_000,
        store_factory=SignalStore,
        strategy_sink=fake_sink,
    )

    register(MagicMock())

    assert (
        captured["strategy"]._signal_source.cursor_ns
        == 1_704_067_200_000_000_000
    )


def test_register_strategies_invokes_default_sink_through_trader(tmp_path: Path):
    db_path = tmp_path / "signals.db"
    SignalStore(db_path)
    spec = FirstCanaryStrategySpec(
        **{**VALID_SPEC_KWARGS, "signal_store_path": db_path}
    )

    register = build_register_strategies(
        spec,
        lineage=[],
        clock_ns=lambda: 1_716_038_400_000_000_000,
    )

    fake_node = MagicMock()
    register(fake_node)

    fake_node.trader.add_strategy.assert_called_once()
    submitted = fake_node.trader.add_strategy.call_args.args[0]
    assert submitted.__class__.__name__ == "BaselineNautilusStrategy"

"""Helpers for ADR-008 §6.6 first real testnet canary session.

This module is the library-side glue that constructs a
``register_strategies(node)`` callback wiring one ``(source,
model_version)`` source into a ``BaselineNautilusStrategy`` backed by a
``SignalStorePollingSource``. It does **not** read credentials, start a
``TradingNode``, or submit any order on its own — those still belong to
``apps.strategies_nautilus.runners.testnet_runner.main`` and the operator
launcher script.

Operators wire it up from a one-off launcher script (see
``docs/runbook/first-testnet-canary.md``). The split exists so the wiring
logic stays unit-tested while the launcher script remains tweakable per
session without code review.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization, SourcePolicy
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    BaselineNautilusStrategy,
    BaselineNautilusStrategyParams,
    LineageRecord,
    SignalStorePollingSource,
)
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig


@dataclass(frozen=True)
class FirstCanaryStrategySpec:
    """All parameters required to wire one streaming source into the strategy.

    The launcher constructs this and passes it to
    :func:`build_register_strategies`. Every field has to be explicit
    because the first canary session is a one-time signed event — there is
    no convenient "default everything" path.
    """

    source: str
    model_version: str
    signal_store_path: Path
    instrument_id_str: str
    bar_type_str: str
    trade_size: Decimal
    base_currency_code: str
    venue: str
    position_pct_multiplier: float
    min_confidence: float = 0.55
    max_position_pct: float = 0.05
    daily_drawdown_stop_pct: float = 0.05
    min_confidence_override: float | None = None
    initial_cursor_ns: int | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.model_version:
            raise ValueError("model_version is required")
        if not 0.0 < self.position_pct_multiplier <= 0.2:
            raise ValueError(
                "ADR-008 §6.6 caps testnet position_pct_multiplier at 0.2, "
                f"got {self.position_pct_multiplier}"
            )
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive")

    def build_authorization(self) -> Authorization:
        policy = SourcePolicy(
            position_pct_multiplier=self.position_pct_multiplier,
            min_confidence_override=self.min_confidence_override,
            dry_run=False,
        )
        return Authorization(
            allowed_sources=frozenset({self.source}),
            allowed_model_versions=frozenset({self.model_version}),
            policies={(self.source, self.model_version): policy},
        )

    def build_baseline_config(self) -> BaselineStrategyConfig:
        return BaselineStrategyConfig(
            venue=self.venue,
            auth=self.build_authorization(),
            min_confidence=self.min_confidence,
            max_position_pct=self.max_position_pct,
            daily_drawdown_stop_pct=self.daily_drawdown_stop_pct,
        )


def build_register_strategies(
    spec: FirstCanaryStrategySpec,
    *,
    lineage: list[LineageRecord],
    clock_ns: Callable[[], int] | None = None,
    store_factory: Callable[[Path], SignalStore] | None = None,
    strategy_sink: Callable[[Any, BaselineNautilusStrategy], None] | None = None,
) -> Callable[[Any], None]:
    """Return a ``register_strategies(node)`` callback for one source.

    ``clock_ns``, ``store_factory``, and ``strategy_sink`` are injection
    points the unit tests use to avoid touching a real SignalStore or the
    native Nautilus ``Strategy`` lifecycle. The defaults are the
    production wiring: ``time.time_ns``, ``SignalStore(path)``, and
    ``node.trader.add_strategy(strategy)``.
    """

    clock: Callable[[], int] = clock_ns if clock_ns is not None else time.time_ns
    factory: Callable[[Path], SignalStore] = (
        store_factory if store_factory is not None else SignalStore
    )

    def _default_sink(node: Any, strategy: BaselineNautilusStrategy) -> None:
        node.trader.add_strategy(strategy)

    sink: Callable[[Any, BaselineNautilusStrategy], None] = (
        strategy_sink if strategy_sink is not None else _default_sink
    )

    def register(node: Any) -> None:
        # Imports are deferred so unit tests that exercise the wiring layer
        # do not have to construct real Nautilus identifier objects.
        from nautilus_trader.model.data import BarType
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.objects import Currency

        instrument_id = InstrumentId.from_str(spec.instrument_id_str)
        bar_type = BarType.from_str(spec.bar_type_str)
        base_currency = Currency.from_str(spec.base_currency_code)

        store = factory(spec.signal_store_path)
        cursor_ns = (
            spec.initial_cursor_ns
            if spec.initial_cursor_ns is not None
            else clock()
        )
        signal_source = SignalStorePollingSource(
            store=store,
            source=spec.source,
            model_version=spec.model_version,
            cursor_ns=cursor_ns,
        )
        strategy = BaselineNautilusStrategy(
            params=BaselineNautilusStrategyParams(
                instrument_id=instrument_id,
                bar_type=bar_type,
                baseline_config=spec.build_baseline_config(),
                trade_size=spec.trade_size,
                equity_currency=base_currency,
                signal_source=signal_source,
                lineage=lineage,
            )
        )
        sink(node, strategy)

    return register


__all__ = [
    "FirstCanaryStrategySpec",
    "build_register_strategies",
]

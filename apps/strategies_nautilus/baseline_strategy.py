"""Baseline signal-to-intent translator.

Phase 2 step 2 (ADR-002 §4.1 + §4.2 first rule). This module is the **decision
layer**: it consumes a `SignalEvent` and a snapshot of account state, and
emits an `OrderIntent` describing the desired target position. It does NOT
talk to NautilusTrader, an exchange, or the network. The Phase 2 runner
(`apps/strategies_nautilus/runners/backtest_runner.py`) will wrap this class
inside a `nautilus_trader.trading.strategy.Strategy` subclass and translate
each `OrderIntent` into `self.submit_order(...)` calls that flow through the
real `RiskEngine` and `ExecutionEngine`.

Keeping the decision layer pure-Python lets us unit-test risk behaviour
(kill-switch, target sizing, §4.1 gating) without spinning up a full
`BacktestNode`, and keeps the "no bypass of RiskEngine" invariant trivially
verifiable: this file submits no orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import Authorization
from apps.strategies_nautilus.signal_consumer import (
    ConsumerConfig,
    evaluate,
)

Action = Literal["target_long", "target_short", "target_flat", "skip"]


@dataclass(frozen=True)
class BaselineStrategyConfig:
    venue: str
    auth: Authorization
    min_confidence: float = 0.55
    max_position_pct: float = 0.05
    daily_drawdown_stop_pct: float = 0.05

    def __post_init__(self) -> None:
        if not 0.0 < self.min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be in (0, 1], got {self.min_confidence}"
            )
        if not 0.0 < self.max_position_pct <= 1.0:
            raise ValueError(
                f"max_position_pct must be in (0, 1], got {self.max_position_pct}"
            )
        if not 0.0 < self.daily_drawdown_stop_pct <= 1.0:
            raise ValueError(
                f"daily_drawdown_stop_pct must be in (0, 1], "
                f"got {self.daily_drawdown_stop_pct}"
            )

    def to_consumer_config(self) -> ConsumerConfig:
        return ConsumerConfig(
            venue=self.venue,
            auth=self.auth,
            min_confidence=self.min_confidence,
        )


@dataclass(frozen=True)
class OrderIntent:
    signal_id: str
    instrument_id: str
    action: Action
    target_position_pct: float
    reason: str | None = None


@dataclass
class _KillSwitch:
    engaged: bool = False
    reason: str | None = None


@dataclass
class BaselineSignalStrategy:
    config: BaselineStrategyConfig
    _kill_switch: _KillSwitch = field(default_factory=_KillSwitch)

    @property
    def kill_switch_engaged(self) -> bool:
        return self._kill_switch.engaged

    @property
    def kill_switch_reason(self) -> str | None:
        return self._kill_switch.reason

    def on_account_update(self, equity_open: float, equity_now: float) -> None:
        """Re-arm the kill-switch if today's drawdown crosses the threshold.

        ADR-002 §4.2: "单日亏损达到 5%，停止新开仓". `equity_open` is the
        account value at the start of the current UTC trading day; the runner
        is responsible for snapshotting it once per day.
        """
        if self._kill_switch.engaged or equity_open <= 0:
            return
        pnl_pct = (equity_now - equity_open) / equity_open
        if pnl_pct <= -self.config.daily_drawdown_stop_pct:
            self._kill_switch.engaged = True
            self._kill_switch.reason = (
                f"daily_pnl={pnl_pct:.6f} <= "
                f"-{self.config.daily_drawdown_stop_pct:.6f}"
            )

    def on_day_start(self) -> None:
        """Clear the kill-switch at the UTC day boundary."""
        self._kill_switch.engaged = False
        self._kill_switch.reason = None

    def decide(
        self,
        event: SignalEvent,
        *,
        now_ns: int | None = None,
    ) -> OrderIntent:
        instrument_id = _instrument_id(event)
        outcome = evaluate(event, self.config.to_consumer_config(), now_ns=now_ns)
        if outcome.decision != "accept":
            return OrderIntent(
                event.signal_id,
                instrument_id,
                "skip",
                0.0,
                reason=f"{outcome.decision}: {outcome.reason or ''}".rstrip(": "),
            )

        # §4.2 risk-side gate: kill-switch blocks new opens and flips but
        # never blocks a `flat` signal (closing reduces risk).
        if self._kill_switch.engaged and event.side != "flat":
            return OrderIntent(
                event.signal_id,
                instrument_id,
                "skip",
                0.0,
                reason=f"kill_switch: {self._kill_switch.reason}",
            )

        if event.side == "buy":
            return OrderIntent(
                event.signal_id,
                instrument_id,
                "target_long",
                +self.config.max_position_pct,
            )
        if event.side == "sell":
            return OrderIntent(
                event.signal_id,
                instrument_id,
                "target_short",
                -self.config.max_position_pct,
            )
        if event.side == "flat":
            return OrderIntent(
                event.signal_id,
                instrument_id,
                "target_flat",
                0.0,
            )

        # Pydantic Literal["buy","sell","flat"] makes this unreachable.
        raise ValueError(f"unknown side: {event.side!r}")


def _instrument_id(event: SignalEvent) -> str:
    return f"{event.symbol}.{event.venue}"


__all__ = [
    "Action",
    "BaselineSignalStrategy",
    "BaselineStrategyConfig",
    "OrderIntent",
]

"""ADR-007 simulated paper runtime bundle writer.

This is not a live or testnet runner. It consumes local `SignalEvent v1` rows
and catalog bars, runs the same pure decision/risk layer used by the Nautilus
strategy wrapper, simulates fills in memory, and writes an ADR-004-compatible
`kind="paper"` bundle under `data/paper/<run_id>/`.

The module intentionally does not read environment variables, exchange
credentials, or instantiate exchange adapters.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Currency, Money

import nautilus_trader
from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import Authorization
from apps.strategies_nautilus.baseline_strategy import (
    BaselineSignalStrategy,
    BaselineStrategyConfig,
    OrderIntent,
)
from apps.strategies_nautilus.result_schema import SCHEMA_VERSION, BacktestManifest
from apps.strategies_nautilus.runners.backtest_runner import (
    BacktestInputs,
    _git_provenance,
    _hash_signal_store,
    _iso_ms_utc,
    _load_inputs,
    _make_run_id,
    _ns_to_iso_ms,
    _policies_from_args,
    _serialize_policies,
    _stable_id,
    _write_parquet,
    validate_sidecar_bundle,
)
from apps.strategies_nautilus.runners.backtest_runner import (
    _config_from_args as _backtest_config_from_args,
)

NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass
class PaperRunnerConfig:
    output_root: Path
    catalog_path: Path
    instrument_id: str
    bar_type: BarType
    signal_store_path: Path
    baseline_config: BaselineStrategyConfig
    trade_size: Decimal
    starting_balance: Money
    base_currency: Currency
    signal_filter: dict[str, Any] = field(default_factory=dict)
    catalog_start: str | int | None = None
    catalog_end: str | int | None = None
    venue_name: str = "BINANCE"
    trader_id: str = "PAPER_TRADER-001"
    machine_id: str = "local"
    seed: int = 0
    git_commit: str | None = None
    git_dirty: bool | None = None
    nautilus_version: str | None = None
    repo_root: Path | None = None
    data_mode: str = "catalog_polling"
    order_mode: str = "simulated"
    heartbeat_interval_seconds: int = 30
    max_signal_lag_seconds: int = 120
    operator: str = "nishiki"
    previous_run_id: str | None = None

    def __post_init__(self) -> None:
        if self.order_mode != "simulated":
            raise ValueError("paper runner only supports order_mode='simulated'")
        if self.data_mode != "catalog_polling":
            raise ValueError("paper runner only supports data_mode='catalog_polling'")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        if self.max_signal_lag_seconds <= 0:
            raise ValueError("max_signal_lag_seconds must be positive")


@dataclass
class PaperRunResult:
    run_id: str
    output_dir: Path
    manifest: BacktestManifest


@dataclass
class _OpenPosition:
    position_id: str
    side: str
    signed_qty: float
    avg_px_open: float
    opened_ts: int
    opening_order_id: str
    signal_ids: list[str]


@dataclass
class _PaperSimulation:
    orders: pd.DataFrame
    fills: pd.DataFrame
    positions: pd.DataFrame
    account_balances: pd.DataFrame
    signal_lineage: pd.DataFrame
    stats_pnls: dict[str, dict[str, float | int | str | bool | None]]
    stats_returns: dict[str, float | int | str | bool | None]
    strategy_log_lines: list[str]
    risk_log_lines: list[str]


def run_paper_session(config: PaperRunnerConfig) -> PaperRunResult:
    """Run a local simulated paper session and write an ADR-007 bundle."""
    started = datetime.now(UTC)
    run_id = _make_run_id(started)
    output_dir = config.output_root / run_id
    inputs = _load_inputs(config)
    output_dir.mkdir(parents=True, exist_ok=False)

    git_commit, git_dirty = _git_provenance(config)
    nautilus_version = config.nautilus_version or nautilus_trader.__version__
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    simulation = _simulate_paper(config, inputs)
    finished = datetime.now(UTC)

    _write_parquet(simulation.orders, output_dir / "orders.parquet")
    _write_parquet(simulation.fills, output_dir / "fills.parquet")
    _write_parquet(simulation.positions, output_dir / "positions.parquet")
    _write_parquet(
        simulation.account_balances,
        output_dir / "account_balances.parquet",
    )
    _write_parquet(simulation.signal_lineage, output_dir / "signal_lineage.parquet")
    validate_sidecar_bundle(output_dir)

    logs_dir = output_dir / "logs"
    logs_dir.mkdir()
    (logs_dir / "strategy.log").write_text(
        "\n".join(simulation.strategy_log_lines) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "risk.log").write_text(
        "\n".join(simulation.risk_log_lines) + "\n",
        encoding="utf-8",
    )

    manifest_payload = _build_paper_manifest_payload(
        config=config,
        inputs=inputs,
        run_id=run_id,
        git_commit=git_commit,
        git_dirty=git_dirty,
        nautilus_version=nautilus_version,
        python_version=python_version,
        started=started,
        finished=finished,
        simulation=simulation,
    )
    manifest = BacktestManifest.model_validate(manifest_payload)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return PaperRunResult(run_id=run_id, output_dir=output_dir, manifest=manifest)


def _simulate_paper(
    config: PaperRunnerConfig,
    inputs: BacktestInputs,
) -> _PaperSimulation:
    baseline = BaselineSignalStrategy(config=config.baseline_config)
    signals = sorted(inputs.signals, key=lambda s: (int(s.ts_event), s.signal_id))
    signal_idx = 0
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    strategy_log_lines: list[str] = []
    risk_log_lines: list[str] = [
        "paper runtime mode=simulated no_exchange_adapter=true no_live_orders=true"
    ]

    starting_equity = float(config.starting_balance.as_double())
    realized_pnl = 0.0
    open_position: _OpenPosition | None = None
    current_day: date | None = None
    day_open_equity: float | None = None
    last_price = 0.0
    last_ts = 0

    for bar in inputs.bars:
        bar_ts = int(bar.ts_event)
        price = float(bar.close)
        last_price = price
        last_ts = bar_ts
        equity_now = _equity(
            starting_equity=starting_equity,
            realized_pnl=realized_pnl,
            open_position=open_position,
            mark_price=price,
        )
        current_day, day_open_equity = _update_daily_risk_state(
            baseline=baseline,
            current_day=current_day,
            day_open_equity=day_open_equity,
            now_ns=bar_ts,
            equity_now=equity_now,
        )

        while signal_idx < len(signals) and int(signals[signal_idx].ts_event) <= bar_ts:
            event = signals[signal_idx]
            signal_idx += 1
            intent = _decide_with_paper_guards(
                baseline=baseline,
                event=event,
                now_ns=bar_ts,
                max_signal_lag_seconds=config.max_signal_lag_seconds,
            )
            apply_result = _apply_paper_intent(
                config=config,
                event=event,
                intent=intent,
                price=price,
                now_ns=bar_ts,
                open_position=open_position,
                realized_pnl=realized_pnl,
                orders=orders,
                fills=fills,
                positions=positions,
            )
            open_position = apply_result["open_position"]
            realized_pnl = apply_result["realized_pnl"]
            reason = apply_result["reason"]
            order_ids = apply_result["order_ids"]
            fill_ids = apply_result["fill_ids"]
            position_ids = apply_result["position_ids"]
            lineage.append(
                {
                    "signal_id": event.signal_id,
                    "source": event.source,
                    "model_version": event.model_version,
                    "ts_event": int(event.ts_event),
                    "decision": intent.action,
                    "reason": reason,
                    "order_ids": ",".join(order_ids),
                    "fill_ids": ",".join(fill_ids),
                    "position_id": ",".join(position_ids),
                    "ts_decision": bar_ts,
                }
            )
            strategy_log_lines.append(
                json.dumps(
                    {
                        "ts_decision": bar_ts,
                        "signal_id": event.signal_id,
                        "decision": intent.action,
                        "dry_run": intent.dry_run,
                        "reason": reason,
                        "order_ids": order_ids,
                    },
                    sort_keys=True,
                )
            )
            if reason and (
                reason.startswith("reject_")
                or reason.startswith("kill_switch")
                or reason.startswith("signal_lag")
            ):
                risk_log_lines.append(
                    json.dumps(
                        {
                            "ts_decision": bar_ts,
                            "signal_id": event.signal_id,
                            "reason": reason,
                        },
                        sort_keys=True,
                    )
                )

    if open_position is not None:
        positions.append(
            _position_row(
                config=config,
                position=open_position,
                avg_px_close=0.0,
                realized_pnl=0.0,
                unrealized_pnl=_unrealized_pnl(open_position, last_price),
                closed_ts=0,
                closing_signal_id=None,
            )
        )

    final_equity = _equity(
        starting_equity=starting_equity,
        realized_pnl=realized_pnl,
        open_position=open_position,
        mark_price=last_price,
    )
    locked = abs(open_position.signed_qty * last_price) if open_position else 0.0
    account_balances = pd.DataFrame(
        [
            {
                "ts_event": last_ts,
                "venue": config.venue_name,
                "account_id": f"{config.venue_name}-PAPER",
                "currency": str(config.base_currency),
                "total": final_equity,
                "free": final_equity - locked,
                "locked": locked,
            }
        ]
    )
    pnl_total = final_equity - starting_equity
    closed_pnls = [float(row["realized_pnl"]) for row in positions if row["closed_ts"]]
    wins = [p for p in closed_pnls if p > 0.0]
    stats_pnls = {
        str(config.base_currency): {
            "PnL (total)": pnl_total,
            "PnL% (total)": (pnl_total / starting_equity * 100.0)
            if starting_equity
            else 0.0,
            "Win Rate": (len(wins) / len(closed_pnls)) if closed_pnls else None,
            "Expectancy": (sum(closed_pnls) / len(closed_pnls))
            if closed_pnls
            else None,
        }
    }
    return _PaperSimulation(
        orders=pd.DataFrame(orders),
        fills=pd.DataFrame(fills),
        positions=pd.DataFrame(positions),
        account_balances=account_balances,
        signal_lineage=pd.DataFrame(lineage),
        stats_pnls=stats_pnls,
        stats_returns={},
        strategy_log_lines=strategy_log_lines or ["no signals consumed"],
        risk_log_lines=risk_log_lines,
    )


def _decide_with_paper_guards(
    *,
    baseline: BaselineSignalStrategy,
    event: SignalEvent,
    now_ns: int,
    max_signal_lag_seconds: int,
) -> OrderIntent:
    intent = baseline.decide(event, now_ns=now_ns)
    if intent.action == "skip" or event.side == "flat":
        return intent
    lag_ns = now_ns - int(event.ts_event)
    max_lag_ns = max_signal_lag_seconds * NANOSECONDS_PER_SECOND
    if lag_ns > max_lag_ns:
        return OrderIntent(
            signal_id=event.signal_id,
            instrument_id=f"{event.symbol}.{event.venue}",
            action="skip",
            target_position_pct=0.0,
            reason=(
                f"signal_lag: {lag_ns / NANOSECONDS_PER_SECOND:.3f}s "
                f"> {max_signal_lag_seconds}s"
            ),
        )
    return intent


def _apply_paper_intent(
    *,
    config: PaperRunnerConfig,
    event: SignalEvent,
    intent: OrderIntent,
    price: float,
    now_ns: int,
    open_position: _OpenPosition | None,
    realized_pnl: float,
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    order_ids: list[str] = []
    fill_ids: list[str] = []
    position_ids: list[str] = []
    reason = intent.reason or ""
    if intent.action == "skip":
        return {
            "open_position": open_position,
            "realized_pnl": realized_pnl,
            "reason": reason,
            "order_ids": order_ids,
            "fill_ids": fill_ids,
            "position_ids": position_ids,
        }
    if intent.dry_run:
        return {
            "open_position": open_position,
            "realized_pnl": realized_pnl,
            "reason": reason or "dry_run",
            "order_ids": order_ids,
            "fill_ids": fill_ids,
            "position_ids": position_ids,
        }
    if intent.action != "target_flat" and abs(intent.target_position_pct) == 0.0:
        return {
            "open_position": open_position,
            "realized_pnl": realized_pnl,
            "reason": "target_position_pct_zero",
            "order_ids": order_ids,
            "fill_ids": fill_ids,
            "position_ids": position_ids,
        }

    if intent.action == "target_long":
        if open_position is not None and open_position.signed_qty > 0:
            reason = "already_target_long"
        else:
            if open_position is not None:
                close_result = _close_position(
                    config=config,
                    event=event,
                    position=open_position,
                    price=price,
                    now_ns=now_ns,
                    orders=orders,
                    fills=fills,
                    positions=positions,
                )
                order_ids.extend(close_result["order_ids"])
                fill_ids.extend(close_result["fill_ids"])
                position_ids.extend(close_result["position_ids"])
                realized_pnl += close_result["realized_pnl"]
            open_position = _open_position(
                config=config,
                event=event,
                side="LONG",
                price=price,
                now_ns=now_ns,
                orders=orders,
                fills=fills,
                order_ids=order_ids,
                fill_ids=fill_ids,
                position_ids=position_ids,
                target_position_pct=abs(intent.target_position_pct),
            )
    elif intent.action == "target_short":
        if open_position is not None and open_position.signed_qty < 0:
            reason = "already_target_short"
        else:
            if open_position is not None:
                close_result = _close_position(
                    config=config,
                    event=event,
                    position=open_position,
                    price=price,
                    now_ns=now_ns,
                    orders=orders,
                    fills=fills,
                    positions=positions,
                )
                order_ids.extend(close_result["order_ids"])
                fill_ids.extend(close_result["fill_ids"])
                position_ids.extend(close_result["position_ids"])
                realized_pnl += close_result["realized_pnl"]
            open_position = _open_position(
                config=config,
                event=event,
                side="SHORT",
                price=price,
                now_ns=now_ns,
                orders=orders,
                fills=fills,
                order_ids=order_ids,
                fill_ids=fill_ids,
                position_ids=position_ids,
                target_position_pct=abs(intent.target_position_pct),
            )
    elif intent.action == "target_flat":
        if open_position is None:
            reason = "already_flat"
        else:
            close_result = _close_position(
                config=config,
                event=event,
                position=open_position,
                price=price,
                now_ns=now_ns,
                orders=orders,
                fills=fills,
                positions=positions,
            )
            order_ids.extend(close_result["order_ids"])
            fill_ids.extend(close_result["fill_ids"])
            position_ids.extend(close_result["position_ids"])
            realized_pnl += close_result["realized_pnl"]
            open_position = None
    else:
        raise ValueError(f"unknown paper intent action={intent.action!r}")

    return {
        "open_position": open_position,
        "realized_pnl": realized_pnl,
        "reason": reason,
        "order_ids": order_ids,
        "fill_ids": fill_ids,
        "position_ids": position_ids,
    }


def _open_position(
    *,
    config: PaperRunnerConfig,
    event: SignalEvent,
    side: str,
    price: float,
    now_ns: int,
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    order_ids: list[str],
    fill_ids: list[str],
    position_ids: list[str],
    target_position_pct: float,
) -> _OpenPosition:
    qty = _paper_quantity(config, target_position_pct)
    signed_qty = qty if side == "LONG" else -qty
    order_side = "BUY" if side == "LONG" else "SELL"
    order_id, fill_id = _append_order_and_fill(
        config=config,
        event=event,
        order_side=order_side,
        quantity=qty,
        price=price,
        now_ns=now_ns,
        orders=orders,
        fills=fills,
    )
    position_id = _stable_id("paper-position", [event.signal_id, now_ns, side])
    order_ids.append(order_id)
    fill_ids.append(fill_id)
    position_ids.append(position_id)
    return _OpenPosition(
        position_id=position_id,
        side=side,
        signed_qty=signed_qty,
        avg_px_open=price,
        opened_ts=now_ns,
        opening_order_id=order_id,
        signal_ids=[event.signal_id],
    )


def _close_position(
    *,
    config: PaperRunnerConfig,
    event: SignalEvent,
    position: _OpenPosition,
    price: float,
    now_ns: int,
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    order_side = "SELL" if position.signed_qty > 0 else "BUY"
    order_id, fill_id = _append_order_and_fill(
        config=config,
        event=event,
        order_side=order_side,
        quantity=abs(position.signed_qty),
        price=price,
        now_ns=now_ns,
        orders=orders,
        fills=fills,
    )
    pnl = position.signed_qty * (price - position.avg_px_open)
    positions.append(
        _position_row(
            config=config,
            position=position,
            avg_px_close=price,
            realized_pnl=pnl,
            unrealized_pnl=0.0,
            closed_ts=now_ns,
            closing_signal_id=event.signal_id,
        )
    )
    return {
        "order_ids": [order_id],
        "fill_ids": [fill_id],
        "position_ids": [position.position_id],
        "realized_pnl": pnl,
    }


def _append_order_and_fill(
    *,
    config: PaperRunnerConfig,
    event: SignalEvent,
    order_side: str,
    quantity: float,
    price: float,
    now_ns: int,
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> tuple[str, str]:
    sequence = len(orders) + 1
    order_id = _stable_id("paper-order", [sequence, event.signal_id, order_side])
    fill_id = _stable_id("paper-fill", [sequence, event.signal_id, order_side])
    order = {
        "order_id": order_id,
        "client_order_id": order_id,
        "venue": config.venue_name,
        "instrument_id": config.instrument_id,
        "side": order_side,
        "quantity": quantity,
        "price": price,
        "type": "MARKET",
        "status": "FILLED",
        "ts_init": now_ns,
        "ts_last": now_ns,
        "signal_id": event.signal_id,
    }
    fill = {
        "fill_id": fill_id,
        "order_id": order_id,
        "venue": config.venue_name,
        "instrument_id": config.instrument_id,
        "side": order_side,
        "quantity": quantity,
        "price": price,
        "commission": 0.0,
        "currency": str(config.base_currency),
        "ts_event": now_ns,
        "signal_id": event.signal_id,
    }
    orders.append(order)
    fills.append(fill)
    return order_id, fill_id


def _position_row(
    *,
    config: PaperRunnerConfig,
    position: _OpenPosition,
    avg_px_close: float,
    realized_pnl: float,
    unrealized_pnl: float,
    closed_ts: int,
    closing_signal_id: str | None,
) -> dict[str, Any]:
    signal_ids = list(position.signal_ids)
    if closing_signal_id is not None:
        signal_ids.append(closing_signal_id)
    return {
        "position_id": position.position_id,
        "venue": config.venue_name,
        "instrument_id": config.instrument_id,
        "side": position.side,
        "quantity": abs(position.signed_qty),
        "peak_qty": abs(position.signed_qty),
        "avg_px_open": position.avg_px_open,
        "avg_px_close": avg_px_close,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "opened_ts": position.opened_ts,
        "closed_ts": closed_ts,
        "signal_ids": ",".join(signal_ids),
    }


def _paper_quantity(config: PaperRunnerConfig, target_position_pct: float) -> float:
    if config.baseline_config.max_position_pct <= 0:
        return 0.0
    scale = target_position_pct / config.baseline_config.max_position_pct
    return float(config.trade_size) * scale


def _update_daily_risk_state(
    *,
    baseline: BaselineSignalStrategy,
    current_day: date | None,
    day_open_equity: float | None,
    now_ns: int,
    equity_now: float,
) -> tuple[date, float]:
    next_day = datetime.fromtimestamp(now_ns / NANOSECONDS_PER_SECOND, tz=UTC).date()
    if current_day != next_day:
        baseline.on_day_start()
        return next_day, equity_now
    if day_open_equity is not None:
        baseline.on_account_update(equity_open=day_open_equity, equity_now=equity_now)
    return next_day, day_open_equity or equity_now


def _equity(
    *,
    starting_equity: float,
    realized_pnl: float,
    open_position: _OpenPosition | None,
    mark_price: float,
) -> float:
    return starting_equity + realized_pnl + _unrealized_pnl(open_position, mark_price)


def _unrealized_pnl(
    position: _OpenPosition | None,
    mark_price: float,
) -> float:
    if position is None:
        return 0.0
    return position.signed_qty * (mark_price - position.avg_px_open)


def _build_paper_manifest_payload(
    *,
    config: PaperRunnerConfig,
    inputs: BacktestInputs,
    run_id: str,
    git_commit: str,
    git_dirty: bool,
    nautilus_version: str,
    python_version: str,
    started: datetime,
    finished: datetime,
    simulation: _PaperSimulation,
) -> dict[str, Any]:
    min_bar_ns = min(int(b.ts_event) for b in inputs.bars)
    max_bar_ns = max(int(b.ts_event) for b in inputs.bars)
    min_signal_ns = (
        min(int(s.ts_event) for s in inputs.signals) if inputs.signals else 0
    )
    max_signal_ns = (
        max(int(s.ts_event) for s in inputs.signals) if inputs.signals else 0
    )
    runtime: dict[str, Any] = {
        "mode": "paper",
        "data_mode": config.data_mode,
        "order_mode": config.order_mode,
        "heartbeat_interval_seconds": config.heartbeat_interval_seconds,
        "max_signal_lag_seconds": config.max_signal_lag_seconds,
        "operator": config.operator,
    }
    if config.previous_run_id is not None:
        runtime["previous_run_id"] = config.previous_run_id
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "kind": "paper",
        "trader_id": config.trader_id,
        "machine_id": config.machine_id,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "nautilus_version": nautilus_version,
        "python_version": python_version,
        "started_at": _iso_ms_utc(started),
        "finished_at": _iso_ms_utc(finished),
        "elapsed_seconds": (finished - started).total_seconds(),
        "backtest_start": _ns_to_iso_ms(min_bar_ns),
        "backtest_end": _ns_to_iso_ms(max_bar_ns),
        "venues": [config.venue_name],
        "instruments": [inputs.instrument.id.value],
        "strategies": [
            {
                "name": "baseline_signal_strategy",
                "params": {
                    "min_confidence": config.baseline_config.min_confidence,
                    "max_position_pct": config.baseline_config.max_position_pct,
                    "daily_drawdown_stop_pct": config.baseline_config.daily_drawdown_stop_pct,
                    "trade_size": str(config.trade_size),
                    "seed": config.seed,
                    "policies": _serialize_policies(
                        config.baseline_config.auth.policies
                    ),
                },
            }
        ],
        "risk_rules": [
            {
                "name": "daily_drawdown_stop",
                "params": {
                    "max_pct": config.baseline_config.daily_drawdown_stop_pct
                },
            },
            {
                "name": "max_signal_lag",
                "params": {"max_seconds": config.max_signal_lag_seconds},
            },
        ],
        "signal_source": {
            "store_path": str(config.signal_store_path),
            "store_sha256": _hash_signal_store(config.signal_store_path),
            "filter": config.signal_filter,
            "row_count": len(inputs.signals),
            "min_ts_event_ns": min_signal_ns,
            "max_ts_event_ns": max_signal_ns,
        },
        "data_catalog": {
            "path": str(config.catalog_path),
            "instruments": [
                {
                    "id": inputs.instrument.id.value,
                    "bars": str(config.bar_type),
                    "rows": len(inputs.bars),
                }
            ],
        },
        "totals": {
            "iterations": len(inputs.bars),
            "events": len(simulation.signal_lineage),
            "orders": len(simulation.orders),
            "positions": len(simulation.positions),
            "fills": len(simulation.fills),
        },
        "stats_pnls": simulation.stats_pnls,
        "stats_returns": simulation.stats_returns,
        "runtime": runtime,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a simulated ADR-007 paper session from catalog + SignalStore.",
    )
    parser.add_argument("--output-root", type=Path, default=Path("data/paper"))
    parser.add_argument("--catalog-path", type=Path, default=Path("data/catalog"))
    parser.add_argument("--instrument-id", required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--catalog-start")
    parser.add_argument("--catalog-end")
    parser.add_argument(
        "--signal-store-path",
        type=Path,
        default=Path("data/bridge/signals.db"),
    )
    parser.add_argument("--signal-source")
    parser.add_argument("--signal-model-version")
    parser.add_argument("--signal-since-ns", type=int)
    parser.add_argument("--signal-until-ns", type=int)
    parser.add_argument("--allowed-source", action="append", default=[])
    parser.add_argument("--allowed-model-version", action="append", default=[])
    parser.add_argument("--policy-source")
    parser.add_argument("--policy-model-version")
    parser.add_argument("--policy-position-pct-multiplier", type=float)
    parser.add_argument("--policy-min-confidence-override", type=float)
    parser.add_argument("--policy-dry-run", action="store_true")
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--trade-size", type=Decimal, required=True)
    parser.add_argument("--starting-balance", type=Decimal, required=True)
    parser.add_argument("--base-currency", default="USDT")
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--max-position-pct", type=float, default=0.05)
    parser.add_argument("--daily-drawdown-stop-pct", type=float, default=0.05)
    parser.add_argument("--trader-id", default="PAPER_TRADER-001")
    parser.add_argument("--machine-id", default="local")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=30)
    parser.add_argument("--max-signal-lag-seconds", type=int, default=120)
    parser.add_argument("--operator", default="nishiki")
    parser.add_argument("--previous-run-id")
    return parser


def _config_from_args(args: argparse.Namespace) -> PaperRunnerConfig:
    base = _backtest_config_from_args(args)
    return PaperRunnerConfig(
        output_root=args.output_root,
        catalog_path=base.catalog_path,
        instrument_id=base.instrument_id,
        bar_type=base.bar_type,
        signal_store_path=base.signal_store_path,
        baseline_config=BaselineStrategyConfig(
            venue=base.baseline_config.venue,
            auth=Authorization(
                allowed_sources=base.baseline_config.auth.allowed_sources,
                allowed_model_versions=base.baseline_config.auth.allowed_model_versions,
                policies=_policies_from_args(args),
            ),
            min_confidence=base.baseline_config.min_confidence,
            max_position_pct=base.baseline_config.max_position_pct,
            daily_drawdown_stop_pct=base.baseline_config.daily_drawdown_stop_pct,
        ),
        trade_size=base.trade_size,
        starting_balance=base.starting_balance,
        base_currency=base.base_currency,
        signal_filter=base.signal_filter,
        catalog_start=base.catalog_start,
        catalog_end=base.catalog_end,
        venue_name=base.venue_name,
        trader_id=args.trader_id,
        machine_id=base.machine_id,
        seed=base.seed,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        max_signal_lag_seconds=args.max_signal_lag_seconds,
        operator=args.operator,
        previous_run_id=args.previous_run_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        config = _config_from_args(args)
        result = run_paper_session(config)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(result.output_dir)
    return 0


__all__ = [
    "PaperRunnerConfig",
    "PaperRunResult",
    "run_paper_session",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

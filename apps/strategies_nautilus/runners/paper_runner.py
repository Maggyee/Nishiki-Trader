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
import hashlib
import json
import sys
import threading
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

import nautilus_trader
from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
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
    _load_signals,
    _make_run_id,
    _ns_to_iso_ms,
    _policies_from_args,
    _select_instrument,
    _serialize_policies,
    _stable_id,
    _write_parquet,
    validate_sidecar_bundle,
)
from apps.strategies_nautilus.runners.backtest_runner import (
    _config_from_args as _backtest_config_from_args,
)
from apps.strategies_nautilus.runners.wall_clock_bar_feed import (
    DEFAULT_BINANCE_PUBLIC_WS_URL,
    BarFeed,
    BinancePublicBarFeed,
)

NANOSECONDS_PER_SECOND = 1_000_000_000
_ALLOWED_DATA_MODES = ("catalog_polling", "wall_clock")
SHUTDOWN_REASON_COMPLETED = "completed"
SHUTDOWN_REASON_MAX_BARS = "max_bars"
SHUTDOWN_REASON_MAX_DURATION = "max_duration"
SHUTDOWN_REASON_SIGTERM = "sigterm"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_BAR_INTERVAL_NANOS: dict[str, int] = {
    "NANOSECOND": 1,
    "MICROSECOND": 1_000,
    "MILLISECOND": 1_000_000,
    "SECOND": NANOSECONDS_PER_SECOND,
    "MINUTE": 60 * NANOSECONDS_PER_SECOND,
    "HOUR": 60 * 60 * NANOSECONDS_PER_SECOND,
    "DAY": 24 * 60 * 60 * NANOSECONDS_PER_SECOND,
}


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
    poll_interval_seconds: int = 60
    poll_batch_size: int = 1
    max_signal_lag_seconds: int = 120
    data_gap_tolerance_intervals: int = 1
    operator: str = "nishiki"
    previous_run_id: str | None = None
    restart_reason: str | None = None
    max_duration_seconds: int | None = None
    max_bars: int | None = None
    ws_base_url: str = DEFAULT_BINANCE_PUBLIC_WS_URL
    ws_symbol: str | None = None
    ws_interval: str = "1m"
    signal_poll_interval_seconds: int = 5

    def __post_init__(self) -> None:
        if self.order_mode != "simulated":
            raise ValueError("paper runner only supports order_mode='simulated'")
        if self.data_mode not in _ALLOWED_DATA_MODES:
            raise ValueError(
                f"paper runner only supports data_mode in {_ALLOWED_DATA_MODES}"
            )
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.poll_batch_size <= 0:
            raise ValueError("poll_batch_size must be positive")
        if self.max_signal_lag_seconds <= 0:
            raise ValueError("max_signal_lag_seconds must be positive")
        if self.data_gap_tolerance_intervals <= 0:
            raise ValueError("data_gap_tolerance_intervals must be positive")
        if self.signal_poll_interval_seconds <= 0:
            raise ValueError("signal_poll_interval_seconds must be positive")
        if self.data_mode == "wall_clock":
            if self.max_duration_seconds is None and self.max_bars is None:
                raise ValueError(
                    "wall_clock data_mode requires max_duration_seconds or max_bars"
                )
            if self.max_duration_seconds is not None and self.max_duration_seconds <= 0:
                raise ValueError("max_duration_seconds must be positive")
            if self.max_bars is not None and self.max_bars <= 0:
                raise ValueError("max_bars must be positive")
            if not self.ws_symbol:
                raise ValueError("wall_clock data_mode requires ws_symbol")
            if not self.ws_base_url:
                raise ValueError("wall_clock data_mode requires ws_base_url")


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
    runtime_log_lines: list[str]
    heartbeat_rows: list[dict[str, Any]]
    data_gaps: list[dict[str, Any]]
    poll_count: int
    first_processed_ns: int
    processed_until_ns: int
    expected_bar_interval_ns: int | None
    bar_count: int = 0
    shutdown_reason: str = SHUTDOWN_REASON_COMPLETED
    ws_reconnect_count: int = 0
    duplicate_bars_dropped: int = 0
    ws_endpoint: str | None = None
    ws_stream: str | None = None
    bar_source: str = "catalog"


@dataclass(frozen=True)
class _RuntimeContext:
    config: PaperRunnerConfig
    previous_manifest_found: bool = False
    previous_manifest_sha256: str | None = None
    previous_processed_until_ns: int | None = None
    resume_from_ns: int | None = None
    restart_sequence: int = 0
    catalog_start_overridden: bool = False


def run_paper_session(
    config: PaperRunnerConfig,
    *,
    bar_feed: BarFeed | None = None,
    stop_event: Any = None,
) -> PaperRunResult:
    """Run a local simulated paper session and write an ADR-007 bundle.

    ``bar_feed`` and ``stop_event`` are injection points for tests of the
    wall_clock data mode; in catalog_polling mode they must not be passed.
    """
    if config.data_mode == "catalog_polling" and bar_feed is not None:
        raise ValueError("bar_feed is only used with data_mode='wall_clock'")
    started = datetime.now(UTC)
    run_id = _make_run_id(started)
    runtime_context = _resolve_runtime_context(config)
    config = runtime_context.config
    output_dir = config.output_root / run_id
    inputs = _load_inputs_for_paper(config)
    output_dir.mkdir(parents=True, exist_ok=False)

    git_commit, git_dirty = _git_provenance(config)
    nautilus_version = config.nautilus_version or nautilus_trader.__version__
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    if config.data_mode == "wall_clock":
        simulation = _simulate_paper_wall_clock(
            config=config,
            inputs=inputs,
            bar_feed=bar_feed,
            stop_event=stop_event,
        )
    else:
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
    (logs_dir / "runtime.log").write_text(
        "\n".join(simulation.runtime_log_lines) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "heartbeat.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in simulation.heartbeat_rows
        ),
        encoding="utf-8",
    )

    manifest_payload = _build_paper_manifest_payload(
        config=config,
        runtime_context=runtime_context,
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


def _load_inputs_for_paper(config: PaperRunnerConfig) -> BacktestInputs:
    """Load inputs honoring data_mode.

    catalog_polling delegates to :func:`_load_inputs` (instrument + bars +
    signals). wall_clock loads only the instrument and a snapshot of signals;
    bars stream in live from the bar feed during the run.
    """
    if config.data_mode != "wall_clock":
        return _load_inputs(config)
    catalog = ParquetDataCatalog(str(config.catalog_path.resolve()))
    instruments = catalog.instruments(instrument_ids=[config.instrument_id])
    instrument = _select_instrument(instruments, config.instrument_id)
    if str(config.bar_type.instrument_id) != config.instrument_id:
        raise ValueError(
            f"bar_type instrument {config.bar_type.instrument_id} does not match "
            f"instrument_id {config.instrument_id}"
        )
    signals = _load_signals(config.signal_store_path, config.signal_filter)
    return BacktestInputs(instrument=instrument, bars=[], signals=signals)


@dataclass
class _StepState:
    config: PaperRunnerConfig
    baseline: BaselineSignalStrategy
    starting_equity: float
    realized_pnl: float = 0.0
    open_position: _OpenPosition | None = None
    current_day: date | None = None
    day_open_equity: float | None = None
    last_price: float = 0.0
    last_ts: int = 0
    first_processed_ns: int = 0
    processed_until_ns: int = 0
    expected_interval_ns: int | None = None
    previous_bar_ts: int | None = None
    last_heartbeat_ns: int | None = None
    poll_count: int = 0
    bar_count: int = 0
    orders: list[dict[str, Any]] = field(default_factory=list)
    fills: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    account_rows: list[dict[str, Any]] = field(default_factory=list)
    lineage: list[dict[str, Any]] = field(default_factory=list)
    strategy_log_lines: list[str] = field(default_factory=list)
    risk_log_lines: list[str] = field(default_factory=list)
    runtime_log_lines: list[str] = field(default_factory=list)
    heartbeat_rows: list[dict[str, Any]] = field(default_factory=list)
    data_gaps: list[dict[str, Any]] = field(default_factory=list)


def _make_step_state(config: PaperRunnerConfig) -> _StepState:
    baseline = BaselineSignalStrategy(config=config.baseline_config)
    state = _StepState(
        config=config,
        baseline=baseline,
        starting_equity=float(config.starting_balance.as_double()),
        expected_interval_ns=_expected_bar_interval_ns(config.bar_type),
    )
    state.risk_log_lines.append(
        "paper runtime mode=simulated no_exchange_adapter=true no_live_orders=true"
    )
    state.runtime_log_lines.append(
        json.dumps(
            {
                "event": "runtime_start",
                "data_mode": config.data_mode,
                "order_mode": config.order_mode,
                "poll_interval_seconds": config.poll_interval_seconds,
                "poll_batch_size": config.poll_batch_size,
            },
            sort_keys=True,
        )
    )
    return state


def _step_one_bar(
    *,
    state: _StepState,
    bar: Any,
    signals: list[SignalEvent],
    signal_idx: int,
) -> int:
    """Process one bar and consume signals with ts_event <= bar.ts_event.

    Returns the new signal_idx after consumption. Mutates state in place.
    """
    config = state.config
    bar_ts = int(bar.ts_event)
    price = float(bar.close)
    state.last_price = price
    state.last_ts = bar_ts
    state.processed_until_ns = bar_ts
    state.bar_count += 1
    if state.first_processed_ns == 0:
        state.first_processed_ns = bar_ts
    if state.previous_bar_ts is not None and state.expected_interval_ns is not None:
        gap = _market_data_gap(
            previous_ts=state.previous_bar_ts,
            current_ts=bar_ts,
            expected_interval_ns=state.expected_interval_ns,
            tolerance_intervals=config.data_gap_tolerance_intervals,
        )
        if gap is not None:
            state.data_gaps.append(gap)
            state.runtime_log_lines.append(
                json.dumps({"event": "data_gap", **gap}, sort_keys=True)
            )
            state.risk_log_lines.append(
                json.dumps({"reason": "data_gap", **gap}, sort_keys=True)
            )
    state.previous_bar_ts = bar_ts

    equity_now = _equity(
        starting_equity=state.starting_equity,
        realized_pnl=state.realized_pnl,
        open_position=state.open_position,
        mark_price=price,
    )
    state.current_day, state.day_open_equity = _update_daily_risk_state(
        baseline=state.baseline,
        current_day=state.current_day,
        day_open_equity=state.day_open_equity,
        now_ns=bar_ts,
        equity_now=equity_now,
    )

    while (
        signal_idx < len(signals)
        and int(signals[signal_idx].ts_event) <= bar_ts
    ):
        event = signals[signal_idx]
        signal_idx += 1
        intent = _decide_with_paper_guards(
            baseline=state.baseline,
            event=event,
            now_ns=bar_ts,
            max_signal_lag_seconds=config.max_signal_lag_seconds,
            data_gap_reason=_data_gap_reason_for_signal(
                int(event.ts_event),
                state.data_gaps,
            ),
        )
        apply_result = _apply_paper_intent(
            config=config,
            event=event,
            intent=intent,
            price=price,
            now_ns=bar_ts,
            open_position=state.open_position,
            realized_pnl=state.realized_pnl,
            orders=state.orders,
            fills=state.fills,
            positions=state.positions,
        )
        state.open_position = apply_result["open_position"]
        state.realized_pnl = apply_result["realized_pnl"]
        reason = apply_result["reason"]
        order_ids = apply_result["order_ids"]
        fill_ids = apply_result["fill_ids"]
        position_ids = apply_result["position_ids"]
        state.lineage.append(
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
        state.strategy_log_lines.append(
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
            or reason.startswith("data_gap")
        ):
            state.risk_log_lines.append(
                json.dumps(
                    {
                        "ts_decision": bar_ts,
                        "signal_id": event.signal_id,
                        "reason": reason,
                    },
                    sort_keys=True,
                )
            )

    equity_after_bar = _equity(
        starting_equity=state.starting_equity,
        realized_pnl=state.realized_pnl,
        open_position=state.open_position,
        mark_price=price,
    )
    locked = abs(state.open_position.signed_qty * price) if state.open_position else 0.0
    state.account_rows.append(
        _account_balance_row(
            config=config,
            ts_event=bar_ts,
            total=equity_after_bar,
            locked=locked,
        )
    )
    if _should_emit_heartbeat(
        last_heartbeat_ns=state.last_heartbeat_ns,
        now_ns=bar_ts,
        heartbeat_interval_seconds=config.heartbeat_interval_seconds,
    ):
        state.last_heartbeat_ns = bar_ts
        heartbeat = _heartbeat_row(
            poll_number=state.poll_count,
            ts_event=bar_ts,
            equity=equity_after_bar,
            last_price=price,
            open_position=state.open_position,
            signal_idx=signal_idx,
            order_count=len(state.orders),
            fill_count=len(state.fills),
            data_gap_count=len(state.data_gaps),
        )
        state.heartbeat_rows.append(heartbeat)
        state.runtime_log_lines.append(
            json.dumps({"event": "heartbeat", **heartbeat}, sort_keys=True)
        )
    return signal_idx


def _close_open_position_as_unrealized(state: _StepState) -> None:
    if state.open_position is None:
        return
    state.positions.append(
        _position_row(
            config=state.config,
            position=state.open_position,
            avg_px_close=0.0,
            realized_pnl=0.0,
            unrealized_pnl=_unrealized_pnl(state.open_position, state.last_price),
            closed_ts=0,
            closing_signal_id=None,
        )
    )


def _ensure_at_least_one_account_row(state: _StepState) -> None:
    if state.account_rows:
        return
    state.account_rows.append(
        _account_balance_row(
            config=state.config,
            ts_event=state.last_ts,
            total=state.starting_equity,
            locked=0.0,
        )
    )


def _finalize_step_state(
    *,
    state: _StepState,
    shutdown_reason: str = SHUTDOWN_REASON_COMPLETED,
    bar_source: str = "catalog",
    ws_reconnect_count: int = 0,
    duplicate_bars_dropped: int = 0,
    ws_endpoint: str | None = None,
    ws_stream: str | None = None,
) -> _PaperSimulation:
    config = state.config
    _close_open_position_as_unrealized(state)
    _ensure_at_least_one_account_row(state)
    account_balances = pd.DataFrame(state.account_rows)
    final_equity = float(state.account_rows[-1]["total"])
    drawdown = _max_drawdown(state.account_rows)
    pnl_total = final_equity - state.starting_equity
    closed_pnls = [
        float(row["realized_pnl"]) for row in state.positions if row["closed_ts"]
    ]
    wins = [p for p in closed_pnls if p > 0.0]
    stats_pnls = {
        str(config.base_currency): {
            "PnL (total)": pnl_total,
            "PnL% (total)": (pnl_total / state.starting_equity * 100.0)
            if state.starting_equity
            else 0.0,
            "Win Rate": (len(wins) / len(closed_pnls)) if closed_pnls else None,
            "Expectancy": (sum(closed_pnls) / len(closed_pnls))
            if closed_pnls
            else None,
            "Max Drawdown (Pct)": drawdown["max_drawdown_pct"],
            "Max Drawdown (Abs)": drawdown["max_drawdown_abs"],
        }
    }
    return _PaperSimulation(
        orders=pd.DataFrame(state.orders),
        fills=pd.DataFrame(state.fills),
        positions=pd.DataFrame(state.positions),
        account_balances=account_balances,
        signal_lineage=pd.DataFrame(state.lineage),
        stats_pnls=stats_pnls,
        stats_returns={
            "max_drawdown": drawdown["max_drawdown_pct"],
            "max_drawdown_abs": drawdown["max_drawdown_abs"],
        },
        strategy_log_lines=state.strategy_log_lines or ["no signals consumed"],
        risk_log_lines=state.risk_log_lines,
        runtime_log_lines=state.runtime_log_lines,
        heartbeat_rows=state.heartbeat_rows,
        data_gaps=state.data_gaps,
        poll_count=state.poll_count,
        first_processed_ns=state.first_processed_ns,
        processed_until_ns=state.processed_until_ns,
        expected_bar_interval_ns=state.expected_interval_ns,
        bar_count=state.bar_count,
        shutdown_reason=shutdown_reason,
        ws_reconnect_count=ws_reconnect_count,
        duplicate_bars_dropped=duplicate_bars_dropped,
        ws_endpoint=ws_endpoint,
        ws_stream=ws_stream,
        bar_source=bar_source,
    )


def _simulate_paper(
    config: PaperRunnerConfig,
    inputs: BacktestInputs,
) -> _PaperSimulation:
    state = _make_step_state(config)
    signals = sorted(inputs.signals, key=lambda s: (int(s.ts_event), s.signal_id))
    signal_idx = 0

    for poll_count, batch in enumerate(
        _iter_poll_batches(inputs.bars, config.poll_batch_size),
        start=1,
    ):
        state.poll_count = poll_count
        state.runtime_log_lines.append(
            json.dumps(
                {
                    "event": "poll",
                    "poll_number": poll_count,
                    "batch_rows": len(batch),
                    "from_ts_event": int(batch[0].ts_event),
                    "until_ts_event": int(batch[-1].ts_event),
                },
                sort_keys=True,
            )
        )
        for bar in batch:
            signal_idx = _step_one_bar(
                state=state,
                bar=bar,
                signals=signals,
                signal_idx=signal_idx,
            )

    return _finalize_step_state(state=state, bar_source="catalog")


def _make_wall_clock_runtime_start_log(config: PaperRunnerConfig) -> str:
    return json.dumps(
        {
            "event": "wall_clock_runtime_start",
            "ws_base_url": config.ws_base_url,
            "ws_symbol": config.ws_symbol,
            "ws_interval": config.ws_interval,
            "max_duration_seconds": config.max_duration_seconds,
            "max_bars": config.max_bars,
            "signal_poll_interval_seconds": config.signal_poll_interval_seconds,
        },
        sort_keys=True,
    )


def _simulate_paper_wall_clock(
    *,
    config: PaperRunnerConfig,
    inputs: BacktestInputs,
    bar_feed: BarFeed | None,
    stop_event: Any,
) -> _PaperSimulation:
    import time as _time

    feed = bar_feed
    owns_feed = False
    if feed is None:
        feed = BinancePublicBarFeed(
            symbol=config.ws_symbol or "",
            interval=config.ws_interval,
            base_url=config.ws_base_url,
        )
        owns_feed = True

    state = _make_step_state(config)
    state.runtime_log_lines.append(_make_wall_clock_runtime_start_log(config))
    signal_store = SignalStore(config.signal_store_path)
    signals = sorted(inputs.signals, key=lambda s: (int(s.ts_event), s.signal_id))
    signal_idx = 0
    last_signal_ts = signals[-1].ts_event if signals else None
    deadline_monotonic: float | None = None
    if config.max_duration_seconds is not None:
        deadline_monotonic = _time.monotonic() + config.max_duration_seconds
    last_signal_repoll_monotonic = _time.monotonic()
    shutdown_reason = SHUTDOWN_REASON_COMPLETED

    if owns_feed:
        feed.start()
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                shutdown_reason = SHUTDOWN_REASON_SIGTERM
                break
            if config.max_bars is not None and state.bar_count >= config.max_bars:
                shutdown_reason = SHUTDOWN_REASON_MAX_BARS
                break
            if (
                deadline_monotonic is not None
                and _time.monotonic() >= deadline_monotonic
            ):
                shutdown_reason = SHUTDOWN_REASON_MAX_DURATION
                break

            wait = float(config.signal_poll_interval_seconds)
            if deadline_monotonic is not None:
                wait = max(0.0, min(wait, deadline_monotonic - _time.monotonic()))
            bar = feed.next_bar(timeout=wait) if wait > 0 else None
            now_monotonic = _time.monotonic()

            if (
                now_monotonic - last_signal_repoll_monotonic
                >= config.signal_poll_interval_seconds
            ):
                signals, signal_idx, last_signal_ts = _wall_clock_refresh_signals(
                    signal_store=signal_store,
                    base_filter=config.signal_filter,
                    last_signal_ts=last_signal_ts,
                    signals=signals,
                    signal_idx=signal_idx,
                )
                last_signal_repoll_monotonic = now_monotonic

            if bar is None:
                continue

            state.poll_count += 1
            state.runtime_log_lines.append(
                json.dumps(
                    {
                        "event": "poll",
                        "poll_number": state.poll_count,
                        "batch_rows": 1,
                        "from_ts_event": int(bar.ts_event),
                        "until_ts_event": int(bar.ts_event),
                    },
                    sort_keys=True,
                )
            )
            signal_idx = _step_one_bar(
                state=state,
                bar=bar,
                signals=signals,
                signal_idx=signal_idx,
            )
    finally:
        if owns_feed:
            feed.stop()

    return _finalize_step_state(
        state=state,
        shutdown_reason=shutdown_reason,
        bar_source=feed.source_name,
        ws_reconnect_count=feed.reconnect_count,
        duplicate_bars_dropped=feed.duplicate_bars_dropped,
        ws_endpoint=feed.endpoint,
        ws_stream=feed.stream_name,
    )


def _wall_clock_refresh_signals(
    *,
    signal_store: SignalStore,
    base_filter: dict[str, Any],
    last_signal_ts: int | None,
    signals: list[SignalEvent],
    signal_idx: int,
) -> tuple[list[SignalEvent], int, int | None]:
    """Incrementally pull newly-written signals from the SignalStore.

    Bars and signals can arrive interleaved during a wall-clock run; this lets
    an upstream research process feed signals into the store while the runner
    is alive. Returns the (possibly-extended) signals list and an updated
    last_signal_ts cursor.
    """
    incremental_filter = dict(base_filter)
    if last_signal_ts is not None:
        existing_since = incremental_filter.get("since_ns")
        cursor = int(last_signal_ts) + 1
        if existing_since is None or int(existing_since) < cursor:
            incremental_filter["since_ns"] = cursor
    new_signals = signal_store.replay(**incremental_filter)
    if not new_signals:
        return signals, signal_idx, last_signal_ts
    appended = sorted(new_signals, key=lambda s: (int(s.ts_event), s.signal_id))
    signals.extend(appended)
    signals.sort(key=lambda s: (int(s.ts_event), s.signal_id))
    last_signal_ts = max(int(s.ts_event) for s in signals)
    return signals, signal_idx, last_signal_ts


def _decide_with_paper_guards(
    *,
    baseline: BaselineSignalStrategy,
    event: SignalEvent,
    now_ns: int,
    max_signal_lag_seconds: int,
    data_gap_reason: str | None = None,
) -> OrderIntent:
    intent = baseline.decide(event, now_ns=now_ns)
    if intent.action == "skip" or event.side == "flat":
        return intent
    if data_gap_reason is not None:
        return OrderIntent(
            signal_id=event.signal_id,
            instrument_id=f"{event.symbol}.{event.venue}",
            action="skip",
            target_position_pct=0.0,
            reason=data_gap_reason,
        )
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


def _account_balance_row(
    *,
    config: PaperRunnerConfig,
    ts_event: int,
    total: float,
    locked: float,
) -> dict[str, Any]:
    return {
        "ts_event": ts_event,
        "venue": config.venue_name,
        "account_id": f"{config.venue_name}-PAPER",
        "currency": str(config.base_currency),
        "total": total,
        "free": total - locked,
        "locked": locked,
    }


def _max_drawdown(account_rows: list[dict[str, Any]]) -> dict[str, float]:
    peak = 0.0
    max_drawdown_abs = 0.0
    max_drawdown_pct = 0.0
    for row in account_rows:
        equity = float(row["total"])
        if peak <= 0.0 or equity > peak:
            peak = equity
        if peak <= 0.0:
            continue
        drawdown_abs = equity - peak
        drawdown_pct = drawdown_abs / peak
        if drawdown_abs < max_drawdown_abs:
            max_drawdown_abs = drawdown_abs
        if drawdown_pct < max_drawdown_pct:
            max_drawdown_pct = drawdown_pct
    return {
        "max_drawdown_abs": max_drawdown_abs,
        "max_drawdown_pct": max_drawdown_pct,
    }


def _iter_poll_batches(items: list[Any], batch_size: int) -> list[list[Any]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _expected_bar_interval_ns(bar_type: BarType) -> int | None:
    parts = str(bar_type).rsplit("-", 4)
    if len(parts) != 5:
        return None
    _, step_text, aggregation, _, _ = parts
    try:
        step = int(step_text)
    except ValueError:
        return None
    nanos = _BAR_INTERVAL_NANOS.get(aggregation.upper())
    return step * nanos if nanos is not None else None


def _market_data_gap(
    *,
    previous_ts: int,
    current_ts: int,
    expected_interval_ns: int,
    tolerance_intervals: int,
) -> dict[str, Any] | None:
    elapsed = current_ts - previous_ts
    if elapsed <= expected_interval_ns * tolerance_intervals:
        return None
    missing_intervals = max((elapsed // expected_interval_ns) - 1, 1)
    missing_start_ns = previous_ts + expected_interval_ns
    missing_end_ns = current_ts - expected_interval_ns
    return {
        "previous_ts_event": previous_ts,
        "current_ts_event": current_ts,
        "expected_interval_ns": expected_interval_ns,
        "missing_start_ns": missing_start_ns,
        "missing_end_ns": missing_end_ns,
        "missing_intervals": missing_intervals,
    }


def _data_gap_reason_for_signal(
    signal_ts_event: int,
    data_gaps: list[dict[str, Any]],
) -> str | None:
    for gap in data_gaps:
        if int(gap["missing_start_ns"]) <= signal_ts_event <= int(gap["missing_end_ns"]):
            return (
                "data_gap: signal_ts_event inside missing market data interval "
                f"{gap['missing_start_ns']}..{gap['missing_end_ns']}"
            )
    return None


def _should_emit_heartbeat(
    *,
    last_heartbeat_ns: int | None,
    now_ns: int,
    heartbeat_interval_seconds: int,
) -> bool:
    if last_heartbeat_ns is None:
        return True
    return now_ns - last_heartbeat_ns >= (
        heartbeat_interval_seconds * NANOSECONDS_PER_SECOND
    )


def _heartbeat_row(
    *,
    poll_number: int,
    ts_event: int,
    equity: float,
    last_price: float,
    open_position: _OpenPosition | None,
    signal_idx: int,
    order_count: int,
    fill_count: int,
    data_gap_count: int,
) -> dict[str, Any]:
    return {
        "ts_wall_clock": _iso_ms_utc(datetime.now(UTC)),
        "ts_event": ts_event,
        "poll_number": poll_number,
        "processed_until_ns": ts_event,
        "signals_seen": signal_idx,
        "orders": order_count,
        "fills": fill_count,
        "equity": equity,
        "last_price": last_price,
        "open_position_id": open_position.position_id if open_position else "",
        "data_gap_count": data_gap_count,
    }


def _resolve_runtime_context(config: PaperRunnerConfig) -> _RuntimeContext:
    if config.previous_run_id is None:
        return _RuntimeContext(config=config)

    manifest_path = config.output_root / config.previous_run_id / "run_manifest.json"
    if not manifest_path.exists():
        return _RuntimeContext(config=config)

    manifest_bytes = manifest_path.read_bytes()
    previous_payload = json.loads(manifest_bytes.decode("utf-8"))
    previous_runtime = previous_payload.get("runtime") or {}
    previous_processed_until_ns = _runtime_processed_until_ns(previous_payload)
    resume_from_ns = (
        previous_processed_until_ns + 1
        if previous_processed_until_ns is not None
        else None
    )
    restart_sequence = int(previous_runtime.get("restart_sequence") or 0) + 1
    effective_config = config
    catalog_start_overridden = False
    signal_filter = dict(config.signal_filter)
    if resume_from_ns is not None:
        current_since = signal_filter.get("since_ns")
        if current_since is None or int(current_since) < resume_from_ns:
            signal_filter["since_ns"] = resume_from_ns
    can_override_catalog_start = (
        config.data_mode != "wall_clock" and config.catalog_start is None
    )
    if resume_from_ns is not None and can_override_catalog_start:
        effective_config = replace(
            config,
            catalog_start=resume_from_ns,
            signal_filter=signal_filter,
        )
        catalog_start_overridden = True
    elif signal_filter != config.signal_filter:
        effective_config = replace(config, signal_filter=signal_filter)
    return _RuntimeContext(
        config=effective_config,
        previous_manifest_found=True,
        previous_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        previous_processed_until_ns=previous_processed_until_ns,
        resume_from_ns=resume_from_ns,
        restart_sequence=restart_sequence,
        catalog_start_overridden=catalog_start_overridden,
    )


def _runtime_processed_until_ns(payload: dict[str, Any]) -> int | None:
    runtime = payload.get("runtime") or {}
    raw = runtime.get("processed_until_ns")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    backtest_end = payload.get("backtest_end")
    if isinstance(backtest_end, str):
        return _iso_ms_utc_to_ns(backtest_end)
    return None


def _iso_ms_utc_to_ns(value: str) -> int:
    dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    delta = dt - _EPOCH
    return (
        ((delta.days * 24 * 60 * 60) + delta.seconds) * NANOSECONDS_PER_SECOND
        + delta.microseconds * 1_000
    )


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
    runtime_context: _RuntimeContext,
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
    if inputs.bars:
        min_bar_ns = min(int(b.ts_event) for b in inputs.bars)
        max_bar_ns = max(int(b.ts_event) for b in inputs.bars)
    else:
        min_bar_ns = simulation.first_processed_ns
        max_bar_ns = simulation.processed_until_ns
    if config.data_mode == "wall_clock":
        lineage_ts = [int(row["ts_event"]) for row in simulation.signal_lineage.to_dict("records")]
        signal_row_count = len(lineage_ts)
        min_signal_ns = min(lineage_ts) if lineage_ts else 0
        max_signal_ns = max(lineage_ts) if lineage_ts else 0
    else:
        signal_row_count = len(inputs.signals)
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
        "bar_source": simulation.bar_source,
        "heartbeat_interval_seconds": config.heartbeat_interval_seconds,
        "heartbeat_count": len(simulation.heartbeat_rows),
        "polling_mode": "incremental",
        "poll_interval_seconds": config.poll_interval_seconds,
        "poll_batch_size": config.poll_batch_size,
        "poll_count": simulation.poll_count,
        "bar_count": simulation.bar_count,
        "first_processed_ns": simulation.first_processed_ns,
        "processed_until_ns": simulation.processed_until_ns,
        "expected_bar_interval_ns": simulation.expected_bar_interval_ns,
        "max_signal_lag_seconds": config.max_signal_lag_seconds,
        "data_gap_tolerance_intervals": config.data_gap_tolerance_intervals,
        "data_gap_count": len(simulation.data_gaps),
        "data_gaps": simulation.data_gaps,
        "operator": config.operator,
        "restart_sequence": runtime_context.restart_sequence,
        "shutdown_reason": simulation.shutdown_reason,
    }
    if config.data_mode == "wall_clock":
        runtime["ws_endpoint"] = simulation.ws_endpoint
        runtime["ws_stream"] = simulation.ws_stream
        runtime["ws_reconnect_count"] = simulation.ws_reconnect_count
        runtime["duplicate_bars_dropped"] = simulation.duplicate_bars_dropped
        runtime["max_duration_seconds"] = config.max_duration_seconds
        runtime["max_bars"] = config.max_bars
        runtime["signal_poll_interval_seconds"] = config.signal_poll_interval_seconds
        runtime["credentials_loaded"] = False
    if config.previous_run_id is not None:
        runtime["previous_run_id"] = config.previous_run_id
        runtime["previous_manifest_found"] = runtime_context.previous_manifest_found
        runtime["catalog_start_overridden"] = runtime_context.catalog_start_overridden
        if runtime_context.previous_manifest_sha256 is not None:
            runtime["previous_manifest_sha256"] = (
                runtime_context.previous_manifest_sha256
            )
        if runtime_context.previous_processed_until_ns is not None:
            runtime["previous_processed_until_ns"] = (
                runtime_context.previous_processed_until_ns
            )
        if runtime_context.resume_from_ns is not None:
            runtime["resume_from_ns"] = runtime_context.resume_from_ns
        if config.restart_reason is not None:
            runtime["restart_reason"] = config.restart_reason
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
            "row_count": signal_row_count,
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
            "iterations": simulation.bar_count,
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
    parser.add_argument("--poll-interval-seconds", type=int, default=60)
    parser.add_argument("--poll-batch-size", type=int, default=1)
    parser.add_argument("--max-signal-lag-seconds", type=int, default=120)
    parser.add_argument("--data-gap-tolerance-intervals", type=int, default=1)
    parser.add_argument("--operator", default="nishiki")
    parser.add_argument("--previous-run-id")
    parser.add_argument("--restart-reason")
    parser.add_argument(
        "--data-mode",
        choices=_ALLOWED_DATA_MODES,
        default="catalog_polling",
    )
    parser.add_argument("--max-duration-seconds", type=int)
    parser.add_argument("--max-bars", type=int)
    parser.add_argument("--ws-base-url", default=DEFAULT_BINANCE_PUBLIC_WS_URL)
    parser.add_argument("--ws-symbol")
    parser.add_argument("--ws-interval", default="1m")
    parser.add_argument("--signal-poll-interval-seconds", type=int, default=5)
    return parser


def _config_from_args(args: argparse.Namespace) -> PaperRunnerConfig:
    base = _backtest_config_from_args(args)
    ws_symbol = args.ws_symbol
    if args.data_mode == "wall_clock" and not ws_symbol:
        instrument_id = base.instrument_id
        ws_symbol = instrument_id.split(".", 1)[0] if "." in instrument_id else instrument_id
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
        poll_interval_seconds=args.poll_interval_seconds,
        poll_batch_size=args.poll_batch_size,
        max_signal_lag_seconds=args.max_signal_lag_seconds,
        data_gap_tolerance_intervals=args.data_gap_tolerance_intervals,
        operator=args.operator,
        previous_run_id=args.previous_run_id,
        restart_reason=args.restart_reason,
        data_mode=args.data_mode,
        max_duration_seconds=args.max_duration_seconds,
        max_bars=args.max_bars,
        ws_base_url=args.ws_base_url,
        ws_symbol=ws_symbol,
        ws_interval=args.ws_interval,
        signal_poll_interval_seconds=args.signal_poll_interval_seconds,
    )


def _install_sigterm_handler(stop_event: Any) -> Any:
    import contextlib
    import signal as _signal

    if threading.current_thread() is not threading.main_thread():
        return None
    previous = {}

    def _handler(_signum: int, _frame: Any) -> None:
        stop_event.set()

    for sig in (_signal.SIGTERM, _signal.SIGINT):
        with contextlib.suppress(OSError, ValueError):
            previous[sig] = _signal.signal(sig, _handler)
    return previous


def _restore_signal_handlers(previous: Any) -> None:
    if not previous:
        return
    import contextlib
    import signal as _signal

    for sig, handler in previous.items():
        with contextlib.suppress(OSError, ValueError):
            _signal.signal(sig, handler)


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        config = _config_from_args(args)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    if config.data_mode == "wall_clock":
        stop_event = threading.Event()
        previous = _install_sigterm_handler(stop_event)
        try:
            result = run_paper_session(config, stop_event=stop_event)
        except Exception as exc:
            parser.exit(2, f"{parser.prog}: error: {exc}\n")
        finally:
            _restore_signal_handlers(previous)
    else:
        try:
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

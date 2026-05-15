"""ADR-004 backtest runner.

Sole writer of the `data/backtests/<run_id>/` bundle. Takes a
`BacktestRunnerConfig` (instrument, bars, signals, baseline-strategy config,
starting balance), runs a `BacktestEngine`, and persists:

- `run_manifest.json` validated by `apps.strategies_nautilus.result_schema.BacktestManifest`
- `orders.parquet`, `fills.parquet`, `positions.parquet`, `account_balances.parquet`
  (sourced from `Trader.generate_*_report()`)
- `signal_lineage.parquet` (sourced from `BaselineNautilusStrategy.lineage`)

All Parquet files use pyarrow + zstd + row_group_size=64_000 per ADR-004 §2.3.
Object-typed columns are coerced to string to keep pyarrow schema inference
stable across runs — this matters for ADR-004 §2.4 reproducibility, where two
runs with identical inputs must produce bit-for-bit identical `fills.parquet`.
"""

from __future__ import annotations

import ast
import hashlib
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money

import nautilus_trader
from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.baseline_nautilus_strategy import (
    SIGNAL_TAG_PREFIX,
    BaselineNautilusStrategy,
    BaselineNautilusStrategyParams,
    LineageRecord,
)
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig
from apps.strategies_nautilus.result_schema import (
    SCHEMA_VERSION,
    BacktestManifest,
)


@dataclass
class BacktestRunnerConfig:
    output_root: Path
    instrument: Instrument
    bars: list[Bar]
    bar_type: BarType
    signals: list[SignalEvent]
    baseline_config: BaselineStrategyConfig
    trade_size: Decimal
    starting_balance: Money
    base_currency: Currency
    signal_store_path: Path
    signal_filter: dict[str, Any] = field(default_factory=dict)
    venue_name: str = "BINANCE"
    trader_id: str = "BACKTEST_TRADER-001"
    machine_id: str = "local"
    seed: int = 0
    git_commit: str | None = None
    git_dirty: bool | None = None
    nautilus_version: str | None = None
    repo_root: Path | None = None
    account_type: AccountType = AccountType.MARGIN
    oms_type: OmsType = OmsType.NETTING


@dataclass
class RunResult:
    run_id: str
    output_dir: Path
    manifest: BacktestManifest


def run_backtest(config: BacktestRunnerConfig) -> RunResult:
    started = datetime.now(UTC)
    run_id = _make_run_id(started)
    output_dir = config.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    git_commit, git_dirty = _git_provenance(config)
    nautilus_version = config.nautilus_version or nautilus_trader.__version__
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    engine = _build_engine(config)
    lineage: list[LineageRecord] = []
    strategy = BaselineNautilusStrategy(
        params=BaselineNautilusStrategyParams(
            instrument_id=config.instrument.id,
            bar_type=config.bar_type,
            signals=config.signals,
            baseline_config=config.baseline_config,
            trade_size=config.trade_size,
            equity_currency=config.base_currency,
            lineage=lineage,
        )
    )
    engine.add_strategy(strategy)

    try:
        engine.run()
        finished = datetime.now(UTC)

        orders_df, fills_df, positions_df, account_df, lineage_df = _prepare_reports(
            orders_df=engine.trader.generate_orders_report(),
            fills_df=engine.trader.generate_fills_report(),
            positions_df=engine.trader.generate_positions_report(),
            account_df=engine.trader.generate_account_report(Venue(config.venue_name)),
            lineage=lineage,
        )

        _write_parquet(orders_df, output_dir / "orders.parquet")
        _write_parquet(fills_df, output_dir / "fills.parquet")
        _write_parquet(positions_df, output_dir / "positions.parquet")
        _write_parquet(account_df, output_dir / "account_balances.parquet")
        _write_parquet(lineage_df, output_dir / "signal_lineage.parquet")

        bt_result = engine.get_result()

        manifest = _build_manifest(
            config=config,
            run_id=run_id,
            git_commit=git_commit,
            git_dirty=git_dirty,
            nautilus_version=nautilus_version,
            python_version=python_version,
            started=started,
            finished=finished,
            bt_result=bt_result,
            fills_count=len(fills_df),
        )
        (output_dir / "run_manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        return RunResult(run_id=run_id, output_dir=output_dir, manifest=manifest)
    finally:
        engine.dispose()


def _build_engine(config: BacktestRunnerConfig) -> BacktestEngine:
    engine_config = BacktestEngineConfig(
        trader_id=TraderId(config.trader_id),
        instance_id=_deterministic_instance_id(config.seed),
        logging=LoggingConfig(bypass_logging=True),
    )
    engine = BacktestEngine(config=engine_config)
    engine.add_venue(
        venue=Venue(config.venue_name),
        oms_type=config.oms_type,
        account_type=config.account_type,
        starting_balances=[config.starting_balance],
        base_currency=config.base_currency,
        default_leverage=Decimal(1),
    )
    engine.add_instrument(config.instrument)
    engine.add_data(config.bars)
    return engine


def _make_run_id(started: datetime) -> str:
    stem = started.strftime("%Y%m%d-%H%M%SZ")
    suffix = secrets.token_hex(4)
    return f"{stem}-{suffix}"


def _deterministic_instance_id(seed: int) -> UUID4:
    """Derive a stable UUID4 from `seed`.

    ADR-004 §2.4 requires bit-for-bit identical `fills.parquet` across two
    runs with identical inputs. NautilusTrader stamps `client_order_id` /
    `fill_id` with the kernel's `instance_id`; without a fixed instance_id,
    every run randomises those identifiers and the parquet files diverge.
    """
    digest = hashlib.sha256(f"trader-backtest-seed-{seed}".encode()).hexdigest()
    # Format as UUID v4 — 13th hex must be '4', 17th in {8,9,a,b}.
    formatted = (
        f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-"
        f"8{digest[17:20]}-{digest[20:32]}"
    )
    return UUID4.from_str(formatted)


def _iso_ms_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _git_provenance(config: BacktestRunnerConfig) -> tuple[str, bool]:
    if config.git_commit is not None:
        return config.git_commit, bool(config.git_dirty)
    repo_root = config.repo_root or _find_repo_root()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    dirty_code = subprocess.call(
        ["git", "diff", "--quiet", "--exit-code"],
        cwd=repo_root,
    )
    return commit, dirty_code != 0


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError(f"no .git found above {here}")


def _hash_signal_store(path: Path) -> str:
    # Force a WAL checkpoint so the main .db file contains every committed
    # row; otherwise the byte content depends on whether SQLite has flushed
    # the WAL, and two `run_backtest` calls in succession could see different
    # bytes for the same logical store.
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL);")
    finally:
        conn.close()
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _prepare_reports(
    *,
    orders_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    account_df: pd.DataFrame,
    lineage: list[LineageRecord],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders = _normalize_report_df(orders_df)
    order_signal_ids = _order_signal_ids(orders)
    orders = _add_order_columns(orders, order_signal_ids)

    fills = _normalize_report_df(fills_df)
    fills = _add_fill_columns(fills, order_signal_ids)

    positions = _normalize_report_df(positions_df)
    positions = _add_position_columns(positions, orders)

    account = _normalize_report_df(account_df)
    lineage_df = _lineage_to_df(lineage, orders, fills, positions)
    return orders, fills, positions, account, lineage_df


def _normalize_report_df(df: pd.DataFrame) -> pd.DataFrame:
    drop_index = all(name is None for name in df.index.names)
    safe = df.reset_index(drop=drop_index).copy()
    for col in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[col]):
            safe[col] = _datetime_to_ns(safe[col])
    for col in safe.columns:
        if col.startswith("ts_") and safe[col].dtype == "object":
            converted = pd.to_datetime(safe[col], utc=True, errors="coerce")
            if converted.notna().any():
                safe[col] = _datetime_to_ns(converted)
    return safe


def _datetime_to_ns(series: pd.Series) -> pd.Series:
    converted = pd.to_datetime(series, utc=True, errors="coerce")
    ns = pd.Series(converted.astype("int64"), index=series.index, dtype="Int64")
    ns[converted.isna()] = pd.NA
    return ns


def _order_signal_ids(orders: pd.DataFrame) -> dict[str, str]:
    if "client_order_id" not in orders.columns or "tags" not in orders.columns:
        return {}
    mapping: dict[str, str] = {}
    for _, row in orders.iterrows():
        signal_id = _extract_signal_id(row["tags"])
        if signal_id:
            mapping[str(row["client_order_id"])] = signal_id
    return mapping


def _extract_signal_id(raw_tags: object) -> str | None:
    if raw_tags is None:
        return None
    if isinstance(raw_tags, float) and pd.isna(raw_tags):
        return None
    tags: object = raw_tags
    if isinstance(raw_tags, str):
        if raw_tags in {"", "None", "nan", "<NA>"}:
            return None
        try:
            tags = ast.literal_eval(raw_tags)
        except (SyntaxError, ValueError):
            tags = [raw_tags]
    if isinstance(tags, (list, tuple, set)):
        for tag in tags:
            text = str(tag)
            if text.startswith(SIGNAL_TAG_PREFIX):
                return text[len(SIGNAL_TAG_PREFIX) :]
    return None


def _add_order_columns(
    orders: pd.DataFrame,
    order_signal_ids: dict[str, str],
) -> pd.DataFrame:
    if orders.empty:
        return _ensure_columns(orders, ["order_id", "signal_id"])
    orders = orders.copy()
    if "client_order_id" in orders.columns:
        if "order_id" in orders.columns:
            orders["order_id"] = orders["client_order_id"].astype(str)
        else:
            orders.insert(0, "order_id", orders["client_order_id"].astype(str))
        orders["signal_id"] = orders["client_order_id"].astype(str).map(order_signal_ids).fillna("")
    if "init_id" in orders.columns:
        orders["init_id"] = [
            _stable_id("order-init", [row.get("client_order_id"), row.get("ts_init")])
            for row in orders.to_dict("records")
        ]
    return _sort_report(orders, ["ts_init", "client_order_id"])


def _add_fill_columns(
    fills: pd.DataFrame,
    order_signal_ids: dict[str, str],
) -> pd.DataFrame:
    if fills.empty:
        return _ensure_columns(fills, ["fill_id", "signal_id"])
    fills = fills.copy()
    fill_ids = [
        _stable_id(
            "fill",
            [
                row.get("client_order_id"),
                row.get("venue_order_id"),
                row.get("trade_id"),
                row.get("ts_event"),
                row.get("last_qty"),
                row.get("last_px"),
            ],
        )
        for row in fills.to_dict("records")
    ]
    if "fill_id" in fills.columns:
        fills["fill_id"] = fill_ids
    else:
        fills.insert(0, "fill_id", fill_ids)
    if "event_id" in fills.columns:
        fills["event_id"] = fill_ids
    if "client_order_id" in fills.columns:
        fills["signal_id"] = fills["client_order_id"].astype(str).map(order_signal_ids).fillna("")
    return _sort_report(fills, ["ts_event", "client_order_id"])


def _add_position_columns(positions: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    if positions.empty:
        return _ensure_columns(positions, ["signal_ids"])
    positions = positions.copy()
    order_to_signal: dict[str, str] = {}
    if {"client_order_id", "signal_id"}.issubset(orders.columns):
        order_to_signal = dict(
            zip(
                orders["client_order_id"].astype(str),
                orders["signal_id"].astype(str),
                strict=False,
            )
        )

    if "position_id" in positions.columns:
        positions["position_id"] = [
            _stable_id(
                "position",
                [
                    row.get("instrument_id"),
                    row.get("strategy_id"),
                    row.get("opening_order_id"),
                    row.get("closing_order_id"),
                    row.get("ts_init"),
                ],
            )
            for row in positions.to_dict("records")
        ]

    signal_ids: list[str] = []
    for _, row in positions.iterrows():
        ids = {
            order_to_signal.get(str(order_id), "")
            for order_id in (
                row.get("opening_order_id", ""),
                row.get("closing_order_id", ""),
            )
        }
        signal_ids.append(",".join(sorted(i for i in ids if i)))
    positions["signal_ids"] = signal_ids
    return _sort_report(positions, ["ts_init", "position_id"])


def _lineage_to_df(
    records: list[LineageRecord],
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    positions: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "signal_id",
        "source",
        "model_version",
        "ts_event",
        "decision",
        "reason",
        "order_ids",
        "fill_ids",
        "position_id",
        "ts_decision",
    ]
    if not records:
        return pd.DataFrame(columns=columns)

    order_ids_by_signal = _group_column_by_signal(orders, "order_id")
    fill_ids_by_signal = _group_column_by_signal(fills, "fill_id")
    position_ids_by_signal = _position_ids_by_signal(positions)

    return pd.DataFrame(
        [
            {
                "signal_id": r.signal_id,
                "source": r.source,
                "model_version": r.model_version,
                "ts_event": r.ts_event,
                "decision": r.decision,
                "reason": r.reason or "",
                "order_ids": ",".join(order_ids_by_signal.get(r.signal_id, [])),
                "fill_ids": ",".join(fill_ids_by_signal.get(r.signal_id, [])),
                "position_id": ",".join(position_ids_by_signal.get(r.signal_id, [])),
                "ts_decision": r.ts_decision,
            }
            for r in records
        ],
        columns=columns,
    )


def _group_column_by_signal(df: pd.DataFrame, value_col: str) -> dict[str, list[str]]:
    if df.empty or "signal_id" not in df.columns or value_col not in df.columns:
        return {}
    grouped: dict[str, list[str]] = {}
    for signal_id, group in df.groupby("signal_id", sort=True):
        signal = str(signal_id)
        if not signal:
            continue
        grouped[signal] = sorted(str(v) for v in group[value_col].tolist())
    return grouped


def _position_ids_by_signal(positions: pd.DataFrame) -> dict[str, list[str]]:
    if positions.empty or "signal_ids" not in positions.columns or "position_id" not in positions.columns:
        return {}
    grouped: dict[str, set[str]] = {}
    for _, row in positions.iterrows():
        position_id = str(row["position_id"])
        for signal_id in str(row["signal_ids"]).split(","):
            if signal_id:
                grouped.setdefault(signal_id, set()).add(position_id)
    return {signal_id: sorted(position_ids) for signal_id, position_ids in grouped.items()}


def _stable_id(prefix: str, values: list[object]) -> str:
    payload = "|".join("" if value is None else str(value) for value in values)
    return f"{prefix}-{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def _sort_report(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    sort_cols = [c for c in columns if c in df.columns]
    if not sort_cols:
        return df.reset_index(drop=True)
    return df.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.Series(dtype="object")
    return result


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    safe = df.reset_index(drop=True).copy()
    for col in safe.columns:
        if safe[col].dtype == "object":
            safe[col] = safe[col].astype(str)
    safe.to_parquet(
        path,
        engine="pyarrow",
        compression="zstd",
        index=False,
        row_group_size=64_000,
    )


def _build_manifest(
    *,
    config: BacktestRunnerConfig,
    run_id: str,
    git_commit: str,
    git_dirty: bool,
    nautilus_version: str,
    python_version: str,
    started: datetime,
    finished: datetime,
    bt_result: Any,
    fills_count: int,
) -> BacktestManifest:
    backtest_start_ns = min(int(b.ts_event) for b in config.bars)
    backtest_end_ns = max(int(b.ts_event) for b in config.bars)
    min_signal_ns = (
        min(int(s.ts_event) for s in config.signals) if config.signals else 0
    )
    max_signal_ns = (
        max(int(s.ts_event) for s in config.signals) if config.signals else 0
    )
    return BacktestManifest.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "kind": "backtest",
            "trader_id": config.trader_id,
            "machine_id": config.machine_id,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
            "nautilus_version": nautilus_version,
            "python_version": python_version,
            "started_at": _iso_ms_utc(started),
            "finished_at": _iso_ms_utc(finished),
            "elapsed_seconds": (finished - started).total_seconds(),
            "backtest_start": _ns_to_iso_ms(backtest_start_ns),
            "backtest_end": _ns_to_iso_ms(backtest_end_ns),
            "venues": [config.venue_name],
            "instruments": [config.instrument.id.value],
            "strategies": [
                {
                    "name": "baseline_signal_strategy",
                    "params": {
                        "min_confidence": config.baseline_config.min_confidence,
                        "max_position_pct": config.baseline_config.max_position_pct,
                        "daily_drawdown_stop_pct": config.baseline_config.daily_drawdown_stop_pct,
                        "trade_size": str(config.trade_size),
                        "seed": config.seed,
                    },
                }
            ],
            "risk_rules": [
                {
                    "name": "daily_drawdown_stop",
                    "params": {
                        "max_pct": config.baseline_config.daily_drawdown_stop_pct
                    },
                }
            ],
            "signal_source": {
                "store_path": str(config.signal_store_path),
                "store_sha256": _hash_signal_store(config.signal_store_path),
                "filter": config.signal_filter,
                "row_count": len(config.signals),
                "min_ts_event_ns": min_signal_ns,
                "max_ts_event_ns": max_signal_ns,
            },
            "data_catalog": {
                "path": "inline:bars",
                "instruments": [
                    {
                        "id": config.instrument.id.value,
                        "bars": str(config.bar_type),
                        "rows": len(config.bars),
                    }
                ],
            },
            "totals": {
                "iterations": int(bt_result.iterations),
                "events": int(bt_result.total_events),
                "orders": int(bt_result.total_orders),
                "positions": int(bt_result.total_positions),
                "fills": int(fills_count),
            },
            "stats_pnls": bt_result.stats_pnls,
            "stats_returns": bt_result.stats_returns,
        }
    )


def _ns_to_iso_ms(ns: int) -> str:
    dt = datetime.fromtimestamp(ns / 1_000_000_000, tz=UTC)
    return _iso_ms_utc(dt)


__all__ = [
    "BacktestRunnerConfig",
    "RunResult",
    "run_backtest",
]

"""ADR-004 backtest runner.

Sole writer of the `data/backtests/<run_id>/` bundle. Takes a
`BacktestRunnerConfig` (catalog path, instrument/bar type, signal-store
filter, baseline-strategy config, starting balance), runs a `BacktestEngine`,
and persists:

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

import argparse
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

import nautilus_trader
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization, SourcePolicy
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


@dataclass(frozen=True)
class BacktestInputs:
    instrument: Instrument
    bars: list[Bar]
    signals: list[SignalEvent]


class SidecarSchemaError(ValueError):
    pass


_SIDECAR_SCHEMAS: dict[str, pa.Schema] = {
    "orders": pa.schema(
        [
            pa.field("order_id", pa.string()),
            pa.field("client_order_id", pa.string()),
            pa.field("venue", pa.string()),
            pa.field("instrument_id", pa.string()),
            pa.field("side", pa.string()),
            pa.field("quantity", pa.float64()),
            pa.field("price", pa.float64()),
            pa.field("type", pa.string()),
            pa.field("status", pa.string()),
            pa.field("ts_init", pa.int64()),
            pa.field("ts_last", pa.int64()),
            pa.field("signal_id", pa.string()),
        ]
    ),
    "fills": pa.schema(
        [
            pa.field("fill_id", pa.string()),
            pa.field("order_id", pa.string()),
            pa.field("venue", pa.string()),
            pa.field("instrument_id", pa.string()),
            pa.field("side", pa.string()),
            pa.field("quantity", pa.float64()),
            pa.field("price", pa.float64()),
            pa.field("commission", pa.float64()),
            pa.field("currency", pa.string()),
            pa.field("ts_event", pa.int64()),
            pa.field("signal_id", pa.string()),
        ]
    ),
    "positions": pa.schema(
        [
            pa.field("position_id", pa.string()),
            pa.field("venue", pa.string()),
            pa.field("instrument_id", pa.string()),
            pa.field("side", pa.string()),
            pa.field("quantity", pa.float64()),
            pa.field("peak_qty", pa.float64()),
            pa.field("avg_px_open", pa.float64()),
            pa.field("avg_px_close", pa.float64()),
            pa.field("realized_pnl", pa.float64()),
            pa.field("unrealized_pnl", pa.float64()),
            pa.field("opened_ts", pa.int64()),
            pa.field("closed_ts", pa.int64()),
            pa.field("signal_ids", pa.string()),
        ]
    ),
    "account_balances": pa.schema(
        [
            pa.field("ts_event", pa.int64()),
            pa.field("venue", pa.string()),
            pa.field("account_id", pa.string()),
            pa.field("currency", pa.string()),
            pa.field("total", pa.float64()),
            pa.field("free", pa.float64()),
            pa.field("locked", pa.float64()),
        ]
    ),
    "signal_lineage": pa.schema(
        [
            pa.field("signal_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("model_version", pa.string()),
            pa.field("ts_event", pa.int64()),
            pa.field("decision", pa.string()),
            pa.field("reason", pa.string()),
            pa.field("order_ids", pa.string()),
            pa.field("fill_ids", pa.string()),
            pa.field("position_id", pa.string()),
        ]
    ),
}


def run_backtest(config: BacktestRunnerConfig) -> RunResult:
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

    engine = _build_engine(config, inputs.instrument, inputs.bars)
    lineage: list[LineageRecord] = []
    strategy = BaselineNautilusStrategy(
        params=BaselineNautilusStrategyParams(
            instrument_id=inputs.instrument.id,
            bar_type=config.bar_type,
            signals=inputs.signals,
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
            venue_name=config.venue_name,
            report_ts_event_ns=max(int(b.ts_event) for b in inputs.bars),
        )

        _write_parquet(orders_df, output_dir / "orders.parquet")
        _write_parquet(fills_df, output_dir / "fills.parquet")
        _write_parquet(positions_df, output_dir / "positions.parquet")
        _write_parquet(account_df, output_dir / "account_balances.parquet")
        _write_parquet(lineage_df, output_dir / "signal_lineage.parquet")
        validate_sidecar_bundle(output_dir)

        bt_result = engine.get_result()

        manifest = _build_manifest(
            config=config,
            inputs=inputs,
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


def _load_inputs(config: BacktestRunnerConfig) -> BacktestInputs:
    catalog = ParquetDataCatalog(str(config.catalog_path.resolve()))
    instruments = catalog.instruments(instrument_ids=[config.instrument_id])
    instrument = _select_instrument(instruments, config.instrument_id)
    if str(config.bar_type.instrument_id) != config.instrument_id:
        raise ValueError(
            f"bar_type instrument {config.bar_type.instrument_id} does not match "
            f"instrument_id {config.instrument_id}"
        )
    bars = catalog.bars(
        bar_types=[str(config.bar_type)],
        start=config.catalog_start,
        end=config.catalog_end,
    )
    bars = sorted(bars, key=lambda b: (int(b.ts_event), int(b.ts_init)))
    if not bars:
        raise ValueError(
            f"no bars found in {config.catalog_path} for bar_type={config.bar_type}"
        )
    signals = _load_signals(config.signal_store_path, config.signal_filter)
    return BacktestInputs(instrument=instrument, bars=bars, signals=signals)


def _select_instrument(
    instruments: list[Instrument],
    instrument_id: str,
) -> Instrument:
    matches = [i for i in instruments if i.id.value == instrument_id]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"instrument {instrument_id!r} not found in catalog")
    raise ValueError(f"catalog returned multiple instruments for {instrument_id!r}")


def _load_signals(path: Path, signal_filter: dict[str, Any]) -> list[SignalEvent]:
    if not path.exists():
        raise FileNotFoundError(f"signal store not found: {path}")
    store = SignalStore(path)
    return store.replay(**signal_filter)


def _build_engine(
    config: BacktestRunnerConfig,
    instrument: Instrument,
    bars: list[Bar],
) -> BacktestEngine:
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
        base_currency=(
            None if config.account_type == AccountType.CASH else config.base_currency
        ),
        default_leverage=Decimal(1),
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)
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
    venue_name: str,
    report_ts_event_ns: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders = _normalize_report_df(orders_df)
    order_signal_ids = _order_signal_ids(orders)
    orders = _add_order_columns(orders, order_signal_ids, venue_name)

    fills = _normalize_report_df(fills_df)
    fills = _add_fill_columns(fills, order_signal_ids, venue_name)

    positions = _normalize_report_df(positions_df)
    positions = _add_position_columns(positions, orders, venue_name)

    account = _normalize_report_df(account_df)
    account = _add_account_columns(account, venue_name, report_ts_event_ns)
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
    venue_name: str,
) -> pd.DataFrame:
    if orders.empty:
        return _ensure_columns(
            orders,
            [
                "order_id",
                "client_order_id",
                "venue",
                "instrument_id",
                "side",
                "quantity",
                "price",
                "type",
                "status",
                "ts_init",
                "ts_last",
                "signal_id",
            ],
        )
    orders = orders.copy()
    orders["venue"] = venue_name
    if "client_order_id" in orders.columns:
        if "order_id" in orders.columns:
            orders["order_id"] = orders["client_order_id"].astype(str)
        else:
            orders.insert(0, "order_id", orders["client_order_id"].astype(str))
        orders["signal_id"] = orders["client_order_id"].astype(str).map(order_signal_ids).fillna("")
    if "avg_px" in orders.columns:
        orders["price"] = _to_float_series(orders["avg_px"])
    orders["quantity"] = _to_float_series(orders.get("quantity"))
    if "init_id" in orders.columns:
        orders["init_id"] = [
            _stable_id("order-init", [row.get("client_order_id"), row.get("ts_init")])
            for row in orders.to_dict("records")
        ]
    return _sort_report(orders, ["ts_init", "client_order_id"])


def _add_fill_columns(
    fills: pd.DataFrame,
    order_signal_ids: dict[str, str],
    venue_name: str,
) -> pd.DataFrame:
    if fills.empty:
        return _ensure_columns(
            fills,
            [
                "fill_id",
                "order_id",
                "venue",
                "instrument_id",
                "side",
                "quantity",
                "price",
                "commission",
                "currency",
                "ts_event",
                "signal_id",
            ],
        )
    fills = fills.copy()
    fills["venue"] = venue_name
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
        fills["order_id"] = fills["client_order_id"].astype(str)
        fills["signal_id"] = fills["client_order_id"].astype(str).map(order_signal_ids).fillna("")
    if "order_side" in fills.columns:
        fills["side"] = fills["order_side"].astype(str)
    fills["quantity"] = _to_float_series(fills.get("last_qty"))
    fills["price"] = _to_float_series(fills.get("last_px"))
    fills["commission"] = _to_float_series(fills.get("commission"))
    return _sort_report(fills, ["ts_event", "client_order_id"])


def _add_position_columns(
    positions: pd.DataFrame,
    orders: pd.DataFrame,
    venue_name: str,
) -> pd.DataFrame:
    if positions.empty:
        return _ensure_columns(
            positions,
            [
                "position_id",
                "venue",
                "instrument_id",
                "side",
                "quantity",
                "peak_qty",
                "avg_px_open",
                "avg_px_close",
                "realized_pnl",
                "unrealized_pnl",
                "opened_ts",
                "closed_ts",
                "signal_ids",
            ],
        )
    positions = positions.copy()
    positions["venue"] = venue_name
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
    positions["quantity"] = _to_float_series(positions.get("quantity"))
    positions["peak_qty"] = _to_float_series(positions.get("peak_qty"))
    positions["avg_px_open"] = _to_float_series(positions.get("avg_px_open"))
    positions["avg_px_close"] = _to_float_series(positions.get("avg_px_close"))
    positions["realized_pnl"] = _to_float_series(positions.get("realized_pnl"))
    if "unrealized_pnl" in positions.columns:
        positions["unrealized_pnl"] = _to_float_series(
            positions["unrealized_pnl"],
            default=0.0,
        )
    else:
        positions["unrealized_pnl"] = 0.0
    positions["opened_ts"] = _nullable_int_series(positions.get("ts_opened"))
    positions["closed_ts"] = _nullable_int_series(positions.get("ts_closed"))
    return _sort_report(positions, ["ts_init", "position_id"])


def _add_account_columns(
    account: pd.DataFrame,
    venue_name: str,
    report_ts_event_ns: int,
) -> pd.DataFrame:
    if account.empty:
        return _ensure_columns(
            account,
            ["ts_event", "venue", "account_id", "currency", "total", "free", "locked"],
        )
    account = account.copy()
    account["ts_event"] = report_ts_event_ns
    account["venue"] = venue_name
    account["total"] = _to_float_series(account.get("total"))
    account["free"] = _to_float_series(account.get("free"))
    account["locked"] = _to_float_series(account.get("locked"))
    return _sort_report(account, ["account_id", "currency"])


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


def _to_float_series(
    series: pd.Series | None,
    *,
    default: float | None = None,
) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    extracted = series.astype(str).str.extract(r"([-+]?\d+(?:\.\d+)?)", expand=False)
    out = pd.to_numeric(extracted, errors="coerce")
    if default is not None:
        out = out.fillna(default)
    return out.astype("float64")


def _nullable_int_series(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="Int64")
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    safe = df.reset_index(drop=True).copy()
    expected_schema = _SIDECAR_SCHEMAS.get(path.stem)
    if expected_schema is not None:
        for field in expected_schema:
            if field.name not in safe.columns:
                safe[field.name] = pd.NA
            if pa.types.is_string(field.type):
                safe[field.name] = safe[field.name].astype("string").fillna("")
            elif pa.types.is_float64(field.type):
                safe[field.name] = pd.to_numeric(
                    safe[field.name],
                    errors="coerce",
                ).astype("float64")
            elif pa.types.is_int64(field.type):
                safe[field.name] = pd.to_numeric(
                    safe[field.name],
                    errors="coerce",
                ).astype("Int64")
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


def validate_sidecar_bundle(output_dir: Path) -> None:
    for name, schema in _SIDECAR_SCHEMAS.items():
        validate_sidecar(output_dir / f"{name}.parquet", schema)


def validate_sidecar(path: Path, expected_schema: pa.Schema) -> None:
    if not path.exists():
        raise SidecarSchemaError(f"missing sidecar: {path}")
    actual = pq.read_schema(path)
    actual_fields = {field.name: field for field in actual}
    for expected in expected_schema:
        actual_field = actual_fields.get(expected.name)
        if actual_field is None:
            raise SidecarSchemaError(
                f"{path.name} missing required column {expected.name!r}"
            )
        if actual_field.type != expected.type:
            raise SidecarSchemaError(
                f"{path.name}.{expected.name} type {actual_field.type} "
                f"!= {expected.type}"
            )


def _build_manifest(
    *,
    config: BacktestRunnerConfig,
    inputs: BacktestInputs,
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
    backtest_start_ns = min(int(b.ts_event) for b in inputs.bars)
    backtest_end_ns = max(int(b.ts_event) for b in inputs.bars)
    min_signal_ns = (
        min(int(s.ts_event) for s in inputs.signals) if inputs.signals else 0
    )
    max_signal_ns = (
        max(int(s.ts_event) for s in inputs.signals) if inputs.signals else 0
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
                        "account_type": config.account_type.name,
                        "oms_type": config.oms_type.name,
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
                }
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


def _serialize_policies(
    policies: dict[tuple[str, str], Any],
) -> list[dict[str, Any]]:
    """Flatten Authorization.policies into a deterministic manifest list.

    ADR-006 §2.6: applied policies must round-trip through the manifest so
    ADR-004 §2.4 reproducibility extends across policy state. Sorted by
    `(source, model_version)` for stable diffs.
    """
    out: list[dict[str, Any]] = []
    for (source, model_version), policy in sorted(policies.items()):
        out.append(
            {
                "source": source,
                "model_version": model_version,
                "position_pct_multiplier": float(policy.position_pct_multiplier),
                "min_confidence_override": (
                    None
                    if policy.min_confidence_override is None
                    else float(policy.min_confidence_override)
                ),
                "dry_run": bool(policy.dry_run),
            }
        )
    return out


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 baseline Nautilus backtest from catalog + SignalStore.",
    )
    parser.add_argument("--output-root", type=Path, default=Path("data/backtests"))
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
    parser.add_argument(
        "--policy-source",
        help="Source for a single ADR-006 policy; defaults to --signal-source.",
    )
    parser.add_argument(
        "--policy-model-version",
        help="Model version for a single ADR-006 policy; defaults to --signal-model-version.",
    )
    parser.add_argument(
        "--policy-position-pct-multiplier",
        type=float,
        help="ADR-006 SourcePolicy.position_pct_multiplier for the policy.",
    )
    parser.add_argument(
        "--policy-min-confidence-override",
        type=float,
        help="ADR-006 SourcePolicy.min_confidence_override for the policy.",
    )
    parser.add_argument(
        "--policy-dry-run",
        action="store_true",
        help="Mark the policy as dry-run: lineage only, no order submission.",
    )
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--trade-size", type=Decimal, required=True)
    parser.add_argument("--starting-balance", type=Decimal, required=True)
    parser.add_argument("--base-currency", default="USDT")
    parser.add_argument(
        "--account-type",
        choices=("cash", "margin"),
        default="margin",
        help="Backtest venue account type; use cash for Spot-compatible research.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--max-position-pct", type=float, default=0.05)
    parser.add_argument("--daily-drawdown-stop-pct", type=float, default=0.05)
    parser.add_argument("--trader-id", default="BACKTEST_TRADER-001")
    parser.add_argument("--machine-id", default="local")
    parser.add_argument("--seed", type=int, default=0)
    return parser


def _config_from_args(args: argparse.Namespace) -> BacktestRunnerConfig:
    signal_filter: dict[str, Any] = {}
    if args.signal_source:
        signal_filter["source"] = args.signal_source
    if args.signal_model_version:
        signal_filter["model_version"] = args.signal_model_version
    if args.signal_since_ns is not None:
        signal_filter["since_ns"] = args.signal_since_ns
    if args.signal_until_ns is not None:
        signal_filter["until_ns"] = args.signal_until_ns

    allowed_sources = frozenset(
        args.allowed_source or ([args.signal_source] if args.signal_source else [])
    )
    allowed_models = frozenset(
        args.allowed_model_version
        or ([args.signal_model_version] if args.signal_model_version else [])
    )
    if not allowed_sources:
        raise ValueError("provide --allowed-source or --signal-source")
    if not allowed_models:
        raise ValueError("provide --allowed-model-version or --signal-model-version")

    currency = Currency.from_str(args.base_currency)
    return BacktestRunnerConfig(
        output_root=args.output_root,
        catalog_path=args.catalog_path,
        instrument_id=args.instrument_id,
        bar_type=BarType.from_str(args.bar_type),
        signal_store_path=args.signal_store_path,
        baseline_config=BaselineStrategyConfig(
            venue=args.venue,
            auth=Authorization(
                allowed_sources=allowed_sources,
                allowed_model_versions=allowed_models,
                policies=_policies_from_args(args),
            ),
            min_confidence=args.min_confidence,
            max_position_pct=args.max_position_pct,
            daily_drawdown_stop_pct=args.daily_drawdown_stop_pct,
        ),
        trade_size=args.trade_size,
        starting_balance=Money(args.starting_balance, currency),
        base_currency=currency,
        signal_filter=signal_filter,
        catalog_start=args.catalog_start,
        catalog_end=args.catalog_end,
        venue_name=args.venue,
        trader_id=args.trader_id,
        machine_id=args.machine_id,
        seed=args.seed,
        account_type=(
            AccountType.CASH
            if getattr(args, "account_type", "margin") == "cash"
            else AccountType.MARGIN
        ),
    )


def _policies_from_args(args: argparse.Namespace) -> dict[tuple[str, str], SourcePolicy]:
    requested = (
        args.policy_source is not None
        or args.policy_model_version is not None
        or args.policy_position_pct_multiplier is not None
        or args.policy_min_confidence_override is not None
        or args.policy_dry_run
    )
    if not requested:
        return {}

    source = args.policy_source or args.signal_source
    model_version = args.policy_model_version or args.signal_model_version
    if not source:
        raise ValueError("provide --policy-source or --signal-source for SourcePolicy")
    if not model_version:
        raise ValueError(
            "provide --policy-model-version or --signal-model-version for SourcePolicy"
        )

    multiplier = (
        1.0
        if args.policy_position_pct_multiplier is None
        else args.policy_position_pct_multiplier
    )
    return {
        (source, model_version): SourcePolicy(
            position_pct_multiplier=multiplier,
            min_confidence_override=args.policy_min_confidence_override,
            dry_run=args.policy_dry_run,
        )
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        config = _config_from_args(args)
        result = run_backtest(config)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(result.output_dir)
    return 0


__all__ = [
    "BacktestRunnerConfig",
    "RunResult",
    "SidecarSchemaError",
    "validate_sidecar",
    "validate_sidecar_bundle",
    "run_backtest",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

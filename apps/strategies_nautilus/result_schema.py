"""Pydantic schema for ADR-004 `run_manifest.json` (`schema_version=backtest.v1`).

The runner under `apps/strategies_nautilus/runners/backtest_runner.py` is the
sole writer of this manifest; this module is its validator and the canonical
loader used by downstream tooling (notebooks, `duckdb` queries, future
comparator code).

Only the manifest is modeled here. Parquet sidecars (`orders / fills /
positions / account_balances / signal_lineage`) are validated by `pyarrow`
schemas defined alongside the runner — keeping Parquet handling out of this
module avoids pulling pyarrow into the consumer-test import path.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Literal["backtest.v1"] = "backtest.v1"

_RUN_ID_RE = re.compile(r"^\d{8}-\d{6}Z-[0-9a-f]{8}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_ISO_MS_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

Kind = Literal["backtest", "paper", "live"]


class _Base(BaseModel):
    # ADR-004 §2.6 allows appending new fields within v1, so older readers
    # must tolerate unknown keys. extra="ignore" gives forward-compat without
    # silently letting typos pollute the model on write.
    model_config = ConfigDict(extra="ignore", frozen=True)


class StrategySpec(_Base):
    name: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class RiskRuleSpec(_Base):
    name: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class SignalSource(_Base):
    store_path: str = Field(min_length=1)
    store_sha256: str = Field(pattern=_SHA256_RE.pattern)
    filter: dict[str, Any] = Field(default_factory=dict)
    row_count: int = Field(ge=0)
    min_ts_event_ns: int = Field(ge=0)
    max_ts_event_ns: int = Field(ge=0)

    @field_validator("max_ts_event_ns")
    @classmethod
    def _max_not_before_min(cls, v: int, info: Any) -> int:
        min_ns = info.data.get("min_ts_event_ns")
        if min_ns is not None and v < min_ns:
            raise ValueError(
                f"max_ts_event_ns={v} < min_ts_event_ns={min_ns}"
            )
        return v


class CatalogInstrument(_Base):
    id: str = Field(min_length=1)
    bars: str = Field(min_length=1)
    rows: int = Field(ge=0)


class DataCatalog(_Base):
    path: str = Field(min_length=1)
    instruments: list[CatalogInstrument] = Field(min_length=1)


class Totals(_Base):
    iterations: int = Field(ge=0)
    events: int = Field(ge=0)
    orders: int = Field(ge=0)
    positions: int = Field(ge=0)
    fills: int = Field(ge=0)


class PnlStats(_Base):
    """Per-settlement-currency PnL aggregates.

    Required keys mirror ADR-004 §2.2: pnl_total, win_rate, sharpe,
    max_drawdown_pct, max_drawdown_abs. sortino and pnl_per_trade_avg are
    accepted when produced by NautilusTrader but not mandatory.
    """

    pnl_total: float
    pnl_per_trade_avg: float | None = None
    win_rate: float = Field(ge=0.0, le=1.0)
    sharpe: float
    sortino: float | None = None
    max_drawdown_pct: float = Field(le=0.0)
    max_drawdown_abs: float = Field(le=0.0)


class ReturnsStats(_Base):
    annualized_return: float
    annualized_vol: float = Field(ge=0.0)
    max_drawdown: float = Field(le=0.0)


class BacktestManifest(_Base):
    schema_version: Literal["backtest.v1"]
    run_id: str
    kind: Kind
    trader_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    git_commit: str
    git_dirty: bool
    nautilus_version: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    started_at: str
    finished_at: str
    elapsed_seconds: float = Field(ge=0.0)
    backtest_start: str
    backtest_end: str
    venues: list[str] = Field(min_length=1)
    instruments: list[str] = Field(min_length=1)
    strategies: list[StrategySpec] = Field(min_length=1)
    risk_rules: list[RiskRuleSpec]
    signal_source: SignalSource
    data_catalog: DataCatalog
    totals: Totals
    stats_pnls: dict[str, PnlStats] = Field(min_length=1)
    stats_returns: ReturnsStats

    @field_validator("run_id")
    @classmethod
    def _run_id_format(cls, v: str) -> str:
        if not _RUN_ID_RE.fullmatch(v):
            raise ValueError(
                f"run_id={v!r} must match YYYYMMDD-HHMMSSZ-<8hex>"
            )
        return v

    @field_validator("git_commit")
    @classmethod
    def _git_commit_format(cls, v: str) -> str:
        if not _GIT_COMMIT_RE.fullmatch(v):
            raise ValueError(
                f"git_commit={v!r} must be 7..40 lowercase hex chars"
            )
        return v

    @field_validator("started_at", "finished_at", "backtest_start", "backtest_end")
    @classmethod
    def _iso_ms_utc(cls, v: str) -> str:
        if not _ISO_MS_UTC_RE.fullmatch(v):
            raise ValueError(
                f"{v!r} must be ISO 8601 UTC ms format YYYY-MM-DDTHH:MM:SS.sssZ"
            )
        return v

    @field_validator("finished_at")
    @classmethod
    def _finish_after_start(cls, v: str, info: Any) -> str:
        started = info.data.get("started_at")
        if started is not None and v < started:
            raise ValueError(f"finished_at={v} earlier than started_at={started}")
        return v

    @field_validator("backtest_end")
    @classmethod
    def _bt_end_after_start(cls, v: str, info: Any) -> str:
        started = info.data.get("backtest_start")
        if started is not None and v < started:
            raise ValueError(
                f"backtest_end={v} earlier than backtest_start={started}"
            )
        return v


__all__ = [
    "SCHEMA_VERSION",
    "Kind",
    "StrategySpec",
    "RiskRuleSpec",
    "SignalSource",
    "CatalogInstrument",
    "DataCatalog",
    "Totals",
    "PnlStats",
    "ReturnsStats",
    "BacktestManifest",
]

"""Live testnet sidecar writer.

This module is the single entry point used by the testnet runner to persist
ADR-004 sidecars (`orders.parquet`, `fills.parquet`, `positions.parquet`,
`account_balances.parquet`, `signal_lineage.parquet`) from a live
`nautilus_trader` ``TradingNode`` after the run finishes.

Implementation reuses the column-mapping and Parquet-writing helpers that
already live in :mod:`apps.strategies_nautilus.runners.backtest_runner` so the
backtest, paper, and testnet bundles share one schema definition.

The runner imports :func:`write_live_sidecars`. Trade events are read via
``node.trader.generate_*_report()`` which sources from the live exec/cache —
in testnet mode this includes both the strategy-originated MARKET orders and
the scheduled-shutdown close orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nautilus_trader.model.identifiers import Venue

from apps.strategies_nautilus.baseline_nautilus_strategy import LineageRecord
from apps.strategies_nautilus.runners.backtest_runner import (
    _prepare_reports,
    _write_parquet,
    validate_sidecar_bundle,
)


@dataclass(frozen=True)
class SidecarRecording:
    """Inputs the testnet runner needs to write live sidecars post-run."""

    venue_name: str
    lineage: list[LineageRecord]


@dataclass(frozen=True)
class SidecarWriteResult:
    paths: dict[str, Path]
    orders_count: int
    fills_count: int
    positions_count: int
    account_rows: int
    lineage_rows: int


def write_live_sidecars(
    *,
    trader: Any,
    venue_name: str,
    lineage: list[LineageRecord],
    bundle_root: Path,
    report_ts_event_ns: int,
) -> SidecarWriteResult:
    """Materialize ADR-004 sidecars from a live Nautilus ``Trader``.

    ``trader`` must expose the same ``generate_orders_report() /
    generate_fills_report() / generate_positions_report() /
    generate_account_report(Venue)`` surface that ``BacktestEngine.trader``
    provides; this is the case for both ``BacktestEngine`` and live
    ``TradingNode`` instances.

    ``report_ts_event_ns`` stamps the account-balance rows. For live runs the
    caller should pass the current wall-clock nanoseconds at write time —
    the live ``generate_account_report`` returns one row per currency without
    its own ``ts_event``.
    """

    bundle_root.mkdir(parents=True, exist_ok=True)

    orders_df = trader.generate_orders_report()
    fills_df = trader.generate_fills_report()
    positions_df = trader.generate_positions_report()
    account_df = trader.generate_account_report(Venue(venue_name))

    orders, fills, positions, account, lineage_df = _prepare_reports(
        orders_df=orders_df,
        fills_df=fills_df,
        positions_df=positions_df,
        account_df=account_df,
        lineage=lineage,
        venue_name=venue_name,
        report_ts_event_ns=report_ts_event_ns,
    )

    paths = {
        "orders": bundle_root / "orders.parquet",
        "fills": bundle_root / "fills.parquet",
        "positions": bundle_root / "positions.parquet",
        "account_balances": bundle_root / "account_balances.parquet",
        "signal_lineage": bundle_root / "signal_lineage.parquet",
    }
    _write_parquet(orders, paths["orders"])
    _write_parquet(fills, paths["fills"])
    _write_parquet(positions, paths["positions"])
    _write_parquet(account, paths["account_balances"])
    _write_parquet(lineage_df, paths["signal_lineage"])
    validate_sidecar_bundle(bundle_root)

    return SidecarWriteResult(
        paths=paths,
        orders_count=int(len(orders)),
        fills_count=int(len(fills)),
        positions_count=int(len(positions)),
        account_rows=int(len(account)),
        lineage_rows=int(len(lineage_df)),
    )


__all__ = [
    "SidecarRecording",
    "SidecarWriteResult",
    "write_live_sidecars",
]

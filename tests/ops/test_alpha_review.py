from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from apps.ops.alpha_review import ELIGIBLE_SOURCES, build_alpha_review
from apps.strategies_nautilus.result_schema import SCHEMA_VERSION
from apps.strategies_nautilus.runners.backtest_runner import _write_parquet

MONTHS = ["2024-08", "2024-09", "2024-10", "2024-11", "2024-12"]


def test_trend_regime_source_is_eligible_for_conservative_gate():
    assert "rule_trend_regime_v1" in ELIGIBLE_SOURCES


def test_pullback_regime_source_is_eligible_for_conservative_gate():
    assert "rule_pullback_regime_v1" in ELIGIBLE_SOURCES


def test_diverse_strategy_sources_are_eligible_for_conservative_gate():
    assert {
        "rule_dual_momentum_v1",
        "rule_mean_reversion_v1",
        "rule_vol_squeeze_v1",
        "rule_volume_breakout_v1",
    } <= ELIGIBLE_SOURCES


def test_multi_asset_sources_are_eligible_for_conservative_gate():
    assert {
        "rule_market_breadth_v1",
        "rule_relative_value_rotation_v1",
        "rule_xs_momentum_rotation_v1",
    } <= ELIGIBLE_SOURCES


def _write_bundle(
    root: Path,
    name: str,
    *,
    source: str,
    pnl_per_position: float,
    positions_per_month: int = 6,
    positions_by_month: list[int] | None = None,
    pnl_by_month: list[float] | None = None,
    commission_per_fill: float = 0.0,
    short: bool = False,
) -> Path:
    bundle = root / name
    bundle.mkdir()
    fills = []
    positions = []
    lineage = []
    positions_by_month = positions_by_month or [positions_per_month] * len(MONTHS)
    pnl_by_month = pnl_by_month or [pnl_per_position] * len(MONTHS)
    for month_index, month in enumerate(MONTHS):
        base = pd.Timestamp(f"{month}-02T00:00:00Z")
        for index in range(positions_by_month[month_index]):
            signal_id = f"{source}-{month_index}-{index}"
            open_ts = int((base + pd.Timedelta(hours=index * 2)).value)
            close_ts = open_ts + 3_600_000_000_000
            for suffix, ts in (("open", open_ts), ("close", close_ts)):
                fills.append(
                    {
                        "fill_id": f"{signal_id}-{suffix}",
                        "order_id": f"order-{signal_id}-{suffix}",
                        "venue": "BINANCE",
                        "instrument_id": "BTCUSDT.BINANCE",
                        "side": "BUY" if suffix == "open" else "SELL",
                        "quantity": 0.001,
                        "price": 50_000.0,
                        "commission": commission_per_fill,
                        "currency": "USDT",
                        "ts_event": ts,
                        "signal_id": signal_id,
                        "position_id": f"position-{signal_id}",
                    }
                )
            positions.append(
                {
                    "position_id": f"position-{signal_id}",
                    "opening_order_id": f"order-{signal_id}-open",
                    "closing_order_id": f"order-{signal_id}-close",
                    "venue": "BINANCE",
                    "instrument_id": "BTCUSDT.BINANCE",
                    "side": "SHORT" if short else "LONG",
                    "quantity": 0.001,
                    "peak_qty": 0.001,
                    "avg_px_open": 50_000.0,
                    "avg_px_close": 50_001.0,
                    "realized_pnl": pnl_by_month[month_index],
                    "unrealized_pnl": 0.0,
                    "opened_ts": open_ts,
                    "closed_ts": close_ts,
                    "signal_ids": signal_id,
                }
            )
            lineage.append(
                {
                    "signal_id": signal_id,
                    "source": source,
                    "model_version": "model-v1",
                    "ts_event": open_ts,
                    "decision": "target_long",
                    "reason": "",
                    "order_ids": f"order-{signal_id}-open",
                    "fill_ids": f"{signal_id}-open",
                    "position_id": f"position-{signal_id}",
                    "ts_decision": open_ts,
                }
            )
    orders = []
    account = [
        {
            "ts_event": int(pd.Timestamp("2024-12-31T23:59:00Z").value),
            "venue": "BINANCE",
            "account_id": "BINANCE-BACKTEST",
            "currency": "USDT",
            "total": 100_000.0,
            "free": 100_000.0,
            "locked": 0.0,
        }
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"20260101-00000{name[-1]}Z-0000000{name[-1]}",
        "kind": "backtest",
        "trader_id": "BACKTEST_TRADER-001",
        "machine_id": "pytest",
        "git_commit": "0" * 40,
        "git_dirty": False,
        "nautilus_version": "1.226.0",
        "python_version": "3.12.0",
        "started_at": "2026-01-01T00:00:00.000Z",
        "finished_at": "2026-01-01T00:00:01.000Z",
        "elapsed_seconds": 1.0,
        "backtest_start": "2024-08-01T00:00:00.000Z",
        "backtest_end": "2024-12-31T23:59:00.000Z",
        "venues": ["BINANCE"],
        "instruments": ["BTCUSDT.BINANCE"],
        "strategies": [{"name": "baseline", "params": {}}],
        "risk_rules": [],
        "signal_source": {
            "store_path": "signals.db",
            "store_sha256": "a" * 64,
            "filter": {"source": source, "model_version": "model-v1"},
            "row_count": len(lineage),
            "min_ts_event_ns": min(row["ts_event"] for row in lineage),
            "max_ts_event_ns": max(row["ts_event"] for row in lineage),
        },
        "data_catalog": {
            "path": "data/catalog",
            "instruments": [
                {
                    "id": "BTCUSDT.BINANCE",
                    "bars": "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
                    "rows": 220_320,
                }
            ],
        },
        "totals": {
            "iterations": 220_320,
            "events": len(lineage),
            "orders": 0,
            "positions": len(positions),
            "fills": len(fills),
        },
        "stats_pnls": {"USDT": {"PnL (total)": sum(p["realized_pnl"] for p in positions)}},
        "stats_returns": {},
    }
    (bundle / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _write_parquet(pd.DataFrame(orders), bundle / "orders.parquet")
    _write_parquet(pd.DataFrame(fills), bundle / "fills.parquet")
    _write_parquet(pd.DataFrame(positions), bundle / "positions.parquet")
    _write_parquet(pd.DataFrame(account), bundle / "account_balances.parquet")
    _write_parquet(pd.DataFrame(lineage), bundle / "signal_lineage.parquet")
    return bundle


def test_cost_formula_adds_recorded_commission_before_scenario_cost(tmp_path):
    bundle = _write_bundle(
        tmp_path,
        "run1",
        source="freqai_linear_v1",
        pnl_per_position=0.2,
        commission_per_fill=0.05,
    )
    report = build_alpha_review(
        [("current", bundle)],
        blind_start="2024-08-01",
        blind_end="2024-12-31",
    )
    candidate = report["candidates"][0]
    metrics = candidate["scenario_metrics"]["base"]
    expected = metrics["recorded_pnl"] + metrics["recorded_commission"]
    expected -= metrics["modeled_fee"] + metrics["modeled_slippage"]
    assert metrics["net_pnl"] == expected


def test_candidate_passes_conservative_gate_with_duplicate_repro_run(tmp_path):
    first = _write_bundle(
        tmp_path,
        "run1",
        source="rule_breakout_v1",
        pnl_per_position=0.2,
    )
    second = _write_bundle(
        tmp_path,
        "run2",
        source="rule_breakout_v1",
        pnl_per_position=0.2,
    )
    report = build_alpha_review(
        [("breakout", first), ("breakout", second)],
        blind_start="2024-08-01",
        blind_end="2024-12-31",
    )
    candidate = report["candidates"][0]
    assert candidate["reproducible"] is True
    assert candidate["passed"] is True
    assert candidate["recommendation"] == "eligible_for_paper_shadow_review"


def test_gate_accepts_exactly_four_positive_months(tmp_path):
    first = _write_bundle(
        tmp_path,
        "run1",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
        pnl_by_month=[0.5, 0.5, 0.5, 0.5, -0.01],
    )
    second = _write_bundle(
        tmp_path,
        "run2",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
        pnl_by_month=[0.5, 0.5, 0.5, 0.5, -0.01],
    )
    report = build_alpha_review(
        [("breakout", first), ("breakout", second)],
        blind_start="2024-08-01",
        blind_end="2024-12-31",
    )
    candidate = report["candidates"][0]
    assert candidate["gates"]["base_positive_months"] == 4
    assert candidate["passed"] is True


def test_gate_rejects_result_dependent_on_single_best_position(tmp_path):
    bundles = []
    for name in ("run1", "run2"):
        bundle = _write_bundle(
            tmp_path,
            name,
            source="rule_pullback_regime_v1",
            pnl_per_position=0.13,
            pnl_by_month=[0.13, 0.13, 0.13, 0.13, 0.0],
        )
        positions_path = bundle / "positions.parquet"
        positions = pd.read_parquet(positions_path)
        positions.loc[24, "realized_pnl"] = 2.0
        _write_parquet(positions, positions_path)
        bundles.append(bundle)

    report = build_alpha_review(
        [("pullback", bundles[0]), ("pullback", bundles[1])],
        blind_start="2024-08-01",
        blind_end="2024-12-31",
    )
    candidate = report["candidates"][0]

    assert candidate["gates"]["base_net_positive"] is True
    assert candidate["gates"]["stress_net_positive"] is True
    assert candidate["gates"]["base_net_without_best_position_positive"] is False
    assert candidate["passed"] is False


def test_gate_blocks_29_positions(tmp_path):
    bundle = _write_bundle(
        tmp_path,
        "run1",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
        positions_by_month=[6, 6, 6, 6, 5],
    )
    report = build_alpha_review(
        [("breakout", bundle), ("breakout", bundle)],
        blind_start="2024-08-01",
        blind_end="2024-12-31",
    )
    candidate = report["candidates"][0]
    assert candidate["gates"]["closed_positions"] == 29
    assert candidate["recommendation"] == "insufficient_evidence"
    assert candidate["passed"] is False


def test_gate_blocks_short_exposure(tmp_path):
    bundle = _write_bundle(
        tmp_path,
        "run1",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
        short=True,
    )
    report = build_alpha_review(
        [("breakout", bundle), ("breakout", bundle)],
        blind_start="2024-08-01",
        blind_end="2024-12-31",
    )
    candidate = report["candidates"][0]
    assert candidate["gates"]["spot_long_flat_only"] is False
    assert candidate["passed"] is False


def test_review_rejects_nonstandard_json_and_missing_sidecar(tmp_path):
    malformed = _write_bundle(
        tmp_path,
        "run1",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
    )
    manifest = malformed / "run_manifest.json"
    manifest.write_text(manifest.read_text().replace('"elapsed_seconds": 1.0', '"elapsed_seconds": NaN'))
    with pytest.raises(ValueError, match="non-standard JSON"):
        build_alpha_review(
            [("breakout", malformed)],
            blind_start="2024-08-01",
            blind_end="2024-12-31",
        )

    missing = _write_bundle(
        tmp_path,
        "run2",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
    )
    (missing / "fills.parquet").unlink()
    with pytest.raises(Exception, match="missing sidecar"):
        build_alpha_review(
            [("breakout", missing)],
            blind_start="2024-08-01",
            blind_end="2024-12-31",
        )


def test_review_requires_exactly_five_complete_months(tmp_path):
    bundle = _write_bundle(
        tmp_path,
        "run1",
        source="rule_breakout_v1",
        pnl_per_position=0.5,
    )
    with pytest.raises(ValueError, match="exactly 5 months"):
        build_alpha_review(
            [("breakout", bundle)],
            blind_start="2024-09-01",
            blind_end="2024-12-31",
        )

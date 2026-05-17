"""Tests for ADR-007 paper bundle reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from apps.strategies_nautilus.result_schema import SCHEMA_VERSION
from apps.strategies_nautilus.runners.backtest_runner import _write_parquet
from apps.strategies_nautilus.runners.report_paper_bundle import (
    load_paper_bundle_report,
    main,
    render_text_report,
)

RUN_ID = "20260101-000000Z-00000000"
SOURCE = "freqai_linear_v1"
MODEL_VERSION = "linear-mom-train20240105"


def _write_bundle(
    tmp_path: Path,
    *,
    manifest_overrides: dict | None = None,
    runtime_overrides: dict | None = None,
    lineage_rows: list[dict] | None = None,
    order_rows: list[dict] | None = None,
    fill_rows: list[dict] | None = None,
    position_rows: list[dict] | None = None,
) -> Path:
    bundle_dir = tmp_path / RUN_ID
    bundle_dir.mkdir()
    lineage_rows = lineage_rows or [
        _lineage_row("s1", decision="target_long", reason="dry_run"),
        _lineage_row("s2", decision="target_long", reason="dry_run"),
    ]
    order_rows = order_rows or []
    fill_rows = fill_rows or []
    position_rows = position_rows or []
    account_rows = [
        {
            "ts_event": 1_704_067_140_000_000_000,
            "venue": "BINANCE",
            "account_id": "BINANCE-PAPER",
            "currency": "USDT",
            "total": 100_000.0,
            "free": 100_000.0,
            "locked": 0.0,
        }
    ]
    runtime = {
        "mode": "paper",
        "data_mode": "catalog_polling",
        "order_mode": "simulated",
        "heartbeat_interval_seconds": 30,
        "max_signal_lag_seconds": 120,
        "operator": "pytest",
    }
    if runtime_overrides:
        runtime.update(runtime_overrides)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "kind": "paper",
        "trader_id": "PAPER_TRADER-001",
        "machine_id": "pytest",
        "git_commit": "0" * 40,
        "git_dirty": False,
        "nautilus_version": "1.226.0",
        "python_version": "3.12.0",
        "started_at": "2026-01-01T00:00:00.000Z",
        "finished_at": "2026-01-01T00:00:01.000Z",
        "elapsed_seconds": 1.0,
        "backtest_start": "2024-01-01T00:00:00.000Z",
        "backtest_end": "2024-01-07T23:59:00.000Z",
        "venues": ["BINANCE"],
        "instruments": ["BTCUSDT.BINANCE"],
        "strategies": [
            {
                "name": "baseline_signal_strategy",
                "params": {
                    "min_confidence": 0.5,
                    "max_position_pct": 0.05,
                    "daily_drawdown_stop_pct": 0.05,
                    "trade_size": "0.001",
                    "seed": 0,
                    "policies": [
                        {
                            "source": SOURCE,
                            "model_version": MODEL_VERSION,
                            "position_pct_multiplier": 0.2,
                            "min_confidence_override": None,
                            "dry_run": True,
                        }
                    ],
                },
            }
        ],
        "risk_rules": [
            {"name": "daily_drawdown_stop", "params": {"max_pct": 0.05}},
            {"name": "max_signal_lag", "params": {"max_seconds": 120}},
        ],
        "signal_source": {
            "store_path": "data/bridge/signals.db",
            "store_sha256": "a" * 64,
            "filter": {"source": SOURCE, "model_version": MODEL_VERSION},
            "row_count": len(lineage_rows),
            "min_ts_event_ns": 1_704_067_200_000_000_000,
            "max_ts_event_ns": 1_704_067_260_000_000_000,
        },
        "data_catalog": {
            "path": "data/catalog",
            "instruments": [
                {
                    "id": "BTCUSDT.BINANCE",
                    "bars": "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
                    "rows": 10080,
                }
            ],
        },
        "totals": {
            "iterations": 10080,
            "events": len(lineage_rows),
            "orders": len(order_rows),
            "positions": len(position_rows),
            "fills": len(fill_rows),
        },
        "stats_pnls": {
            "USDT": {
                "PnL (total)": 0.0,
                "PnL% (total)": 0.0,
                "Win Rate": None,
                "Expectancy": None,
                "Max Drawdown (Pct)": -0.01,
                "Max Drawdown (Abs)": -10.0,
            }
        },
        "stats_returns": {
            "max_drawdown": -0.01,
            "max_drawdown_abs": -10.0,
        },
        "runtime": runtime,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (bundle_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_parquet(pd.DataFrame(order_rows), bundle_dir / "orders.parquet")
    _write_parquet(pd.DataFrame(fill_rows), bundle_dir / "fills.parquet")
    _write_parquet(pd.DataFrame(position_rows), bundle_dir / "positions.parquet")
    _write_parquet(pd.DataFrame(account_rows), bundle_dir / "account_balances.parquet")
    _write_parquet(pd.DataFrame(lineage_rows), bundle_dir / "signal_lineage.parquet")
    return bundle_dir


def _lineage_row(signal_id: str, *, decision: str, reason: str) -> dict:
    return {
        "signal_id": signal_id,
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "ts_event": 1_704_067_200_000_000_000,
        "decision": decision,
        "reason": reason,
        "order_ids": "",
        "fill_ids": "",
        "position_id": "",
        "ts_decision": 1_704_067_200_000_000_000,
    }


def test_load_paper_bundle_report_summarizes_dry_run_bundle(tmp_path):
    bundle_dir = _write_bundle(tmp_path)

    report = load_paper_bundle_report(bundle_dir)

    assert report.run_id == RUN_ID
    assert report.kind == "paper"
    assert report.source == SOURCE
    assert report.model_version == MODEL_VERSION
    assert report.policy_dry_run is True
    assert report.position_pct_multiplier == 0.2
    assert report.signal_rows == 2
    assert report.session_days_inclusive == 7
    assert report.accepted_signals == 2
    assert report.dry_run_signals == 2
    assert report.totals["orders"] == 0
    assert report.pnl_total_by_currency == {"USDT": 0.0}
    assert report.max_drawdown_pct_by_currency == {"USDT": -0.01}
    assert report.max_drawdown_abs_by_currency == {"USDT": -10.0}
    assert report.missing_metrics == []
    assert report.eligible_for_review is True
    assert report.review_blockers == []
    assert "manual_review_required_before_disabling_dry_run" in report.promotion_blockers
    assert report.recommendation == "manual_review_required_before_paper_simulated"


def test_load_paper_bundle_report_flags_review_blockers(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        manifest_overrides={"git_dirty": True},
        lineage_rows=[
            _lineage_row("stale", decision="skip", reason="signal_lag: 180s > 120s"),
            _lineage_row(
                "unauthorized",
                decision="skip",
                reason="reject_unauthorized_source: test",
            ),
            _lineage_row("risk", decision="skip", reason="kill_switch: daily_drawdown"),
        ],
    )

    report = load_paper_bundle_report(bundle_dir)

    assert report.eligible_for_review is False
    assert "git_dirty" in report.review_blockers
    assert "signal_lag_signals=1" in report.review_blockers
    assert "unauthorized_signals=1" in report.review_blockers
    assert "kill_switch_signals=1" in report.review_blockers
    assert report.skipped_signals == 3
    assert report.recommendation == "hold_until_review_blockers_clear"


def test_load_paper_bundle_report_flags_sidecar_count_mismatch(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        manifest_overrides={
            "totals": {
                "iterations": 10080,
                "events": 2,
                "orders": 1,
                "positions": 0,
                "fills": 0,
            }
        },
    )

    report = load_paper_bundle_report(bundle_dir)

    assert "sidecar_mismatch:orders manifest=1 actual=0" in report.review_blockers
    assert report.eligible_for_review is False


def test_load_paper_bundle_report_flags_missing_drawdown_metric(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        manifest_overrides={
            "stats_pnls": {
                "USDT": {
                    "PnL (total)": 0.0,
                    "PnL% (total)": 0.0,
                    "Win Rate": None,
                    "Expectancy": None,
                }
            },
            "stats_returns": {},
        },
    )

    report = load_paper_bundle_report(bundle_dir)

    assert report.max_drawdown_pct_by_currency == {"USDT": None}
    assert report.max_drawdown_abs_by_currency == {"USDT": None}
    assert report.missing_metrics == ["max_drawdown_pct"]


def test_report_cli_outputs_json(tmp_path, capsys):
    bundle_dir = _write_bundle(tmp_path)

    rc = main(["--json", str(bundle_dir)])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == RUN_ID
    assert payload["source"] == SOURCE
    assert payload["eligible_for_review"] is True


def test_report_cli_outputs_text(tmp_path, capsys):
    bundle_dir = _write_bundle(tmp_path)

    rc = main([str(bundle_dir)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "eligible_for_review: True" in out
    assert "source_model: freqai_linear_v1 / linear-mom-train20240105" in out


def test_load_paper_bundle_report_rejects_non_paper_kind(tmp_path):
    bundle_dir = _write_bundle(tmp_path, manifest_overrides={"kind": "backtest"})

    with pytest.raises(ValueError, match="expected 'paper'"):
        load_paper_bundle_report(bundle_dir)


def test_render_text_report_contains_blocker_summary(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        lineage_rows=[
            _lineage_row("expired", decision="skip", reason="expired: signal ttl")
        ],
    )
    report = load_paper_bundle_report(bundle_dir)

    text = render_text_report(report)

    assert "review_blockers: expired_signals=1" in text
    assert 'max_drawdown_pct={"USDT": -0.01}' in text
    assert 'max_drawdown_abs={"USDT": -10.0}' in text
    assert "recommendation: hold_until_review_blockers_clear" in text

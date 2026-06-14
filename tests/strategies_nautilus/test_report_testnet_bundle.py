"""Tests for ADR-008 testnet bundle reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from apps.strategies_nautilus.runners.backtest_runner import _write_parquet
from apps.strategies_nautilus.runners.report_testnet_bundle import (
    load_testnet_bundle_report,
    load_testnet_continuity_summary,
    load_testnet_evidence_summary,
    main,
    render_continuity_markdown,
    render_continuity_text,
    render_markdown_summary,
    render_summary_text,
    render_text_report,
)

RUN_ID = "20260101-000000Z-00000000"
SOURCE = "freqai_linear_v1"
MODEL_VERSION = "linear-mom-train20240105"


def _write_bundle(
    tmp_path: Path,
    *,
    run_id: str = RUN_ID,
    manifest_overrides: dict | None = None,
    runtime_overrides: dict | None = None,
    heartbeat_rows: list[dict] | None = None,
    alert_rows: list[dict] | None = None,
    realized_pnl: float = -0.5,
    started_at: str = "2026-01-01T00:00:00.000Z",
    finished_at: str = "2026-01-01T06:00:00.000Z",
    elapsed_seconds: float = 21600.0,
    write_sidecars: bool = True,
) -> Path:
    bundle_dir = tmp_path / run_id
    bundle_dir.mkdir()
    logs_dir = bundle_dir / "logs"
    logs_dir.mkdir()

    order_rows = [
        _order_row("O-entry", "BUY", "s1"),
        _order_row("O-close", "SELL", ""),
    ]
    fill_rows = [
        _fill_row("F-entry", "O-entry", "BUY", "s1", 1_704_067_200_000_000_000),
        _fill_row("F-close", "O-close", "SELL", "", 1_704_067_260_000_000_000),
    ]
    position_rows = [
        {
            "position_id": "P-1",
            "venue": "BINANCE",
            "instrument_id": "BTCUSDT.BINANCE",
            "side": "FLAT",
            "quantity": 0.0,
            "peak_qty": 0.001,
            "avg_px_open": 100.0,
            "avg_px_close": 99.5,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": 0.0,
            "opened_ts": 1_704_067_200_000_000_000,
            "closed_ts": 1_704_067_260_000_000_000,
            "signal_ids": "s1",
        }
    ]
    account_rows = [
        {
            "ts_event": 1_704_067_260_000_000_000,
            "venue": "BINANCE",
            "account_id": "BINANCE-SPOT-master",
            "currency": "USDT",
            "total": 9999.5,
            "free": 9999.5,
            "locked": 0.0,
        }
    ]
    lineage_rows = [
        _lineage_row("s1", order_ids="O-entry", fill_ids="F-entry", position_id="P-1"),
        _lineage_row("s2", order_ids="", fill_ids="", position_id=""),
    ]

    runtime = {
        "mode": "testnet",
        "data_mode": "live",
        "order_mode": "real",
        "shutdown_reason": "max_duration",
        "strategies_registered": 1,
        "actors_registered": 0,
        "enable_strategy_execution": True,
        "write_live_sidecars": True,
        "open_orders": 0,
        "open_positions": 0,
        "open_state_source": "live_sidecars",
        "exchange_error_count": 0,
        "ws_reconnect_count": 0,
        "sidecar": {
            "success": True,
            "error": None,
            "result": {
                "orders_count": len(order_rows),
                "fills_count": len(fill_rows),
                "positions_count": len(position_rows),
                "account_rows": len(account_rows),
                "lineage_rows": len(lineage_rows),
                "paths": {
                    "orders": str(bundle_dir / "orders.parquet"),
                    "fills": str(bundle_dir / "fills.parquet"),
                    "positions": str(bundle_dir / "positions.parquet"),
                    "account_balances": str(bundle_dir / "account_balances.parquet"),
                    "signal_lineage": str(bundle_dir / "signal_lineage.parquet"),
                },
            },
        },
    }
    if runtime_overrides:
        runtime.update(runtime_overrides)

    manifest = {
        "schema_version": "backtest.v1",
        "kind": "testnet",
        "run_id": run_id,
        "trader_id": "TESTNET_TRADER-001",
        "git_commit": "0" * 40,
        "git_dirty": False,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed_seconds,
        "venues": ["BINANCE"],
        "instruments": ["BTCUSDT.BINANCE"],
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "runtime": runtime,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (bundle_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    heartbeat_rows = heartbeat_rows or [
        _heartbeat("2026-01-01T00:00:00.000Z", run_id=run_id, open_positions=0),
        _heartbeat("2026-01-01T00:00:30.000Z", run_id=run_id, open_positions=1),
        _heartbeat("2026-01-01T00:01:00.000Z", run_id=run_id, open_positions=1),
    ]
    (logs_dir / "heartbeat.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in heartbeat_rows),
        encoding="utf-8",
    )
    if alert_rows is not None:
        (logs_dir / "alerts.log").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in alert_rows),
            encoding="utf-8",
        )

    if write_sidecars:
        _write_parquet(pd.DataFrame(order_rows), bundle_dir / "orders.parquet")
        _write_parquet(pd.DataFrame(fill_rows), bundle_dir / "fills.parquet")
        _write_parquet(pd.DataFrame(position_rows), bundle_dir / "positions.parquet")
        _write_parquet(pd.DataFrame(account_rows), bundle_dir / "account_balances.parquet")
        _write_parquet(pd.DataFrame(lineage_rows), bundle_dir / "signal_lineage.parquet")
    return bundle_dir


def _order_row(order_id: str, side: str, signal_id: str) -> dict:
    return {
        "order_id": order_id,
        "client_order_id": order_id,
        "venue": "BINANCE",
        "instrument_id": "BTCUSDT.BINANCE",
        "side": side,
        "quantity": 0.001,
        "price": 100.0,
        "type": "MARKET",
        "status": "FILLED",
        "ts_init": 1_704_067_200_000_000_000,
        "ts_last": 1_704_067_200_000_000_000,
        "signal_id": signal_id,
    }


def _fill_row(fill_id: str, order_id: str, side: str, signal_id: str, ts: int) -> dict:
    return {
        "fill_id": fill_id,
        "order_id": order_id,
        "client_order_id": order_id,
        "venue_order_id": f"V-{order_id}",
        "trade_id": f"T-{fill_id}",
        "venue": "BINANCE",
        "instrument_id": "BTCUSDT.BINANCE",
        "side": side,
        "quantity": 0.001,
        "price": 100.0,
        "commission": 0.0,
        "currency": "USDT",
        "ts_event": ts,
        "signal_id": signal_id,
    }


def _lineage_row(
    signal_id: str,
    *,
    order_ids: str,
    fill_ids: str,
    position_id: str,
) -> dict:
    return {
        "signal_id": signal_id,
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "ts_event": 1_704_067_200_000_000_000,
        "decision": "target_long",
        "reason": "",
        "order_ids": order_ids,
        "fill_ids": fill_ids,
        "position_id": position_id,
        "ts_decision": 1_704_067_200_000_000_000,
    }


def _heartbeat(ts: str, *, open_positions: int, run_id: str = RUN_ID) -> dict:
    return {
        "event": "heartbeat",
        "kind": "testnet",
        "run_id": run_id,
        "ts": ts,
        "ws_connected": True,
        "ws_reconnect_count": 0,
        "exchange_error_count": 0,
        "open_orders": 0,
        "open_positions": open_positions,
        "account_total_usdt": 10_000.0,
        "daily_pnl": 0.0,
    }


def test_load_testnet_bundle_report_summarizes_clean_canary(tmp_path):
    bundle_dir = _write_bundle(tmp_path)

    report = load_testnet_bundle_report(bundle_dir)

    assert report.run_id == RUN_ID
    assert report.kind == "testnet"
    assert report.source == SOURCE
    assert report.model_version == MODEL_VERSION
    assert report.shutdown_reason == "max_duration"
    assert report.heartbeat_count == 3
    assert report.max_heartbeat_gap_seconds == 30.0
    assert report.alert_count == 0
    assert report.alert_msg_counts["heartbeat_lost"] == 0
    assert report.sidecar_rows == {
        "orders": 2,
        "fills": 2,
        "positions": 1,
        "account_balances": 1,
        "signal_lineage": 2,
    }
    assert report.sidecar_mismatches == []
    assert report.first_signal_ts_event_ns == 1_704_067_200_000_000_000
    assert report.last_signal_ts_event_ns == 1_704_067_200_000_000_000
    assert report.decision_counts == {"target_long": 2}
    assert report.lineage_rows_with_order_ids == 1
    assert report.first_fill is not None
    assert report.first_fill["signal_id"] == "s1"
    assert report.last_fill is not None
    assert report.last_fill["signal_id"] == ""
    assert report.final_position_sides == {"FLAT": 1}
    assert report.realized_pnl_total == -0.5
    assert report.final_account_usdt["total"] == 9999.5
    assert report.clean_for_retro is True
    assert report.review_blockers == []


def test_load_testnet_bundle_report_counts_alerts_and_blocks_clean_retro(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        alert_rows=[
            {
                "ts": "2026-01-01T00:02:00.000Z",
                "severity": "critical",
                "kind": "testnet",
                "run_id": RUN_ID,
                "msg": "heartbeat_lost",
                "context": {"watchdog_status": "heartbeat_stale"},
            }
        ],
    )

    report = load_testnet_bundle_report(bundle_dir)

    assert report.alert_count == 1
    assert report.alert_msg_counts["heartbeat_lost"] == 1
    assert report.alert_kind_counts == {"testnet": 1}
    assert report.alert_severity_counts == {"critical": 1}
    assert "alerts=1" in report.review_blockers
    assert report.clean_for_retro is False


def test_load_testnet_bundle_report_flags_sidecar_count_mismatch(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        runtime_overrides={
            "sidecar": {
                "success": True,
                "error": None,
                "result": {
                    "orders_count": 3,
                    "fills_count": 2,
                    "positions_count": 1,
                    "account_rows": 1,
                    "lineage_rows": 2,
                },
            }
        },
    )

    report = load_testnet_bundle_report(bundle_dir)

    assert "sidecar_mismatch:orders manifest=3 actual=2" in report.review_blockers
    assert report.clean_for_retro is False


def test_load_testnet_bundle_report_treats_flat_sidecars_as_final_state(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        runtime_overrides={
            "open_positions": 1,
            "open_state_source": "telemetry",
        },
    )

    report = load_testnet_bundle_report(bundle_dir)

    assert report.final_position_sides == {"FLAT": 1}
    assert "open_positions=1" not in report.review_blockers
    assert "open_state_source_not_live_sidecars" not in report.review_blockers
    assert report.clean_for_retro is True


def test_load_testnet_bundle_report_flags_missing_live_sidecars(tmp_path):
    bundle_dir = _write_bundle(tmp_path, write_sidecars=False)

    report = load_testnet_bundle_report(bundle_dir)

    assert report.sidecar_rows["orders"] == 0
    assert any("missing sidecar" in error for error in report.sidecar_schema_errors)
    assert "sidecar_mismatch:orders manifest=2 actual=0" in report.review_blockers
    assert "no_orders" in report.review_blockers
    assert report.clean_for_retro is False


def test_load_testnet_evidence_summary_aggregates_clean_and_blocked_runs(tmp_path):
    clean_one = _write_bundle(
        tmp_path,
        run_id="20260101-000000Z-00000001",
        realized_pnl=-0.25,
    )
    clean_two = _write_bundle(
        tmp_path,
        run_id="20260102-000000Z-00000002",
        realized_pnl=0.75,
    )
    blocked = _write_bundle(
        tmp_path,
        run_id="20260103-000000Z-00000003",
        manifest_overrides={"git_dirty": True},
        realized_pnl=-1.0,
    )

    summary = load_testnet_evidence_summary([clean_one, clean_two, blocked])

    assert summary.run_count == 3
    assert summary.clean_run_count == 2
    assert summary.blocked_run_count == 1
    assert summary.clean_run_ids == [
        "20260101-000000Z-00000001",
        "20260102-000000Z-00000002",
    ]
    assert summary.blocked_run_ids == ["20260103-000000Z-00000003"]
    assert summary.clean_elapsed_seconds == 43_200.0
    assert summary.clean_orders == 4
    assert summary.clean_fills == 4
    assert summary.clean_positions == 2
    assert summary.clean_heartbeats == 6
    assert summary.clean_alerts == 0
    assert summary.clean_realized_pnl == 0.5
    assert summary.total_realized_pnl == -0.5
    assert summary.final_flat_run_count == 3
    assert summary.review_blockers_by_run == {
        "20260103-000000Z-00000003": ["git_dirty"]
    }
    assert summary.recommendation == "review_blocked_runs_before_progress_evidence"


def test_render_summary_text_and_markdown(tmp_path):
    clean_one = _write_bundle(tmp_path, run_id="20260101-000000Z-00000001")
    clean_two = _write_bundle(tmp_path, run_id="20260102-000000Z-00000002")
    summary = load_testnet_evidence_summary([clean_one, clean_two])

    text = render_summary_text(summary)
    markdown = render_markdown_summary(summary)

    assert "clean_run_count: 2" in text
    assert "recommendation: ready_for_progress_evidence" in text
    assert "| run_id | date | clean | heartbeats | alerts | sidecars |" in markdown
    assert "`20260101-000000Z-00000001`" in markdown
    assert "- clean_run_count: 2/2" in markdown


def test_load_testnet_continuity_summary_counts_current_streak(tmp_path):
    day_one = _write_bundle(
        tmp_path,
        run_id="20260101-000000Z-00000001",
        started_at="2026-01-01T00:00:00.000Z",
        finished_at="2026-01-01T06:00:00.000Z",
        realized_pnl=0.25,
    )
    day_two = _write_bundle(
        tmp_path,
        run_id="20260102-000000Z-00000002",
        started_at="2026-01-02T00:00:00.000Z",
        finished_at="2026-01-02T06:00:00.000Z",
        realized_pnl=-0.5,
    )
    day_three = _write_bundle(
        tmp_path,
        run_id="20260103-000000Z-00000003",
        started_at="2026-01-03T00:00:00.000Z",
        finished_at="2026-01-03T06:00:00.000Z",
        realized_pnl=1.0,
    )

    summary = load_testnet_continuity_summary(
        [day_one, day_two, day_three],
        required_consecutive_days=3,
    )

    assert summary.day_count == 3
    assert summary.qualified_day_count == 3
    assert summary.longest_qualified_streak_days == 3
    assert summary.current_qualified_streak_days == 3
    assert summary.required_gate_met is True
    assert summary.total_exchange_error_count == 0
    assert summary.total_ws_reconnect_count == 0
    assert summary.blockers == []
    assert summary.recommendation == "ready_for_live_risk_adr_review"
    assert [day.date for day in summary.days] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]


def test_load_testnet_continuity_summary_breaks_on_blocked_day(tmp_path):
    day_one = _write_bundle(
        tmp_path,
        run_id="20260101-000000Z-00000001",
        started_at="2026-01-01T00:00:00.000Z",
        finished_at="2026-01-01T06:00:00.000Z",
    )
    blocked_day = _write_bundle(
        tmp_path,
        run_id="20260102-000000Z-00000002",
        started_at="2026-01-02T00:00:00.000Z",
        finished_at="2026-01-02T06:00:00.000Z",
        alert_rows=[
            {
                "ts": "2026-01-02T00:02:00.000Z",
                "severity": "critical",
                "kind": "testnet",
                "run_id": "20260102-000000Z-00000002",
                "msg": "heartbeat_lost",
                "context": {"watchdog_status": "heartbeat_stale"},
            }
        ],
    )
    day_three = _write_bundle(
        tmp_path,
        run_id="20260103-000000Z-00000003",
        started_at="2026-01-03T00:00:00.000Z",
        finished_at="2026-01-03T06:00:00.000Z",
    )

    summary = load_testnet_continuity_summary(
        [day_one, blocked_day, day_three],
        required_consecutive_days=2,
    )

    assert summary.qualified_day_count == 2
    assert summary.longest_qualified_streak_days == 1
    assert summary.current_qualified_streak_days == 1
    assert summary.required_gate_met is False
    assert (
        "current_qualified_streak_days=1<required=2"
        in summary.blockers
    )
    assert summary.days[1].qualified is False
    assert summary.days[1].blocked_run_ids == ["20260102-000000Z-00000002"]
    assert "alerts=1" in summary.days[1].blockers


def test_load_testnet_continuity_summary_blocks_mixed_same_day(tmp_path):
    blocked = _write_bundle(
        tmp_path,
        run_id="20260102-000000Z-00000001",
        started_at="2026-01-02T00:00:00.000Z",
        finished_at="2026-01-02T00:30:00.000Z",
        elapsed_seconds=1800.0,
        alert_rows=[
            {
                "ts": "2026-01-02T00:02:00.000Z",
                "severity": "critical",
                "kind": "testnet",
                "run_id": "20260102-000000Z-00000001",
                "msg": "emergency_flatten_completed",
                "context": {"success": True},
            }
        ],
    )
    clean = _write_bundle(
        tmp_path,
        run_id="20260102-060000Z-00000002",
        started_at="2026-01-02T06:00:00.000Z",
        finished_at="2026-01-02T12:00:00.000Z",
    )

    summary = load_testnet_continuity_summary(
        [blocked, clean],
        required_consecutive_days=1,
    )

    assert summary.qualified_day_count == 0
    assert summary.current_qualified_streak_days == 0
    assert summary.days[0].clean_run_ids == ["20260102-060000Z-00000002"]
    assert summary.days[0].blocked_run_ids == ["20260102-000000Z-00000001"]
    assert "blocked_runs=20260102-000000Z-00000001" in summary.days[0].blockers
    assert "emergency_flatten_completed=1" in summary.blockers


def test_load_testnet_continuity_summary_applies_adr_thresholds(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        runtime_overrides={
            "exchange_error_count": 1000,
            "ws_reconnect_count": 50,
            "restart_sequence": 4,
            "restart_drift_detected": True,
        },
        alert_rows=[
            {
                "ts": "2026-01-01T00:02:00.000Z",
                "severity": "critical",
                "kind": "testnet",
                "run_id": RUN_ID,
                "msg": "kill_switch_fired",
                "context": {"daily_loss_pct": 0.05},
            }
        ],
    )

    summary = load_testnet_continuity_summary(
        [bundle_dir],
        required_consecutive_days=1,
    )

    assert summary.required_gate_met is False
    assert summary.total_exchange_error_count == 1000
    assert summary.total_ws_reconnect_count == 50
    assert summary.max_restart_sequence == 4
    assert summary.restart_drift_days == ["2026-01-01"]
    assert summary.kill_switch_alerts == 1
    assert "exchange_error_count=1000>999" in summary.blockers
    assert "ws_reconnect_count=50>49" in summary.blockers
    assert "max_restart_sequence=4>3" in summary.blockers
    assert "restart_drift_days=2026-01-01" in summary.blockers
    assert "kill_switch_fired=1" in summary.blockers


def test_render_continuity_text_and_markdown(tmp_path):
    day_one = _write_bundle(
        tmp_path,
        run_id="20260101-000000Z-00000001",
        started_at="2026-01-01T00:00:00.000Z",
        finished_at="2026-01-01T06:00:00.000Z",
    )
    day_two = _write_bundle(
        tmp_path,
        run_id="20260102-000000Z-00000002",
        started_at="2026-01-02T00:00:00.000Z",
        finished_at="2026-01-02T06:00:00.000Z",
    )
    summary = load_testnet_continuity_summary(
        [day_one, day_two],
        required_consecutive_days=2,
    )

    text = render_continuity_text(summary)
    markdown = render_continuity_markdown(summary)

    assert "testnet continuity summary" in text
    assert "required_gate_met: True" in text
    assert "# Testnet Continuity Summary" in markdown
    assert "- current_qualified_streak_days: 2/2" in markdown
    assert "| date | qualified | clean hours | runs | alerts |" in markdown


def test_report_cli_outputs_json(tmp_path, capsys):
    bundle_dir = _write_bundle(tmp_path)

    rc = main(["--json", str(bundle_dir)])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == RUN_ID
    assert payload["clean_for_retro"] is True
    assert payload["sidecar_rows"]["fills"] == 2


def test_report_cli_outputs_text(tmp_path, capsys):
    bundle_dir = _write_bundle(tmp_path)

    rc = main([str(bundle_dir)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "clean_for_retro: True" in out
    assert "source_model: freqai_linear_v1 / linear-mom-train20240105" in out
    assert "last_signal_ts_event_ns=1704067200000000000" in out


def test_report_cli_outputs_summary_json_for_multiple_bundles(tmp_path, capsys):
    clean_one = _write_bundle(tmp_path, run_id="20260101-000000Z-00000001")
    clean_two = _write_bundle(tmp_path, run_id="20260102-000000Z-00000002")

    rc = main(["--json", str(clean_one), str(clean_two)])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_count"] == 2
    assert payload["clean_run_count"] == 2
    assert payload["clean_orders"] == 4


def test_report_cli_outputs_summary_markdown(tmp_path, capsys):
    clean_one = _write_bundle(tmp_path, run_id="20260101-000000Z-00000001")
    clean_two = _write_bundle(tmp_path, run_id="20260102-000000Z-00000002")

    rc = main(["--markdown", str(clean_one), str(clean_two)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "# Testnet Evidence Summary" in out
    assert "- clean_run_count: 2/2" in out
    assert "`20260102-000000Z-00000002`" in out


def test_report_cli_outputs_continuity_json(tmp_path, capsys):
    day_one = _write_bundle(
        tmp_path,
        run_id="20260101-000000Z-00000001",
        started_at="2026-01-01T00:00:00.000Z",
        finished_at="2026-01-01T06:00:00.000Z",
    )
    day_two = _write_bundle(
        tmp_path,
        run_id="20260102-000000Z-00000002",
        started_at="2026-01-02T00:00:00.000Z",
        finished_at="2026-01-02T06:00:00.000Z",
    )

    rc = main(
        [
            "--continuity",
            "--json",
            "--required-consecutive-days",
            "2",
            str(day_one),
            str(day_two),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["current_qualified_streak_days"] == 2
    assert payload["required_gate_met"] is True
    assert payload["days"][1]["date"] == "2026-01-02"


def test_report_cli_outputs_continuity_markdown(tmp_path, capsys):
    day_one = _write_bundle(
        tmp_path,
        run_id="20260101-000000Z-00000001",
        started_at="2026-01-01T00:00:00.000Z",
        finished_at="2026-01-01T06:00:00.000Z",
    )

    rc = main(["--continuity", "--markdown", str(day_one)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "# Testnet Continuity Summary" in out
    assert "- qualified_day_count: 1/1" in out
    assert "`20260101-000000Z-00000001`" in out


def test_load_testnet_bundle_report_rejects_non_testnet_kind(tmp_path):
    bundle_dir = _write_bundle(tmp_path, manifest_overrides={"kind": "paper"})

    with pytest.raises(ValueError, match="expected 'testnet'"):
        load_testnet_bundle_report(bundle_dir)


def test_render_text_report_contains_blocker_summary(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path,
        manifest_overrides={"git_dirty": True},
    )
    report = load_testnet_bundle_report(bundle_dir)

    text = render_text_report(report)

    assert "review_blockers: git_dirty" in text
    assert "recommendation: review_blockers_before_retro" in text

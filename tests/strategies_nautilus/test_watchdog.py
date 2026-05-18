"""Tests for the ADR-008 Phase 3d heartbeat watchdog."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

from infra.watchdog import watchdog
from infra.watchdog.watchdog import WatchdogSettings, check_once, main

RUN_ID = "20260518-130000Z-feedface"


def _write_heartbeat(root: Path, *, ts: str) -> None:
    heartbeat = root / RUN_ID / "logs" / "heartbeat.jsonl"
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    heartbeat.write_text(
        json.dumps(
            {
                "event": "heartbeat",
                "ts": ts,
                "kind": "testnet",
                "run_id": RUN_ID,
                "ws_connected": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _settings(tmp_path: Path) -> WatchdogSettings:
    return WatchdogSettings(
        active_run_id=RUN_ID,
        instrument_ids=("BTCUSDT.BINANCE",),
        testnet_root=tmp_path / "data" / "testnet",
        state_path=tmp_path / "infra" / "watchdog" / "state.json",
        heartbeat_timeout_seconds=90.0,
        operator="pytest-watchdog",
    )


def test_watchdog_healthy_heartbeat_writes_state_without_flatten(tmp_path):
    now = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    settings = _settings(tmp_path)
    _write_heartbeat(
        settings.testnet_root,
        ts="2026-05-18T12:59:30.000Z",
    )
    flatten_calls = []

    result = check_once(
        settings,
        clock=lambda: now,
        flatten_invoker=lambda s: flatten_calls.append(s) or 0,
    )

    assert result.exit_code == 0
    assert result.status == "healthy"
    assert result.flatten_invoked is False
    assert flatten_calls == []
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state["status"] == "healthy"
    assert state["heartbeat_age_seconds"] == 30.0
    assert not (settings.testnet_root / RUN_ID / "logs" / "alerts.log").exists()


def test_watchdog_stale_heartbeat_alerts_and_invokes_flatten(tmp_path):
    now = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    settings = _settings(tmp_path)
    _write_heartbeat(
        settings.testnet_root,
        ts="2026-05-18T12:58:00.000Z",
    )
    flatten_calls = []

    result = check_once(
        settings,
        clock=lambda: now,
        flatten_invoker=lambda s: flatten_calls.append(s) or 0,
    )

    assert result.exit_code == 4
    assert result.status == "heartbeat_stale"
    assert result.flatten_invoked is True
    assert flatten_calls == [settings]
    alerts = [
        json.loads(line)
        for line in (
            settings.testnet_root / RUN_ID / "logs" / "alerts.log"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert alerts[0]["msg"] == "heartbeat_lost"
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["context"]["heartbeat_age_seconds"] == 120.0
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state["flatten_invoked"] is True
    assert state["exit_code"] == 4


def test_watchdog_missing_heartbeat_maps_failed_flatten_to_exit_5(tmp_path):
    settings = _settings(tmp_path)

    result = check_once(
        settings,
        clock=lambda: datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC),
        flatten_invoker=lambda s: 1,
    )

    assert result.exit_code == 5
    assert result.status == "heartbeat_missing"
    assert result.last_heartbeat_at is None
    assert result.heartbeat_age_seconds is None


def test_watchdog_cli_dispatches_once(tmp_path, capsys):
    now = datetime(2026, 5, 18, 13, 0, 0, tzinfo=UTC)
    root = tmp_path / "data" / "testnet"
    state_path = tmp_path / "infra" / "watchdog" / "state.json"
    _write_heartbeat(root, ts="2026-05-18T12:58:00.000Z")
    flatten_calls = []

    rc = main(
        [
            "--active-run-id",
            RUN_ID,
            "--instrument-id",
            "BTCUSDT.BINANCE",
            "--testnet-root",
            str(root),
            "--state-path",
            str(state_path),
            "--heartbeat-timeout-seconds",
            "90",
        ],
        clock=lambda: now,
        flatten_invoker=lambda s: flatten_calls.append(s) or 0,
    )

    assert rc == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "heartbeat_stale"
    assert Path(payload["state_path"]).is_file()
    assert len(flatten_calls) == 1


def test_watchdog_source_does_not_read_testnet_credentials():
    source = inspect.getsource(watchdog)

    assert "BINANCE_TESTNET_API_KEY" not in source
    assert "BINANCE_TESTNET_API_SECRET" not in source

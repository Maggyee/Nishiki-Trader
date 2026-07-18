from __future__ import annotations

import json

import pytest

from apps.ops.research_v5_collector_status import (
    _ssh_runner,
    build_collector_status,
    parse_latest_daily_report,
)


def _incomplete_report() -> dict:
    return {
        "schema_version": "research.v5.daily_collection.v1",
        "data_date": "2026-07-17",
        "complete": False,
        "valid_snapshot_count": 0,
        "failed_snapshot_count": 4,
        "vintage_conflict_count": 0,
        "signals_generated": False,
        "pnl_computed": False,
        "snapshots": [],
        "failures": [
            {
                "kind": kind,
                "asset": asset,
                "error": f"{kind} archive request failed: HTTP Error 404: Not Found",
                "snapshot_written": False,
                "desired_state": "flat",
            }
            for kind in ("delivery_curve", "bvol")
            for asset in ("BTCUSDT", "ETHUSDT")
        ],
    }


def test_parse_latest_daily_report_ignores_noise_and_uses_last_report() -> None:
    older = {**_incomplete_report(), "data_date": "2026-07-16"}
    latest = _incomplete_report()
    journal = "container created\n" + json.dumps(older, indent=2)
    journal += "\nunrelated {not json}\n" + json.dumps(latest, indent=2)

    assert parse_latest_daily_report(journal) == latest


def test_incomplete_archive_batch_is_attention_and_awaits_retry() -> None:
    report = build_collector_status(
        observed_at_ns=1_774_070_400_000_000_000,
        source={
            "service_unit": "collector.service",
            "timer_unit": "collector.timer",
            "data_root": "/data/research-v5",
            "checkout": "/opt/trader",
            "image": "collector:sha",
        },
        service={
            "active": "failed",
            "result": "exit-code",
            "exit_status": 2,
            "started_at": "Sat 2026-07-18 04:15:00 UTC",
            "finished_at": "Sat 2026-07-18 04:15:03 UTC",
        },
        timer={
            "active": "active",
            "enabled": "enabled",
            "last_trigger_at": "Sat 2026-07-18 04:15:00 UTC",
            "next_trigger_at": "Sat 2026-07-18 08:15:00 UTC",
        },
        deployment={
            "git_commit": "a" * 40,
            "checkout_clean": True,
            "image_id": "sha256:image",
            "image_revision": "a" * 40,
        },
        storage={
            "snapshot_count": 4,
            "normalized_parquet_count": 4,
            "vintage_conflict_count": 0,
            "comparison_marker_count": 0,
        },
        daily_report=_incomplete_report(),
    )

    assert report["state"] == "attention"
    assert report["next_action"] == "await_scheduled_retry"
    assert report["blockers"] == ["last_batch_incomplete"]
    assert report["gates"]["timer_ready"] is True
    assert report["gates"]["deployment_identity_match"] is True
    assert report["gates"]["no_vintage_conflicts"] is True
    assert report["last_run"]["failed_snapshot_count"] == 4
    assert report["last_run"]["failure_types"] == [
        {"type": "http_404_not_published", "count": 4}
    ]
    assert [row["status"] for row in report["last_run"]["streams"]] == [
        "failed",
        "failed",
        "failed",
        "failed",
    ]
    assert report["last_run"]["signals_generated"] is False
    assert report["last_run"]["pnl_computed"] is False
    assert report["boundaries"]["touches_live_path"] is False
    json.dumps(report, allow_nan=False)


def test_identity_mismatch_is_a_breach() -> None:
    report = build_collector_status(
        observed_at_ns=1,
        source={},
        service={},
        timer={"active": "active", "enabled": "enabled"},
        deployment={
            "git_commit": "a" * 40,
            "checkout_clean": True,
            "image_revision": "b" * 40,
        },
        storage={
            "vintage_conflict_count": 0,
            "comparison_marker_count": 0,
        },
        daily_report=_incomplete_report(),
    )

    assert report["state"] == "breach"
    assert "deployment_identity_mismatch" in report["blockers"]


def test_complete_flag_cannot_hide_missing_stream_evidence() -> None:
    daily = _incomplete_report()
    daily["complete"] = True
    daily["failures"] = daily["failures"][:-1]
    report = build_collector_status(
        observed_at_ns=1,
        source={},
        service={},
        timer={"active": "active", "enabled": "enabled", "next_trigger_at": "next"},
        deployment={
            "git_commit": "a" * 40,
            "checkout_clean": True,
            "image_revision": "a" * 40,
        },
        storage={
            "vintage_conflict_count": 0,
            "comparison_marker_count": 0,
        },
        daily_report=daily,
    )

    assert report["state"] == "attention"
    assert "expected_stream_count_mismatch" in report["blockers"]
    assert report["gates"]["expected_stream_count"] is False
    assert report["next_action"] == "await_scheduled_retry"


def test_complete_batch_with_disabled_timer_needs_attention() -> None:
    daily = _incomplete_report()
    daily["complete"] = True
    daily["snapshots"] = [
        {"kind": kind, "asset": asset, "valid": True}
        for kind in ("delivery_curve", "bvol")
        for asset in ("BTCUSDT", "ETHUSDT")
    ]
    daily["failures"] = []
    report = build_collector_status(
        observed_at_ns=1,
        source={},
        service={},
        timer={"active": "inactive", "enabled": "disabled"},
        deployment={
            "git_commit": "a" * 40,
            "checkout_clean": True,
            "image_revision": "a" * 40,
        },
        storage={
            "vintage_conflict_count": 0,
            "comparison_marker_count": 0,
        },
        daily_report=daily,
    )

    assert report["state"] == "attention"
    assert report["next_action"] == "review_timer_state"
    assert "timer_not_ready" in report["blockers"]


def test_ssh_runner_quotes_remote_read_only_command() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str]) -> tuple[int, str, str]:
        calls.append(command)
        return 0, "ok", ""

    remote = _ssh_runner("oracle", runner)

    assert remote(["find", "/var/lib/research v5", "-name", "*.parquet"]) == (
        0,
        "ok",
        "",
    )
    assert calls == [
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "oracle",
            "find '/var/lib/research v5' -name '*.parquet'",
        ]
    ]


def test_ssh_runner_rejects_shell_syntax_in_host() -> None:
    with pytest.raises(ValueError, match="plain SSH host"):
        _ssh_runner("oracle;touch-bad", lambda _command: (0, "", ""))

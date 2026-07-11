from __future__ import annotations

import fcntl
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import apps.ops.research_v2_daily as daily_module
from apps.ops.research_v2_daily import preflight, review_only, run_daily
from apps.ops.research_v2_snapshot import collect_snapshot
from tests.ops.test_research_v2_snapshot import _basis_payloads, _bytes, _option_payload

GIT_SHA = "a" * 40
START = datetime(2026, 7, 11, 3, 15, tzinfo=UTC)


def _basis_fetch(url: str) -> bytes:
    payloads = _basis_payloads()
    if "exchangeInfo" in url:
        return payloads["exchangeInfo"]
    if "NEXT_QUARTER" in url:
        return payloads["NEXT_QUARTER"]
    return payloads["CURRENT_QUARTER"]


class FakeCollector:
    def __init__(self, fail_basis_once: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_basis_once = fail_basis_once

    def __call__(self, kind: str, *, output_dir: Path, now: datetime):
        self.calls.append(kind)
        if kind == "basis" and self.fail_basis_once:
            self.fail_basis_once = False
            raise urllib.error.URLError("temporary provider failure")
        fetch = (lambda _: _bytes(_option_payload())) if kind == "options" else _basis_fetch
        return collect_snapshot(kind, output_dir=output_dir, now=now, fetch=fetch)


def test_first_pair_and_same_day_retry_are_idempotent(tmp_path: Path) -> None:
    collector = FakeCollector()

    first = run_daily(tmp_path, GIT_SHA, now=START, collector=collector)
    second = run_daily(tmp_path, GIT_SHA, now=START + timedelta(hours=3), collector=collector)

    assert first["status"] == "pair_collected"
    assert first["paired_day_count"] == 1
    assert second["status"] == "already_collected_today"
    assert second["network_accessed"] is False
    assert collector.calls == ["options", "basis"]
    assert len((tmp_path / "qualification-ledger.jsonl").read_text().splitlines()) == 2


def test_partial_pair_retries_only_missing_kind(tmp_path: Path) -> None:
    collector = FakeCollector(fail_basis_once=True)

    with pytest.raises(urllib.error.URLError):
        run_daily(tmp_path, GIT_SHA, now=START, collector=collector)
    result = run_daily(tmp_path, GIT_SHA, now=START + timedelta(hours=3), collector=collector)

    assert result["status"] == "pair_collected"
    assert result["fetched_kinds"] == ["basis"]
    assert collector.calls == ["options", "basis", "basis"]


def test_prepared_transaction_recovers_after_first_ledger_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = FakeCollector()
    original_append = daily_module._append_jsonl
    failed = False

    def append_then_crash(path: Path, value) -> None:
        nonlocal failed
        original_append(path, value)
        if path.name == "qualification-ledger.jsonl" and not failed:
            failed = True
            raise OSError("simulated crash after first ledger append")

    monkeypatch.setattr(daily_module, "_append_jsonl", append_then_crash)
    with pytest.raises(OSError, match="simulated crash"):
        run_daily(tmp_path, GIT_SHA, now=START, collector=collector)
    monkeypatch.setattr(daily_module, "_append_jsonl", original_append)

    recovered = run_daily(tmp_path, GIT_SHA, now=START + timedelta(hours=1), collector=collector)

    assert recovered["status"] == "already_collected_today"
    assert recovered["paired_day_count"] == 1
    assert collector.calls == ["options", "basis"]
    assert len((tmp_path / "qualification-ledger.jsonl").read_text().splitlines()) == 2


def test_operational_gap_starts_new_attempt_without_deleting_evidence(tmp_path: Path) -> None:
    collector = FakeCollector()
    first = run_daily(tmp_path, GIT_SHA, now=START, collector=collector)

    restarted = run_daily(tmp_path, GIT_SHA, now=START + timedelta(days=2), collector=collector)

    assert restarted["attempt_id"] != first["attempt_id"]
    assert restarted["paired_day_count"] == 1
    assert len((tmp_path / "qualification-ledger.jsonl").read_text().splitlines()) == 4
    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text().splitlines()]
    assert any(row.get("reason") == "failed_operational_gap" for row in attempts)


def test_partial_unpaired_day_is_closed_as_an_operational_gap(tmp_path: Path) -> None:
    collector = FakeCollector(fail_basis_once=True)
    with pytest.raises(urllib.error.URLError):
        run_daily(tmp_path, GIT_SHA, now=START, collector=collector)

    result = run_daily(tmp_path, GIT_SHA, now=START + timedelta(days=1), collector=collector)

    assert result["paired_day_count"] == 1
    assert result["attempt_id"].startswith("attempt-20260712-")
    assert (tmp_path / "pending" / "2026-07-11").exists()


def test_seventh_consecutive_pair_writes_complete_and_eighth_run_fetches_nothing(
    tmp_path: Path,
) -> None:
    collector = FakeCollector()
    result = None
    for offset in range(7):
        result = run_daily(
            tmp_path,
            GIT_SHA,
            now=START + timedelta(days=offset),
            collector=collector,
        )

    assert result is not None
    assert result["status"] == "collection_complete"
    assert result["paired_day_count"] == 7
    assert (tmp_path / "COMPLETE").exists()
    calls = list(collector.calls)
    stopped = run_daily(
        tmp_path,
        GIT_SHA,
        now=START + timedelta(days=7),
        collector=collector,
    )
    assert stopped["status"] == "already_complete"
    assert collector.calls == calls


def test_preflight_and_review_only_do_not_write_or_fetch(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    result = preflight(missing, GIT_SHA)
    assert result["data_written"] is False
    assert not missing.exists()

    collector = FakeCollector()
    run_daily(tmp_path, GIT_SHA, now=START, collector=collector)
    before = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    reviewed = review_only(tmp_path, GIT_SHA)
    after = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    assert reviewed["network_accessed"] is False
    assert before == after


def test_tampering_and_image_sha_drift_fail_closed(tmp_path: Path) -> None:
    collector = FakeCollector()
    run_daily(tmp_path, GIT_SHA, now=START, collector=collector)
    snapshot = next((tmp_path / "raw").glob("options-*.json"))
    payload = json.loads(snapshot.read_text())
    payload["audit"]["row_count"] += 1
    snapshot.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="audit summary"):
        run_daily(tmp_path, GIT_SHA, now=START + timedelta(hours=3), collector=collector)
    with pytest.raises(ValueError, match="git SHA"):
        preflight(tmp_path, "b" * 40)


def test_lock_contention_is_a_hard_blocker(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    with (tmp_path / ".collector.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="holds the data-directory lock"):
            run_daily(tmp_path, GIT_SHA, now=START, collector=FakeCollector())


def test_git_sha_must_be_exact_lowercase_commit() -> None:
    with pytest.raises(ValueError, match="40 lowercase"):
        preflight(Path("unused"), "ABC")


def test_cloud_deployment_is_nonroot_readonly_and_stops_after_complete() -> None:
    dockerfile = Path("infra/research-v2/Dockerfile").read_text()
    compose = Path("infra/research-v2/compose.yml").read_text()
    service = Path(
        "infra/research-v2/systemd/nishiki-research-v2-collector.service"
    ).read_text()
    timer = Path("infra/research-v2/systemd/nishiki-research-v2-collector.timer").read_text()

    assert "USER 1002:1002" in dockerfile
    assert 'user: "${COLLECTOR_UID:-1002}:${COLLECTOR_GID:-1002}"' in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "ports:" not in compose
    assert "docker.sock" not in compose
    assert "ExecCondition=/usr/bin/test ! -f" in service
    assert timer.count("OnCalendar=") == 3
    assert "Persistent=true" in timer

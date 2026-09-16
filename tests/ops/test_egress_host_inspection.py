"""Read-only inspection failures must remain visible and cannot grant admission."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/inspect_host.py"


@pytest.fixture
def inspector():
    spec = importlib.util.spec_from_file_location("egress_inspection_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def local_reads(inspector, monkeypatch):
    calls = []

    def capture(argv):
        calls.append(argv)
        if "ruleset" in argv:
            value = {"nftables": [{"chain": {"hook": "output"}}, {"flowtable": {}}]}
        elif "address" in argv:
            value = [{"ifname": "private-host-interface"}]
        elif "route" in argv:
            value = [{"dst": "default"}]
        else:
            value = []
        return {"status": "ok", "stdout": json.dumps(value)}

    monkeypatch.setattr(inspector, "capture", capture)
    return calls


def test_successful_reads_are_only_a_snapshot(inspector, local_reads, tmp_path):
    tmp_path.chmod(0o700)
    result = inspector.collect(nft_via_sudo=True, storage_root=tmp_path)
    assert len(local_reads) == 7
    assert local_reads[-1] == (inspector.SUDO, "-n", inspector.NFT, "-j", "list", "ruleset")
    assert result["summary"]["default_route_counts"] == {"ipv4": 1, "ipv6": 1}
    assert result["summary"]["nft_base_chain_count"] == 1
    assert result["summary"]["nft_flowtable_count"] == 1
    assert result["storage"]["status"] == "private_directory_observed"
    assert result["storage"]["qualified"] is False
    assert result["network_admitted"] is False
    assert result["public_source_verified"] is False
    assert result["continuous_coverage_verified"] is False
    assert len(result["blockers"]) == 5


@pytest.mark.parametrize(
    "status,raw",
    [
        ("command_failed", ""),
        ("timeout", ""),
        ("unavailable", ""),
        ("ok", "bad-json"),
        ("ok", "{}"),
        ("ok", '["not-an-object"]'),
    ],
)
def test_missing_reads_do_not_become_zero_usage(inspector, monkeypatch, status, raw):
    monkeypatch.setattr(inspector, "capture", lambda argv: {"status": status, "stdout": raw})
    result = inspector.collect()
    assert "local_read_incomplete:routes_v4" in result["blockers"]
    assert result["summary"]["default_route_counts"]["ipv4"] is None
    assert result["summary"]["nft_base_chain_count"] is None
    assert result["network_admitted"] is False


def test_changed_namespace_is_reported(inspector, local_reads, monkeypatch):
    monkeypatch.setattr(inspector.os, "readlink", Mock(side_effect=["net:a", "net:b"]))
    assert "network_namespace_changed_during_snapshot" in inspector.collect()["blockers"]


@pytest.mark.parametrize("kind", ["missing", "symlink", "ancestor_symlink", "mode", "file"])
def test_storage_observation_never_creates_or_qualifies_root(inspector, tmp_path, kind):
    path = tmp_path / "selected"
    if kind in {"symlink", "ancestor_symlink"}:
        path.symlink_to(tmp_path, target_is_directory=True)
        if kind == "ancestor_symlink":
            path = path / "child"
    elif kind == "mode":
        path.mkdir(mode=0o755)
    elif kind == "file":
        path.write_text("original")
    result = inspector.storage_snapshot(path)
    assert result["qualified"] is False
    assert result["status"] != "private_directory_observed"
    if kind == "missing":
        assert not path.exists()


def test_mutation_command_refused_before_process(inspector, monkeypatch):
    runner = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(inspector.subprocess, "run", runner)
    with pytest.raises(ValueError, match="allowlist"):
        inspector.capture((inspector.NFT, "flush", "ruleset"))
    runner.assert_not_called()


@pytest.mark.parametrize("mode", ["ok", "timeout", "large", "encoding", "failed"])
def test_capture_preserves_bytes_and_failures(inspector, monkeypatch, mode):
    def run(argv, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["env"] == inspector.ENV
        assert kwargs["timeout"] == 5
        assert "shell" not in kwargs
        raw = b"[]\n"
        if mode == "large":
            raw = b"x" * (inspector.LIMIT + 1)
        elif mode == "encoding":
            raw = b"\xff"
        kwargs["stdout"].write(raw)
        if mode == "timeout":
            raise subprocess.TimeoutExpired(argv, 5)
        return subprocess.CompletedProcess(argv, 1 if mode == "failed" else 0)

    monkeypatch.setattr(inspector.subprocess, "run", run)
    row = inspector.capture(inspector.COMMANDS["links"])
    assert (
        row["status"]
        == {
            "ok": "ok",
            "timeout": "timeout",
            "large": "output_limit",
            "encoding": "invalid_encoding",
            "failed": "command_failed",
        }[mode]
    )
    if mode in {"large", "encoding"}:
        assert row["stdout"] is None
        assert row["stdout_sha256"] is None
    else:
        assert row["stdout_sha256"] == hashlib.sha256(b"[]\n").hexdigest()


def test_cli_private_output_and_sanitized_summary(inspector, local_reads, tmp_path, capsys):
    path = tmp_path / "report.json"
    assert inspector.main(["--report", str(path)]) == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    result = json.loads(path.read_bytes())
    printed = capsys.readouterr().out
    assert "private-host-interface" not in printed
    assert json.loads(printed)["report_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["venue_requests_made"] == 0


@pytest.mark.parametrize("symlink", [False, True])
def test_existing_output_refused_before_reads(inspector, monkeypatch, tmp_path, symlink):
    original = tmp_path / "original"
    original.write_bytes(b"keep")
    path = tmp_path / "link" if symlink else original
    if symlink:
        path.symlink_to(original)
    collector = Mock(side_effect=AssertionError("no collection"))
    monkeypatch.setattr(inspector, "collect", collector)
    assert inspector.main(["--report", str(path)]) == 1
    assert original.read_bytes() == b"keep"
    collector.assert_not_called()


def test_invalid_storage_argument_does_not_create_report(inspector, tmp_path):
    report = tmp_path / "report"
    with pytest.raises(SystemExit):
        inspector.main(["--report", str(report), "--storage-root", "relative"])
    assert not report.exists()


def test_storage_owner_mismatch(inspector, monkeypatch, tmp_path):
    monkeypatch.setattr(inspector.os, "getuid", lambda: os.stat(tmp_path).st_uid + 1)
    assert inspector.storage_snapshot(tmp_path)["status"] == "owner_or_mode_mismatch"

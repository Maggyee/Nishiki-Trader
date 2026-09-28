"""The activation probe must refuse an unprotected or non-isolated entry."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/gateway_window_isolated_probe.py"


@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("joint_isolated_probe_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checkout_probe_does_not_spawn_unshare_or_write_nft(probe, monkeypatch, capsys):
    runner = Mock(side_effect=AssertionError("unprotected checkout reached a subprocess"))
    monkeypatch.setattr(probe.subprocess, "run", runner)
    assert probe.main(["--probe", "--base-sha256", "a" * 64, "--joint-sha256", "b" * 64]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "joint_protected_isolated_probe_refused",
        "network_admitted": False,
    }
    runner.assert_not_called()


def test_inner_must_be_private_pid_one_before_any_nft_read(probe, monkeypatch):
    monkeypatch.setattr(probe.os, "getpid", lambda: 79)
    startup = Mock(side_effect=AssertionError("non-private child loaded installed code"))
    monkeypatch.setattr(probe, "_startup", startup)
    with pytest.raises(ValueError, match="private_pid"):
        probe._inner("a" * 64, "b" * 64)
    startup.assert_not_called()


def test_nonfixed_cli_refuses_before_private_process(probe, monkeypatch, capsys):
    runner = Mock(side_effect=AssertionError("invalid CLI spawned a process"))
    monkeypatch.setattr(probe.subprocess, "run", runner)
    assert probe.main(["--probe", "--duration-ms", "425000"]) == 2
    assert json.loads(capsys.readouterr().out)["network_admitted"] is False
    runner.assert_not_called()

"""A persistent private kernel deny must survive owner exit and lease expiry."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2] / "infra/egress-guard/gateway_window_failclosed_selftest.py"
)


def load():
    spec = importlib.util.spec_from_file_location("window_failclosed_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_owner_exit_and_lease_expiry_keep_host_and_forward_denied(tmp_path, capsys):
    path = tmp_path / "result.json"
    module = load()
    assert module.main(["--report", str(path)]) == 0
    result = json.loads(path.read_bytes())
    output = json.loads(capsys.readouterr().out)
    assert output["report_sha256"] == module.hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["harness_sha256"] == module.hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert result["reachable_before_baseline"] == 4
    assert result["denied_after_owner_exit"] == 4
    assert result["denied_after_expiry"] == 4
    assert result["owner_exited_before_expiry"] is True
    assert result["permanent_rules_unchanged"] is True
    assert result["wan_raw_fallback_drops"] == 2
    assert result["bypass_rules_refused"] is True
    assert result["policy_and_device_drift_refused"] is True
    assert result["network_admitted"] is False
    assert result["host_firewall_modified"] is False


def test_worker_refuses_unisolated_pid_before_nft(monkeypatch):
    module = load()
    monkeypatch.setattr(module.os, "getpid", lambda: 100)
    try:
        module._empty_private_root(module._namespaces())
    except ValueError as exc:
        assert str(exc) == "private_failclosed_new_namespaces_required"
    else:
        raise AssertionError("host namespace accepted")


@pytest.mark.parametrize("family,wrong", [("inet", "ip"), ("netdev", "ipv4")])
def test_blackout_rejects_wrong_family_even_with_two_elements(family, wrong):
    module = load()
    doc = {
        "elem": [
            {"elem": {"val": wrong, "timeout": 3, "expires": 2}},
            {"elem": {"val": "ipv6" if family == "inet" else "ip6", "timeout": 3, "expires": 2}},
        ]
    }
    with pytest.raises(ValueError, match="blackout_elements_invalid"):
        module._blackout_elements(doc, family)

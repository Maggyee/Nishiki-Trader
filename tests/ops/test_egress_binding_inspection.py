"""A local binding match must never become host, caller or network authority."""

import copy
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/inspect_binding.py"


@pytest.fixture
def binding():
    spec = importlib.util.spec_from_file_location("egress_binding_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def local(binding, monkeypatch):
    host = {
        "boot_id": "fixture-boot",
        "namespaces": {"net": "net:host", "user": "user:host", "mnt": "mnt:host"},
    }
    caller = {
        "pid": 42,
        "start_ticks": 111,
        "uids": [1234] * 4,
        "gids": [1234] * 4,
        "groups": [],
        "capabilities": {key: 0 for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")},
        "no_new_privileges": 1,
        "namespaces": {**host["namespaces"], "net": "net:collector"},
        "cgroup_sha256": "fixture-cgroup",
        "executable": {"device": 1, "inode": 2, "size": 3, "mtime_ns": 4},
    }
    parsed = {
        "links": [{"ifname": "eth0", "ifindex": 2}],
        "addresses": [
            {
                "ifname": "eth0",
                "addr_info": [
                    {
                        "family": "inet",
                        "local": "10.0.0.2",
                        "scope": "global",
                        "valid_life_time": 1234,
                    }
                ],
            }
        ],
        "routes_v4": [{"dst": "default", "dev": "eth0", "gateway": "10.0.0.1"}],
        "routes_v6": [{"dst": "default", "dev": "eth0", "expires": 1234}],
        "rules_v4": [{"priority": 0, "table": "local"}],
        "rules_v6": [],
        "nft": {
            "nftables": [
                {"metainfo": {"version": "fixture"}},
                {
                    "rule": {
                        "expr": [{"counter": {"packets": 2, "bytes": 20}}, {"quota": {"bytes": 99}}]
                    }
                },
            ]
        },
    }
    storage = {
        "status": "owner_or_mode_mismatch",
        "qualified": False,
        "components": [
            {
                "path": str(path),
                "uid": 0,
                "gid": 0,
                "mode": "0o700" if path == binding.STORAGE_ROOT else "0o755",
                "device": 1,
                "inode": i,
            }
            for i, path in enumerate(
                (*reversed(binding.STORAGE_ROOT.parents), binding.STORAGE_ROOT)
            )
        ],
    }

    def snapshot(**kwargs):
        assert kwargs["storage_root"] == binding.STORAGE_ROOT
        return {
            "namespace_before": "net:host",
            "namespace_after": "net:host",
            "storage": copy.deepcopy(storage),
            "observations": {
                key: {"status": "ok", "stdout": json.dumps(value)} for key, value in parsed.items()
            },
        }

    monkeypatch.setattr(binding, "host_identity", lambda: copy.deepcopy(host))
    monkeypatch.setattr(binding, "process_identity", lambda pid: copy.deepcopy(caller))
    inspector = SimpleNamespace(COMMANDS=dict.fromkeys(parsed), collect=snapshot)
    return inspector, parsed, storage, host, caller


def collect(binding, local, **kwargs):
    return binding.collect(
        local[0], wan_interface="eth0", source_ipv4="10.0.0.2", collector_pid=42, **kwargs
    )


def compare(binding, current, previous):
    raw = json.dumps(previous).encode()
    return binding.compare(current, raw, hashlib.sha256(raw).hexdigest())


def test_complete_local_binding_is_not_authorization(binding, local):
    result = collect(binding, local)
    assert result["local_binding_complete"] and result["local_blockers"] == []
    comparison = compare(binding, result, result)
    assert comparison["local_binding_matches"]
    assert not comparison["comparison_is_authorization"]
    for key in (
        "public_source_verified",
        "caller_authorized",
        "storage_qualified",
        "host_deployment_qualified",
        "network_admitted",
    ):
        assert result[key] is False
    assert result["venue_requests_made"] == 0
    assert len(result["remaining_requirements"]) == 6


@pytest.mark.parametrize(
    "change",
    [
        "boot",
        "namespace",
        "pid_reuse",
        "executable",
        "route",
        "policy_route",
        "ipv6",
        "new_interface",
        "source",
        "quota",
        "storage_inode",
    ],
)
def test_comparison_detects_binding_drift(binding, local, change):
    before = collect(binding, local)
    _, network, storage, host, caller = local
    if change == "boot":
        host["boot_id"] = "rebooted"
    elif change == "namespace":
        caller["namespaces"]["net"] = "net:replaced"
    elif change == "pid_reuse":
        caller["start_ticks"] += 1
    elif change == "executable":
        caller["executable"]["inode"] += 1
    elif change == "route":
        network["routes_v4"][0]["gateway"] = "10.0.0.99"
    elif change == "policy_route":
        network["rules_v4"].append({"priority": 10, "table": 52})
    elif change == "ipv6":
        network["routes_v6"][0]["dev"] = "tunnel0"
    elif change == "new_interface":
        network["links"].append({"ifname": "tunnel0", "ifindex": 3})
    elif change == "source":
        network["addresses"][0]["addr_info"][0]["local"] = "10.0.0.3"
    elif change == "quota":
        network["nft"]["nftables"][1]["rule"]["expr"][1]["quota"]["bytes"] += 1
    else:
        storage["components"][-1]["inode"] += 1
    result = compare(binding, collect(binding, local), before)
    assert not result["local_binding_matches"]
    assert result["changed_fields"]


def test_observation_counters_and_lifetimes_do_not_hide_policy(binding, local):
    before = collect(binding, local)
    network = local[1]
    network["nft"]["nftables"][1]["rule"]["expr"][0]["counter"]["bytes"] += 20
    network["nft"]["nftables"][1]["rule"]["expr"][0]["counter"]["packets"] += 2
    network["routes_v6"][0]["expires"] -= 1
    network["addresses"][0]["addr_info"][0]["valid_life_time"] -= 1
    assert compare(binding, collect(binding, local), before)["local_binding_matches"]


@pytest.mark.parametrize(
    "change", ["missing", "symlink", "ancestor_owner", "ancestor_write", "root_mode"]
)
def test_fixed_storage_requires_root_authority_for_every_component(binding, local, change):
    storage = local[2]
    if change == "missing":
        storage["components"].pop()
    elif change == "symlink":
        storage["status"] = "non_directory_or_symlink"
    elif change == "ancestor_owner":
        storage["components"][1]["uid"] = 1234
    elif change == "ancestor_write":
        storage["components"][1]["mode"] = "0o777"
    else:
        storage["components"][-1]["mode"] = "0o755"
    result = collect(binding, local)
    assert "fixed_root_owned_private_storage_missing" in result["local_blockers"]
    assert not compare(binding, result, result)["local_binding_matches"]


@pytest.mark.parametrize("change", ["root", "caps", "setuid", "privileges", "host_net"])
def test_collector_privilege_or_namespace_gaps_remain_blocked(binding, local, change):
    caller = local[4]
    if change == "root":
        caller["uids"] = [0] * 4
    elif change == "caps":
        caller["capabilities"]["CapBnd"] = 1
    elif change == "setuid":
        caller["uids"][2] = 0
    elif change == "privileges":
        caller["no_new_privileges"] = 0
    else:
        caller["namespaces"]["net"] = local[3]["namespaces"]["net"]
    assert not collect(binding, local)["local_binding_complete"]


def test_changed_process_during_snapshot_refuses_binding(binding, local, monkeypatch):
    first = copy.deepcopy(local[4])
    second = copy.deepcopy(first)
    second["start_ticks"] += 1
    monkeypatch.setattr(binding, "process_identity", Mock(side_effect=[first, second]))
    assert "collector_identity_unavailable_or_changed" in collect(binding, local)["local_blockers"]


def test_missing_process_is_explicit_and_not_authorized(binding, local, monkeypatch):
    monkeypatch.setattr(binding, "process_identity", Mock(side_effect=ProcessLookupError))
    result = collect(binding, local)
    assert result["binding"]["collector"] is None
    assert not result["local_binding_complete"]


def test_missing_read_does_not_become_empty_policy(binding, local):
    native = local[0].collect

    def read(**kwargs):
        result = native(**kwargs)
        result["observations"]["nft"] = {"status": "unavailable"}
        return result

    local[0].collect = read
    result = collect(binding, local)
    assert "local_read_incomplete:nft" in result["local_blockers"]
    assert "nft" not in result["binding"]["network"]
    assert not compare(binding, result, result)["local_binding_matches"]


def test_real_process_metadata_stable_without_arguments_or_environment(binding):
    first = binding.process_identity(os.getpid())
    assert first == binding.process_identity(os.getpid())
    assert first["start_ticks"] > 0
    assert first["uids"][0] == os.getuid()
    assert set(first["namespaces"]) == {"net", "user", "mnt"}
    assert "argv" not in first and "environment" not in first


def test_selected_original_hash_and_internal_binding_hash_required(binding, local):
    result = collect(binding, local)
    with pytest.raises(ValueError, match="snapshot_hash"):
        binding.compare(result, json.dumps(result).encode(), "0" * 64)
    before = copy.deepcopy(result)
    before["binding"]["host"]["boot_id"] = "tampered"
    with pytest.raises(ValueError, match="invalid_previous_binding"):
        compare(binding, result, before)


def test_cli_private_output_no_success_exit_or_replacement(
    binding, local, monkeypatch, tmp_path, capsys
):
    report = collect(binding, local)
    reader = Mock(return_value=report)
    monkeypatch.setattr(binding, "collect", reader)
    output = tmp_path / "report.json"
    args = ["--wan-interface", "eth0", "--source-ipv4", "10.0.0.2", "--report", str(output)]
    assert binding.main(args) == 2
    raw = output.read_bytes()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    printed = capsys.readouterr().out
    assert "10.0.0.2" not in printed and "fixture-boot" not in printed
    assert json.loads(printed)["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert binding.main(args) == 1
    assert output.read_bytes() == raw and reader.call_count == 1


@pytest.mark.parametrize(
    "args", [["--source-ipv4", "::1"], ["--collector-pid", "0"], ["--compare-sha256", "0" * 64]]
)
def test_cli_invalid_selection_fails_before_collection(binding, monkeypatch, tmp_path, args):
    reader = Mock(side_effect=AssertionError("must not collect"))
    monkeypatch.setattr(binding, "collect", reader)
    output = tmp_path / "report"
    assert (
        binding.main(
            ["--wan-interface", "eth0", "--source-ipv4", "10.0.0.2", "--report", str(output), *args]
        )
        == 1
    )
    assert not output.exists()
    reader.assert_not_called()


@pytest.mark.parametrize("kind", ["hash", "json_shape", "symlink", "fifo"])
def test_cli_invalid_previous_report_precedes_local_reads(binding, monkeypatch, tmp_path, kind):
    prior = tmp_path / "prior"
    raw = b"[]"
    digest = hashlib.sha256(raw).hexdigest()
    if kind == "symlink":
        original = tmp_path / "original"
        original.write_bytes(raw)
        prior.symlink_to(original)
    elif kind == "fifo":
        os.mkfifo(prior)
    else:
        prior.write_bytes(raw)
        if kind == "hash":
            digest = "0" * 64
    reader = Mock(side_effect=AssertionError("must not collect"))
    monkeypatch.setattr(binding, "collect", reader)
    output = tmp_path / "report"
    assert (
        binding.main(
            [
                "--wan-interface",
                "eth0",
                "--source-ipv4",
                "10.0.0.2",
                "--compare",
                str(prior),
                "--compare-sha256",
                digest,
                "--report",
                str(output),
            ]
        )
        == 1
    )
    assert not output.exists()
    reader.assert_not_called()


def test_cli_compares_pinned_report_but_never_admits(binding, local, monkeypatch, tmp_path, capsys):
    report = collect(binding, local)
    monkeypatch.setattr(binding, "collect", Mock(return_value=copy.deepcopy(report)))
    prior = tmp_path / "prior"
    raw = json.dumps(report).encode()
    prior.write_bytes(raw)
    output = tmp_path / "report"
    assert (
        binding.main(
            [
                "--wan-interface",
                "eth0",
                "--source-ipv4",
                "10.0.0.2",
                "--compare",
                str(prior),
                "--compare-sha256",
                hashlib.sha256(raw).hexdigest(),
                "--report",
                str(output),
            ]
        )
        == 2
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["comparison"]["local_binding_matches"]
    assert not summary["network_admitted"]
    assert prior.read_bytes() == raw

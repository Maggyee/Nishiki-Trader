"""Held local authority fails closed on archive, code, account and route drift."""

import copy
import importlib.util
import json
import os
from pathlib import Path

import pytest

from tests.ops.test_egress_installation import policy as policy
from tests.ops.test_egress_installation import staged as staged

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/authority_binding.py"


@pytest.fixture
def binder():
    spec = importlib.util.spec_from_file_location("authority_binding_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prepared(binder, policy, staged, monkeypatch):
    root = staged[0]

    def write(path, raw, mode=0o600):
        local = root / path.lstrip("/")
        local.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if local.exists():
            local.chmod(0o600)
        local.write_bytes(raw)
        local.chmod(mode)
        return binder.digest(raw)

    source = SOURCE.with_name("inspect_binding.py").read_bytes()
    manifest = root / policy.MANIFEST.lstrip("/")
    value = json.loads(manifest.read_bytes())
    value["files"]["inspect_binding.py"] = write(
        policy.CODE_ROOT + "/inspect_binding.py", source, 0o444
    )
    manifest.write_text(json.dumps(value))
    response_hash = write(binder.SCOPE + "/response.bin", b"x" * (2 * 1024 * 1024))
    events_hash = write(binder.SCOPE + "/events.jsonl", b"fixture consumed archive\n")
    plan = {
        "schema_version": "portfolio.egress_bootstrap_execution.v1",
        "scope": "portfolio.testnet_rest_bootstrap.v1",
        "collector": value["collector"],
        "installation_manifest_sha256": binder.digest(manifest.read_bytes()),
        "wan_interface": "enp0s6",
        "private_ipv4": "10.0.0.136",
        "public_ipv4": "149.118.158.46",
        "destination_ipv4": "192.0.2.1",
        "vnic_mac": "02:00:17:00:5f:ef",
        "source_commit": "fixture",
        "operator_mapping_sha256": "0" * 64,
        "host_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "helper_sha256": write(
            binder.BOOTSTRAP_CODE + "/bootstrap_once.py", b"# fixture runner\n", 0o444
        ),
        "parser_sha256": write(
            binder.BOOTSTRAP_CODE + "/http_parser.py", b"# fixture parser\n", 0o444
        ),
        "ca_sha256": write("/etc/ssl/certs/ca-certificates.crt", b"fixture CA", 0o644),
    }
    raw = json.dumps(plan).encode()
    pins = {
        "plan_sha256": write(binder.PLAN, raw),
        "events_sha256": events_hash,
        "response_sha256": response_hash,
    }
    write(binder.SCOPE + "/plan.json", raw)
    observed = {
        "links": [{"ifname": "enp0s6", "address": plan["vnic_mac"]}],
        "selected_route": [{"dev": "enp0s6", "prefsrc": plan["private_ipv4"]}],
        "routes_v4": [],
        "routes_v6": [],
        "rules_v4": [],
        "rules_v6": [],
        "addresses": [{"addr_info": [{"valid_life_time": 100, "preferred_life_time": 100}]}],
        "nft": {"nftables": [{"rule": {"expr": [{"counter": {"packets": 1, "bytes": 100}}]}}]},
    }
    monkeypatch.setattr(binder, "network", lambda plan: copy.deepcopy(observed))
    return root, pins, observed


def open_binding(binder, policy, prepared):
    return binder.AuthorityBinding(policy.TrustedInstallation(), **prepared[1])


def test_stable_local_custody_is_not_source_or_gateway_admission(binder, policy, prepared):
    with_before = len(list(Path("/proc/self/fd").iterdir()))
    binding = open_binding(binder, policy, prepared)
    report = binding.verify()
    assert report["local_root_custody_verified"]
    assert not any(
        report[k]
        for k in [
            "source_signer_authority_qualified",
            "gateway_signer_authority_qualified",
            "complete_gateway_coverage_verified",
            "future_enforcement_verified",
            "network_admitted",
            "trading_admitted",
        ]
    )
    assert len(report["binding"]["files"]) == 7
    assert report["binding_sha256"] == binder.digest(binder.canonical(report["binding"]))
    prepared[2]["nft"]["nftables"][0]["rule"]["expr"][0]["counter"]["packets"] += 100
    prepared[2]["addresses"][0]["addr_info"][0]["valid_life_time"] -= 5
    assert binding.verify()["binding_sha256"] == report["binding_sha256"]
    binding.close()
    assert len(list(Path("/proc/self/fd").iterdir())) == with_before
    with pytest.raises(ValueError):
        binding.verify()
    second = open_binding(binder, policy, prepared)
    try:
        assert second.verify()["binding_sha256"] == report["binding_sha256"]
    finally:
        second.close()


@pytest.mark.parametrize(
    "damage",
    [
        "replacement",
        "bytes",
        "symlink",
        "hardlink",
        "mode",
        "parent",
        "source",
        "ca",
        "account",
        "boot",
        "route",
        "mac",
        "nft",
        "during_network",
    ],
)
def test_observed_drift_permanently_closes_binding(
    binder, policy, prepared, staged, monkeypatch, damage
):
    before = len(list(Path("/proc/self/fd").iterdir()))
    binding = open_binding(binder, policy, prepared)
    response = prepared[0] / (binder.SCOPE + "/response.bin").lstrip("/")
    if damage == "replacement":
        raw = response.read_bytes()
        response.unlink()
        response.write_bytes(raw)
        response.chmod(0o600)
    elif damage == "bytes":
        response.write_bytes(b"changed")
    elif damage == "symlink":
        other = response.with_name("moved")
        response.rename(other)
        response.symlink_to(other)
    elif damage == "hardlink":
        os.link(response, response.with_name("alias"))
    elif damage == "mode":
        response.chmod(0o644)
    elif damage == "parent":
        response.parent.rename(response.parent.with_name("moved"))
    elif damage in ("source", "ca"):
        target = prepared[0] / (
            (binder.BOOTSTRAP_CODE + "/http_parser.py").lstrip("/")
            if damage == "source"
            else "etc/ssl/certs/ca-certificates.crt"
        )
        target.chmod(0o600)
        target.write_bytes(b"changed")
    elif damage == "account":
        staged[1][0].pw_uid += 1
    elif damage == "boot":
        previous = binding.host_reader()
        monkeypatch.setattr(binding, "host_reader", lambda: {**previous, "boot_id": "different"})
    elif damage == "route":
        prepared[2]["selected_route"][0]["prefsrc"] = "10.0.0.137"
    elif damage == "mac":
        prepared[2]["links"][0]["address"] = "02:00:00:00:00:01"
    elif damage == "nft":
        prepared[2]["nft"]["nftables"].append({"chain": {"name": "new"}})
    else:

        def network(plan):
            response.write_bytes(b"changed while observing network")
            return copy.deepcopy(prepared[2])

        monkeypatch.setattr(binder, "network", network)
    with pytest.raises((ValueError, OSError)):
        binding.verify()
    assert binding.closed and binding.authority.closed
    assert len(list(Path("/proc/self/fd").iterdir())) == before
    with pytest.raises(ValueError, match="closed"):
        binding.verify()


@pytest.mark.parametrize(
    "damage",
    [
        "wrong_pin",
        "scope_mode",
        "fifo",
        "wrong_boot",
        "wrong_plan",
        "bad_destination",
        "network_read_failed",
    ],
)
def test_bad_initial_selection_leaks_no_descriptors(binder, policy, prepared, monkeypatch, damage):
    root, pins, _ = prepared
    if damage == "wrong_pin":
        pins["response_sha256"] = "0" * 64
    elif damage == "scope_mode":
        (root / binder.SCOPE.lstrip("/")).chmod(0o755)
    elif damage == "fifo":
        target = root / (binder.SCOPE + "/response.bin").lstrip("/")
        target.unlink()
        os.mkfifo(target, 0o600)
    elif damage == "network_read_failed":

        def fail(plan):
            raise OSError("unavailable")

        monkeypatch.setattr(binder, "network", fail)
    else:
        target = root / binder.PLAN.lstrip("/")
        plan = json.loads(target.read_bytes())
        if damage == "wrong_boot":
            plan["host_boot_id"] = "different"
        elif damage == "wrong_plan":
            plan["collector"]["uid"] += 1
        else:
            plan["destination_ipv4"] = "--help"
        raw = json.dumps(plan).encode()
        target.write_bytes(raw)
        (root / (binder.SCOPE + "/plan.json").lstrip("/")).write_bytes(raw)
        pins["plan_sha256"] = binder.digest(raw)
    before = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises((ValueError, OSError)):
        open_binding(binder, policy, prepared)
    assert len(list(Path("/proc/self/fd").iterdir())) == before

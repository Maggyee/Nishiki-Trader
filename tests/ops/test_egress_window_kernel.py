"""Read-only nft observer: exact local structure and bounded live timers."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/gateway_window_kernel.py"


@pytest.fixture
def observer():
    spec = importlib.util.spec_from_file_location("egress_window_kernel_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table(family):
    values = ("ipv4", "ipv6") if family == "inet" else ("ip", "ip6")
    chains = ("output", "forward") if family == "inet" else ("egress",)
    return {
        "nftables": [
            {"metainfo": {"json_schema_version": 1}},
            {"table": {"family": family, "name": "trader_joint_window_v1", "handle": 1}},
            {
                "set": {
                    "family": family,
                    "table": "trader_joint_window_v1",
                    "name": "blackout",
                    "type": "nf_proto" if family == "inet" else "ether_type",
                    "flags": ["timeout"],
                    "handle": 2,
                    "elem": [{"elem": {"val": v, "timeout": 426, "expires": 425}} for v in values],
                }
            },
            {
                "set": {
                    "family": family,
                    "table": "trader_joint_window_v1",
                    "name": "permits",
                    "type": "ipv4_addr",
                    "flags": ["timeout"],
                    "handle": 3,
                }
            },
            *[
                {
                    "chain": {
                        "family": family,
                        "table": "trader_joint_window_v1",
                        "name": name,
                        "type": "filter",
                        "hook": name,
                        "prio": -310 if family == "inet" else 0,
                        "policy": "accept",
                        "handle": 4 + index,
                        **({"dev": "wan"} if family == "netdev" else {}),
                    }
                }
                for index, name in enumerate(chains)
            ],
            *[
                {
                    "rule": {
                        "family": family,
                        "table": "trader_joint_window_v1",
                        "chain": name,
                        "handle": 8 + index,
                        "expr": [{"counter": {"packets": 0, "bytes": 0}}, {"drop": None}],
                    }
                }
                for index, name in enumerate(chains)
            ],
        ]
    }


@pytest.fixture
def pinned(observer):
    rows = {family: table(family) for family in ("inet", "netdev")}
    pins = {
        family: observer.digest(observer._static(value["nftables"]))
        for family, value in rows.items()
    }
    return rows, pins


CHAIN = """table netdev trader_joint_window_v1 {
    chain egress {
        type filter hook egress device "wan" priority filter; policy accept;
        ether type @blackout counter packets 0 bytes 0 drop
    }
}
"""


def test_two_tables_report_timer_lower_bound_but_no_coverage_promotion(observer, pinned):
    rows, pins = pinned
    ticks = iter([100_000_000_000, 100_000_100_000, 100_000_200_000, 100_000_300_000])
    result = observer.observe(
        expected_static_sha256=pins,
        wan_interface="wan",
        reader=lambda family: rows[family],
        chain_reader=lambda: CHAIN,
        clock=lambda: next(ticks),
    )
    assert result["minimum_blackout_through_monotonic_ns"] == 100_000_100_000 + 425_000_000_000
    assert result["remaining_ns_lower_bound"] > 424_000_000_000
    assert result["status"] == "local_kernel_timers_observed_unqualified"
    assert not result["source_authenticated"] and not result["complete_caller_coverage_verified"]
    assert result["network_admitted"] is False


@pytest.mark.parametrize(
    "damage",
    ["missing_v6", "no_expiry", "permit", "device", "priority", "rule", "extra_row", "wrong_table"],
)
def test_changed_static_or_live_kernel_state_fails_closed(observer, pinned, damage):
    rows, pins = copy.deepcopy(pinned)
    inet, netdev = rows["inet"]["nftables"], rows["netdev"]["nftables"]
    if damage == "missing_v6":
        inet[2]["set"]["elem"].pop()
    elif damage == "no_expiry":
        inet[2]["set"]["elem"][0]["elem"].pop("expires")
    elif damage == "permit":
        netdev[3]["set"]["elem"] = ["203.0.113.10"]
    elif damage == "device":
        netdev[4]["chain"]["dev"] = "other"
    elif damage == "priority":
        inet[4]["chain"]["prio"] = 0
    elif damage == "rule":
        inet[-1]["rule"]["expr"][-1] = {"accept": None}
    elif damage == "extra_row":
        inet.append(
            {"rule": {"family": "inet", "table": observer.TABLE, "chain": "output", "expr": []}}
        )
    else:
        inet[1]["table"]["name"] = "other"
    with pytest.raises(ValueError, match="kernel_window"):
        observer.inspect_table(
            rows["inet"] if damage not in {"permit", "device"} else rows["netdev"],
            "inet" if damage not in {"permit", "device"} else "netdev",
            expected_static_sha256=pins["inet" if damage not in {"permit", "device"} else "netdev"],
            wan_interface="wan",
            chain_text=CHAIN,
        )


def test_netdev_text_device_is_required_even_when_json_digest_matches(observer, pinned):
    rows, pins = pinned
    for text in (
        None,
        CHAIN.replace('device "wan"', 'device "other"'),
        CHAIN.replace('device "wan" ', ""),
    ):
        with pytest.raises(ValueError, match="kernel_window_device"):
            observer.inspect_table(
                rows["netdev"],
                "netdev",
                expected_static_sha256=pins["netdev"],
                wan_interface="wan",
                chain_text=text,
            )


def test_duplicate_json_and_missing_root_refuse_read_before_claim(observer, monkeypatch):
    monkeypatch.setattr(observer.os, "geteuid", lambda: 1000)
    with pytest.raises(ValueError, match="kernel_window_root_and_fixed_family_required"):
        observer.read_table("inet")
    with pytest.raises(ValueError, match="kernel_window_duplicate_json_key"):
        json.loads('{"elem":1,"elem":2}', object_pairs_hook=observer._pairs)


def test_real_nft_json_in_disposable_user_and_network_namespace(observer):
    """No host table is created; unshare grants CAP_NET_ADMIN only inside its namespace."""
    child = r"""
import importlib.util,json,subprocess,sys
from pathlib import Path
source=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location("isolated_probe",source)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
table=module.TABLE
rules=f'''table inet {table} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept; meta nfproto @blackout counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy accept; meta nfproto @blackout counter drop; }}
}}
table netdev {table} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "lo" priority 0; policy accept; ether type @blackout counter drop; }}
}}'''
setup=subprocess.run(['/usr/sbin/nft','-f','-'],input=rules.encode(),capture_output=True)
if setup.returncode:
 raise RuntimeError('nft_setup: '+setup.stderr.decode())
elements=f'''add element inet {table} blackout {{ ipv4 timeout 5000ms, ipv6 timeout 5000ms }}
add element netdev {table} blackout {{ 0x0800 timeout 5000ms, 0x86dd timeout 5000ms }}'''
added=subprocess.run(['/usr/sbin/nft','-f','-'],input=elements.encode(),capture_output=True)
if added.returncode:
 raise RuntimeError('nft_elements: '+added.stderr.decode())
rows={family:module.read_table(family) for family in module.KINDS}
pins={family:module.digest(module._static(value['nftables'])) for family,value in rows.items()}
try:
 result=module.observe(expected_static_sha256=pins,wan_interface='lo')
 print(json.dumps({'status':result['status'],'remaining_ns_lower_bound':result['remaining_ns_lower_bound']}))
except Exception:
 print(json.dumps(rows),file=sys.stderr)
 raise
"""
    result = subprocess.run(
        ["/usr/bin/unshare", "-Urn", sys.executable, "-I", "-c", child, str(SOURCE)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout)
    assert report["status"] == "local_kernel_timers_observed_unqualified"
    assert 0 < report["remaining_ns_lower_bound"] < 5_000_000_000

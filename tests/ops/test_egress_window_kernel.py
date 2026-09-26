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
                        "expr": [
                            {
                                "match": {
                                    "op": "==",
                                    "left": (
                                        {"meta": {"key": "nfproto"}}
                                        if family == "inet"
                                        else {"payload": {"protocol": "ether", "field": "type"}}
                                    ),
                                    "right": "@blackout",
                                }
                            },
                            {"counter": {"packets": 0, "bytes": 0}},
                            {"drop": None},
                        ],
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


def test_inactive_tables_keep_exact_rules_and_empty_sets(observer, pinned):
    rows, pins = copy.deepcopy(pinned)
    for family in ("inet", "netdev"):
        rows[family]["nftables"][2]["set"].pop("elem")
        assert (
            observer.inspect_table(
                rows[family],
                family,
                expected_static_sha256=pins[family],
                wan_interface="wan",
                chain_text=CHAIN,
                expect_inactive=True,
            )
            == {}
        )
    with pytest.raises(ValueError, match="kernel_window_not_inactive"):
        observer.inspect_table(
            pinned[0]["inet"],
            "inet",
            expected_static_sha256=pins["inet"],
            expect_inactive=True,
        )
    rows["inet"]["nftables"][-1]["rule"]["expr"] = [{"accept": None}]
    pin = observer.digest(observer._static(rows["inet"]["nftables"]))
    with pytest.raises(ValueError, match="kernel_window_blackout_drop_or_bypass"):
        observer.inspect_table(
            rows["inet"], "inet", expected_static_sha256=pin, expect_inactive=True
        )


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


def test_exact_loopback_exception_precedes_blackout_without_external_bypass(observer, pinned):
    rows, _ = copy.deepcopy(pinned)
    rules = rows["inet"]["nftables"]
    rules.insert(
        -2,
        {
            "rule": {
                "family": "inet",
                "table": observer.TABLE,
                "chain": "output",
                "expr": [
                    {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "lo"}},
                    {"accept": None},
                ],
            }
        },
    )
    pin = observer.digest(observer._static(rules))
    assert set(observer.inspect_table(rows["inet"], "inet", expected_static_sha256=pin)) == {
        "ipv4",
        "ipv6",
    }


@pytest.mark.parametrize(
    "damage", ["no_drop", "early_accept", "wrong_match", "forward_bypass", "netdev_bypass"]
)
def test_self_pinned_rules_cannot_turn_empty_or_bypassed_blackout_into_evidence(
    observer, pinned, damage
):
    rows, _ = copy.deepcopy(pinned)
    if damage == "no_drop":
        rows["inet"]["nftables"][-1]["rule"]["expr"] = [{"accept": None}]
    elif damage == "early_accept":
        rows["inet"]["nftables"].insert(
            -2,
            {
                "rule": {
                    "family": "inet",
                    "table": observer.TABLE,
                    "chain": "output",
                    "expr": [{"accept": None}],
                }
            },
        )
    elif damage == "wrong_match":
        rows["inet"]["nftables"][-1]["rule"]["expr"][0]["match"]["right"] = "ipv4"
    elif damage == "forward_bypass":
        rows["inet"]["nftables"].insert(
            -1,
            {
                "rule": {
                    "family": "inet",
                    "table": observer.TABLE,
                    "chain": "forward",
                    "expr": [{"accept": None}],
                }
            },
        )
    else:
        rows["netdev"]["nftables"].insert(
            -1,
            {
                "rule": {
                    "family": "netdev",
                    "table": observer.TABLE,
                    "chain": "egress",
                    "expr": [{"accept": None}],
                }
            },
        )
    family = "netdev" if damage == "netdev_bypass" else "inet"
    # The attacker controls the plan digest too; exact semantics must reject it.
    selected = rows[family]
    pin = observer.digest(observer._static(selected["nftables"]))
    with pytest.raises(ValueError, match="kernel_window_blackout"):
        observer.inspect_table(
            selected, family, expected_static_sha256=pin, wan_interface="wan", chain_text=CHAIN
        )


def test_duplicate_json_and_missing_root_refuse_read_before_claim(observer, monkeypatch):
    monkeypatch.setattr(observer.os, "geteuid", lambda: 1000)
    with pytest.raises(ValueError, match="kernel_window_root_and_fixed_family_required"):
        observer.read_table("inet")
    with pytest.raises(ValueError, match="kernel_window_duplicate_json_key"):
        json.loads('{"elem":1,"elem":2}', object_pairs_hook=observer._pairs)


@pytest.mark.parametrize(
    "collector",
    [
        {},
        {"host_link": "wan", "child_ipv4": "169.254.254.2", "source_ipv4": "10.0.0.136"},
        {"host_link": "gw-jc1", "child_ipv4": "169.254.254.2/32", "source_ipv4": "10.0.0.136"},
        {"host_link": "gw-jc1", "child_ipv4": "169.254.254.2", "source_ipv4": "169.254.254.2"},
    ],
)
def test_invalid_collector_selection_fails_before_kernel_read(observer, collector):
    with pytest.raises(ValueError, match="kernel_window"):
        observer.observe(
            expected_static_sha256={"inet": "0" * 64, "netdev": "0" * 64},
            wan_interface="wan",
            collector=collector,
            reader=lambda _: pytest.fail("invalid selection reached kernel read"),
        )


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
 chain output {{ type filter hook output priority -310; policy accept; oifname "lo" accept; meta nfproto @blackout counter drop; }}
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


def test_real_nft_collector_rule_json_probe():
    child = r"""
import copy,importlib.util,json,subprocess,sys
from pathlib import Path
source=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('joint_collector_observer',source)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
name='trader_joint_window_v1'
rules=f'''table inet {name} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept; meta mark 0x6f720002 counter drop; oifname "lo" accept; meta nfproto @blackout counter drop; }}
 chain input {{ type filter hook input priority -310; policy accept; iifname "gw-jc1" counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy accept;
  iifname "gw-jc1" oifname "lo" ip saddr 169.254.254.2 ip daddr @permits tcp dport 443 meta mark set 0x6f720002 accept;
  oifname "gw-jc1" iifname "lo" ip saddr @permits ip daddr 169.254.254.2 tcp sport 443 ct state established accept;
  iifname "gw-jc1" counter drop;
  oifname "gw-jc1" counter drop;
  meta nfproto @blackout counter drop;
 }}
}}
table netdev {name} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "lo" priority 0; policy accept;
  meta mark 0x6f720002 ip saddr 10.0.0.136 ip daddr @permits tcp dport 443 accept;
  meta mark 0x6f720002 counter drop;
  ether type @blackout counter drop;
 }}
}}'''
setup=subprocess.run(['/usr/sbin/nft','-f','-'],input=rules.encode(),capture_output=True)
if setup.returncode: raise RuntimeError(setup.stderr.decode())
elements=f'''add element inet {name} blackout {{ ipv4 timeout 5000ms, ipv6 timeout 5000ms }}
add element netdev {name} blackout {{ 0x0800 timeout 5000ms, 0x86dd timeout 5000ms }}'''
added=subprocess.run(['/usr/sbin/nft','-f','-'],input=elements.encode(),capture_output=True)
if added.returncode: raise RuntimeError(added.stderr.decode())
collector={'host_link':'gw-jc1','child_ipv4':'169.254.254.2','source_ipv4':'10.0.0.136'}
rows={family:module.read_table(family) for family in module.KINDS}
pins={family:module.digest(module._static(value['nftables'])) for family,value in rows.items()}
observed=module.observe(expected_static_sha256=pins,wan_interface='lo',collector=collector)
rejected=[]
for damage in ('host_mark','forward_permit','wan_mark','wan_early_accept','return_source'):
 changed=copy.deepcopy(rows)
 family='netdev' if damage in ('wan_mark','wan_early_accept') else 'inet'
 rules=[item['rule'] for item in changed[family]['nftables'] if 'rule' in item]
 if damage=='host_mark': rules[0]['expr']=[{'accept':None}]
 if damage=='forward_permit': rules[4]['expr'].pop(3)
 if damage=='wan_mark': rules[0]['expr'][0]['match']['right']=0
 if damage=='wan_early_accept': changed[family]['nftables'].insert(-3,{'rule':{'family':family,'table':name,'chain':'egress','expr':[{'accept':None}]}})
 if damage=='return_source': rules[5]['expr'][3]['match']['right']='169.254.254.3'
 pin=module.digest(module._static(changed[family]['nftables']))
 try:
  module.inspect_table(changed[family],family,expected_static_sha256=pin,wan_interface='lo',collector=collector,chain_text=module.read_netdev_chain() if family=='netdev' else None)
 except ValueError: rejected.append(damage)
print(json.dumps({'status':observed['status'],'remaining_ns_lower_bound':observed['remaining_ns_lower_bound'],'network_admitted':observed['network_admitted'],'rejected':rejected}))
"""
    result = subprocess.run(
        ["/usr/bin/unshare", "-Urn", sys.executable, "-I", "-c", child, str(SOURCE)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "local_kernel_timers_observed_unqualified"
    assert 0 < report["remaining_ns_lower_bound"] < 5_000_000_000
    assert report["network_admitted"] is False
    assert report["rejected"] == [
        "host_mark",
        "forward_permit",
        "wan_mark",
        "wan_early_accept",
        "return_source",
    ]

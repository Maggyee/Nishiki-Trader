"""Read-only nft window observation, never a caller-coverage or network permit.

The selected structural digest must come from independently reviewed, protected
root code. A caller-chosen digest or a pair of active sets proves neither the
policy's completeness nor uninterrupted coverage since activation.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time

TABLE = "trader_joint_window_v1"
NFT = "/usr/sbin/nft"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
LIMIT = 1024 * 1024
SECOND = 1_000_000_000
KINDS = {"inet": {"ipv4", "ipv6"}, "netdev": {"ip", "ip6"}}
COLLECTOR_MARK = 0x6F720002


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("kernel_window_duplicate_json_key")
        value[key] = item
    return value


def read_table(family):
    if family not in KINDS or os.geteuid() != 0:
        raise ValueError("kernel_window_root_and_fixed_family_required")
    result = subprocess.run(
        [NFT, "-j", "list", "table", family, TABLE],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=ENV,
        cwd="/",
        timeout=3,
        check=False,
    )
    if result.returncode or not 0 < len(result.stdout) <= LIMIT:
        raise ValueError("kernel_window_read_failed_or_oversized")
    return json.loads(result.stdout, object_pairs_hook=_pairs)


def read_netdev_chain():
    if os.geteuid() != 0:
        raise ValueError("kernel_window_root_required")
    # nft 1.0.2 omits the netdev hook device from its JSON output.
    result = subprocess.run(
        [NFT, "list", "chain", "netdev", TABLE, "egress"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=ENV,
        cwd="/",
        timeout=3,
        check=False,
    )
    if result.returncode or not 0 < len(result.stdout) <= LIMIT:
        raise ValueError("kernel_window_device_read_failed")
    return result.stdout.decode("ascii")


def _check_netdev_device(chain_text, wan_interface):
    if not isinstance(chain_text, str):
        raise ValueError("kernel_window_device_unknown")
    header = re.fullmatch(
        r"type filter hook egress device \"([a-zA-Z0-9_.-]{1,15})\" "
        r"priority (?:filter|0); policy accept;",
        next((line.strip() for line in chain_text.splitlines() if "type filter hook" in line), ""),
    )
    if (
        header is None
        or header.group(1) != wan_interface
        or not chain_text.startswith(f"table netdev {TABLE} {{\n")
        or chain_text.count("type filter hook") != 1
    ):
        raise ValueError("kernel_window_device_changed_or_unknown")


def _static(rows):
    result = []
    for row in rows:
        if "metainfo" in row:
            continue
        entry = json.loads(canonical(row))
        for value in entry.values():
            value.pop("handle", None)
            if "set" in row:
                value.pop("elem", None)
            for expression in value.get("expr", []):
                if "counter" in expression:
                    expression["counter"].pop("packets", None)
                    expression["counter"].pop("bytes", None)
        result.append(entry)
    return result


def _elements(row, family):
    elements = row.get("elem")
    if not isinstance(elements, list) or len(elements) != 2:
        raise ValueError("kernel_window_both_families_required")
    result = {}
    for item in elements:
        if not isinstance(item, dict) or set(item) != {"elem"}:
            raise ValueError("kernel_window_timer_element_required")
        element = item["elem"]
        if not isinstance(element, dict) or set(element) != {"val", "timeout", "expires"}:
            raise ValueError("kernel_window_timer_remaining_unknown")
        key = str(element["val"])
        if key in result or key not in KINDS[family]:
            raise ValueError("kernel_window_family_or_duplicate_element")
        timeout, expires = element["timeout"], element["expires"]
        if type(timeout) is not int or type(expires) is not int or not 0 < expires <= timeout:
            raise ValueError("kernel_window_timer_invalid")
        result[key] = expires
    if set(result) != KINDS[family]:
        raise ValueError("kernel_window_family_set_incomplete")
    return result


def _selected_collector(collector, wan_interface):
    if collector is None:
        return None
    if (
        not isinstance(collector, dict)
        or set(collector) != {"host_link", "child_ipv4", "source_ipv4"}
        or not isinstance(collector["host_link"], str)
        or re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", collector["host_link"]) is None
        or collector["host_link"] in {"lo", wan_interface}
    ):
        raise ValueError("kernel_window_fixed_collector_selection_required")
    for key in ("child_ipv4", "source_ipv4"):
        value = collector[key]
        if not isinstance(value, str):
            raise ValueError("kernel_window_fixed_collector_ipv4_required")
        try:
            address = ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError as exc:
            raise ValueError("kernel_window_fixed_collector_ipv4_required") from exc
        if (
            str(address) != value
            or address.is_multicast
            or address.is_loopback
            or address.is_unspecified
        ):
            raise ValueError("kernel_window_fixed_collector_ipv4_required")
    if collector["child_ipv4"] == collector["source_ipv4"]:
        raise ValueError("kernel_window_distinct_collector_source_required")
    return collector


def _check_blackout_rules(rows, family, *, collector, wan_interface):
    rules = [row["rule"] for row in _static(rows) if "rule" in row]
    expected_chains = (
        ("output", "input", "forward")
        if collector and family == "inet"
        else (("output", "forward") if family == "inet" else ("egress",))
    )

    def match(left, right, op="=="):
        return {"match": {"op": op, "left": left, "right": right}}

    def meta(key, right):
        return match({"meta": {"key": key}}, right)

    def ip(field, right):
        return match({"payload": {"protocol": "ip", "field": field}}, right)

    def tcp(field, right):
        return match({"payload": {"protocol": "tcp", "field": field}}, right)

    counted_drop = [{"counter": {}}, {"drop": None}]
    blackout_match = (
        meta("nfproto", "@blackout")
        if family == "inet"
        else match({"payload": {"protocol": "ether", "field": "type"}}, "@blackout")
    )
    drop = [blackout_match, *counted_drop]
    loopback = [meta("oifname", "lo"), {"accept": None}]
    if collector is None:
        expected = (
            {"output": ([loopback, drop], [drop]), "forward": (drop,)}
            if family == "inet"
            else {"egress": (drop,)}
        )
    elif family == "inet":
        link, child = collector["host_link"], collector["child_ipv4"]
        expected = {
            "output": ([meta("mark", COLLECTOR_MARK), *counted_drop], loopback, drop),
            "input": ([meta("iifname", link), *counted_drop],),
            "forward": (
                [
                    meta("iifname", link),
                    meta("oifname", wan_interface),
                    ip("saddr", child),
                    ip("daddr", "@permits"),
                    tcp("dport", 443),
                    {"mangle": {"key": {"meta": {"key": "mark"}}, "value": COLLECTOR_MARK}},
                    {"accept": None},
                ],
                [
                    meta("oifname", link),
                    meta("iifname", wan_interface),
                    ip("saddr", "@permits"),
                    ip("daddr", child),
                    tcp("sport", 443),
                    match({"ct": {"key": "state"}}, "established", op="in"),
                    {"accept": None},
                ],
                [meta("iifname", link), *counted_drop],
                [meta("oifname", link), *counted_drop],
                drop,
            ),
        }
    else:
        expected = {
            "egress": (
                [
                    meta("mark", COLLECTOR_MARK),
                    ip("saddr", collector["source_ipv4"]),
                    ip("daddr", "@permits"),
                    tcp("dport", 443),
                    {"accept": None},
                ],
                [meta("mark", COLLECTOR_MARK), *counted_drop],
                drop,
            )
        }
    allowed_lengths = (
        {len(expected_chains), len(expected_chains) + (family == "inet")}
        if collector is None
        else {sum(len(expressions) for expressions in expected.values())}
    )
    if len(rules) not in allowed_lengths:
        raise ValueError("kernel_window_blackout_rule_count")
    for name in expected_chains:
        expressions = [rule.get("expr") for rule in rules if rule.get("chain") == name]
        allowed = expected[name]
        if (
            expressions not in allowed
            if name == "output" and collector is None
            else expressions != list(allowed)
        ):
            raise ValueError("kernel_window_blackout_drop_or_bypass")


def inspect_table(
    value, family, *, expected_static_sha256, wan_interface=None, chain_text=None, collector=None
):
    """Check one owned table and retain all four original timer expiries."""
    if (
        family not in KINDS
        or not isinstance(value, dict)
        or set(value) != {"nftables"}
        or not isinstance(value["nftables"], list)
        or not isinstance(expected_static_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", expected_static_sha256) is None
    ):
        raise ValueError("kernel_window_selected_table_required")
    rows = [row for row in value["nftables"] if "metainfo" not in row]
    if not rows or any(not isinstance(row, dict) or len(row) != 1 for row in rows):
        raise ValueError("kernel_window_table_rows_invalid")
    for row in rows:
        entry = next(iter(row.values()))
        if not isinstance(entry, dict) or entry.get("family") != family:
            raise ValueError("kernel_window_foreign_table_row")
        if ("table" in row and entry.get("name") != TABLE) or (
            "table" not in row and entry.get("table") != TABLE
        ):
            raise ValueError("kernel_window_wrong_table")
    tables = [row["table"] for row in rows if "table" in row]
    sets = [row["set"] for row in rows if "set" in row]
    chain_rows = [row["chain"] for row in rows if "chain" in row]
    rule_rows = [row["rule"] for row in rows if "rule" in row]
    chains = {row["name"]: row for row in chain_rows}
    collector = _selected_collector(collector, wan_interface)
    expected_chains = (
        {
            name: (name, -310)
            for name in ("output", "input", "forward")
            if name != "input" or collector
        }
        if family == "inet"
        else {"egress": ("egress", 0)}
    )
    if (
        len(tables) != 1
        or len(sets) != 2
        or len(rows) != len(tables) + len(sets) + len(chain_rows) + len(rule_rows)
        or len(chains) != len(chain_rows)
        or set(chains) != set(expected_chains)
    ):
        raise ValueError("kernel_window_table_structure_changed")
    if set(row["name"] for row in sets) != {"blackout", "permits"}:
        raise ValueError("kernel_window_sets_changed")
    for name, (hook, priority) in expected_chains.items():
        chain = chains[name]
        if (
            chain.get("type") != "filter"
            or chain.get("hook") != hook
            or chain.get("prio") != priority
            or chain.get("policy") != "accept"
            or (family == "netdev" and chain.get("dev", wan_interface) != wan_interface)
        ):
            raise ValueError("kernel_window_hook_or_device_changed")
    if family == "netdev":
        _check_netdev_device(chain_text, wan_interface)
    blackout = next(row for row in sets if row["name"] == "blackout")
    permits = next(row for row in sets if row["name"] == "permits")
    if (
        blackout.get("type") != ("nf_proto" if family == "inet" else "ether_type")
        or set(blackout.get("flags", [])) != {"timeout"}
        or permits.get("type") != "ipv4_addr"
        or set(permits.get("flags", [])) != {"timeout"}
        or permits.get("elem")
    ):
        raise ValueError("kernel_window_set_type_or_early_permission")
    _check_blackout_rules(rows, family, collector=collector, wan_interface=wan_interface)
    if digest(_static(rows)) != expected_static_sha256:
        raise ValueError("kernel_window_static_rules_changed")
    return _elements(blackout, family)


def observe(
    *,
    expected_static_sha256,
    wan_interface,
    collector=None,
    reader=read_table,
    chain_reader=read_netdev_chain,
    clock=time.monotonic_ns,
):
    """Read both live tables; account for read time before reporting expiry."""
    if (
        not isinstance(wan_interface, str)
        or re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", wan_interface) is None
        or not isinstance(expected_static_sha256, dict)
        or set(expected_static_sha256) != set(KINDS)
    ):
        raise ValueError("kernel_window_fixed_selection_required")
    _selected_collector(collector, wan_interface)
    started = clock()
    originals = {}
    for family in KINDS:
        captured_at = clock()
        originals[family] = (
            captured_at,
            inspect_table(
                reader(family),
                family,
                expected_static_sha256=expected_static_sha256[family],
                wan_interface=wan_interface,
                collector=collector,
                chain_text=chain_reader() if family == "netdev" else None,
            ),
        )
    finished = clock()
    if (
        type(started) is not int
        or type(finished) is not int
        or finished < started
        or finished - started > SECOND
    ):
        raise ValueError("kernel_window_observation_clock_or_deadline")
    expiry = min(
        instant + remaining * SECOND
        for instant, elements in originals.values()
        for remaining in elements.values()
    )
    if expiry <= finished:
        raise ValueError("kernel_window_blackout_already_expired")
    return {
        "schema_version": "portfolio.local_kernel_window_observation.v1",
        "status": "local_kernel_timers_observed_unqualified",
        "static_rules_sha256": expected_static_sha256,
        "observed_monotonic_ns": [started, finished],
        "minimum_blackout_through_monotonic_ns": expiry,
        "remaining_ns_lower_bound": expiry - finished,
        "source_authenticated": False,
        "complete_caller_coverage_verified": False,
        "network_admitted": False,
    }

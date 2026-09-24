"""Offline installed handoff pins and planned-operation gap."""

import copy
import json

import pytest

from apps.ops import portfolio_installed_joint_handoff as handoff


@pytest.fixture
def source_report():
    namespace = {"__name__": "test_installed_inventory"}
    path = handoff.GATEWAY / "installed_gateway.py"
    from subprocess import PIPE, run

    def frozen(name):
        path = (
            "apps/strategies_nautilus/" + name
            if name.startswith("portfolio_")
            else "infra/egress-guard/" + name
        )
        return run(
            ["git", "show", handoff.V14_SOURCE_COMMIT + ":" + path],
            cwd=handoff.ROOT,
            stdout=PIPE,
            check=True,
        ).stdout

    exec(compile(frozen("installed_gateway.py"), str(path), "exec"), namespace)
    pins = {name: handoff.digest(frozen(name)) for name in namespace["FILES"]}
    return {
        "source_sha256": pins,
        "gateway_manifest": {"schema_version": namespace["PROFILE"], "files": pins.copy()},
    }


def test_frozen_inventory_matches_pinned_sources(source_report):
    _, sources = handoff.selected_sources(source_report)
    assert len(sources) == len(source_report["source_sha256"])
    assert all(
        handoff.digest(raw) == source_report["source_sha256"][name] for name, raw in sources.items()
    )


@pytest.mark.parametrize("damage", ["source_pin", "extra_source", "missing_source", "profile"])
def test_inventory_refuses_changed_or_unlisted_sources(source_report, damage):
    changed = copy.deepcopy(source_report)
    pins = changed["source_sha256"]
    manifest = changed["gateway_manifest"]
    if damage == "source_pin":
        name = next(iter(pins))
        pins[name] = manifest["files"][name] = "0" * 64
    elif damage == "extra_source":
        pins["extra.py"] = manifest["files"]["extra.py"] = "0" * 64
    elif damage == "missing_source":
        name = next(iter(pins))
        del pins[name]
        del manifest["files"][name]
    else:
        manifest["schema_version"] = "wrong"
    with pytest.raises(ValueError):
        handoff.selected_sources(changed)


def test_two_symbol_gap_matches_full_joint_request_plan():
    plan, installed, expected, ws = handoff.operation_gap(["BNBUSDT", "BTCUSDT"])
    assert plan["rest_get_count"] == 15
    assert sum(installed.values()) == 8
    assert expected - installed == {"time": 3, "account_read": 2, "open_orders": 2}
    assert len(ws) + plan["market_connections"] == 4


def test_unknown_joint_operation_refuses_comparison(monkeypatch):
    original = handoff.request_budget

    def changed(symbols):
        result = copy.deepcopy(original(symbols))
        result["rest_requests"][0]["path"] = "/api/v3/unreviewed"
        return result

    monkeypatch.setattr(handoff, "request_budget", changed)
    with pytest.raises(ValueError, match="handoff_joint_budget_changed"):
        handoff.operation_gap(["BNBUSDT", "BTCUSDT"])


def test_changed_snapshot_depth_refuses_comparison(monkeypatch):
    original = handoff.request_budget

    def changed(symbols):
        result = copy.deepcopy(original(symbols))
        depth = next(row for row in result["rest_requests"] if row["path"] == "/api/v3/depth")
        depth["params"]["limit"] = "500"
        return result

    monkeypatch.setattr(handoff, "request_budget", changed)
    with pytest.raises(ValueError, match="handoff_joint_budget_changed"):
        handoff.operation_gap(["BNBUSDT", "BTCUSDT"])


def test_report_hash_duplicate_key_and_scenario_refused_before_replay():
    raw = b'{"scenario":"snapshot_success","scenario":"snapshot_success"}'
    with pytest.raises(ValueError, match="handoff_selected_complete_report_required"):
        handoff.review(raw, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="handoff_duplicate_json_key"):
        handoff.review(raw, expected_sha256=handoff.digest(raw))
    good = json.dumps({"scenarios": []}).encode()
    with pytest.raises(ValueError, match="handoff_selected_complete_report_required"):
        handoff.review(good, expected_sha256=handoff.digest(good), scenario="snapshot_gap")

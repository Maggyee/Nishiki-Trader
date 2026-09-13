"""Route completeness and total protocol budget, using original archive replay."""

import copy
import hashlib
import json
import subprocess
import sys
from decimal import Decimal

import pytest

from apps.ops.portfolio_testnet_observation_plan import plan_from_originals
from apps.strategies_nautilus.portfolio_observation_plan import observation_plan, request_budget
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_testnet_valuation import indicative_valuation
from tests.ops import test_portfolio_testnet_admission as admission_tests
from tests.ops.test_portfolio_testnet_admission import book, symbol
from tests.strategies_nautilus.test_portfolio_market_depth_v2 import v2_archive

case = admission_tests.case


def plan(balances, symbols, books):
    v = indicative_valuation(
        {a: (Decimal(q), Decimal("0")) for a, q in balances.items()}, {"symbols": symbols}, books
    )
    return observation_plan(
        {"valuation": v, "observation_anchor": {"start_ns": 1}},
        {"summary": {"observed_weight_limit_1m": 6000}},
    )


def test_pilot_preserves_unpriced_zero_locked_depth_and_omitted_routes():
    assets = {"BTC": "2", "ETH": "1", "BNB": "1", "USDT": "10", "USDC": "3", "X": "2", "ZERO": "0"}
    symbols = [symbol(a) for a in ("BTC", "ETH", "BNB", "X")]
    books = [book(s["symbol"]) for s in symbols]
    books[0]["bidQty"] = "1"
    p = plan(assets, symbols, books)
    assert p["pilot"]["symbols"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT"]
    assert p["unpriced_assets"] == ["USDC"] and p["historical_depth_exceeded_assets"] == ["BTC"]
    rows = {r["asset"]: r for r in p["asset_coverage"]}
    assert rows["USDT"]["status"] == rows["ZERO"]["status"] == "no_market_leg_required"
    assert rows["X"]["missing_pilot_symbols"] == ["XUSDT"]
    assert rows["USDC"]["status"] == "unpriced_nonzero_asset"
    assert not p["pilot"]["all_assets_covered"] and not p["runtime_ready"]
    assert p["interval_semantics"]["qualified_equity_usdt"] is None


def test_pilot_uses_existing_two_hop_route_and_deduplicates_shared_leg():
    symbols = [symbol("BTC"), symbol("ETH", "BTC"), symbol("BNB", "BTC")]
    p = plan({"BTC": "1", "ETH": "1", "BNB": "1"}, symbols, [book(s["symbol"]) for s in symbols])
    assert p["pilot"]["symbols"] == ["BNBBTC", "BTCUSDT", "ETHBTC"]
    assert p["pilot"]["budget"]["total_documented_weight"] == 448
    eth = next(r for r in p["asset_coverage"] if r["asset"] == "ETH")
    assert eth["required_symbols"] == ["BTCUSDT", "ETHBTC"]
    assert not p["new_probe_authorized"] and not p["baseline_qualified"]


def test_direct_route_priority_and_one_sided_native_quote_blocker():
    symbols = [symbol("BTC"), symbol("ETH"), symbol("BNB"), symbol("ETH", "BTC")]
    books = [book(s["symbol"]) for s in symbols]
    books[1].update(askPrice="0", askQty="0")
    p = plan({"BTC": "1", "ETH": "1", "BNB": "1"}, symbols, books)
    assert p["pilot"]["symbols"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT"]
    assert p["pilot"]["native_quote_side_blockers"] == ["ETHUSDT"]
    assert not p["pilot"]["collector_implemented"]


def test_missing_pilot_asset_is_explicit_without_substitution():
    p = plan({"BTC": "1", "X": "1"}, [symbol("BTC"), symbol("X")], [book("BTCUSDT"), book("XUSDT")])
    assert p["pilot"]["missing_or_unpriced_targets"] == ["ETH", "BNB"]
    assert p["pilot"]["symbols"] == ["BTCUSDT"]
    assert not p["new_probe_authorized"]


def test_budget_counts_complete_before_after_collections_and_ws_cost():
    p = request_budget(["ETHUSDT", "BTCUSDT", "BNBUSDT"])
    assert (
        p["rest_get_count"],
        p["private_get_count"],
        p["rest_weight"],
        p["ws_api_weight"],
        p["total_documented_weight"],
    ) == (16, 8, 442, 6, 448)
    rows = p["rest_requests"]
    for phase in ("account_before", "account_after"):
        assert [r["path"] for r in rows if r["phase"] == phase] == [
            "/api/v3/account",
            "/api/v3/openOrders",
            "/api/v3/openOrders",
            "/api/v3/account",
        ]
    assert all(r["params"] == {} for r in rows if r["path"].endswith("/openOrders"))
    assert all(
        r["params"] == {"omitZeroBalances": "false"} for r in rows if r["path"].endswith("/account")
    )
    assert all(r["method"] == "GET" for r in rows)
    assert p["reconnects"] == p["http_retries"] == p["snapshot_retries"] == 0
    assert not p["current_shared_ip_budget_verified"]


@pytest.mark.parametrize(
    "levels,expected", [(100, 2928), (500, 12908), (1000, 25383), (5000, 125183)]
)
def test_full_route_budget_does_not_ignore_joint_observation_overhead(levels, expected):
    assert (
        request_budget([f"ASSET{i}USDT" for i in range(499)], levels=levels)[
            "total_documented_weight"
        ]
        == expected
    )


@pytest.fixture
def originals(case, tmp_path):
    account, initial, market, params = case
    raws = {
        "account": account,
        "initial": initial,
        "market": canonical(market),
        "depth": v2_archive(tmp_path),
    }
    return (
        raws,
        {k: hashlib.sha256(v).hexdigest() for k, v in raws.items()},
        params["collection_id"],
    )


def test_replays_all_originals_and_keeps_independent_historical_intervals(originals):
    raws, hashes, collection = originals
    before = copy.deepcopy(raws)
    p = plan_from_originals(raws, hashes, collection=collection)
    assert raws == before and p["venue_requests_made"] == 0 and not p["credentials_loaded"]
    assert p["btc_only_transport_observation"]["native_quote_count"] == 2
    assert p["btc_only_transport_observation"]["max_frames_in_rolling_second"] == 3
    assert not p["btc_only_transport_observation"]["extrapolation_to_other_symbols_qualified"]
    assert p["interval_semantics"]["common_revision"] is None
    assert not p["interval_semantics"]["equal_endpoints_prove_complete_flow_or_reset_history"]


@pytest.mark.parametrize("key", ["account", "initial", "market", "depth"])
def test_changed_original_refused(originals, key):
    raws, hashes, collection = originals
    hashes[key] = "0" * 64
    with pytest.raises(ValueError):
        plan_from_originals(raws, hashes, collection=collection)


def test_failed_depth_cannot_support_planning(originals):
    raws, hashes, collection = originals
    raws["depth"] = b"\n".join(raws["depth"].splitlines()[:-1]) + b"\n"
    hashes["depth"] = hashlib.sha256(raws["depth"]).hexdigest()
    with pytest.raises(ValueError):
        plan_from_originals(raws, hashes, collection=collection)


def test_cli_private_output_no_overwrite_or_network(originals, tmp_path):
    raws, hashes, collection = originals
    args = ["--collection", collection, "--output", str(tmp_path / "plan.json")]
    for k, v in raws.items():
        path = tmp_path / (k + ".input")
        path.write_bytes(v)
        path.chmod(0o600)
        args += ["--" + k, str(path), "--" + k + "-sha256", hashes[k]]
    script = """import socket,sys
from apps.ops.portfolio_testnet_observation_plan import main
def blocked(*a,**kw): raise AssertionError("no network")
socket.create_connection=blocked
socket.socket.connect=blocked
raise SystemExit(main(sys.argv[1:]))
"""
    p = subprocess.run([sys.executable, "-c", script, *args], capture_output=True, timeout=30)
    assert p.returncode == 0, p.stdout + p.stderr
    path = tmp_path / "plan.json"
    raw = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    p = subprocess.run([sys.executable, "-c", script, *args], capture_output=True, timeout=30)
    assert p.returncode == 1 and path.read_bytes() == raw
    assert json.loads(raw)["runtime_ready"] is False

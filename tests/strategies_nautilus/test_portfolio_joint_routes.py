"""Selected raw routes, per-asset exclusions and pre-dispatch resource evidence."""

import copy
import json

import pytest

from apps.strategies_nautilus import portfolio_joint_observation as joint
from apps.strategies_nautilus.portfolio_joint_routes import RoutedJointEvidence, loopback_url
from apps.strategies_nautilus.portfolio_market_depth import DepthError
from apps.strategies_nautilus.portfolio_stream import canonical
from tests.strategies_nautilus.test_portfolio_joint_observation import (
    BASE,
    SYMBOLS,
    Clock,
    Fixture,
    manifest,
)
from tests.strategies_nautilus.test_portfolio_market_depth import rechain

KEY = "A" * 64


def route_manifest(clock, endpoints=None):
    result = manifest()
    account = result["initial_account"]
    wrapped = canonical(
        {
            "schema_version": "portfolio.testnet_initial_account_observation.v1",
            "endpoint": joint.REST,
            "path": "/api/v3/account",
            "key_sha256": joint.digest(KEY.encode()),
            "response_body": canonical(account).decode(),
            "response_sha256": joint.digest(canonical(account)),
        }
    )
    return {
        **result,
        "symbols": [],
        "source": {**result["source"], "key_sha256": joint.digest(KEY.encode())},
        "initial_raw": wrapped.decode(),
        "initial_sha256": joint.digest(wrapped),
        "transport_scope": "loopback_only",
        "wire_endpoints": endpoints
        or {
            "http": "http://127.0.0.1:19001",
            "account": "ws://127.0.0.1:19002",
            "market": "ws://127.0.0.1:19003",
        },
        "budget_sample": {
            "scope": "loopback_peer_shared_usage_fixture",
            "observed_ns": clock()[0],
            "used_weight": 0,
            "weight_limit": 6000,
            "connection_limit": 300,
            "connection_attempts": 0,
        },
    }


def route_books():
    return [
        {"symbol": s, "bidPrice": "99", "bidQty": "100", "askPrice": "101", "askQty": "100"}
        for s in SYMBOLS
    ]


class RouteFixture(Fixture):
    def __init__(self, tmp_path):
        self.path = tmp_path / "routes.jsonl"
        self.clock = Clock()
        self.journal = joint.JointJournal(
            self.path,
            manifest=route_manifest(self.clock),
            clock=self.clock,
            evidence_type=RoutedJointEvidence,
        )

    def prepare(self):
        state = self.journal.state
        op_id = state.prepared_count
        self.append(
            "operation_prepared",
            operation=state.next_operation(),
            operation_id=op_id,
            request_id=f"loopback-{op_id}",
        )
        return op_id

    def read(self, body=None, **changes):
        op_id = self.prepare()
        state = self.journal.state
        if body is None and state.budget["rest_requests"][state.request_index]["path"].endswith(
            "bookTicker"
        ):
            body = route_books()
        return super().read(
            body, **{"operation_id": op_id, "used_weight_1m": state.usage, **changes}
        )

    def ws(self):
        op_id = self.prepare()
        state = self.journal.state
        operation = state.prepared["operation"]["operation"]
        if operation == "ws_api_connection":
            self.append(
                "ws_operation",
                operation_id=op_id,
                operation=operation,
                status=200,
                epoch="synthetic-account",
            )
        else:
            self.append(
                "account_wire",
                epoch="synthetic-account",
                **joint.raw_fields(
                    canonical(
                        {
                            "id": f"loopback-{op_id}",
                            "status": 200,
                            "result": {"subscriptionId": 7} if state.ws_index == 1 else {},
                            "rateLimits": [
                                {
                                    "rateLimitType": "REQUEST_WEIGHT",
                                    "interval": "MINUTE",
                                    "intervalNum": 1,
                                    "limit": 6000,
                                    "count": state.usage,
                                }
                            ],
                        }
                    )
                ),
            )

    def connect(self):
        self.read()
        self.ws()
        self.ws()
        for _ in range(6):
            self.read()
        op_id = self.prepare()
        self.append(
            "market_connected",
            operation_id=op_id,
            epoch="synthetic-market",
            url="wss://stream.testnet.binance.vision/stream?streams="
            + "/".join(s.lower() + "@depth@100ms" for s in self.journal.state.manifest["symbols"]),
        )


def replay(raw):
    return joint.replay_joint(
        raw, expected_sha256=joint.digest(raw), evidence_type=RoutedJointEvidence
    )


def test_original_raw_inputs_freeze_routes_and_preserve_unpriced_asset(tmp_path):
    f = RouteFixture(tmp_path)
    f.link()
    raw = f.finish()
    result = replay(raw)
    summary = result["summary"]
    assert summary["route_fixation"]["symbols"] == SYMBOLS
    assert summary["route_fixation"]["assets"][-1] == {
        "asset": "USDT",
        "required_symbols": [],
        "status": "selected_or_no_market_leg",
        "historical_top_book_exceeded": False,
    }
    assert (
        next(r for r in summary["route_fixation"]["assets"] if r["asset"] == "UNPRICED")["status"]
        == "unpriced"
    )
    assert summary["prepared_operations"] == 20
    assert summary["loopback_connection_attempts"] == 2
    assert summary["loopback_observed_used_weight"] == summary["documented_weight"] == 448
    assert all(n["exact_assets"] == 5 for n in result["native_accounts"])
    assert (
        not summary["fresh_route_selection_verified"]
        and summary["original_inputs_replayed_for_routes"]
    )
    with pytest.raises(DepthError):
        joint.replay_joint(raw, expected_sha256=joint.digest(raw))


@pytest.mark.parametrize(
    "damage", ["initial_hash", "uid", "key", "production", "prefilled_symbols"]
)
def test_selected_source_cannot_be_replaced(tmp_path, damage):
    selected = route_manifest(Clock())
    if damage == "initial_hash":
        selected["initial_sha256"] = "f" * 64
    elif damage == "uid":
        selected["source"]["account_uid"] = "99"
    elif damage == "key":
        selected["source"]["key_sha256"] = "b" * 64
    elif damage == "production":
        selected["source"]["endpoint"] = "https://api.binance.com"
    else:
        selected["symbols"] = SYMBOLS
    with pytest.raises(DepthError):
        joint.JointJournal(
            tmp_path / "bad.jsonl",
            manifest=selected,
            clock=Clock(),
            evidence_type=RoutedJointEvidence,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://testnet.binance.vision",
        "ws://localhost:8000",
        "ws://127.0.0.1.evil:80",
        "ws://127.0.0.1:80?x=1",
        "ws://key@127.0.0.1:80",
        "ws://[::1]:80",
        "ws://127.0.0.1",
    ],
)
def test_only_explicit_ipv4_loopback_is_callable(url):
    with pytest.raises((DepthError, ValueError)):
        loopback_url(url, "ws")


@pytest.mark.parametrize("damage", ["missing", "one_sided", "depth", "duplicate", "stale"])
def test_invalid_route_inputs_stop_before_market_connect(tmp_path, damage):
    f = RouteFixture(tmp_path)
    f.read()
    f.ws()
    f.ws()
    for _ in range(5):
        f.read()
    books = route_books()
    if damage == "missing":
        books.pop()
    elif damage == "one_sided":
        books[0]["askQty"] = "0"
    elif damage == "depth":
        books[0]["bidQty"] = "0.01"
    elif damage == "duplicate":
        books.append(copy.deepcopy(books[0]))
    else:
        f.clock.advance(61 * joint.SECOND)
    with pytest.raises(DepthError):
        f.read(books)
    assert not f.journal.state.market_connected
    f.journal.close()


@pytest.mark.parametrize(
    "damage",
    [
        "weight",
        "connections",
        "stale",
        "window",
        "double_prepare",
        "missing_prepare",
        "regressing_usage",
        "wrong_selector",
    ],
)
def test_dispatch_refusals_and_consumed_attempts(tmp_path, damage):
    f = RouteFixture(tmp_path)
    state = f.journal.state
    if damage == "weight":
        state.usage = 5600  # Leaves too little for the complete 448-weight scope.
    elif damage == "connections":
        state.connection_attempts = 299
    elif damage == "stale":
        f.clock.advance(6 * joint.SECOND)
    elif damage == "window":
        f.clock.advance(60 * joint.SECOND)
    elif damage in {"double_prepare", "missing_prepare", "regressing_usage", "wrong_selector"}:
        if damage != "missing_prepare":
            f.prepare()
        with pytest.raises(DepthError):
            if damage == "double_prepare":
                f.prepare()
            else:
                Fixture.read(
                    f,
                    {"serverTime": BASE // 1_000_000},
                    operation_id=0,
                    used_weight_1m=0 if damage == "regressing_usage" else 1,
                    **({"params": {"symbol": "FOREIGN"}} if damage == "wrong_selector" else {}),
                )
    if damage in {"weight", "connections", "stale", "window"}:
        with pytest.raises(DepthError):
            f.prepare()
    assert f.journal.failed
    f.journal.close()
    with pytest.raises(DepthError):
        replay(f.path.read_bytes())


def test_rechained_routing_body_cannot_inherit_success(tmp_path):
    f = RouteFixture(tmp_path)
    f.link()
    rows = [json.loads(line) for line in f.finish().splitlines()]
    row = next(r for r in rows if r.get("path", "").endswith("bookTicker"))
    row.update(joint.raw_fields(canonical(route_books()[:-1])))
    with pytest.raises(DepthError):
        replay(rechain(rows))


def test_loopback_profile_two_fresh_cli_replays(tmp_path):
    import subprocess
    import sys

    f = RouteFixture(tmp_path)
    f.link()
    raw = f.finish()
    expected = replay(raw)
    outputs = []
    for i in range(2):
        report = tmp_path / f"route-replay{i}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_joint_observation",
                "--loopback-profile",
                "--archive",
                str(f.path),
                "--archive-sha256",
                joint.digest(raw),
                "--report",
                str(report),
            ],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        outputs.append(report.read_bytes())
        assert report.stat().st_mode & 0o777 == 0o600
    assert outputs[0] == outputs[1] and json.loads(outputs[0]) == expected
    assert f.path.read_bytes() == raw


def test_two_hop_fixed_route_uses_same_three_stream_cap(tmp_path):
    from tests.strategies_nautilus.test_portfolio_joint_observation import all_metadata

    f = RouteFixture(tmp_path)
    f.read()
    f.ws()
    f.ws()
    for _ in range(4):
        f.read()
    info = all_metadata()
    info["symbols"][0].update(
        symbol="BNBBTC",
        quoteAsset="BTC",
        filters=[{"filterType": "PRICE_FILTER", "tickSize": "0.001"}],
    )
    f.read(info)
    books = route_books()
    books[0].update(symbol="BNBBTC", bidPrice="0.01", askPrice="0.011")
    f.read(books)
    assert f.journal.state.routes["symbols"] == ["BNBBTC", "BTCUSDT", "ETHUSDT"]
    row = next(r for r in f.journal.state.routes["assets"] if r["asset"] == "BNB")
    assert row["required_symbols"] == ["BNBBTC", "BTCUSDT"]
    f.journal.close()


def test_account_wire_honors_lowered_frame_limit(tmp_path):
    from dataclasses import replace

    f = RouteFixture(tmp_path)
    f.read()
    f.ws()
    f.journal.limits = replace(f.journal.limits, frame_bytes=1)
    with pytest.raises(DepthError, match="frame_limit"):
        f.ws()
    f.journal.close()


def test_original_synthetic_archive_bytes_stay_compatible(tmp_path):
    f = Fixture(tmp_path)
    f.link()
    raw = f.finish()
    # Independently generated with the committed pre-integration module at a9b4104.
    assert joint.digest(raw) == "4a3ced9b9aab7ffd0ce5b5d97baa31a87c11d35e3cd607984f69d528cffcbb0a"
    assert (
        joint.replay_joint(raw, expected_sha256=joint.digest(raw))["summary"]["profile"]
        == joint.PROFILE
    )
    with pytest.raises(DepthError):
        replay(raw)

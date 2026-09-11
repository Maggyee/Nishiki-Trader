from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from nautilus_trader.model.objects import Currency

from apps.ops.portfolio_testnet_account_review import main, review_accounts
from apps.strategies_nautilus.portfolio_stream import StreamError, bind_source, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.portfolio_testnet_observation import (
    TestnetObservationJournal,
    collect_testnet_observation,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS

SELECTION = "a" * 64
UNKNOWN = "未定义_TESTNET_ASSET"


def body():
    return {
        "uid": 123,
        "accountType": "SPOT",
        "canTrade": True,
        "balances": [
            {"asset": "BTC", "free": "1.00000000", "locked": "0.00000000"},
            {"asset": "USDT", "free": "500.00000000", "locked": "0.00000000"},
            {"asset": UNKNOWN, "free": "3.00000000", "locked": "0.00000000"},
        ],
    }


def capture(
    path, *, account=None, orders=None, ts=BASE_NS, key="synthetic-key", selection=SELECTION
):
    clock = SimpleNamespace(now=ts)
    http = SimpleNamespace(base_url=TESTNET_REST, api_key=key)
    binding = bind_source(http, "123")
    bodies = [account or body(), orders or [], orders or [], account or body()]
    calls = []

    async def sign(method, request_path, *, payload):
        clock.now += 1_000_000
        calls.append(request_path)
        return canonical(bodies[len(calls) - 1])

    http.sign_request = sign
    journal = TestnetObservationJournal(path, binding, clock_ns=lambda: clock.now)
    try:
        journal.subscribed(7, binding)
        result = asyncio.run(collect_testnet_observation(http, journal, selection_sha256=selection))
        journal.disconnect()
    finally:
        journal.close()
    raw = path.read_bytes()
    return raw, hashlib.sha256(raw).hexdigest(), result["collection_id"]


@pytest.fixture
def captures(tmp_path):
    return capture(tmp_path / "before.jsonl"), capture(tmp_path / "after.jsonl", ts=BASE_NS + 10**9)


def review(captures, **kwargs):
    before, after = captures
    params = dict(
        before_sha256=before[1],
        before_collection=before[2],
        after_sha256=after[1],
        after_collection=after[2],
        selection_sha256=SELECTION,
    )
    return review_accounts(before[0], after[0], **(params | kwargs))


def test_equal_complete_observations_do_not_prove_history_or_qualification(captures):
    assert Currency.from_str(UNKNOWN, strict=True) is None
    result = review(captures)
    assert result["status"] == "observed_equal"
    assert result["assets_recorded"] == 3
    assert set(result["current_observed_balances"]) == {"BTC", "USDT", UNKNOWN}
    assert result["missing_native_currencies"] == 1
    assert result["inexact_native_balances"] == 0
    assert result["current_observed_balances"]["USDT"]["free"] == "500.00000000"
    assert Currency.from_str(UNKNOWN, strict=True) is None  # no fallback registration
    for field in (
        "runtime_ready",
        "baseline_qualified",
        "independent_uid_verified",
        "reset_history_verified",
        "no_trading_history_verified",
        "global_continuity_verified",
        "native_mapping_qualified",
        "valuation_qualified",
        "api_key_restrictions_verified",
    ):
        assert result[field] is False


@pytest.mark.parametrize(
    "change", ["locked", "added", "removed", "orders", "metadata", "precision"]
)
def test_all_asset_and_order_drift_is_retained(tmp_path, captures, change):
    account, orders = body(), []
    if change == "locked":
        account["balances"][2].update(free="2", locked="1")  # total unchanged
    elif change == "added":
        account["balances"].append({"asset": "NEW_ASSET", "free": "0", "locked": "0"})
    elif change == "removed":
        account["balances"].pop()
    elif change == "orders":
        orders = [{"symbol": "BTCUSDT", "orderId": 77}]
    elif change == "metadata":
        account["canTrade"] = False
    else:
        account["balances"][0]["free"] = "1.000000001"
    changed = capture(
        tmp_path / "changed.jsonl", account=account, orders=orders, ts=BASE_NS + 10**9
    )
    result = review((captures[0], changed))
    assert result["status"] == "observed_drift"
    assert "observed_account_drift_requires_review" in result["blocking_reasons"]
    if change == "locked":
        row = result["balances_changed"][0]
        assert row["asset"] == UNKNOWN and row["after"]["locked"] == "1"
    elif change == "added":
        assert result["assets_added"] == ["NEW_ASSET"]
    elif change == "removed":
        assert result["assets_removed"] == [UNKNOWN]
    elif change == "orders":
        assert not result["open_orders_equal"] and result["after_open_orders"] == 1
    elif change == "metadata":
        assert result["account_fields_changed"] == ["canTrade"]
    else:
        assert result["inexact_native_balances"] == 1
        assert result["current_observed_balances"]["BTC"]["free"] == "1.000000001"


def test_order_and_asset_row_order_is_not_balance_drift(tmp_path):
    original = body()
    reordered = copy.deepcopy(original)
    reordered["balances"].reverse()
    orders = [{"symbol": "BTCUSDT", "orderId": 77}, {"symbol": "ETHUSDT", "orderId": 78}]
    before = capture(tmp_path / "before.jsonl", account=original, orders=orders)
    after = capture(
        tmp_path / "after.jsonl", account=reordered, orders=orders[::-1], ts=BASE_NS + 10**9
    )
    assert review((before, after))["status"] == "observed_equal"


@pytest.mark.parametrize(
    "field",
    ["before_sha256", "after_sha256", "before_collection", "after_collection", "selection_sha256"],
)
def test_wrong_selected_evidence_is_rejected(captures, field):
    with pytest.raises(StreamError):
        review(captures, **{field: "b" * 64})


def test_changed_source_is_not_silently_rebound(tmp_path, captures):
    after = capture(tmp_path / "other.jsonl", key="other-key", ts=BASE_NS + 10**9)
    with pytest.raises(StreamError, match="integrity"):
        review((captures[0], after))


def test_overlapping_or_reversed_observations_are_rejected(captures):
    for pair in ((captures[0], captures[0]), captures[::-1]):
        with pytest.raises(StreamError, match="forward observation"):
            review(pair)


def cli_args(tmp_path, captures):
    args = []
    for side, (raw, digest, collection) in zip(("before", "after"), captures, strict=True):
        path = tmp_path / f"{side}.jsonl"
        assert path.read_bytes() == raw
        args.extend(
            [
                f"--{side}-archive",
                str(path),
                f"--{side}-sha256",
                digest,
                f"--{side}-collection",
                collection,
            ]
        )
    return args + ["--selection-sha256", SELECTION, "--output", str(tmp_path / "report.json")]


def test_cli_private_report_sanitized_summary_and_no_overwrite(tmp_path, captures, capsys):
    args = cli_args(tmp_path, captures)
    assert main(args) == 0
    output = capsys.readouterr().out
    assert UNKNOWN not in output and '"free"' not in output
    summary = json.loads(output)
    assert not summary["runtime_ready"]
    path = tmp_path / "report.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == summary["report_sha256"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert main(args) == 2
    assert path.read_bytes() == raw
    assert json.loads(capsys.readouterr().out)["status"] == "review_failed"
    for side, record in zip(("before", "after"), captures, strict=True):
        assert (tmp_path / f"{side}.jsonl").read_bytes() == record[0]


def test_cli_bad_private_input_does_not_echo_response(tmp_path, captures, capsys):
    args = cli_args(tmp_path, captures)
    (tmp_path / "after.jsonl").write_bytes(b"private-invalid-payload")
    assert main(args) == 2
    assert "private-invalid-payload" not in capsys.readouterr().out
    assert not (tmp_path / "report.json").exists()


def metadata(symbols=None, **changes):
    if symbols is None:
        symbols = [
            {
                "symbol": f"{asset}USDT",
                "baseAsset": asset,
                "baseAssetPrecision": 8,
                "quoteAsset": "USDT",
                "quoteAssetPrecision": 8,
            }
            for asset in ("BTC", UNKNOWN)
        ]
    response = canonical({"symbols": symbols}).decode()
    wrapped = {
        "schema_version": "portfolio.testnet_exchange_info_observation.v1",
        "endpoint": "https://testnet.binance.vision/api/v3/exchangeInfo",
        "started_ns": BASE_NS,
        "received_ns": BASE_NS + 2 * 10**9,
        "response_body": response,
        "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
    } | changes
    raw = canonical(wrapped)
    return dict(exchange_info_raw=raw, exchange_info_sha256=hashlib.sha256(raw).hexdigest())


def test_full_native_account_uses_metadata_without_global_registration(captures):
    result = review(captures, **metadata())
    mapped = result["exchange_metadata_mapping"]
    assert mapped["exact_assets"] == 3
    assert mapped["detached_native_account_balances_equal"]
    assert mapped["isolated_native_process"]
    assert Currency.from_str(UNKNOWN, strict=True) is None
    assert "missing_native_currency_definitions" not in result["blocking_reasons"]
    assert not mapped["native_mapping_qualified"] and not result["runtime_ready"]
    assert not mapped["metadata_current_for_execution_verified"]


@pytest.mark.parametrize("fault", ["missing", "conflict", "quote_conflict"])
def test_incomplete_metadata_never_constructs_a_partial_account(captures, fault):
    params = metadata()
    wrapped = json.loads(params["exchange_info_raw"])
    symbols = json.loads(wrapped["response_body"])["symbols"]
    if fault == "missing":
        symbols.pop()
    elif fault == "conflict":
        symbols.append(symbols[-1] | {"symbol": "SECOND", "baseAssetPrecision": 7})
    else:
        # Two listings disagree on USDT precision; no convenient one may win.
        symbols[1]["quoteAssetPrecision"] = 2
    result = review(captures, **metadata(symbols))
    assert not result["exchange_metadata_mapping"]["detached_native_account_balances_equal"]
    assert "exchange_metadata_mapping_incomplete" in result["blocking_reasons"]
    assert not result["runtime_ready"]


def test_metadata_precision_loss_is_retained_without_rounding_snapshot(tmp_path, captures):
    account = body()
    account["balances"][0]["free"] = "1.000000001"
    after = capture(tmp_path / "precision.jsonl", account=account, ts=BASE_NS + 10**9)
    result = review((captures[0], after), **metadata())
    mapped = result["exchange_metadata_mapping"]
    assert not mapped["detached_native_account_balances_equal"]
    assert mapped["exact_assets"] == 2
    assert any(r["status"] == "native_amount_rounding" for r in mapped["assets"])
    assert result["current_observed_balances"]["BTC"]["free"] == "1.000000001"


@pytest.mark.parametrize(
    "fault", ["digest", "endpoint", "response_hash", "clock", "duplicate", "precision_bool"]
)
def test_malformed_or_wrong_source_metadata_is_rejected(captures, fault):
    params = metadata()
    if fault == "digest":
        params["exchange_info_sha256"] = "0" * 64
    elif fault == "endpoint":
        params = metadata(endpoint="https://api.binance.com/api/v3/exchangeInfo")
    elif fault == "response_hash":
        params = metadata(response_sha256="0" * 64)
    elif fault == "clock":
        params = metadata(received_ns=BASE_NS - 1)
    else:
        symbols = json.loads(json.loads(params["exchange_info_raw"])["response_body"])["symbols"]
        if fault == "duplicate":
            symbols.append(symbols[-1])
        else:
            symbols[0]["baseAssetPrecision"] = True
        params = metadata(symbols)
    with pytest.raises(StreamError):
        review(captures, **params)


def test_cli_can_select_metadata_without_changing_source_archives(tmp_path, captures, capsys):
    params = metadata()
    path = tmp_path / "metadata.json"
    path.write_bytes(params["exchange_info_raw"])
    args = cli_args(tmp_path, captures) + [
        "--exchange-info",
        str(path),
        "--exchange-info-sha256",
        params["exchange_info_sha256"],
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["detached_native_account_balances_equal"]
    assert not result["runtime_ready"]
    assert path.read_bytes() == params["exchange_info_raw"]

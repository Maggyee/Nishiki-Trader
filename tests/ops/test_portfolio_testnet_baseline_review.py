from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from apps.ops.portfolio_testnet_baseline_review import (
    INPUTS,
    _balance_bridge,
    _gaps,
    review_baseline,
)
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from tests.ops.test_portfolio_testnet_account_review import capture
from tests.ops.test_portfolio_testnet_admission import book, symbol
from tests.strategies_nautilus import test_portfolio_session_transport as transport_tests

case = transport_tests.case
DAY = 86_400_000_000_000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def test_native_fills_and_fees_explain_endpoint_changes_in_asset_units():
    reference = {"BTC": {"free": "2", "locked": "0"}, "USDT": {"free": "100", "locked": "0"}}
    baseline = {"BTC": ["2", "0"], "USDT": ["100", "0"]}
    result = _balance_bridge(reference, baseline, {"BTC": "2.00004", "USDT": "97.19999999"})
    rows = {r["asset"]: r for r in result["assets"]}
    assert D(rows["BTC"]["known_session_delta"]) == D("0.00004")
    assert D(rows["USDT"]["known_session_delta"]) == D("-2.80000001")
    assert result["observed_endpoint_deltas_explained"]
    assert result["external_net_cash_flow_usdt"] is None
    assert not result["cash_flow_history_complete"] and not result["reset_history_verified"]


@pytest.mark.parametrize("delta", ["-0.00000001", "0.00000001", "5", "-5"])
def test_unexplained_delta_is_not_labeled_deposit_withdrawal_or_pnl(delta):
    reference = {"ETH": {"free": "5", "locked": "0"}}
    changed = str(D(5) + D(delta))
    result = _balance_bridge(reference, {"ETH": [changed, "0"]}, {"ETH": changed})
    assert result["unexplained_net_delta_assets"] == ["ETH"]
    assert D(result["assets"][0]["unexplained_net_delta"]) == D(delta)
    assert not result["observed_endpoint_deltas_explained"]
    assert result["external_net_cash_flow_usdt"] is None


@pytest.mark.parametrize("missing", ["reference", "baseline", "final"])
def test_missing_zero_asset_is_not_silently_filled(missing):
    values = [{"X": {"free": "0", "locked": "0"}}, {"X": ["0", "0"]}, {"X": "0"}]
    values[["reference", "baseline", "final"].index(missing)] = {}
    result = _balance_bridge(*values)
    assert result["asset_coverage_gaps"] == ["X"]
    assert result["assets"][0]["unexplained_net_delta"] is None
    assert not result["observed_endpoint_deltas_explained"]


def test_reservation_change_is_separate_from_total_fund_change():
    result = _balance_bridge({"USDT": {"free": "93", "locked": "7"}},
        {"USDT": ["100", "0"]}, {"USDT": "100"})
    assert result["reference_to_session_locked_changes"] == ["USDT"]
    assert result["observed_endpoint_deltas_explained"]
    assert not result["cash_flow_history_complete"]


@pytest.fixture
def selected(case, tmp_path):
    state = read_session(case.ledger.path.read_bytes())["state"]
    account = {"uid": 123, "accountType": "SPOT", "canTrade": True, "balances": [
        {"asset": a, "free": v[0], "locked": v[1]} for a, v in state["baseline"].items()]}
    initial = canonical({"schema_version": "portfolio.testnet_initial_account_observation.v1",
        "endpoint": state["source"]["endpoint"], "path": "/api/v3/account",
        "key_sha256": state["source"]["key_sha256"], "response_body": canonical(account).decode(),
        "response_sha256": sha(canonical(account))})
    # Prior day reference, not the later session's UTC day-open, even with all marks.
    base = state["started_ns"] - DAY - 10_000_000_000
    raw, digest, collection = capture(tmp_path / "reference.jsonl", account=account,
        ts=base, key="offline-session-key", selection=sha(initial))
    symbols = [symbol(a) for a in state["baseline"] if a != "USDT"]
    bodies = [{"symbols": symbols}, [book(s["symbol"]) for s in symbols]]
    captures = [{"endpoint": state["source"]["endpoint"] + path,
        "started_ns": base + (i + 1) * 1_000_000_000, "received_ns": base + (i + 1) * 1_000_000_000 + 1,
        "response_body": canonical(body).decode(), "response_sha256": sha(canonical(body))}
        for i, (path, body) in enumerate(zip(("/api/v3/exchangeInfo", "/api/v3/ticker/bookTicker"), bodies, strict=True))]
    market = canonical({"schema_version": "portfolio.testnet_market_capture.v1",
        "account_archive_sha256": digest, "account_collection_id": collection, "captures": captures})
    receipt = transport_tests.collect(case)
    raws = {"initial": initial, "account_archive": raw, "market": market,
        "session_archive": case.archive.read_bytes(), "checkpoint": case.ledger.path.read_bytes()}
    return SimpleNamespace(raws=raws, hashes={k: sha(v) for k, v in raws.items()},
        account_collection=collection, session_collection=receipt.collection_id,
        reviewed_ns=state["started_ns"] + 3 * DAY, loop=case.loop, state=state)


def review(selected):
    return review_baseline(selected.raws, selected.hashes, account_collection=selected.account_collection,
        session_collection=selected.session_collection, reviewed_ns=selected.reviewed_ns, loop=selected.loop)


def test_all_priced_equal_endpoints_with_actual_native_fill_still_cannot_qualify_day_open(selected):
    result = review(selected)
    assert result["valuation"]["all_assets_priced"]
    assert result["balance_bridge"]["observed_endpoint_deltas_explained"]
    assert result["historical_session"]["fills"] == 1
    assert result["utc_evidence"]["crosses_utc_day"]
    assert not result["utc_evidence"]["qualified_midnight_baseline_present"]
    for field in ("qualified_current_equity_usdt", "qualified_day_open_equity_usdt", "daily_loss_usdt",
                  "effective_daily_limit_usdt", "qualified_peak_equity_usdt", "peak_loss_usdt"):
        assert result["risk_inputs"][field] is None
    assert result["risk_inputs"]["policy_daily_cap_usdt"] == "25"
    assert result["risk_inputs"]["policy_daily_fraction"] == "0.05"
    assert result["risk_inputs"]["policy_fixed_peak_loss_ceiling_usdt"] == "250"
    for flag in ("baseline_qualified", "source_authenticated", "current_venue_state_verified",
                 "new_orders_authorized", "runtime_ready", "fixed_checkpoint_written"):
        assert result[flag] is False


@pytest.mark.parametrize("name", list(INPUTS))
def test_original_input_hash_changes_fail_closed(selected, name):
    selected.hashes[name] = "0" * 64
    with pytest.raises(ValueError):
        review(selected)


@pytest.mark.parametrize("change", ["source", "overlap", "midnight"])
def test_source_ordering_and_even_exact_midnight_do_not_create_independent_baseline(selected, change):
    # Reuse validated reviewers; helper rejects pairing and never upgrades timestamps.
    from apps.ops.portfolio_session_archive import review_archive
    from apps.ops.portfolio_testnet_admission import review_admission

    a = review_admission(selected.raws["account_archive"], selected.raws["market"], selected.raws["initial"],
        archive_sha256=selected.hashes["account_archive"], collection_id=selected.account_collection,
        market_sha256=selected.hashes["market"], selection_sha256=selected.hashes["initial"])
    s = review_archive(selected.raws["session_archive"], selected.raws["checkpoint"],
        archive_sha256=selected.hashes["session_archive"], checkpoint_sha256=selected.hashes["checkpoint"],
        collection_id=selected.session_collection, reviewed_ns=selected.reviewed_ns, loop=selected.loop)
    if change == "source":
        a["inputs"]["source_binding_sha256"] = "f" * 64
    elif change == "overlap":
        a["observation_anchor"]["start_ns"] = selected.state["started_ns"]
    else:
        a["observation_anchor"]["start_ns"] = (selected.state["started_ns"] // DAY - 1) * DAY
        result = _gaps(a, s, selected.state)
        assert result["utc_evidence"]["reference_offset_from_midnight_ns"] == 0
        assert not result["utc_evidence"]["qualified_midnight_baseline_present"]
        return
    with pytest.raises(StreamError):
        _gaps(a, s, selected.state)


def test_missing_quote_keeps_full_equity_null_and_exposes_specific_gap(selected):
    market = json.loads(selected.raws["market"])
    capture = market["captures"][1]
    books = json.loads(capture["response_body"])
    for row in books:
        if row["symbol"] == "ETHUSDT":
            row.update(bidPrice="0", askPrice="0", bidQty="0", askQty="0")
    capture["response_body"] = canonical(books).decode()
    capture["response_sha256"] = sha(canonical(books))
    selected.raws["market"] = canonical(market)
    selected.hashes["market"] = sha(selected.raws["market"])
    result = review(selected)
    assert "ETH" in result["valuation"]["unpriced_assets"]
    assert "unpriced_nonzero_assets" in result["blocking_reasons"]
    assert result["valuation"]["full_indicative_mark_usdt"] is None


def test_cli_publishes_private_diagnostic_only_and_preserves_all_inputs(selected, tmp_path):
    paths = {}
    for name, raw in selected.raws.items():
        p = tmp_path / (name + ".json")
        p.write_bytes(raw)
        p.chmod(0o600)
        paths[name] = p
    output = tmp_path / "review.json"
    args = [sys.executable, "-m", "apps.ops.portfolio_testnet_baseline_review"]
    for name in INPUTS:
        option = name.replace("_", "-")
        args.extend(["--" + option, str(paths[name]), "--" + option + "-sha256", selected.hashes[name]])
    args.extend(["--account-collection", selected.account_collection, "--session-collection",
                 selected.session_collection, "--output", str(output)])
    guard = """
import sys

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("network forbidden")
    if event == "open" and isinstance(args[0], str) and "/.config/trader/" in args[0]:
        raise AssertionError("credential file forbidden")
    if event == "subprocess.Popen" and args[1][1:3] != ["-m", "apps.strategies_nautilus.portfolio_testnet_mapping"]:
        raise AssertionError("only isolated native mapping process allowed")
sys.addaudithook(audit)
from apps.ops.portfolio_testnet_baseline_review import main
raise SystemExit(main())
"""
    proc = subprocess.run([sys.executable, "-c", guard, *args[3:]], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "historical_review_complete_baseline_blocked"
    assert not result["baseline_qualified"] and not result["runtime_ready"]
    assert "key_sha256" not in proc.stdout and "balances" not in proc.stdout
    before = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    for name, path in paths.items():
        assert path.read_bytes() == selected.raws[name]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1 and output.read_bytes() == before

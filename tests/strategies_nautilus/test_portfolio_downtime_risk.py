from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import asdict, replace
from decimal import Decimal as D

import pytest
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.objects import AccountBalance, Money

from apps.ops.portfolio_downtime_risk_check import main
from apps.strategies_nautilus.portfolio_adapter_checkpoint import NUMERIC_MODE, checkpoint_bytes
from apps.strategies_nautilus.portfolio_downtime_risk import DowntimeRiskError, review_downtime_risk
from apps.strategies_nautilus.portfolio_recovery import (
    encode,
    reconstruct_native,
    verify_checkpoint,
)
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance import (
    BINDING,
    fixture_checkpoint,
    resume,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND, quote


@pytest.fixture
def case(tmp_path):
    loop = asyncio.new_event_loop()
    try:
        before = verify_checkpoint(fixture_checkpoint(loop))
    finally:
        loop.close()
    before["state"]["risk_latched"] = False
    before_raw = checkpoint_bytes(before["state"], before["native"])
    before_hash = hashlib.sha256(before_raw).hexdigest()
    result = resume(before_raw, before_hash, tmp_path / "stream.jsonl", BASE_NS + 8 * SECOND)
    after_raw = result.checkpoint
    instrument, initial, _, _ = reconstruct_native(before["native"], venue_id_mode=NUMERIC_MODE)
    _, final, _, _ = reconstruct_native(
        verify_checkpoint(after_raw)["native"], venue_id_mode=NUMERIC_MODE
    )

    def observation(ts, account, bid="100000"):
        return {
            "ts_ns": ts,
            "account_event": encode(account.events[-1]),
            "quote": encode(quote(instrument, ts, bid=bid, ask=str(D(bid) + 10))),
        }

    rows = [
        observation(BASE_NS + 3 * SECOND, initial),
        observation(BASE_NS + 3 * SECOND + SECOND // 2, initial, "20000"),
        observation(BASE_NS + 8 * SECOND, final),
    ]
    history = {
        "schema_version": "portfolio.downtime_risk.v1",
        "input_sha256": before_hash,
        "output_sha256": result.output_sha256,
        "source": asdict(BINDING),
        "observations": rows,
    }
    return before_raw, after_raw, history, instrument, initial.events[-1]


def review(case, **updates):
    before, after, history, *_ = case
    args = dict(
        source=BINDING,
        expected_before_sha256=hashlib.sha256(before).hexdigest(),
        expected_after_sha256=hashlib.sha256(after).hexdigest(),
    )
    args.update(updates)
    return review_downtime_risk(before, after, canonical(history), **args)


def test_rebound_cannot_hide_an_observed_daily_stop(case):
    before, after = case[:2]
    result = review(case)
    assert result["observed_stop_required"] and result["incident_review_required"]
    assert not result["prior_risk_latched"]
    assert D(result["minimum_observed_equity_usdt"]) == D("473.35")
    assert D(result["ending_equity_usdt"]) == D("499.75")
    assert set(result["first_breaches"]) == {"daily_5pct"}
    assert result["first_breaches"]["daily_5pct"]["ts_ns"] == BASE_NS + 3 * SECOND + SECOND // 2
    assert D(result["daily_5pct_limit_usdt"]) == 25
    assert D(result["planning_daily_limit_usdt"]) == 50
    assert result["planning_daily_exceeds_5pct"]
    assert not result["runtime_ready"] and not result["downtime_history_complete"]
    assert case[:2] == (before, after)
    assert not verify_checkpoint(before)["state"]["risk_latched"]


def set_quote(case, index, bid):
    row = case[2]["observations"][index]
    row["quote"] = encode(quote(case[3], row["ts_ns"], bid=bid, ask=str(D(bid) + 10)))


def test_clean_observations_are_not_proof_of_complete_history(case):
    set_quote(case, 1, "100000")
    result = review(case)
    assert result["status"] == "observed_no_breach"
    assert not result["observed_stop_required"]
    assert result["observation_gaps"]
    assert not result["runtime_ready"] and result["downtime_risk_review_required"]


def test_dense_observations_still_do_not_prove_lossless_coverage(case):
    set_quote(case, 1, "100000")
    rows = case[2]["observations"]
    middle = copy.deepcopy(rows[1])
    case[2]["observations"] = [rows[0]]
    for second in range(4, 8):
        row = copy.deepcopy(middle)
        row["ts_ns"] = BASE_NS + second * SECOND
        row["quote"] = encode(quote(case[3], row["ts_ns"]))
        case[2]["observations"].append(row)
    case[2]["observations"].append(rows[-1])
    result = review(case)
    assert not result["observation_gaps"]
    assert not result["downtime_history_complete"] and not result["runtime_ready"]


@pytest.mark.parametrize("equity,breached", [("475.01", False), ("475.00", True), ("474.99", True)])
def test_five_percent_threshold_is_inclusive(case, equity, breached):
    # Independent native account observation for the boundary arithmetic.
    event = case[4]
    middle = case[2]["observations"][1]
    observed = AccountState(
        account_id=event.account_id,
        account_type=event.account_type,
        base_currency=None,
        balances=[
            AccountBalance(Money(D(equity), USDT), Money(0, USDT), Money(D(equity), USDT)),
            AccountBalance(Money(0, BTC), Money(0, BTC), Money(0, BTC)),
        ],
        margins=[],
        reported=True,
        info={},
        event_id=UUID4(),
        ts_event=middle["ts_ns"],
        ts_init=middle["ts_ns"],
    )
    middle["account_event"] = encode(observed)
    result = review(case)
    assert ("daily_5pct" in result["first_breaches"]) == breached
    assert "planning_daily" not in result["first_breaches"]
    from apps.bridge.validators import Authorization
    from apps.strategies_nautilus.baseline_strategy import (
        BaselineSignalStrategy,
        BaselineStrategyConfig,
    )

    runtime = BaselineSignalStrategy(
        BaselineStrategyConfig("BINANCE", Authorization(frozenset(), frozenset()))
    )
    runtime.on_account_update(500.0, float(equity))
    assert runtime.kill_switch_engaged == breached


def test_observed_peak_is_not_reset_at_recovery(case):
    set_quote(case, 1, "1000000")
    result = review(case)
    assert "planning_drawdown" in result["first_breaches"]
    assert "daily_5pct" not in result["first_breaches"]
    assert result["observed_stop_required"]


def test_previous_latch_cannot_be_cleared_by_a_clean_path(case):
    set_quote(case, 1, "100000")
    before, after, history, *rest = case
    pair = []
    for raw in (before, after):
        wrapped = verify_checkpoint(raw)
        wrapped["state"]["risk_latched"] = True
        pair.append(checkpoint_bytes(wrapped["state"], wrapped["native"]))
    history["input_sha256"], history["output_sha256"] = (
        hashlib.sha256(raw).hexdigest() for raw in pair
    )
    result = review((*pair, history, *rest))
    assert result["prior_risk_latched"] and result["observed_stop_required"]
    assert not result["first_breaches"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda h: h.update(source={**h["source"], "account_uid": "other"}),
        lambda h: h.update(input_sha256="0" * 64),
        lambda h: h.update(output_sha256="0" * 64),
        lambda h: h.update(schema_version="unknown"),
        lambda h: h.update(complete=True),
        lambda h: h["observations"].pop(0),
        lambda h: h["observations"].pop(),
        lambda h: h["observations"].reverse(),
        lambda h: h["observations"].insert(1, h["observations"][0]),
        lambda h: h["observations"][1].update(ts_ns=True),
        lambda h: h["observations"][0].update(account_event=h["observations"][-1]["account_event"]),
        lambda h: h["observations"][-1].update(account_event=h["observations"][0]["account_event"]),
        lambda h: h["observations"][1].update(quote=h["observations"][-1]["quote"]),
        lambda h: h["observations"][1].update(quote="{}"),
    ],
)
def test_unbound_or_inconsistent_observations_are_rejected(case, mutation):
    mutation(case[2])
    with pytest.raises((ValueError, TypeError)):
        review(case)


@pytest.mark.parametrize(
    "field,value",
    [("day_ns", BASE_NS - 1), ("day_open", "0"), ("peak", "499"), ("risk_latched", "false")],
)
def test_invalid_or_missing_day_baselines_are_rejected(case, field, value):
    before, after, history, *rest = case
    pair = []
    for raw in (before, after):
        wrapped = verify_checkpoint(raw)
        wrapped["state"][field] = value
        pair.append(checkpoint_bytes(wrapped["state"], wrapped["native"]))
    history["input_sha256"], history["output_sha256"] = (
        hashlib.sha256(raw).hexdigest() for raw in pair
    )
    with pytest.raises(ValueError):
        review((*pair, history, *rest))


def test_cross_utc_day_requires_a_new_qualified_baseline(case):
    before, after, history, *rest = case
    wrapped = verify_checkpoint(after)
    wrapped["native"]["ts_ns"] = BASE_NS + 86_400 * SECOND
    after = checkpoint_bytes(wrapped["state"], wrapped["native"])
    history["output_sha256"] = hashlib.sha256(after).hexdigest()
    with pytest.raises(DowntimeRiskError, match="UTC rollover"):
        review((before, after, history, *rest))


def test_selected_checkpoint_hash_and_source_are_required(case):
    with pytest.raises(DowntimeRiskError, match="digest"):
        review(case, expected_before_sha256="0" * 64)
    with pytest.raises(DowntimeRiskError):
        review(case, source=replace(BINDING, endpoint="https://example.com"))


@pytest.mark.parametrize("clean", [False, True])
def test_cli_reports_observed_stop_without_modifying_inputs(case, tmp_path, capsys, clean):
    if clean:
        set_quote(case, 1, "100000")
    before, after, history, *_ = case
    values = {
        "before.json": before,
        "after.json": after,
        "history.json": canonical(history),
        "source.json": canonical(asdict(BINDING)),
    }
    for name, raw in values.items():
        (tmp_path / name).write_bytes(raw)
    code = main(
        [str(tmp_path / name) for name in ("before.json", "after.json", "history.json")]
        + [
            "--source-binding",
            str(tmp_path / "source.json"),
            "--before-sha256",
            hashlib.sha256(before).hexdigest(),
            "--after-sha256",
            hashlib.sha256(after).hexdigest(),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == (0 if clean else 2)
    assert report["observed_stop_required"] is not clean
    assert not report["runtime_ready"]
    assert all((tmp_path / name).read_bytes() == raw for name, raw in values.items())


def test_conflicting_quote_replay_cannot_change_an_old_price(case):
    row = case[2]["observations"][1]
    row["quote"] = encode(quote(case[3], BASE_NS + 3 * SECOND, bid="20000", ask="20010"))
    with pytest.raises(DowntimeRiskError, match="conflicting"):
        review(case)


def test_stale_quote_cannot_value_a_later_account_snapshot(case):
    rows = case[2]["observations"]
    rows[1]["ts_ns"] = BASE_NS + 5 * SECOND
    rows[1]["quote"] = rows[0]["quote"]
    with pytest.raises(DowntimeRiskError, match="stale"):
        review(case)


def test_non_btc_quote_is_rejected(case):
    row = case[2]["observations"][1]
    body = json.loads(row["quote"])
    body["instrument_id"] = "ETHUSDT.BINANCE"
    row["quote"] = json.dumps(body)
    with pytest.raises(DowntimeRiskError, match="BTCUSDT"):
        review(case)

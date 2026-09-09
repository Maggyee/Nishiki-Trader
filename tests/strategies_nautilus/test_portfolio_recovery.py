from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal as D

import pytest

from apps.strategies_nautilus.portfolio_account import reconcile_account
from apps.strategies_nautilus.portfolio_recovery import (
    RecoveryError,
    reconstruct_native,
    recover_simulation,
    verify_checkpoint,
)
from apps.strategies_nautilus.portfolio_simulation import SimulationBlocked, canonical
from apps.strategies_nautilus.runners.portfolio_recovery_acceptance import (
    fixture_account_evidence,
    run_acceptance,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
    BASE_NS,
    SECOND,
    advance,
    build_simulation,
    fixture_signal,
)


@pytest.fixture
def native_case(tmp_path):
    def enter(s):
        s.process_signals((fixture_signal("v16", "entry", BASE_NS),))

    path = tmp_path / "checkpoint.json"
    engine, strategy, instrument = build_simulation(
        path,
        {BASE_NS: enter},
        fee_mode="received_asset",
        exit_policy="whole_steps_v1",
        persist_native=True,
    )
    advance(engine, instrument, BASE_NS)
    advance(engine, instrument, BASE_NS + 2 * SECOND, bid="99999", ask="100000", size="0.000333")
    anchor, evidence = fixture_account_evidence(strategy)
    wrapped = verify_checkpoint(path.read_bytes())
    _, account, orders, positions = reconstruct_native(wrapped["native"])
    yield engine, strategy, instrument, anchor, evidence, (account, orders, positions), path
    engine.end()
    engine.dispose()


def check(case, evidence=None, *, anchor=None, venue=None):
    _, s, _, original_anchor, original_evidence, native, _ = case
    return reconcile_account(
        evidence or original_evidence,
        anchor=anchor or original_anchor,
        native=native,
        intents=s.state_data["orders"],
        now_ns=BASE_NS + 4 * SECOND,
        max_age_ns=60 * SECOND,
        venue=venue,
    )


def change_body(evidence, field, mutation):
    response = getattr(evidence, field)
    data = json.loads(response.body)
    mutation(data)
    return replace(evidence, **{field: replace(response, body=json.dumps(data))})


def test_complete_account_agreement_includes_locked_balance_and_native_fees(native_case):
    checked = check(native_case)
    assert checked.checks_passed
    assert len(checked.response_sha256) == 4
    assert not checked.runtime_ready
    assert checked.evidence_ts_ns == BASE_NS + 3 * SECOND


@pytest.mark.parametrize(
    "field,mutation,reason",
    [
        ("account", lambda b: b.update(uid="wrong"), "UID/type mismatch"),
        ("account", lambda b: b.update(canTrade=False), "permission absent"),
        ("account", lambda b: b.update(permissions=[]), "permission absent"),
        ("account", lambda b: b["balances"][0].update(free="0.00033251"), "balances mismatch"),
        (
            "account",
            lambda b: b["balances"][1].update(free="400", locked="66.7"),
            "balances mismatch",
        ),
        ("account", lambda b: b["balances"].append(b["balances"][0]), "duplicate account asset"),
        (
            "account",
            lambda b: b["balances"].append({"asset": "BNB", "free": "1", "locked": "0"}),
            "unexpected funded",
        ),
        ("account", lambda b: b["balances"][0].update(free="NaN"), "invalid venue decimal"),
        ("orders", lambda b: b.clear(), "unknown"),
        ("orders", lambda b: b.append(b[0]), "duplicate venue order"),
        ("orders", lambda b: b[0].update(executedQty="0.000334"), "drifting"),
        ("trades", lambda b: b.clear(), "trades mismatch"),
        ("trades", lambda b: b.append(b[0]), "duplicate venue trade"),
        ("trades", lambda b: b[0].update(commission="0.00000049"), "trades mismatch"),
        ("trades", lambda b: b[0].update(commissionAsset="BNB"), "trades mismatch"),
        ("trades", lambda b: b[0].update(orderId="unknown"), "unknown"),
        ("trades", lambda b: b[0].update(isBuyer="true"), "coverage/side"),
        ("trades", lambda b: b[0].update(time=0), "coverage/side"),
        ("open_orders", lambda b: b.clear(), "incomplete open-order"),
        ("open_orders", lambda b: b.append(b[0]), "duplicate"),
        ("open_orders", lambda b: b[0].update(symbol="ETHUSDT"), "unknown"),
    ],
)
def test_account_drift_and_incomplete_evidence_fail_closed(native_case, field, mutation, reason):
    evidence = change_body(native_case[4], field, mutation)
    checked = check(native_case, evidence)
    assert not checked.checks_passed
    assert reason in checked.reasons[0]


@pytest.mark.parametrize("field", ["account", "orders", "trades", "open_orders"])
@pytest.mark.parametrize(
    "change",
    [
        {"received_ns": BASE_NS - 61 * SECOND},
        {"received_ns": BASE_NS + 5 * SECOND},
        {"account_id": "wrong"},
    ],
)
def test_each_private_response_requires_fresh_matching_identity(native_case, field, change):
    evidence = native_case[4]
    evidence = replace(evidence, **{field: replace(getattr(evidence, field), **change)})
    assert not check(native_case, evidence).checks_passed


def test_anchor_coverage_and_external_cash_flow_are_not_inferred(native_case):
    anchor, evidence = native_case[3:5]
    assert not check(native_case, replace(evidence, start_ns=BASE_NS + 1)).checks_passed
    assert not check(native_case, anchor=replace(anchor, quote=D("501"))).checks_passed
    assert not check(native_case, anchor=replace(anchor, base=D("1"))).checks_passed
    assert not check(
        native_case,
        replace(evidence, open_orders=replace(evidence.open_orders, requested_symbol="BTCUSDT")),
    ).checks_passed


def test_effective_venue_rules_must_attach_to_same_fresh_account(native_case):
    from apps.strategies_nautilus.portfolio_venue import VenueRulesEvidence

    venue = VenueRulesEvidence(native_case[1].rules(), native_case[3].venue_uid, (), (), ())
    assert check(native_case, venue=venue).checks_passed
    assert not check(native_case, venue=replace(venue, account_id="wrong")).checks_passed
    assert not check(
        native_case, venue=replace(venue, rules=replace(venue.rules, ts_ns=BASE_NS - 61 * SECOND))
    ).checks_passed


def test_duplicate_json_keys_cannot_override_account_permissions(native_case):
    evidence = native_case[4]
    response = replace(evidence.account, body='{"canTrade":true,"canTrade":false}')
    assert "duplicate JSON key" in check(native_case, replace(evidence, account=response)).reasons


@pytest.mark.parametrize("part", ["native", "state"])
def test_corrupt_checkpoint_is_rejected_before_engine_creation(native_case, part):
    path = native_case[-1]
    wrapped = json.loads(path.read_bytes())
    wrapped[part]["injected"] = True
    with pytest.raises(RecoveryError, match="integrity mismatch"):
        verify_checkpoint(canonical(wrapped))


def test_mixed_checkpoint_generations_are_rejected(native_case):
    wrapped = json.loads(native_case[-1].read_bytes())
    wrapped["native"]["ts_ns"] += 1
    wrapped["native_sha256"] = hashlib.sha256(canonical(wrapped["native"])).hexdigest()
    with pytest.raises(RecoveryError, match="generation mismatch"):
        verify_checkpoint(canonical(wrapped))


def test_duplicate_native_events_and_version_drift_are_rejected(native_case):
    wrapped = verify_checkpoint(native_case[-1].read_bytes())
    bundle = wrapped["native"]
    bundle["orders"][0]["events"].append(bundle["orders"][0]["events"][-1])
    with pytest.raises(RecoveryError, match="duplicate native event"):
        reconstruct_native(bundle)
    bundle["nautilus_version"] = "unknown"
    with pytest.raises(RecoveryError, match="version mismatch"):
        reconstruct_native(bundle)


def test_uncertain_prepared_intent_never_resubmits_from_journal(native_case):
    s = native_case[1]
    s.state_data["orders"]["missing"] = {**next(iter(s.state_data["orders"].values()))}
    checked = check(native_case)
    assert not checked.checks_passed
    assert "uncertain prepared submission" in checked.reasons[0]


def test_cold_restore_rechecks_evidence_freshness_when_engine_actually_starts(native_case):
    original, _, _, anchor, evidence, _, path = native_case
    original.end()  # release exclusive strategy writer
    engine, _, inst, _ = recover_simulation(
        path, evidence=evidence, anchor=anchor, now_ns=BASE_NS + 4 * SECOND
    )
    try:
        with pytest.raises(RecoveryError, match="stale"):
            advance(engine, inst, BASE_NS + 70 * SECOND)
    finally:
        engine.end()
        engine.dispose()


def test_restore_rejects_policy_change_and_keeps_checkpoint(native_case):
    _, _, _, anchor, evidence, _, path = native_case
    before = path.read_bytes()
    with pytest.raises(SimulationBlocked, match="config mismatch"):
        recover_simulation(
            path,
            evidence=evidence,
            anchor=anchor,
            now_ns=BASE_NS + 4 * SECOND,
            exit_policy="exact_v1",
        )
    assert path.read_bytes() == before


def test_restore_binds_account_anchor_and_rejects_market_cursor_replay(native_case):
    _, _, _, anchor, evidence, _, path = native_case
    with pytest.raises(RecoveryError, match="account anchor mismatch"):
        recover_simulation(
            path,
            evidence=evidence,
            anchor=replace(anchor, venue_uid="another"),
            now_ns=BASE_NS + 4 * SECOND,
        )
    with pytest.raises(RecoveryError, match="advance beyond"):
        recover_simulation(path, evidence=evidence, anchor=anchor, now_ns=BASE_NS + 3 * SECOND)


def test_concurrent_writer_and_changed_checkpoint_cannot_be_overwritten(native_case):
    original, _, _, anchor, evidence, _, path = native_case
    before = path.read_bytes()
    engine, _, inst, _ = recover_simulation(
        path, evidence=evidence, anchor=anchor, now_ns=BASE_NS + 4 * SECOND
    )
    try:
        with pytest.raises(BlockingIOError):
            advance(engine, inst, BASE_NS + 4 * SECOND)
        assert path.read_bytes() == before
    finally:
        engine.end()
        engine.dispose()
    original.end()
    engine, _, inst, _ = recover_simulation(
        path, evidence=evidence, anchor=anchor, now_ns=BASE_NS + 4 * SECOND
    )
    changed = before + b"\n"
    path.write_bytes(changed)
    try:
        with pytest.raises(SimulationBlocked, match="changed during native restore"):
            advance(engine, inst, BASE_NS + 4 * SECOND)
        assert path.read_bytes() == changed
    finally:
        engine.end()
        engine.dispose()


def test_pending_cancel_requires_authoritative_resolution_before_cold_resume(native_case):
    _, s, _, anchor, _, _, path = native_case
    oid = next(iter(s.state_data["orders"]))
    s.request_cancel(oid)
    s._persist()
    wrapped = verify_checkpoint(path.read_bytes())
    _, account, orders, positions = reconstruct_native(wrapped["native"])
    from apps.strategies_nautilus.portfolio_account import native_account_view

    with pytest.raises(ValueError, match="uncertain native"):
        native_account_view(account, orders, positions, s.state_data["orders"], anchor)


def test_abrupt_exit_and_independent_process_recovery(tmp_path):
    report = run_acceptance(tmp_path)
    assert report["distinct_processes"] and report["abrupt_exit_code"] == 23
    assert report["partial_order_resumed_without_resubmit"]
    assert report["risk_latched"]
    assert report["residual_btc"] == "0.000001"
    assert not report["real_account_verified"] and not report["runtime_ready"]

"""Offline source/egress consistency over the real consumed joint ledger."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as attempts
from apps.strategies_nautilus.portfolio_joint_admission import ENDPOINTS
from apps.strategies_nautilus.portfolio_tls_provenance import digest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/gateway_source_egress.py"
START = 1_000_000_000_000
SECOND = 1_000_000_000
PIN = "a" * 64
BASE = "b" * 64


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("gateway_source_egress_test", SOURCE)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Authority:
    manifest_sha256 = BASE

    def verify(self):
        return None


class Sources:
    manifest_sha256 = "c" * 64

    def source(self, name):
        assert name == "gateway_joint_ipc.py"
        return getattr(self, "raw", b"selected fixture gateway bytes")


class Guard:
    def __init__(self):
        self.row = {
            "binding_sha256": PIN,
            "installation_manifest_sha256": BASE,
            "boot_id": "fixture-boot",
            "window_started_monotonic_ns": START - 300 * SECOND,
            "exclusive_through_monotonic_ns": START + 200 * SECOND,
            "all_other_callers_denied": True,
            "collector_quarantined": True,
        }

    def verify(self):
        return dict(self.row)


class Binding:
    def verify(self):
        return {"binding_sha256": PIN}


def fixed_bindings():
    return {
        role: {
            "endpoint": endpoint,
            "destination_ip": "198.51.100.2",
            "address_family": 4,
            "local_source_ip": "192.0.2.10",
            "public_source_ip": "203.0.113.10",
            "collector_uid": 1201,
            "network_namespace": "net:[123]",
        }
        for role, endpoint in ENDPOINTS.items()
    }


def archive(tmp_path, *, outcome="succeeded", close=True, operation="time"):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    moment = START

    def clock():
        nonlocal moment
        moment += 1
        return 1_800_000_000_000_000_000 + moment - START, moment

    ledger = attempts.AttemptLedger(
        root,
        binding=Binding(),
        binding_sha256=PIN,
        clock=clock,
        profile=attempts.JOINT_PROFILE,
    )
    try:
        prepared = ledger.prepare(caller="collector", operation=operation, joint_prefix_sha256=PIN)
        if outcome is not None:
            ledger.outcome(index=prepared["index"], result=outcome, joint_prefix_sha256=PIN)
        if close:
            ledger.close()
        raw = (ledger.path / "events.jsonl").read_bytes()
    finally:
        if not ledger.closed:
            ledger.close()
    return raw


def review(adapter, raw, bindings, **kwargs):
    return adapter.review(
        observed=bindings,
        ledger_raw=raw,
        ledger_sha256=digest(raw),
        binding_sha256=PIN,
        now_ns=START + 10 * SECOND,
        **kwargs,
    )


def test_complete_local_archive_still_cannot_authorize_source_or_traffic(module, tmp_path):
    bindings = fixed_bindings()
    adapter = module.OfflineSourceEgress(
        Authority(),
        Sources(),
        Guard(),
        collector_uid=1201,
        bindings=bindings,
    )
    result = review(adapter, archive(tmp_path), bindings)
    assert result["counts"][0]["prepared_attempts"] == 1
    assert result["counts"][0]["outcomes"]["succeeded"] == 1
    assert result["status"] == "offline_local_consistency_only"
    assert all(
        result[k] is False
        for k in (
            "source_authenticated",
            "complete_caller_coverage_verified",
            "provider_usage_qualified",
            "network_admitted",
            "trading_admitted",
        )
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("endpoint", "https://other.example"),
        ("destination_ip", "198.51.100.3"),
        ("local_source_ip", "192.0.2.11"),
        ("public_source_ip", "203.0.113.11"),
        ("address_family", 6),
        ("collector_uid", 1202),
        ("network_namespace", "net:[456]"),
    ],
)
def test_bound_route_uid_family_and_source_drift_refuses(module, tmp_path, field, value):
    bindings = fixed_bindings()
    observed = fixed_bindings()
    observed["market"][field] = value
    adapter = module.OfflineSourceEgress(
        Authority(),
        Sources(),
        Guard(),
        collector_uid=1201,
        bindings=bindings,
    )
    with pytest.raises(ValueError, match="source_egress"):
        review(adapter, archive(tmp_path), observed)
    with pytest.raises(ValueError, match="closed_or_foreign_owner"):
        review(adapter, b"", bindings)


@pytest.mark.parametrize(
    "outcome,close,operation",
    [
        (None, False, "time"),
        ("failed", True, "time"),
        ("uncertain", True, "time"),
        ("succeeded", True, "market_connect"),
    ],
)
def test_incomplete_crashed_failed_or_unknown_charge_refuses(
    module,
    tmp_path,
    outcome,
    close,
    operation,
):
    bindings = fixed_bindings()
    raw = archive(tmp_path, outcome=outcome, close=close, operation=operation)
    adapter = module.OfflineSourceEgress(
        Authority(),
        Sources(),
        Guard(),
        collector_uid=1201,
        bindings=bindings,
    )
    with pytest.raises(ValueError, match="incomplete_or_unknown_attempt_history"):
        review(adapter, raw, bindings)
    report = attempts.replay(
        raw, expected_sha256=digest(raw), binding_sha256=PIN, profile=attempts.JOINT_PROFILE
    )
    assert report["recorded_attempts"] == 1
    assert report["counts"][0]["outcomes"]["uncertain" if outcome is None else outcome] == 1


@pytest.mark.parametrize("drift", ["expired", "gap", "boot", "pin"])
def test_guard_gap_expiry_or_selection_drift_refuses(module, tmp_path, drift):
    bindings = fixed_bindings()
    guard, authority = Guard(), Authority()
    adapter = module.OfflineSourceEgress(
        authority,
        Sources(),
        guard,
        collector_uid=1201,
        bindings=bindings,
    )
    if drift == "expired":
        guard.row["exclusive_through_monotonic_ns"] = START + 125 * SECOND
    elif drift == "gap":
        guard.row["window_started_monotonic_ns"] = START + 5
    elif drift == "boot":
        guard.row["installation_manifest_sha256"] = "f" * 64
    else:
        authority.manifest_sha256 = "f" * 64
    with pytest.raises(ValueError, match="source_egress"):
        review(adapter, archive(tmp_path), bindings)


def test_missing_role_and_public_source_conflict_refuse_at_selection(module):
    bindings = fixed_bindings()
    bindings.pop("account")
    with pytest.raises(ValueError, match="three_roles_required"):
        module.OfflineSourceEgress(
            Authority(), Sources(), Guard(), collector_uid=1201, bindings=bindings
        )
    bindings = fixed_bindings()
    bindings["market"]["public_source_ip"] = "203.0.113.11"
    with pytest.raises(ValueError, match="shared_public_source_missing"):
        module.OfflineSourceEgress(
            Authority(), Sources(), Guard(), collector_uid=1201, bindings=bindings
        )


def test_short_lookback_and_missing_other_caller_exclusion_refuse(module, tmp_path):
    bindings = fixed_bindings()
    guard = Guard()
    adapter = module.OfflineSourceEgress(
        Authority(),
        Sources(),
        guard,
        collector_uid=1201,
        bindings=bindings,
    )
    guard.row["window_started_monotonic_ns"] = START - 289 * SECOND
    with pytest.raises(ValueError, match="exclusion_gap_or_expiry"):
        review(adapter, archive(tmp_path), bindings)
    guard = Guard()
    adapter = module.OfflineSourceEgress(
        Authority(),
        Sources(),
        guard,
        collector_uid=1201,
        bindings=bindings,
    )
    guard.row["all_other_callers_denied"] = False
    (tmp_path / "second").mkdir()
    with pytest.raises(ValueError, match="exclusion_gap_or_expiry"):
        review(adapter, archive(tmp_path / "second"), bindings)


def test_selected_gateway_bytes_changing_after_construction_refuse(module, tmp_path):
    bindings = fixed_bindings()
    sources = Sources()
    adapter = module.OfflineSourceEgress(
        Authority(),
        sources,
        Guard(),
        collector_uid=1201,
        bindings=bindings,
    )
    sources.raw = b"different fixture source"
    with pytest.raises(ValueError, match="selection_drift"):
        review(adapter, archive(tmp_path), bindings)


def test_guard_changes_on_final_verification_refuse(module, tmp_path):
    bindings = fixed_bindings()
    guard = Guard()
    original = guard.verify
    calls = 0

    def changed():
        nonlocal calls
        calls += 1
        row = original()
        if calls == 2:
            row["exclusive_through_monotonic_ns"] -= 1
        return row

    guard.verify = changed
    adapter = module.OfflineSourceEgress(
        Authority(),
        Sources(),
        guard,
        collector_uid=1201,
        bindings=bindings,
    )
    with pytest.raises(ValueError, match="observation_drift"):
        review(adapter, archive(tmp_path), bindings)

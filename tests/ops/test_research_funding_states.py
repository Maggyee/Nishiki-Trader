"""Offline tests for the shared funding-state harness and the v50/v51 contracts."""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from apps.ops import research_protocol_v50, research_protocol_v51
from apps.ops.research_funding_states import (
    apply_gates,
    build_candidate_states,
    funding_quality_errors,
    funding_quality_report,
    parse_funding_zip,
)

RULE_PARAMS = {
    "window_hours": 72,
    "min_settlements": 6,
    "baseline_rate": 0.0001,
    "overheat_rate": 0.0005,
}


def _zip_with_csv(csv_text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BTCUSDT-fundingRate-test.csv", csv_text)
    return buffer.getvalue()


def test_both_contracts_are_valid_with_stable_fingerprints() -> None:
    for contract in (research_protocol_v50, research_protocol_v51):
        assert contract.validate_contract() == []
        assert contract.contract_sha256() == contract.contract_sha256()
    # v51 is the provider-corrected recovery: new identities, corrected months.
    assert research_protocol_v50.FUNDING_SOURCE["development_months"][0] == "2019-12"
    assert research_protocol_v51.FUNDING_SOURCE["development_months"][0] == "2020-01"
    v50_ids = {v for pair in research_protocol_v50.IDENTITIES.values() for v in pair}
    v51_ids = {v for pair in research_protocol_v51.IDENTITIES.values() for v in pair}
    assert v50_ids.isdisjoint(v51_ids)
    assert research_protocol_v50.RULES == research_protocol_v51.RULES
    assert research_protocol_v50.PARAMETERS == research_protocol_v51.PARAMETERS


def test_parse_funding_zip_handles_both_schema_eras() -> None:
    modern = _zip_with_csv(
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1577836800000,8,0.0001\n1577865600000,8,-0.0002\n"
    )
    frame = parse_funding_zip(modern)
    assert list(frame["rate"]) == [0.0001, -0.0002]
    assert frame["timestamp"].iloc[0] == pd.Timestamp("2020-01-01", tz="UTC")

    legacy = _zip_with_csv("fundingTime,fundingRate\n1577836800000,0.0003\n")
    frame = parse_funding_zip(legacy)
    assert list(frame["rate"]) == [0.0003]

    with pytest.raises(ValueError, match="unrecognized funding schema"):
        parse_funding_zip(_zip_with_csv("a,b\n1,2\n"))


def _closes(start: str, end: str) -> pd.Series:
    dates = pd.date_range(start, end, freq="D", tz="UTC")
    return pd.Series(np.linspace(10_000.0, 11_000.0, len(dates)), index=dates)


def _funding_series(values: dict[str, float]) -> pd.Series:
    stamps = pd.DatetimeIndex([pd.Timestamp(k, tz="UTC") for k in values])
    return pd.Series(list(values.values()), index=stamps, name="funding").sort_index()


def test_candidate_states_follow_frozen_rules_and_cutoff() -> None:
    closes = _closes("2020-01-10", "2020-01-12")
    stamps: dict[str, float] = {}
    for day in ("2020-01-08", "2020-01-09", "2020-01-10"):
        for hour in ("00:00", "08:00", "16:00"):
            stamps[f"{day} {hour}"] = -0.0002
    for day in ("2020-01-11", "2020-01-12"):
        for hour in ("00:00", "08:00", "16:00"):
            stamps[f"{day} {hour}"] = 0.001
    states = build_candidate_states(closes, _funding_series(stamps), **RULE_PARAMS)
    day0 = 0  # 2020-01-10: trailing 72h all negative
    assert bool(states["fund_neg_3d"][day0]) is True
    assert bool(states["fund_below_baseline_3d"][day0]) is True
    assert bool(states["fund_overheat_flat_3d"][day0]) is True  # not overheated -> long
    day2 = 2  # 2020-01-12: trailing window dominated by +0.001
    assert bool(states["fund_neg_3d"][day2]) is False
    assert bool(states["fund_overheat_flat_3d"][day2]) is False  # overheated -> flat


def test_candidate_states_ignore_settlements_after_cutoff() -> None:
    closes = _closes("2020-01-10", "2020-01-10")
    base = {
        f"2020-01-{day} {hour}": -0.0001
        for day in ("08", "09", "10")
        for hour in ("00:00", "08:00", "16:00")
    }
    with_future = dict(base)
    with_future["2020-01-11 00:00"] = 1.0
    states_a = build_candidate_states(closes, _funding_series(base), **RULE_PARAMS)
    states_b = build_candidate_states(closes, _funding_series(with_future), **RULE_PARAMS)
    for key in states_a:
        assert np.array_equal(states_a[key], states_b[key])


def test_candidate_states_force_flat_when_settlements_missing() -> None:
    closes = _closes("2020-01-10", "2020-01-10")
    sparse = _funding_series({"2020-01-10 00:00": -0.01, "2020-01-10 08:00": -0.01})
    states = build_candidate_states(closes, sparse, **RULE_PARAMS)
    for key in states:
        assert bool(states[key][0]) is False


def test_funding_quality_gates_fail_closed() -> None:
    stamps = {f"2020-01-01 {h:02d}:00": 0.0001 for h in range(0, 24, 8)}
    report = funding_quality_report(_funding_series(stamps), "2020-01-01", "2020-01-01")
    assert report["settlements"] == 3
    errors = funding_quality_errors(
        report, min_settlements=10, max_gap_hours=16.0, rate_abs_max=0.05
    )
    assert any("settlement count" in e for e in errors)
    crazy = _funding_series({"2020-01-01 00:00": 0.2, "2020-01-01 08:00": 0.0})
    report = funding_quality_report(crazy, "2020-01-01", "2020-01-01")
    errors = funding_quality_errors(
        report, min_settlements=1, max_gap_hours=16.0, rate_abs_max=0.05
    )
    assert any("sanity" in e for e in errors)


def test_apply_gates_requires_all_checks() -> None:
    candidate = {
        "base_net_pnl": 10.0,
        "stress_net_pnl": 8.0,
        "positive_years": 2,
        "positive_months": 20,
        "closed_positions": 80,
        "leave_best_base_net_pnl": 1.0,
        "time_in_market_fraction": 0.5,
    }
    gates = research_protocol_v51.GATES_V2["confirmation"]
    good = apply_gates(gates, candidate, bh_pnl=10.0, p_value=0.05)
    assert good["pass_gates"] is True
    assert good["benchmark_floor"] == pytest.approx(5.0)
    bad = apply_gates(gates, candidate, bh_pnl=30.0, p_value=0.05)
    assert bad["checks"]["benchmark_relative"] is False and bad["pass_gates"] is False

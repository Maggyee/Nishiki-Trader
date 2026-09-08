from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from apps.bridge.store import SignalStore
from apps.ops.research_portfolio_monitor import CANDIDATE_SPECS, contract_identity

CASES = [(22, "generate_option_surface_signals"),
         (34, "generate_treasury_yield_signals"), (36, "generate_option_strategy_signals")]


def fixture_fetch(now, *, constant=False):
    def fetch(url):
        if "klines" in url:
            last = int(now.replace(minute=0, second=0, microsecond=0).timestamp()*1000)
            return json.dumps([[t, "100", "102", "99", "101", "10", t+3599999]
                               for t in range(last-168*3600000, last, 3600000)]).encode()
        dates = pd.date_range("2019-11-01", now.date()-timedelta(days=1), freq="D")
        scalar = "VPN_History" in url
        rows = ["DATE,VPN" if scalar else "DATE,OPEN,HIGH,LOW,CLOSE"]
        for i, d in enumerate(dates):
            value = 100 if constant else 100 + 10*(i % 2)
            rows.append(f"{d:%m/%d/%Y},{value}" if scalar else f"{d:%m/%d/%Y},{value},{value+1},{value-1},{value}")
        return ("\n".join(rows)+"\n").encode()
    return fetch


@pytest.mark.parametrize("version,generator", CASES)
def test_real_collector_generates_signals_without_crediting_backfill(tmp_path, version, generator):
    module = importlib.import_module(f"apps.ops.research_v{version}_shadow_daily")
    now = datetime(2026,8,25,5,tzinfo=UTC)
    git = {"dirty": False, "origin_main_contains_commit": True, "commit": "a"*40}
    def run(at):
        return module.collect_daily(repo_root=tmp_path, data_root=tmp_path,
                                    now=at, fetch=fixture_fetch(at), git_state=git)
    first = run(now)
    assert first["record"]["signals"]["generated_total"] > 0
    assert first["status"]["qualified_day_count"] == 1
    assert first["status"]["new_forward_signal_count"] == 0
    assert first["status"]["signal_generation_checked"] is True
    identity = contract_identity(f"v{version}")
    stored = SignalStore(tmp_path / "signals.db").replay(**identity)
    assert len(stored) == first["record"]["signals"]["generated_total"]
    assert max(e.ts_event for e in stored) <= int(now.timestamp()*1e9)
    repeated = run(now+timedelta(seconds=1))
    assert repeated["status"]["qualified_day_count"] == 1
    assert repeated["record"]["signals"]["written"] == 0
    second = run(now+timedelta(days=1))
    assert second["status"]["qualified_day_count"] == 2
    assert second["status"]["new_forward_signal_count"] == 1


@pytest.mark.parametrize("version,generator", CASES)
def test_generator_date_guard_and_prefix_invariance(version, generator):
    module = importlib.import_module(f"apps.ops.research_v{version}_shadow_daily")
    contract = module.load_contract()
    key = contract["candidate"]["candidate_key"]
    rows = [{"date": str(d.date()), "value": 100 + 10*(i % 2)}
            for i, d in enumerate(pd.date_range("2025-12-01", "2026-08-31"))]
    frame = module._factor_frame(rows, vintage_id="fixture", snapshot_sha256="sha256:"+"a"*64)
    generate = getattr(module, generator)
    with pytest.raises(ValueError, match="date range is reversed"):
        generate(frame, candidate=key, start_date="2026-01-01")
    baseline = generate(frame, candidate=key, start_date="2026-01-01", end_date="2026-08-24")
    altered = frame.copy()
    altered.loc[altered.index >= pd.Timestamp("2026-08-25", tz="UTC"), "index_value"] = 999
    prefix = generate(altered, candidate=key, start_date="2026-01-01", end_date="2026-08-24")
    assert baseline and baseline == prefix


@pytest.mark.parametrize("version,generator", CASES)
def test_legitimate_no_transition_is_not_a_pipeline_failure(tmp_path, version, generator):
    module = importlib.import_module(f"apps.ops.research_v{version}_shadow_daily")
    now = datetime(2026,8,25,5,tzinfo=UTC)
    result = module.collect_daily(repo_root=tmp_path, data_root=tmp_path, now=now,
        fetch=fixture_fetch(now, constant=True), git_state={"dirty":False,"origin_main_contains_commit":True})
    assert result["record"]["signals"]["generated_total"] == 0
    assert result["status"]["signal_generation_checked"] is True
    assert result["record"]["blockers"] == []


def test_roster_identities_come_from_frozen_contracts():
    for spec in CANDIDATE_SPECS:
        assert {k: spec[k] for k in ("source", "model_version")} == contract_identity(spec["protocol"])
    vpn = next(s for s in CANDIDATE_SPECS if s["protocol"] == "v36")
    assert vpn["source"] == "rule_cboe_vpn_expansion_v1"
    assert vpn["model_version"] == "cboe-vpn-diff5-positive-lag1d-v1"

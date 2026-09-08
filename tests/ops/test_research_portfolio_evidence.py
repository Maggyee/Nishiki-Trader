from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from apps.ops import research_portfolio_evidence as evidence

IDENTITY = {"source": "fixture", "model_version": "v1"}


def fills():
    return pd.DataFrame(
        [
            {
                "fill_id": "a",
                "ts_event": pd.Timestamp("2023-01-01T12:00:00Z").value,
                "side": "BUY",
                "quantity": 0.001,
                "price": 100.0,
                "signal_id": "fixture:v1:BTCUSDT:BINANCE:1:buy",
                "instrument_id": "BTCUSDT.BINANCE",
            },
            {
                "fill_id": "b",
                "ts_event": pd.Timestamp("2023-01-03T12:00:00Z").value,
                "side": "SELL",
                "quantity": 0.001,
                "price": 110.0,
                "signal_id": "fixture:v1:BTCUSDT:BINANCE:2:flat",
                "instrument_id": "BTCUSDT.BINANCE",
            },
        ]
    )


def test_cash_accounting_costs_drawdown_and_exposure():
    prices = pd.Series(
        [100.0, 100.0, 90.0, 110.0], index=pd.date_range("2022-12-31", periods=4, tz="UTC")
    )
    curve, metrics = evidence.account_fills(evidence.audit_fills(fills(), IDENTITY), prices)
    assert metrics["net_pnl_usdt"]["gross"] == pytest.approx(0.01)
    assert metrics["net_pnl_usdt"]["base"] == pytest.approx(0.01 - 0.21 * 0.0012)
    assert metrics["net_pnl_usdt"]["stress"] == pytest.approx(0.01 - 0.21 * 0.0015)
    assert metrics["daily_marked_max_drawdown_usdt"]["base"] == pytest.approx(0.01012)
    assert metrics["time_in_market_fraction"] == pytest.approx(2 / 1096)
    assert metrics["account_return_pct"] is None
    assert metrics["actual_account_leverage"] is None
    assert curve["qty"].tolist() == [0.001, 0.001, 0.0]


@pytest.mark.parametrize(
    "fault", ["future", "wrong_identity", "nan", "duplicate", "short", "open", "size", "instrument"]
)
def test_invalid_fill_evidence_fails_closed(fault):
    frame = fills()
    if fault == "future":
        frame.loc[1, "ts_event"] = pd.Timestamp("2026-09-01", tz="UTC").value
    elif fault == "wrong_identity":
        frame.loc[0, "signal_id"] = "other:v1:BTCUSDT:BINANCE:1:buy"
    elif fault == "nan":
        frame.loc[0, "price"] = float("nan")
    elif fault == "duplicate":
        frame.loc[1, "fill_id"] = "a"
    elif fault == "short":
        frame.loc[0, "side"] = "SELL"
    elif fault == "open":
        frame = frame.iloc[:1]
    elif fault == "size":
        frame.loc[0, "quantity"] = 0.002
    elif fault == "instrument":
        frame.loc[0, "instrument_id"] = "ETHUSDT.BINANCE"
    with pytest.raises(ValueError):
        evidence.audit_fills(frame, IDENTITY)


def test_evidence_hashes_are_checked_before_use(tmp_path):
    path = tmp_path / "evidence"
    path.write_bytes(b"retained")
    digest = hashlib.sha256(b"retained").hexdigest()
    assert evidence.verified_bytes(path, digest) == b"retained"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        evidence.verified_bytes(path, digest)


def test_duplicate_normalization_does_not_double_one_path():
    prices = pd.Series(
        [100.0, 100.0, 90.0, 110.0], index=pd.date_range("2022-12-31", periods=4, tz="UTC")
    )
    curve, _ = evidence.account_fills(evidence.audit_fills(fills(), IDENTITY), prices)
    raw = evidence.basket_metrics({"v18": curve, "v40": curve}, {"v18": 1.0, "v40": 1.0})
    normalized = evidence.basket_metrics({"v18": curve, "v40": curve}, {"v18": 0.5, "v40": 0.5})
    assert raw["net_pnl_usdt"]["base"] == pytest.approx(normalized["net_pnl_usdt"]["base"] * 2)
    assert normalized["max_daily_marked_btc_quantity"] == pytest.approx(0.001)


def test_only_exact_terminal_sell_may_lack_signal_lineage():
    frame = fills()
    frame.loc[1, "signal_id"] = ""
    with pytest.raises(ValueError, match="lineage"):
        evidence.audit_fills(frame, IDENTITY)
    frame.loc[1, "ts_event"] = (evidence.END - pd.Timedelta(hours=1)).value
    checked = evidence.audit_fills(frame, IDENTITY)
    assert checked["terminal_close_without_signal"].sum() == 1


def test_missing_hash_references_exclude_instead_of_guessing_bundle(tmp_path):
    directory = tmp_path / "docs/progress"
    directory.mkdir(parents=True)
    (directory / "phase-2-research-v8-confirmation-results.json").write_text(
        json.dumps({"candidate": IDENTITY})
    )
    with pytest.raises(ValueError, match="lacks manifest-and-fills hash"):
        evidence.load_candidate(tmp_path, {**IDENTITY, "protocol": "v8"}, pd.Series(dtype=float))


def test_report_refuses_to_overwrite_before_reading_inputs(tmp_path):
    path = tmp_path / "old.json"
    path.write_text("retained")
    with pytest.raises(SystemExit):
        evidence.main(
            [
                "--repo-root",
                str(tmp_path),
                "--output-json",
                str(path),
                "--output-md",
                str(tmp_path / "new.md"),
            ]
        )
    assert path.read_text() == "retained"


def test_partial_cohort_is_explicit(monkeypatch):
    prices = pd.Series(
        [100.0, 100.0, 90.0, 110.0], index=pd.date_range("2022-12-31", periods=4, tz="UTC")
    )
    monkeypatch.setattr(evidence, "load_benchmark", lambda root: (prices, {}))
    monkeypatch.setattr(evidence, "CANDIDATE_SPECS", [{"protocol": "v18"}, {"protocol": "v40"}])

    def load(root, spec, closes):
        if spec["protocol"] == "v40":
            raise ValueError("missing proof")
        curve, metrics = evidence.account_fills(evidence.audit_fills(fills(), IDENTITY), closes)
        return curve, {**metrics, "protocol": "v18", "execution_path_sha256": "fixture"}

    monkeypatch.setattr(evidence, "load_candidate", load)
    report = evidence.build_report(None)
    assert report["cohort_status"] == "partial"
    assert report["verified_candidates"] == 1 and report["requested_candidates"] == 2
    assert report["excluded"][0]["protocol"] == "v40"


@pytest.mark.parametrize("fault", [None, "missing_day", "future_day"])
def test_benchmark_requires_hashed_complete_historical_coverage(tmp_path, fault):
    dates = pd.date_range("2022-12-31", "2025-12-31", tz="UTC")
    if fault == "missing_day":
        dates = dates.delete(20)
    elif fault == "future_day":
        dates = dates.append(pd.DatetimeIndex([evidence.END]))
    frame = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "close": 100.0})
    raw = frame.to_csv(index=False).encode()
    (tmp_path / "prices.csv").write_bytes(raw)
    directory = tmp_path / "docs/progress"
    directory.mkdir(parents=True)
    (directory / "phase-2-research-v49-provider-qualification.json").write_text(
        json.dumps({"closes": {"path": "prices.csv", "sha256": hashlib.sha256(raw).hexdigest()}})
    )
    if fault:
        with pytest.raises(ValueError, match="incomplete|beyond authorized"):
            evidence.load_benchmark(tmp_path)
    else:
        closes, metadata = evidence.load_benchmark(tmp_path)
        assert len(closes) == metadata["rows"] == 1097


@pytest.mark.parametrize("wrong_pnl", [False, True])
def test_verified_bundle_reconciles_recorded_pnl(tmp_path, wrong_pnl):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    fills().to_parquet(bundle / "fills.parquet", index=False)
    manifest = {
        "kind": "backtest",
        "git_dirty": False,
        "nautilus_version": "fixture",
        "backtest_start": evidence.START.isoformat(),
        "backtest_end": (evidence.END - pd.Timedelta(hours=1)).isoformat(),
        "signal_source": {"filter": IDENTITY},
    }
    (bundle / "run_manifest.json").write_text(json.dumps(manifest))
    ref = {
        "path": "bundle",
        "manifest_sha256": hashlib.sha256((bundle / "run_manifest.json").read_bytes()).hexdigest(),
        "fills_sha256": hashlib.sha256((bundle / "fills.parquet").read_bytes()).hexdigest(),
    }
    directory = tmp_path / "docs/progress"
    directory.mkdir(parents=True)
    (directory / "phase-2-research-v16-confirmation-results.json").write_text(
        json.dumps(
            {
                "candidate": {
                    **IDENTITY,
                    "bundle_runs": [ref],
                    "base_net_pnl": 42 if wrong_pnl else 0.009748,
                    "stress_net_pnl": 0.009685,
                }
            }
        )
    )
    prices = pd.Series(100.0, index=pd.date_range("2022-12-31", "2025-12-31", tz="UTC"))
    if wrong_pnl:
        with pytest.raises(ValueError, match="does not reconcile"):
            evidence.load_candidate(tmp_path, {**IDENTITY, "protocol": "v16"}, prices)
    else:
        _, metrics = evidence.load_candidate(tmp_path, {**IDENTITY, "protocol": "v16"}, prices)
        assert metrics["net_pnl_usdt"]["base"] == pytest.approx(0.009748)
        assert metrics["evidence"]["fills_sha256"] == ref["fills_sha256"]

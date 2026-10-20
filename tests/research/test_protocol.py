"""Synthetic wiring checks; no protocol data or performance is evaluated."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from apps.research import protocol


@pytest.mark.parametrize(
    ("options", "bar", "lag", "unit", "shift"),
    [
        ({}, "1D", 0, "bar", 1),
        (
            {"bar": "1min", "execution_lag_bars": 1, "null": {"shift_unit": "day"}},
            "1min",
            1,
            "day",
            1440,
        ),
        ({"bar": "1h", "null": {"shift_unit": "day"}}, "1h", 0, "day", 24),
        ({"bar": "15min"}, "15min", 0, "bar", 1),
    ],
)
def test_report_options_reach_replay_and_null(
    tmp_path, monkeypatch, options, bar, lag, unit, shift
):
    contract = {
        "protocol": 0,
        "mechanism_module": "synthetic",
        "data": {"dataset": "spot_klines_1m", "symbols": ["A"]},
        "null": {"trials": 2, "seed": 1},
        "notional_usdt": 1000.0,
        "cost_scenarios_bps_per_fill": {"base": 12.0, "stress": 15.0},
        "candidates": {"toy": {"params": {}, "source": "toy", "model_version": "toy"}},
        "windows": {"development": ["2020-01-01", "2020-01-01"]},
        "gates": {},
    }
    for key, value in options.items():
        if key == "null":
            contract[key].update(value)
        else:
            contract[key] = value
    index = pd.date_range("2020-01-01", periods=3, freq="min", tz="UTC")
    prices = pd.DataFrame({"close": 100.0}, index=index)
    weights = pd.DataFrame({"A": 0.0}, index=index)
    calls = {"run": [], "window": [], "null": []}

    def fake_run(*args, **kwargs):
        calls["run"].append(kwargs)
        return {"base_net_pnl": 0.0, "base_pnl_sha256": "same"}

    def fake_window(*args, **kwargs):
        calls["window"].append(kwargs)
        return index, np.zeros((3, 1)), np.zeros((3, 1))

    def fake_null(*args, **kwargs):
        calls["null"].append(kwargs)
        return {}

    module = SimpleNamespace(PRICE_DATASET="spot_klines_1m", target_weights=lambda *args: weights)
    monkeypatch.setattr(protocol, "load_contract", lambda path: (contract, "contract-sha"))
    monkeypatch.setattr(protocol.importlib, "import_module", lambda name: module)
    monkeypatch.setattr(
        protocol.data, "load_frames", lambda *args, **kwargs: {"spot_klines_1m": {"A": prices}}
    )
    monkeypatch.setattr(protocol.replay, "run", fake_run)
    monkeypatch.setattr(protocol.replay, "window_arrays", fake_window)
    monkeypatch.setattr(protocol.gates, "shift_null", fake_null)
    monkeypatch.setattr(protocol.gates, "apply_gates", lambda *args: {"checks": {}, "pass": True})
    monkeypatch.setattr(protocol, "_manifest_digest", lambda *args: "data-sha")
    monkeypatch.setattr(protocol, "_update_registry", lambda *args: None)

    report = protocol.run_stage(
        tmp_path / "toy.json",
        "development",
        root=tmp_path,
        results_dir=tmp_path / "results",
        registry_path=tmp_path / "registry.json",
    )
    assert report["bar"] == bar
    assert report["execution_lag_bars"] == lag
    assert report["null_shift_unit"] == unit
    assert len(calls["run"]) == 2
    for call in calls["run"] + calls["window"]:
        assert call["bar"] == bar
        assert call["lag"] == lag
    assert calls["null"][0]["shift_unit"] == shift
    assert report["candidates"]["toy"]["gates"]["checks"]["duplicate_replay_identical"]


@pytest.mark.parametrize("bar", ["7min", "2D", "0D"])
def test_day_null_requires_an_integer_number_of_bars_per_day(tmp_path, monkeypatch, bar):
    monkeypatch.setattr(
        protocol, "load_contract", lambda path: ({"bar": bar, "null": {"shift_unit": "day"}}, "sha")
    )
    with pytest.raises(ValueError, match="integer number of bars"):
        protocol.run_stage(tmp_path / "toy.json", "development")


def test_unknown_null_shift_unit_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        protocol, "load_contract", lambda path: ({"null": {"shift_unit": "week"}}, "sha")
    )
    with pytest.raises(ValueError, match="shift_unit"):
        protocol.run_stage(tmp_path / "toy.json", "development")

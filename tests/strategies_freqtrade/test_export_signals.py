"""Synthetic research-signal export and temporary-store CLI checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from pydantic import ValidationError

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research import export_signals

SOURCE = "rule_crypto_tsmom_vol_v1"
MODEL = "trend-learning-v1"


def _export(weights: pd.DataFrame, **kwargs) -> list[SignalEvent]:
    return export_signals.weights_to_signals(
        weights,
        **(
            {
                "source": SOURCE,
                "model_version": MODEL,
                "start": "2024-01-01",
                "end": "2024-01-31",
                "emit_weekday": None,
                "long_only": False,
            }
            | kwargs
        ),
    )


def test_weekday_filter_inclusive_dates_and_next_midnight() -> None:
    index = pd.date_range("2024-01-01", periods=28, tz="UTC")
    weights = pd.DataFrame({"BTCUSDT": 0.25, "ETHUSDT": -0.4}, index=index)
    events = _export(weights, start="2024-01-07", end="2024-01-21", emit_weekday=6)

    assert len(events) == 6
    expected = [
        pd.Timestamp(day, tz="UTC").value for day in ["2024-01-08", "2024-01-15", "2024-01-22"]
    ]
    assert [event.ts_event for event in events] == [stamp for stamp in expected for _ in range(2)]
    assert [event.symbol for event in events] == ["BTCUSDT", "ETHUSDT"] * 3
    assert len({event.signal_id for event in events}) == 6
    assert events[0].signal_id == f"{SOURCE}:{MODEL}:BTCUSDT:2024-01-07"


@pytest.mark.parametrize(
    ("weight", "long_only", "side", "score"),
    [
        (0.3, False, "buy", 0.3),
        (1.5, False, "buy", 1.0),
        (-0.4, False, "sell", -0.4),
        (-1.5, False, "sell", -1.0),
        (-0.4, True, "flat", 0.0),
        (-1.5, True, "flat", 0.0),
        (0.0, False, "flat", 0.0),
        (0.0, True, "flat", 0.0),
        (0.3, True, "buy", 0.3),
    ],
)
def test_side_score_metadata_and_defaults(
    weight: float, long_only: bool, side: str, score: float
) -> None:
    weights = pd.DataFrame(
        {"BTCUSDT": [weight]}, index=pd.date_range("2024-01-07", periods=1, tz="UTC")
    )
    (event,) = _export(weights, long_only=long_only)

    assert (event.side, event.score) == (side, score)
    assert event.metadata == {"weight": weight, "learning_simulation": True}
    assert event.venue == "BINANCE"
    assert event.horizon == "7d"
    assert event.ttl_seconds == 8 * 86_400
    assert event.confidence == 0.75
    assert SignalEvent.model_validate_json(event.model_dump_json()) == event


def test_daily_refreshes_and_deterministic_store_idempotence(tmp_path: Path) -> None:
    index = pd.date_range("2024-01-01", periods=3, tz="UTC")
    weights = pd.DataFrame({"BTCUSDT": 0.25, "ETHUSDT": 0.0}, index=index)
    original = weights.copy(deep=True)
    events = _export(weights)
    assert len(events) == 6
    assert events == _export(weights)
    assert len({event.signal_id for event in events}) == 6
    store = SignalStore(tmp_path / "signals.db")
    assert store.write_many(events) == (6, 0)
    assert store.write_many(_export(weights)) == (0, 6)
    assert len(store.replay()) == 6
    assert {event.signal_id: event for event in store.replay()} == {
        event.signal_id: event for event in events
    }
    pd.testing.assert_frame_equal(weights, original)


def test_custom_signal_fields() -> None:
    weights = pd.DataFrame(
        {"BTCUSDT": [0.2]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC")
    )
    (event,) = _export(weights, venue="SIM", horizon="1d", ttl_seconds=86_400, confidence=0.9)
    assert (event.venue, event.horizon, event.ttl_seconds, event.confidence) == (
        "SIM",
        "1d",
        86_400,
        0.9,
    )


def test_invalid_source_is_rejected_by_signal_schema() -> None:
    weights = pd.DataFrame(
        {"BTCUSDT": [0.2]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC")
    )
    with pytest.raises(ValidationError, match="family"):
        _export(weights, source="bad-source")


@pytest.mark.parametrize("weight", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_weights_are_rejected(weight: float) -> None:
    weights = pd.DataFrame(
        {"BTCUSDT": [weight]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC")
    )
    with pytest.raises(ValueError, match="Non-finite weight"):
        _export(weights)


def test_empty_selection_emits_nothing() -> None:
    weights = pd.DataFrame(
        {"BTCUSDT": [0.2]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC")
    )
    assert _export(weights, emit_weekday=6) == []
    assert _export(weights, start="2024-01-02") == []


@pytest.mark.parametrize("end", ["2026-09-01", "2026-09-02", "2027-01-01"])
def test_cli_refuses_blind_before_loading_or_writing(
    end: str, tmp_path: Path, monkeypatch, capsys
) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("Blind refusal must happen before loading data or opening the store")

    monkeypatch.setattr(export_signals.data, "load_frames", forbidden)
    monkeypatch.setattr(export_signals, "SignalStore", forbidden)
    with pytest.raises(SystemExit) as exc:
        export_signals.main(
            [
                str(tmp_path / "nonexistent.json"),
                "--candidate",
                "trend",
                "--start",
                "2024-01-01",
                "--end",
                end,
                "--signal-store-path",
                str(tmp_path / "signals.db"),
            ]
        )
    assert exc.value.code == 2
    assert "sealed blind starting 2026-09-01" in capsys.readouterr().err
    assert not (tmp_path / "signals.db").exists()


@pytest.mark.parametrize("weekly", [True, False])
def test_cli_loads_contract_mechanism_and_writes_idempotently(
    weekly: bool, tmp_path: Path, monkeypatch, capsys
) -> None:
    index = pd.date_range("2024-01-06", periods=10, tz="UTC")
    weights = pd.DataFrame({"BTCUSDT": 0.25, "ETHUSDT": -0.5}, index=index)
    frames = {"synthetic": {symbol: weights[[symbol]] for symbol in weights}}
    params = {"rebalance_weekday": 6} if weekly else {}
    spec = {"symbols": ["BTCUSDT", "ETHUSDT"]}
    spec.update({"dataset": "synthetic"} if weekly else {"datasets": ["synthetic", "metrics"]})
    contract = {
        "mechanism_module": "synthetic_signal_mechanism",
        "data": spec,
        "candidates": {"trend": {"source": SOURCE, "model_version": MODEL, "params": params}},
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract))
    data_root, db = tmp_path / "cache", tmp_path / "signals.db"
    calls = []

    def load_frames(datasets, symbols, *, root):
        assert datasets == (["synthetic"] if weekly else ["synthetic", "metrics"])
        assert symbols == ["BTCUSDT", "ETHUSDT"]
        assert root == data_root
        calls.append("load")
        return frames

    def target_weights(actual_frames, candidate, actual_params):
        assert actual_frames is frames
        assert candidate == "trend"
        assert actual_params == params
        calls.append("weights")
        return weights

    module = ModuleType("synthetic_signal_mechanism")
    monkeypatch.setattr(module, "target_weights", target_weights, raising=False)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(export_signals.data, "load_frames", load_frames)
    argv = [
        str(contract_path),
        "--candidate",
        "trend",
        "--start",
        "2024-01-07",
        "--end",
        "2024-01-14",
        "--long-only",
        "--model-version-suffix",
        "learning-spot",
        "--signal-store-path",
        str(db),
        "--data-root",
        str(data_root),
    ]
    count = 2 if weekly else 8
    assert export_signals.main(argv) == 0
    assert json.loads(capsys.readouterr().out) == {
        "written": 2 * count,
        "duplicates": 0,
        "by_symbol": {"BTCUSDT": count, "ETHUSDT": count},
        "by_side": {"buy": count, "flat": count},
    }
    assert export_signals.main(argv) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert (repeated["written"], repeated["duplicates"]) == (0, 2 * count)
    assert calls == ["load", "weights", "load", "weights"]
    events = SignalStore(db).replay()
    assert len(events) == 2 * count
    assert {event.model_version for event in events} == {MODEL + "-learning-spot"}
    assert {event.source for event in events} == {SOURCE}
    assert {event.side for event in events} == {"buy", "flat"}
    assert all(event.metadata["learning_simulation"] is True for event in events)
    assert {event.metadata["weight"] for event in events} == {0.25, -0.5}
    assert events[0].ts_event == pd.Timestamp("2024-01-08", tz="UTC").value
    assert events[-1].ts_event == pd.Timestamp("2024-01-15", tz="UTC").value

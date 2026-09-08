import pandas as pd
import pytest

from apps.ops.research_portfolio_cash import event_cash_bounds


def frame(times, prices):
    return pd.DataFrame(
        {
            "fill_id": ["buy", "sell"],
            "ts_event": [pd.Timestamp(t).value for t in times],
            "quantity": [0.001, 0.001],
            "price": prices,
            "side": ["BUY", "SELL"],
        }
    )


def test_same_day_roundtrip_needs_cash_despite_zero_end_of_day_inventory():
    fills = {"a": frame(["2023-01-01T09:00:00Z", "2023-01-01T17:00:00Z"], [100000.0, 100000.0])}
    result = event_cash_bounds(fills, {"a": 1.0}, 100.0)
    base = result["scenarios"]["base"]
    assert base["required_initial_cash_sell_before_buy_usdt"] == pytest.approx(100.12)
    assert base["required_initial_cash_buy_before_sell_usdt"] == pytest.approx(100.12)
    assert base["covers_buy_before_sell_bound"] is False
    assert base["final_cash_change_usdt"] == pytest.approx(-0.24)
    assert result["mixed_buy_sell_timestamp_count"] == 0
    assert result["new_fills_created"] is False


def test_cross_sleeve_tie_order_is_bounded_not_invented():
    fills = {
        "a": frame(["2023-01-01T01:00:00Z", "2023-01-02T12:00:00Z"], [100000.0, 100000.0]),
        "b": frame(["2023-01-02T12:00:00Z", "2023-01-03T12:00:00Z"], [200000.0, 200000.0]),
    }
    result = event_cash_bounds(fills, {"a": 1.0, "b": 1.0}, 250.0)
    gross, base = result["scenarios"]["gross"], result["scenarios"]["base"]
    assert gross["required_initial_cash_sell_before_buy_usdt"] == 200.0
    assert gross["required_initial_cash_buy_before_sell_usdt"] == 300.0
    assert base["required_initial_cash_sell_before_buy_usdt"] == pytest.approx(200.48)
    assert base["required_initial_cash_buy_before_sell_usdt"] == pytest.approx(300.36)
    assert base["final_cash_change_usdt"] == pytest.approx(-0.72)
    assert base["covers_sell_before_buy_bound"] is True
    assert base["covers_buy_before_sell_bound"] is False
    assert result["mixed_buy_sell_timestamp_count"] == 1
    assert result["actual_execution_order_known"] is False
    reordered = event_cash_bounds(
        {"b": fills["b"].iloc[::-1], "a": fills["a"]}, {"b": 1.0, "a": 1.0}, 250.0
    )
    assert result == reordered


def test_existing_duplicate_normalization_and_unspent_profits():
    one = frame(["2023-01-01T01:00:00Z", "2023-01-02T12:00:00Z"], [100000.0, 110000.0])
    single = event_cash_bounds({"a": one}, {"a": 1.0}, 500.0)
    double = event_cash_bounds({"a": one, "b": one}, {"a": 1.0, "b": 1.0}, 500.0)
    normalized = event_cash_bounds({"a": one, "b": one}, {"a": 0.5, "b": 0.5}, 500.0)
    assert single["scenarios"] == normalized["scenarios"]
    assert double["scenarios"]["gross"]["required_initial_cash_buy_before_sell_usdt"] == 200.0
    assert single["scenarios"]["gross"]["final_cash_change_usdt"] == 10.0


@pytest.mark.parametrize(
    "fault",
    ["future", "nan", "negative_quantity", "side", "duplicate", "weight", "capital", "cohort"],
)
def test_invalid_cash_inputs_fail_closed(fault):
    one = frame(["2023-01-01T01:00:00Z", "2023-01-02T12:00:00Z"], [100000.0, 110000.0])
    weights, capital = {"a": 1.0}, 500.0
    if fault == "future":
        one.loc[1, "ts_event"] = pd.Timestamp("2026-09-01T00:00:00Z").value
    elif fault == "nan":
        one.loc[0, "price"] = float("nan")
    elif fault == "negative_quantity":
        one.loc[0, "quantity"] = -0.001
    elif fault == "side":
        one.loc[0, "side"] = "flat"
    elif fault == "duplicate":
        one.loc[1, "fill_id"] = "buy"
    elif fault == "weight":
        weights["a"] = -1.0
    elif fault == "capital":
        capital = float("inf")
    elif fault == "cohort":
        weights["b"] = 1.0
    with pytest.raises(ValueError):
        event_cash_bounds({"a": one}, weights, capital)

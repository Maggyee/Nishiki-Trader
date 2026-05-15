"""Tests for `apps/strategies_nautilus/result_schema.py` (ADR-004 §2.2).

Covers:
- Round-trip via `model_validate` and `model_dump_json`.
- Schema-version guard rejects anything not `backtest.v1`.
- Each top-level required field rejected when missing.
- Format validators on `run_id`, `git_commit`, ISO ms-UTC timestamps.
- Range checks on counts, win_rate, max_drawdown.
- ADR-004 §2.6 forward compatibility: appended fields are tolerated.
"""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from apps.strategies_nautilus.result_schema import (
    SCHEMA_VERSION,
    BacktestManifest,
)

VALID_MANIFEST: dict = {
    "schema_version": "backtest.v1",
    "run_id": "20260615-021530Z-9a2c4f81",
    "kind": "backtest",
    "trader_id": "TRADER-001",
    "machine_id": "home-frp",
    "git_commit": "1a174c70123456789abcdef0123456789abcdef0",
    "git_dirty": False,
    "nautilus_version": "1.220.0",
    "python_version": "3.12.13",
    "started_at": "2026-06-15T02:15:30.000Z",
    "finished_at": "2026-06-15T02:16:42.318Z",
    "elapsed_seconds": 72.318,
    "backtest_start": "2026-01-01T00:00:00.000Z",
    "backtest_end": "2026-06-01T00:00:00.000Z",
    "venues": ["BINANCE"],
    "instruments": ["BTCUSDT", "ETHUSDT"],
    "strategies": [
        {
            "name": "baseline_signal_strategy",
            "params": {"max_position_pct": 0.05, "min_confidence": 0.55},
        }
    ],
    "risk_rules": [
        {"name": "daily_drawdown_stop", "params": {"max_pct": 0.05}}
    ],
    "signal_source": {
        "store_path": "data/bridge/signals.db",
        "store_sha256": "8c0be6f1" * 8,
        "filter": {"source": "freqai_v1", "model_version": "2026-05-14"},
        "row_count": 4321,
        "min_ts_event_ns": 1735689600000000000,
        "max_ts_event_ns": 1748736000000000000,
    },
    "data_catalog": {
        "path": "data/catalog/",
        "instruments": [
            {"id": "BTCUSDT.BINANCE", "bars": "1m", "rows": 217440}
        ],
    },
    "totals": {
        "iterations": 217440,
        "events": 184902,
        "orders": 1037,
        "positions": 215,
        "fills": 1842,
    },
    "stats_pnls": {
        "USDT": {
            "PnL (total)": 3142.18,
            "PnL% (total)": 31.4218,
            "Win Rate": 0.546,
            "Sharpe Ratio (252 days)": 1.82,
            "Sortino Ratio (252 days)": 2.41,
            "Profit Factor": 1.71,
            "Risk Return Ratio": 0.32,
        }
    },
    "stats_returns": {
        "Returns Volatility (252 days)": 0.132,
        "Average (Return)": 0.0007,
        "Sharpe Ratio (252 days)": 1.82,
    },
}


@pytest.fixture
def payload() -> dict:
    return deepcopy(VALID_MANIFEST)


def test_round_trip_via_json(payload: dict) -> None:
    manifest = BacktestManifest.model_validate(payload)
    again = BacktestManifest.model_validate_json(manifest.model_dump_json())
    assert again == manifest


def test_stats_pnls_keys_passed_through_verbatim(payload: dict) -> None:
    # ADR-004 §2.2: stats_pnls values are forwarded from NautilusTrader's
    # PortfolioAnalyzer.get_performance_stats_pnls() unchanged. Schema must
    # not pin individual key names — they depend on the active Statistic
    # registry on the Nautilus side.
    manifest = BacktestManifest.model_validate(payload)
    assert "PnL (total)" in manifest.stats_pnls["USDT"]
    assert "Sharpe Ratio (252 days)" in manifest.stats_pnls["USDT"]
    assert manifest.stats_pnls["USDT"]["PnL (total)"] == 3142.18


def test_round_trip_preserves_iso_timestamp_text(payload: dict) -> None:
    manifest = BacktestManifest.model_validate(payload)
    j = json.loads(manifest.model_dump_json())
    assert j["started_at"] == "2026-06-15T02:15:30.000Z"
    assert j["finished_at"] == "2026-06-15T02:16:42.318Z"
    assert j["backtest_start"] == "2026-01-01T00:00:00.000Z"


def test_schema_version_constant_matches_literal() -> None:
    assert SCHEMA_VERSION == "backtest.v1"


def test_schema_version_v2_rejected(payload: dict) -> None:
    payload["schema_version"] = "backtest.v2"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_schema_version_typo_rejected(payload: dict) -> None:
    payload["schema_version"] = "backtest_v1"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_kind_must_be_known_enum(payload: dict) -> None:
    payload["kind"] = "shadow"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


@pytest.mark.parametrize(
    "key",
    [
        "schema_version",
        "run_id",
        "kind",
        "trader_id",
        "machine_id",
        "git_commit",
        "git_dirty",
        "nautilus_version",
        "python_version",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "backtest_start",
        "backtest_end",
        "venues",
        "instruments",
        "strategies",
        "risk_rules",
        "signal_source",
        "data_catalog",
        "totals",
        "stats_pnls",
        "stats_returns",
    ],
)
def test_each_required_top_level_field_rejected_when_missing(
    payload: dict, key: str
) -> None:
    payload.pop(key)
    with pytest.raises(ValidationError) as exc_info:
        BacktestManifest.model_validate(payload)
    assert key in str(exc_info.value)


def test_run_id_format_rejects_wrong_shape(payload: dict) -> None:
    payload["run_id"] = "2026-06-15-9a2c4f81"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_run_id_format_rejects_uppercase_hex(payload: dict) -> None:
    payload["run_id"] = "20260615-021530Z-9A2C4F81"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_git_commit_must_be_lowercase_hex(payload: dict) -> None:
    payload["git_commit"] = "DEADBEEF"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_git_commit_short_seven_hex_accepted(payload: dict) -> None:
    payload["git_commit"] = "1a174c7"
    manifest = BacktestManifest.model_validate(payload)
    assert manifest.git_commit == "1a174c7"


def test_started_at_must_be_iso_ms_utc(payload: dict) -> None:
    payload["started_at"] = "2026-06-15 02:15:30"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_started_at_without_ms_rejected(payload: dict) -> None:
    payload["started_at"] = "2026-06-15T02:15:30Z"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_finished_at_before_started_at_rejected(payload: dict) -> None:
    payload["finished_at"] = "2026-06-15T02:15:29.999Z"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_backtest_end_before_start_rejected(payload: dict) -> None:
    payload["backtest_end"] = "2025-12-31T23:59:59.999Z"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_stats_pnls_empty_dict_rejected(payload: dict) -> None:
    payload["stats_pnls"] = {}
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_stats_pnls_empty_currency_metrics_rejected(payload: dict) -> None:
    payload["stats_pnls"]["USDT"] = {}
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_stats_pnls_currency_can_have_arbitrary_metric_keys(payload: dict) -> None:
    # New Statistic plugins on the Nautilus side must round-trip through.
    payload["stats_pnls"]["USDT"]["Custom Metric (v2)"] = 0.42
    manifest = BacktestManifest.model_validate(payload)
    assert manifest.stats_pnls["USDT"]["Custom Metric (v2)"] == 0.42


def test_stats_returns_can_be_empty_when_no_trades(payload: dict) -> None:
    # Backtests with no fills produce an empty returns dict from the analyzer.
    payload["stats_returns"] = {}
    manifest = BacktestManifest.model_validate(payload)
    assert manifest.stats_returns == {}


def test_negative_count_rejected(payload: dict) -> None:
    payload["totals"]["fills"] = -1
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_signal_source_sha256_must_be_64_hex(payload: dict) -> None:
    payload["signal_source"]["store_sha256"] = "8c0be6f1"
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_signal_source_max_ts_below_min_rejected(payload: dict) -> None:
    payload["signal_source"]["min_ts_event_ns"] = 2_000_000_000_000_000_000
    payload["signal_source"]["max_ts_event_ns"] = 1_700_000_000_000_000_000
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_venues_must_be_non_empty(payload: dict) -> None:
    payload["venues"] = []
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_strategies_must_be_non_empty(payload: dict) -> None:
    payload["strategies"] = []
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_data_catalog_instruments_must_be_non_empty(payload: dict) -> None:
    payload["data_catalog"]["instruments"] = []
    with pytest.raises(ValidationError):
        BacktestManifest.model_validate(payload)


def test_extra_top_level_field_ignored_for_forward_compat(payload: dict) -> None:
    payload["future_field_added_in_v1_3"] = {"some": "data"}
    manifest = BacktestManifest.model_validate(payload)
    dumped = manifest.model_dump()
    assert "future_field_added_in_v1_3" not in dumped


def test_extra_nested_field_passed_through_in_stats_pnls(payload: dict) -> None:
    # stats_pnls is a free-form dict; new Nautilus metric keys are preserved
    # rather than dropped (in contrast to typed nested models which use ignore).
    payload["stats_pnls"]["USDT"]["future_metric"] = 0.42
    manifest = BacktestManifest.model_validate(payload)
    assert manifest.stats_pnls["USDT"]["future_metric"] == 0.42


def test_kind_paper_and_live_accepted(payload: dict) -> None:
    for kind in ("paper", "live"):
        payload["kind"] = kind
        manifest = BacktestManifest.model_validate(payload)
        assert manifest.kind == kind


def test_model_is_frozen(payload: dict) -> None:
    manifest = BacktestManifest.model_validate(payload)
    with pytest.raises(ValidationError):
        manifest.kind = "paper"  # type: ignore[misc]

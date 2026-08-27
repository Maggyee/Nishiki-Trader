"""Offline tests for the ADR-014 §5 meta-analysis tool (no network access)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from apps.ops.research_meta_analysis import (
    NullParams,
    _binom_sf,
    _closes_from_kline_zip,
    _parse_checksum_file,
    buy_and_hold_stats,
    load_closes,
    run_random_timing_null,
    window,
)


def _synthetic_closes(tmp_path: Path) -> Path:
    dates = pd.date_range("2020-01-01", "2025-12-31", freq="D", tz="UTC")
    rng = np.random.default_rng(7)
    steps = rng.normal(loc=0.4, scale=30.0, size=len(dates))
    closes = 10_000.0 + np.cumsum(steps)
    closes = np.maximum(closes, 1_000.0)
    path = tmp_path / "closes.csv"
    pd.DataFrame({"date": dates.date, "close": closes}).to_csv(path, index=False)
    return path


def test_load_closes_rejects_calendar_gaps(tmp_path: Path) -> None:
    path = tmp_path / "gappy.csv"
    pd.DataFrame({"date": ["2020-01-01", "2020-01-03"], "close": [1.0, 2.0]}).to_csv(
        path, index=False
    )
    with pytest.raises(ValueError, match="calendar gaps"):
        load_closes(path)


def test_buy_and_hold_stats_match_endpoints(tmp_path: Path) -> None:
    closes = load_closes(_synthetic_closes(tmp_path))
    dev = window(closes, "2020-01-01", "2022-12-31")
    stats = buy_and_hold_stats(dev, trade_size=0.001)
    assert stats["pnl"] == pytest.approx((dev.iloc[-1] - dev.iloc[0]) * 0.001)
    assert stats["months_total"] == 36
    assert 0 <= stats["months_positive"] <= 36
    assert 0 <= stats["years_positive"] <= 3


def test_random_timing_null_is_deterministic_and_bounded(tmp_path: Path) -> None:
    closes = load_closes(_synthetic_closes(tmp_path))
    dev = window(closes, "2020-01-01", "2022-12-31")
    conf = window(closes, "2023-01-01", "2025-12-31")
    params = NullParams(n_trials=200, seed=123)
    first = run_random_timing_null(dev, conf, params)
    second = run_random_timing_null(dev, conf, params)
    assert first == second
    assert 0.0 <= first["p_two_stage_pass"] <= first["p_dev_pass"] <= 1.0
    assert first["n_trials"] == 200


def test_binom_sf_basic_properties() -> None:
    assert _binom_sf(0, 10, 0.3) == pytest.approx(1.0)
    assert _binom_sf(11, 10, 0.3) == pytest.approx(0.0, abs=1e-12)
    assert _binom_sf(3, 10, 0.3) > _binom_sf(5, 10, 0.3)
    # P(X >= 1) = 1 - (1-p)^n
    assert _binom_sf(1, 4, 0.5) == pytest.approx(1 - 0.5**4)


def test_closes_from_kline_zip_handles_ms_and_us_timestamps() -> None:
    ms_row = "1577836800000,7195.24,7255.0,7175.15,7200.85,16792.38,1577923199999,0,0,0,0,0"
    us_row = "1735689600000000,93500.0,94000.0,93000.0,93800.0,1000.0,1735775999999999,0,0,0,0,0"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BTCUSDT-1d-test.csv", ms_row + "\n" + us_row + "\n")
    rows = _closes_from_kline_zip(buffer.getvalue())
    assert rows == [("2020-01-01", 7200.85), ("2025-01-01", 93800.0)]


def test_parse_checksum_file_accepts_standard_format() -> None:
    digest = "a" * 64
    assert _parse_checksum_file(f"{digest}  BTCUSDT-1d-2020-01.zip\n".encode()) == digest
    with pytest.raises(ValueError):
        _parse_checksum_file(b"<html>blocked</html>")

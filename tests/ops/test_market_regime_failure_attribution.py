from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from notebooks.market_regime_failure_attribution import (
    _json_safe,
    _monthly_market_metrics,
)


def test_monthly_market_metrics_uses_open_to_close_and_log_path() -> None:
    frame = pd.DataFrame(
        {
            "open": [100.0, 110.0, 115.0],
            "high": [111.0, 116.0, 122.0],
            "low": [99.0, 109.0, 114.0],
            "close": [110.0, 115.0, 121.0],
        },
        index=pd.date_range("2025-01-01", periods=3, tz="UTC"),
    )

    result = _monthly_market_metrics(frame)

    assert result["return_pct"] == pytest.approx(21.0)
    assert result["trend_efficiency"] == pytest.approx(1.0)
    assert result["max_drawdown_pct"] == pytest.approx(0.0)
    assert result["diagnostic_regime"] == "directional_up"


def test_json_safe_replaces_non_finite_diagnostics_with_null() -> None:
    result = _json_safe(
        {
            "nan": np.float64(np.nan),
            "positive_infinity": math.inf,
            "negative_infinity": -math.inf,
            "count": np.int64(3),
        }
    )

    assert result == {
        "nan": None,
        "positive_infinity": None,
        "negative_infinity": None,
        "count": 3,
    }

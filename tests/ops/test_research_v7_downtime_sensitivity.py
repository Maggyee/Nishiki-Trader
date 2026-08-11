from __future__ import annotations

import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from apps.ops.research_v7_downtime_sensitivity import build_gap_markers

BAR_TYPE = BarType.from_str("BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL")
HOUR_NS = 3_600_000_000_000


def _bar(ts_event: int, close: str) -> Bar:
    price = Price.from_str(close)
    return Bar(
        bar_type=BAR_TYPE,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Quantity.from_str("1.000000"),
        ts_event=ts_event,
        ts_init=ts_event,
    )


def test_build_gap_markers_carries_previous_close_with_zero_volume() -> None:
    bars = [_bar(0, "100.00"), _bar(3 * HOUR_NS, "103.00")]

    markers, gaps = build_gap_markers(
        bars,
        step_ns=HOUR_NS,
        expected_start_ns=0,
        expected_end_ns=3 * HOUR_NS,
    )

    assert [int(marker.ts_event) for marker in markers] == [HOUR_NS, 2 * HOUR_NS]
    assert all(str(marker.close) == "100.00" for marker in markers)
    assert all(float(marker.volume) == 0.0 for marker in markers)
    assert gaps == [
        {
            "previous_real_bar_ts_ns": 0,
            "next_real_bar_ts_ns": 3 * HOUR_NS,
            "synthetic_marker_timestamps_ns": [HOUR_NS, 2 * HOUR_NS],
            "marker_count": 2,
            "carry_forward_close": "100.00",
        }
    ]


def test_build_gap_markers_rejects_non_grid_timestamps() -> None:
    bars = [_bar(0, "100.00"), _bar(HOUR_NS + 1, "101.00")]

    with pytest.raises(ValueError, match="non-grid"):
        build_gap_markers(
            bars,
            step_ns=HOUR_NS,
            expected_start_ns=0,
            expected_end_ns=HOUR_NS + 1,
        )

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.ops.research_v20_confirmation_factor import _audit_confirmation_rows


def _rows(*, omitted: set[date] | None = None) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    current = date(2022, 11, 1)
    end = date(2025, 12, 31)
    while current <= end:
        if current.weekday() < 5 and current not in (omitted or set()):
            values.append({"date": current.isoformat(), "safe_asset_stress": 0.0})
        current += timedelta(days=1)
    return values


def test_v20_confirmation_factor_uses_decision_dates() -> None:
    audit = _audit_confirmation_rows(_rows())
    assert audit["confirmation_decision_count"] >= 700
    assert audit["annual_decision_counts"].keys() == {"2023", "2024", "2025"}
    assert audit["partition_basis"] == "decision_available_at"
    assert audit["forward_fill_used"] is False


def test_v20_confirmation_factor_rejects_large_gap() -> None:
    omitted = {
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    }
    with pytest.raises(ValueError, match="gap exceeds"):
        _audit_confirmation_rows(_rows(omitted=omitted))

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.ops.research_v25_confirmation_factor import _audit_confirmation_rows


def _rows(*, omitted: set[date] | None = None) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    current = date(2023, 1, 1)
    end = date(2025, 12, 31)
    while current <= end:
        if current not in (omitted or set()):
            values.append({"date": current.isoformat(), "value": 1_000_000.0})
        current += timedelta(days=1)
    return values


def test_v25_confirmation_factor_audit_accepts_complete_grid() -> None:
    audit = _audit_confirmation_rows(_rows())

    assert audit["confirmation_row_count"] >= 700
    assert audit["annual_row_counts"].keys() == {"2023", "2024", "2025"}
    assert audit["forward_fill_used"] is False
    assert audit["trailing_rows_ignored"] == 0


def test_v25_confirmation_factor_audit_rejects_large_gap() -> None:
    omitted = {date(2024, 1, 1) + timedelta(days=offset) for offset in range(6)}

    with pytest.raises(ValueError, match="gap exceeds"):
        _audit_confirmation_rows(_rows(omitted=omitted))

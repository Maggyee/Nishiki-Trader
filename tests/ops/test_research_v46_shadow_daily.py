from __future__ import annotations

from apps.ops.research_v46_shadow_daily import (
    fetch_and_snapshot_premium,
    generate_shadow_factor_csv,
)


def test_shadow_daily_v46_functions_exist() -> None:
    assert callable(fetch_and_snapshot_premium)
    assert callable(generate_shadow_factor_csv)

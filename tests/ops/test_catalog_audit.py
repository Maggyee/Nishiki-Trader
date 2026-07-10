from __future__ import annotations

from dataclasses import dataclass

from apps.ops import catalog_audit


@dataclass
class _Bar:
    ts_event: int
    open: float = 1.0
    high: float = 2.0
    low: float = 0.5
    close: float = 1.5
    volume: float = 10.0


class _Catalog:
    rows: dict[str, list[_Bar]] = {}

    def __init__(self, _path: str) -> None:
        pass

    def bars(self, *, bar_types, start, end):
        return [bar for bar in self.rows[bar_types[0]] if start <= bar.ts_event <= end]


def test_catalog_audit_accepts_complete_aligned_series(monkeypatch, tmp_path) -> None:
    half_day = 720 * 60_000_000_000
    _Catalog.rows = {
        "BTC": [_Bar(0), _Bar(half_day)],
        "ETH": [_Bar(0), _Bar(half_day)],
    }
    monkeypatch.setattr(catalog_audit, "ParquetDataCatalog", _Catalog)

    result = catalog_audit.build_catalog_audit(
        tmp_path,
        ["BTC", "ETH"],
        start_date="1970-01-01",
        end_date="1970-01-01",
        interval_minutes=720,
    )

    assert result["expected_rows_per_instrument"] == 2
    assert result["timestamp_alignment"]["aligned"] is True
    assert result["passed"] is True


def test_catalog_audit_rejects_gap_and_cross_asset_misalignment(monkeypatch, tmp_path) -> None:
    half_day = 720 * 60_000_000_000
    _Catalog.rows = {
        "BTC": [_Bar(0), _Bar(half_day)],
        "ETH": [_Bar(0)],
    }
    monkeypatch.setattr(catalog_audit, "ParquetDataCatalog", _Catalog)

    result = catalog_audit.build_catalog_audit(
        tmp_path,
        ["BTC", "ETH"],
        start_date="1970-01-01",
        end_date="1970-01-01",
        interval_minutes=720,
    )

    assert result["timestamp_alignment"]["aligned"] is False
    assert result["instruments"][1]["passed"] is False
    assert result["passed"] is False

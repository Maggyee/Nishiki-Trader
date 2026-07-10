from __future__ import annotations

import hashlib

import pytest

from apps.ops import backfill_funding


def test_download_monthly_funding_reuses_files_and_verifies_checksum(tmp_path) -> None:
    archive = tmp_path / "BTCUSDT-fundingRate-2024-01.zip"
    archive.write_bytes(b"funding-fixture")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (tmp_path / f"{archive.name}.CHECKSUM").write_text(f"{digest}  {archive.name}\n")

    path, actual = backfill_funding.download_monthly_funding(
        symbol="BTCUSDT",
        month="2024-01",
        output_dir=tmp_path,
    )

    assert path == archive
    assert actual == digest


def test_funding_backfill_covers_complete_month_range(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_download_monthly_funding(**kwargs):
        calls.append(kwargs["month"])
        return tmp_path / f"{kwargs['month']}.zip", kwargs["month"].replace("-", "") * 8

    monkeypatch.setattr(
        backfill_funding,
        "download_monthly_funding",
        fake_download_monthly_funding,
    )

    result = backfill_funding.run_funding_backfill(
        symbol="ETHUSDT",
        start_date="2024-01-01",
        end_date="2024-02-29",
        output_dir=tmp_path,
    )

    assert calls == ["2024-01", "2024-02"]
    assert result.months == 2
    assert result.symbol == "ETHUSDT"


def test_funding_backfill_rejects_partial_month(tmp_path) -> None:
    with pytest.raises(ValueError, match="complete calendar months"):
        backfill_funding.run_funding_backfill(
            symbol="SOLUSDT",
            start_date="2024-01-02",
            end_date="2024-01-31",
            output_dir=tmp_path,
        )

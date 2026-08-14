from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v35_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v35-development-results.json")


def test_v35_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == [
        {
            "development_row_count": 757,
            "factor_csv_path": "data/research-v35/factors/irx_development.csv",
            "factor_csv_sha256": "sha256:faa0a6ddeab5b5cfb2484cb2454165ba05dd24de9e4ca756efc21926022a86dd",
            "first_development_date": "2020-01-02",
            "index": "IRX",
            "key": "irx_relief",
            "last_development_date": "2022-12-30",
            "maximum_calendar_gap_days": 4,
            "row_count": 798,
            "snapshot_path": "data/research-v35/raw/irx-20260814T015435Z-d202531a22d3.json",
            "snapshot_sha256": "sha256:d202531a22d37e3fcdd117c0c1e2f938d88a922d76da48b52fc408450b0d31cb",
            "warmup_row_count": 41,
        },
        {
            "development_row_count": 756,
            "factor_csv_path": "data/research-v35/factors/vix1y_development.csv",
            "factor_csv_sha256": "sha256:effd501235910644a76ab350520451d676783483c5db4da40a01b5358866ad70",
            "first_development_date": "2020-01-02",
            "index": "VIX1Y",
            "key": "vix1y_relief",
            "last_development_date": "2022-12-30",
            "maximum_calendar_gap_days": 4,
            "row_count": 797,
            "snapshot_path": "data/research-v35/raw/vix1y-20260814T015507Z-3d61344be84e.json",
            "snapshot_sha256": "sha256:3d61344be84e5c27b1e4afc8bb4c8ad7685617224f618c578e1627ed9e892241",
            "warmup_row_count": 41,
        },
        {
            "development_row_count": 756,
            "factor_csv_path": "data/research-v35/factors/vix6m_development.csv",
            "factor_csv_sha256": "sha256:7287fe5949a11eed1d970a794c4a5e8d260fedaa0eaf23e38b443f604c0d5096",
            "first_development_date": "2020-01-02",
            "index": "VIX6M",
            "key": "vix6m_relief",
            "last_development_date": "2022-12-30",
            "maximum_calendar_gap_days": 4,
            "row_count": 797,
            "snapshot_path": "data/research-v35/raw/vix6m-20260814T015508Z-d1f14aef0a1f.json",
            "snapshot_sha256": "sha256:d1f14aef0a1f202ac7e6ccd0b591a10ec4bf49c4de9d52c0f51a5d64ac860141",
            "warmup_row_count": 41,
        },
    ]
    assert payload["rejected_candidates"] == []
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False


def test_v35_development_results_pass_all_three() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v35.development_results.v1"
    assert payload["development_passer_count"] == 3
    assert payload["confirmation_open_eligible_candidates"] == [
        "irx_relief",
        "vix1y_relief",
        "vix6m_relief",
    ]
    assert payload["recommendation"] == "commit_development_results_before_confirmation_open"
    by_key = {row["key"]: row for row in payload["candidates"]}
    for key in ("irx_relief", "vix1y_relief", "vix6m_relief"):
        assert by_key[key]["classification"] == "development_pass_confirmation_open_eligible"
        assert by_key[key]["reproducible"] is True
        assert by_key[key]["base_net_pnl"] > 0.0
        assert by_key[key]["leave_best_base_net_pnl"] > 0.0
    assert payload["boundaries"]["opens_confirmation"] is False

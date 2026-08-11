from __future__ import annotations

import hashlib
import json

import pytest

from apps.ops.research_v9_review import (
    _confirmation_holdout_status,
    _effective_bundle_blockers,
    _verified_gap_timestamps,
)


def _audit() -> tuple[dict, dict, bytes]:
    gaps = [
        {"synthetic_marker_timestamps_ns": [index * 3_600_000_000_000]}
        for index in range(30)
    ]
    detail = {"official_rows": 26_274, "synthetic_marker_rows": 30, "gaps": gaps}
    raw = json.dumps(detail, sort_keys=True).encode()
    results = {
        "schema_version": "research.v7.downtime_sensitivity_results.v1",
        "provider_audit": {
            "monthly_archive_checksum_matches": 36,
            "gap_windows_checked_with_official_rest": 14,
            "gap_windows_empty_in_official_rest": 14,
        },
        "sensitivity_catalog": {
            "build_report_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}"
        },
    }
    return results, detail, raw


def test_verified_gap_timestamps_require_hash_and_official_rest_evidence() -> None:
    results, detail, raw = _audit()

    timestamps = _verified_gap_timestamps(results, detail, gap_detail_bytes=raw)

    assert len(timestamps) == 30


def test_verified_gap_timestamps_reject_unverified_window() -> None:
    results, detail, raw = _audit()
    results["provider_audit"]["gap_windows_empty_in_official_rest"] = 13

    with pytest.raises(ValueError, match="REST-empty"):
        _verified_gap_timestamps(results, detail, gap_detail_bytes=raw)


def test_effective_blockers_remove_only_exact_verified_row_mismatch() -> None:
    raw = ["catalog_rows=26274!=expected=26304", "invalid_fill_lineage=1"]

    assert _effective_bundle_blockers(raw, verified_gap_count=30) == [
        "invalid_fill_lineage=1"
    ]
    assert _effective_bundle_blockers(raw, verified_gap_count=29) == raw


def test_confirmation_stays_sealed_without_development_passer() -> None:
    assert _confirmation_holdout_status(0) == "sealed_not_opened_no_development_passer"
    assert _confirmation_holdout_status(1) == "sealed_pending_committed_development_review"

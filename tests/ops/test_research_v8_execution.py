from apps.ops.research_v8_execution import STEP_NS, missing_windows
from apps.ops.research_v8_review import _effective_bundle_blockers


def test_missing_windows_groups_boundaries_and_interior_gaps() -> None:
    timestamps = [STEP_NS, 3 * STEP_NS, 4 * STEP_NS]

    assert missing_windows(
        timestamps,
        expected_start_ns=0,
        expected_end_ns=5 * STEP_NS,
    ) == [[0], [2 * STEP_NS], [5 * STEP_NS]]


def test_missing_windows_returns_empty_for_complete_grid() -> None:
    timestamps = [0, STEP_NS, 2 * STEP_NS]

    assert (
        missing_windows(
            timestamps,
            expected_start_ns=0,
            expected_end_ns=2 * STEP_NS,
        )
        == []
    )


def test_v8_review_removes_only_session_explained_row_blocker() -> None:
    audit = {
        "passed": True,
        "official_bar_rows": 26_303,
        "verified_no_kline_rows": 1,
        "expected_clock_rows": 26_304,
    }

    assert _effective_bundle_blockers(
        ["catalog_rows=26303!=expected=26304", "invalid_fill_lineage=1"],
        audit,
    ) == ["invalid_fill_lineage=1"]


def test_v8_review_keeps_row_blocker_when_session_audit_fails() -> None:
    audit = {
        "passed": False,
        "official_bar_rows": 26_303,
        "verified_no_kline_rows": 1,
        "expected_clock_rows": 26_304,
    }

    assert _effective_bundle_blockers(
        ["catalog_rows=26303!=expected=26304"],
        audit,
    ) == ["catalog_rows=26303!=expected=26304"]

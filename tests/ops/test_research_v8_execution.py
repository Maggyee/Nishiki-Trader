from apps.ops.research_v8_execution import STEP_NS, missing_windows


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

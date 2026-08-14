from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_protocol_v35 import load_and_validate
from apps.ops.research_v35_snapshot import (
    KINDS,
    parse_and_audit_csv,
    request_plan,
    verify_snapshot,
    write_factor_csv,
)

RAW_DIR = Path("data/research-v35/raw")
FACTORS_DIR = Path("data/research-v35/factors")


def test_v35_request_plans_are_valid() -> None:
    for kind in KINDS:
        plan = request_plan(kind)
        assert plan["schema_version"] == "research.snapshot.request_plan.v35"
        assert plan["kind"] == kind
        assert plan["network_accessed"] is False


def test_v35_snapshots_verify_cleanly() -> None:
    load_and_validate()
    for kind in KINDS:
        matches = list(RAW_DIR.glob(f"{kind}-*.json"))
        assert len(matches) == 1, f"expected exactly one snapshot for {kind}"
        result = verify_snapshot(matches[0])
        assert result["valid"] is True
        assert result["kind"] == kind
        assert result["audit"]["development_row_count"] >= 700


def test_v35_factor_csv_extraction_matches(tmp_path: Path) -> None:
    for kind in KINDS:
        snapshot_path = next(RAW_DIR.glob(f"{kind}-*.json"))
        target = tmp_path / f"{kind}.csv"
        result = write_factor_csv(snapshot_path, target)
        assert result["row_count"] >= 700
        existing = FACTORS_DIR / f"{kind}_development.csv"
        assert existing.exists()
        assert existing.read_text() == target.read_text()

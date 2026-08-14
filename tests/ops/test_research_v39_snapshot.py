from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v39_snapshot import (
    collect_and_qualify_all,
    parse_and_audit_csv,
)


def test_parse_and_audit_csv() -> None:
    header = b"Date,Close\n"
    lines = [f"01/{i:02d}/2020,100.{i}\n".encode() for i in range(1, 29)] * 20
    payload = header + b"".join(lines)
    rows, audit = parse_and_audit_csv("lovol", payload)
    assert len(rows) == 560
    assert audit["kind"] == "lovol"
    assert audit["row_count"] == 560


def test_collect_and_qualify_all_mocked(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    factors_dir = tmp_path / "factors"
    qual_path = tmp_path / "qualification.json"

    import pandas as pd

    dates = pd.date_range("2019-11-01", "2023-01-10", freq="B")
    csv_lines = ["Date,Close"]
    for d in dates:
        csv_lines.append(f"{d.strftime('%m/%d/%Y')},100.0")
    dummy_csv = "\n".join(csv_lines).encode("utf-8")

    def mock_fetch(url: str) -> bytes:
        return dummy_csv

    qual = collect_and_qualify_all(
        raw_dir=raw_dir,
        factors_dir=factors_dir,
        qualification_path=qual_path,
        fetch=mock_fetch,
    )
    assert qual["passed"] is True
    assert set(qual["sources"]) == {"lovol", "putd", "cndr"}
    assert qual_path.exists()
    payload = json.loads(qual_path.read_text())
    assert payload["schema_version"] == "research.provider_qualification.v39.v1"

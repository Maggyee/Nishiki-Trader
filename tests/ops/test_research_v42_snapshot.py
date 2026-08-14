from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v42_snapshot import (
    collect_and_qualify_all,
    parse_and_audit_csv,
)


def test_parse_and_audit_csv_ohlc() -> None:
    csv_text = b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2020,15.2,16.0,14.8,15.5\n01/03/2020,15.5,15.8,14.9,15.0\n"
    rows, audit = parse_and_audit_csv("vix3m", csv_text)
    assert len(rows) == 2
    assert audit["total_rows"] == 2
    assert rows[0]["date"] == "2020-01-02"
    assert rows[0]["value"] == 15.5


def test_collect_and_qualify_all_mocked(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    factors_dir = tmp_path / "factors"
    qual_path = tmp_path / "qualification.json"

    import pandas as pd

    dates = pd.date_range("2019-11-01", "2023-01-10", freq="D")
    csv_lines = ["DATE,OPEN,HIGH,LOW,CLOSE"]
    for d in dates:
        csv_lines.append(f"{d.strftime('%m/%d/%Y')},20.0,22.0,19.0,20.5")
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
    assert qual_path.exists()
    payload = json.loads(qual_path.read_text())
    assert payload["schema_version"] == "research.v42.provider_qualification.v1"

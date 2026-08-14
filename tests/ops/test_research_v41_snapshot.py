from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v41_snapshot import (
    collect_and_qualify_all,
    compute_factors,
)


def test_compute_factors() -> None:
    btc_rows = [
        {"date": f"2020-01-{i:02d}", "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0 + i, "volume": 1000.0}
        for i in range(1, 15)
    ]
    eth_rows = [
        {"date": f"2020-01-{i:02d}", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0 + i * 0.1, "volume": 5000.0}
        for i in range(1, 15)
    ]
    factors = compute_factors(btc_rows, eth_rows)
    assert "eth_btc_rs" in factors
    assert "btc_parkinson" in factors
    assert "btc_obv" in factors
    assert len(factors["eth_btc_rs"]) == 14
    assert len(factors["btc_parkinson"]) == 14
    assert len(factors["btc_obv"]) == 14


def test_collect_and_qualify_all_mocked(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    factors_dir = tmp_path / "factors"
    qual_path = tmp_path / "qualification.json"

    import io
    import zipfile

    import pandas as pd

    dates = pd.date_range("2019-11-01", "2023-01-10", freq="D")
    csv_lines = []
    for d in dates:
        ts = int(d.timestamp() * 1000)
        csv_lines.append(f"{ts},10000.0,10500.0,9500.0,10200.0,1000.0,{ts+86399999},10200000.0,500,500.0,5100000.0,0")
    dummy_csv = "\n".join(csv_lines).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("test.csv", dummy_csv)
    dummy_zip = buf.getvalue()

    def mock_fetch(url: str) -> bytes:
        return dummy_zip

    qual = collect_and_qualify_all(
        raw_dir=raw_dir,
        factors_dir=factors_dir,
        qualification_path=qual_path,
        fetch=mock_fetch,
    )
    assert qual["passed"] is True
    assert qual_path.exists()
    payload = json.loads(qual_path.read_text())
    assert payload["schema_version"] == "research.provider_qualification.v41.v1"

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from apps.research import data


def _zip(csv: str, name: str = "file.csv") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, csv)
    return buffer.getvalue()


KLINE_ROW = "{t},100,110,90,105,10,0,1050,7,6,630,0"


def test_periods_refuse_the_sealed_blind() -> None:
    assert data.periods("monthly", "2025-11", "2025-12") == ["2025-11", "2025-12"]
    with pytest.raises(data.BlindWindowError):
        data.periods("monthly", "2026-08", "2026-09")
    with pytest.raises(data.BlindWindowError):
        data.periods("daily", "2026-08-30", "2026-09-01")


def test_parse_klines_handles_header_and_microseconds() -> None:
    csv = "open_time,open,high,low,close,volume,close_time,quote_volume,count,tb,tbq,ignore\n"
    csv += KLINE_ROW.format(t=1577836800000) + "\n"  # 2020-01-01 in ms
    csv += KLINE_ROW.format(t=1735689600000000) + "\n"  # 2025-01-01 in us
    frame = data.parse_klines(pd.read_csv(io.StringIO(csv), header=None, dtype=str))

    assert list(frame.index.strftime("%Y-%m-%d")) == ["2020-01-01", "2025-01-01"]
    assert frame["taker_buy_volume"].tolist() == [6.0, 6.0]
    assert str(frame.index.tz) == "UTC"


def test_parse_metrics_keeps_last_row_per_day() -> None:
    csv = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,a,b,c,d\n"
        "2022-01-01 00:00:00,BTCUSDT,100,1,0,0,0,0\n"
        "2022-01-01 23:55:00,BTCUSDT,120,2,0,0,0,0\n"
        "2022-01-02 00:00:00,BTCUSDT,130,3,0,0,0,0\n"
    )
    frame = data.parse_metrics(pd.read_csv(io.StringIO(csv), header=None, dtype=str))

    assert frame["open_interest"].tolist() == [120.0, 130.0]


def test_fetch_verifies_checksum_records_manifest_and_tolerates_daily_gaps(
    tmp_path: Path,
) -> None:
    payload = _zip(KLINE_ROW.format(t=1577836800000))
    digest = hashlib.sha256(payload).hexdigest()

    def get(url: str) -> bytes:
        if url.endswith(".CHECKSUM"):
            return f"{digest}  name.zip".encode()
        if "metrics" in url and url.endswith("2022-01-02.zip"):
            raise urllib.error.HTTPError(url, 404, "missing", None, None)
        return payload

    spot = data.fetch("spot_klines_1d", "BTCUSDT", "2020-01", "2020-02", root=tmp_path, get=get)
    metrics = data.fetch(
        "um_metrics_daily", "BTCUSDT", "2022-01-01", "2022-01-02", root=tmp_path, get=get
    )

    assert set(spot.values()) == {digest}
    assert list(metrics.values()) == [digest, None]
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest) == 4
    assert len(data.load("spot_klines_1d", "BTCUSDT", root=tmp_path)) == 1

    with pytest.raises(ValueError, match="checksum"):
        data.fetch(
            "um_klines_1d",
            "BTCUSDT",
            "2020-01",
            "2020-01",
            root=tmp_path,
            get=lambda url: b"0" * 64 if url.endswith(".CHECKSUM") else payload,
        )

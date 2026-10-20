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


def test_parse_funding_keeps_rounded_settlements_and_sums_duplicate_stamps() -> None:
    csv = (
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1577923200000,8,0.0001\n"  # 2020-01-02 00:00
        "1577952000003,8,0.0002\n"  # 2020-01-02 08:00 (+3 ms)
        "1577951999997,8,0.0004\n"  # same hour (-3 ms)
        "1577980800000,8,0.0003\n"  # 2020-01-02 16:00
    )
    frame = data.parse_funding(pd.read_csv(io.StringIO(csv), header=None, dtype=str))

    assert frame["funding_rate"].round(6).to_dict() == {
        pd.Timestamp("2020-01-02 00:00", tz="UTC"): 0.0001,
        pd.Timestamp("2020-01-02 08:00", tz="UTC"): 0.0006,
        pd.Timestamp("2020-01-02 16:00", tz="UTC"): 0.0003,
    }


def test_parse_minute_klines_preserves_ms_and_us_minutes() -> None:
    stamps = [1577836800000, 1577836860000, 1735689600000000, 1735689690000000]
    raw = pd.read_csv(
        io.StringIO("\n".join(KLINE_ROW.format(t=t) for t in stamps)), header=None, dtype=str
    )
    frame = data.parse_klines(raw, bar="1min")
    assert list(frame.index.strftime("%Y-%m-%d %H:%M")) == [
        "2020-01-01 00:00",
        "2020-01-01 00:01",
        "2025-01-01 00:00",
        "2025-01-01 00:01",
    ]
    assert str(frame.index.tz) == "UTC"


def test_metrics_5m_keeps_observations_sorted_and_last_duplicate() -> None:
    csv = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
        "2022-01-01 23:55:00,BTCUSDT,100,1\n"
        "2022-01-01 00:05:00,BTCUSDT,110,2\n"
        "2022-01-01 23:55:00,BTCUSDT,120,3\n"
        "2022-01-02 00:00:00,BTCUSDT,130,4\n"
    )
    raw = pd.read_csv(io.StringIO(csv), header=None, dtype=str)
    frame = data.parse_metrics_5m(raw)
    assert frame["open_interest"].tolist() == [110.0, 120.0, 130.0]
    assert frame["open_interest_value"].tolist() == [2.0, 3.0, 4.0]
    assert list(frame.index.strftime("%H:%M")) == ["00:05", "23:55", "00:00"]
    assert str(frame.index.tz) == "UTC"
    daily = data.parse_metrics(raw)
    assert daily["open_interest"].tolist() == [120.0, 130.0]
    assert list(daily.index.strftime("%H:%M")) == ["00:00", "00:00"]


def test_daily_metrics_retains_original_last_nonmissing_column_semantics() -> None:
    csv = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
        "2022-01-01 00:00:00,BTCUSDT,100,1\n"
        "2022-01-01 23:55:00,BTCUSDT,120,2\n"
        "2022-01-01 23:55:00,BTCUSDT,,3\n"
    )
    raw = pd.read_csv(io.StringIO(csv), header=None, dtype=str)
    assert data.parse_metrics(raw).iloc[0].tolist() == [120.0, 3.0]
    assert pd.isna(data.parse_metrics_5m(raw).iloc[-1]["open_interest"])


def _raw_archive(root: Path, dataset: str, csv: str, period: str = "2020-01") -> Path:
    directory, template, _ = data.DATASETS[dataset]
    path = (
        root
        / "raw"
        / directory.format(symbol="BTCUSDT")
        / template.format(symbol="BTCUSDT", period=period)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_zip(csv))
    return path


@pytest.mark.parametrize("dataset", ["spot_klines_1m", "um_klines_1m"])
def test_load_selects_minute_parser_and_reuses_versioned_cache(
    tmp_path, monkeypatch, dataset
) -> None:
    csv = "\n".join(KLINE_ROW.format(t=t) for t in [1577836800000, 1577836860000])
    raw = _raw_archive(tmp_path, dataset, csv)
    payload = raw.read_bytes()
    expected = data.load(dataset, "BTCUSDT", root=tmp_path)
    assert list(expected.index.minute) == [0, 1]
    cache = tmp_path / "parsed" / f"v{data.PARSE_VERSION}" / dataset / f"{raw.stem}.parquet"
    assert cache.exists()
    assert list(cache.parent.iterdir()) == [cache]

    def fail(*args, **kwargs):
        raise AssertionError("a cache hit must not parse raw data")

    with monkeypatch.context() as patch:
        patch.setattr(data, "parse_klines", fail)
        patch.setattr(data, "_read_zip_csv", fail)
        pd.testing.assert_frame_equal(data.load(dataset, "BTCUSDT", root=tmp_path), expected)
    monkeypatch.setattr(data, "PARSE_VERSION", data.PARSE_VERSION + 1)
    pd.testing.assert_frame_equal(data.load(dataset, "BTCUSDT", root=tmp_path), expected)
    assert (tmp_path / "parsed" / f"v{data.PARSE_VERSION}" / dataset / cache.name).exists()
    assert raw.read_bytes() == payload


def test_metrics_datasets_share_raw_files_but_have_separate_parsed_caches(tmp_path) -> None:
    csv = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
        "2022-01-01 00:00:00,BTCUSDT,100,1\n"
        "2022-01-01 23:55:00,BTCUSDT,120,2\n"
    )
    _raw_archive(tmp_path, "um_metrics_daily", csv, "2022-01-01")
    assert data.DATASETS["um_metrics_daily"] == data.DATASETS["um_metrics_5m"]
    assert "um_metrics_5m" in data.GAP_TOLERANT
    assert len(data.load("um_metrics_5m", "BTCUSDT", root=tmp_path)) == 2
    assert len(data.load("um_metrics_daily", "BTCUSDT", root=tmp_path)) == 1


def test_parsed_cache_hit_still_checks_the_blind(tmp_path, monkeypatch) -> None:
    csv = KLINE_ROW.format(t=pd.Timestamp("2026-09-01", tz="UTC").value // 1_000_000)
    _raw_archive(tmp_path, "spot_klines_1m", csv)
    with pytest.raises(data.BlindWindowError):
        data.load("spot_klines_1m", "BTCUSDT", root=tmp_path)

    def fail(*args, **kwargs):
        raise AssertionError("expected a cache hit")

    monkeypatch.setattr(data, "parse_klines", fail)
    with pytest.raises(data.BlindWindowError):
        data.load("spot_klines_1m", "BTCUSDT", root=tmp_path)


def test_failed_parquet_write_leaves_no_partial_cache(tmp_path, monkeypatch) -> None:
    raw = _raw_archive(tmp_path, "spot_klines_1m", KLINE_ROW.format(t=1577836800000))

    def fail(frame, path):
        Path(path).write_bytes(b"partial")
        raise OSError("interrupted")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail)
    with pytest.raises(OSError, match="interrupted"):
        data.load("spot_klines_1m", "BTCUSDT", root=tmp_path)
    cache_dir = tmp_path / "parsed" / f"v{data.PARSE_VERSION}" / "spot_klines_1m"
    assert list(cache_dir.iterdir()) == []
    assert raw.exists()

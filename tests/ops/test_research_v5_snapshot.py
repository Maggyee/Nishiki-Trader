from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import apps.ops.research_v5_snapshot as snapshot_module
from apps.ops.research_v5_snapshot import (
    HttpResponse,
    build_requests,
    collect_snapshot,
    request_plan,
    select_quarterly_contracts,
    verify_snapshot,
)


def _zip_csv(name: str, text: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)
    return output.getvalue()


def _response(body: bytes, url: str) -> HttpResponse:
    return HttpResponse(body=body, status=200, final_url=url, headers={"etag": "fixture"})


def _fixture_fetch(
    kind: str,
    asset: str,
    day: date,
    *,
    unit: str = "ms",
    missing_bvol_second: int | None = None,
):
    specs = build_requests(kind, asset, day)
    bodies = {}
    multiplier = {"ms": 1, "us": 1_000, "ns": 1_000_000}[unit]
    close_adjustment = {"ms": 0, "us": 999, "ns": 999_999}[unit]
    start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    end_ms = start_ms + 86_400_000 - 1
    for index, spec in enumerate(specs):
        if kind == "delivery_curve":
            close = (100.0, 101.0, 104.0)[index]
            row = [
                start_ms * multiplier,
                close,
                close + 1,
                close - 1,
                close,
                1,
                end_ms * multiplier + close_adjustment,
                1,
                1,
                1,
                1,
                0,
            ]
            body = _zip_csv(spec.filename.removesuffix(".zip") + ".csv", ",".join(map(str, row)) + "\n")
        else:
            symbol = f"{asset.removesuffix('USDT')}BVOLUSDT"
            base_asset = f"{asset.removesuffix('USDT')}BVOL"
            rows = [
                [
                    start_ms * multiplier + offset * 1_000 * multiplier,
                    symbol,
                    base_asset,
                    "USDT",
                    60.0 - 2.0 * offset / 86_399,
                ]
                for offset in range(86_400)
                if offset != missing_bvol_second
            ]
            body = _zip_csv(spec.filename.removesuffix(".zip") + ".csv", "\n".join(",".join(map(str, row)) for row in rows) + "\n")
        digest = hashlib.sha256(body).hexdigest()
        bodies[spec.url] = body
        bodies[f"{spec.url}.CHECKSUM"] = f"{digest}  {spec.filename}\n".encode()

    def fetch(url: str) -> HttpResponse:
        return _response(bodies[url], url)

    return fetch


def test_dry_run_plan_is_offline_and_contains_checksums(tmp_path: Path) -> None:
    day = date(2026, 7, 16)
    plan = request_plan("delivery_curve", "BTCUSDT", [day])

    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert len(plan["dates"][0]["requests"]) == 3
    assert all(row["checksum_url"].endswith(".CHECKSUM") for row in plan["dates"][0]["requests"])
    assert not tmp_path.exists() or not list(tmp_path.iterdir())


def test_curve_snapshot_checksums_normalizes_and_is_idempotent(tmp_path: Path) -> None:
    day = date(2021, 8, 1)
    fetch = _fixture_fetch("delivery_curve", "BTCUSDT", day, unit="us")
    kwargs = {
        "raw_root": tmp_path / "raw",
        "normalized_root": tmp_path / "normalized",
        "fetch": fetch,
    }
    first = collect_snapshot(
        "delivery_curve",
        "BTCUSDT",
        day,
        now=datetime(2026, 7, 17, 10, tzinfo=UTC),
        **kwargs,
    )
    second = collect_snapshot(
        "delivery_curve",
        "BTCUSDT",
        day,
        now=datetime(2026, 7, 17, 11, tzinfo=UTC),
        **kwargs,
    )

    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["audit"]["quarter_order_valid"] is True
    assert verify_snapshot(Path(first["path"]))["valid"] is True
    assert Path(first["normalized_path"]).exists()
    assert len(list((tmp_path / "raw" / "delivery_curve" / "BTCUSDT" / day.isoformat()).glob("*/snapshot.json"))) == 1


def test_snapshot_accepts_nanosecond_archives_and_rejects_http_audit_drift(
    tmp_path: Path,
) -> None:
    day = date(2021, 8, 1)
    result = collect_snapshot(
        "delivery_curve",
        "BTCUSDT",
        day,
        raw_root=tmp_path / "raw",
        normalized_root=tmp_path / "normalized",
        fetch=_fixture_fetch("delivery_curve", "BTCUSDT", day, unit="ns"),
        now=datetime(2026, 7, 17, 10, tzinfo=UTC),
    )
    snapshot = Path(result["path"])
    assert verify_snapshot(snapshot)["valid"] is True

    payload = json.loads(snapshot.read_text())
    payload["requests"][0]["http"]["status"] = 500
    snapshot.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="HTTP metadata"):
        verify_snapshot(snapshot)


def test_changed_archive_creates_new_vintage_and_blocks_comparison(tmp_path: Path) -> None:
    day = date(2021, 8, 1)
    first_fetch = _fixture_fetch("delivery_curve", "BTCUSDT", day)
    root = tmp_path / "raw"
    normalized = tmp_path / "normalized"
    collect_snapshot("delivery_curve", "BTCUSDT", day, raw_root=root, normalized_root=normalized, fetch=first_fetch, now=datetime(2026, 7, 17, 10, tzinfo=UTC))

    specs = build_requests("delivery_curve", "BTCUSDT", day)
    original = _fixture_fetch("delivery_curve", "BTCUSDT", day)
    cache = {url: original(url) for spec in specs for url in (spec.url, f"{spec.url}.CHECKSUM")}
    changed_body = _zip_csv("changed.csv", "1627776000000,100,102,99,101.5,1,1627862399999,1,1,1,1,0\n")
    cache[specs[1].url] = _response(changed_body, specs[1].url)
    digest = hashlib.sha256(changed_body).hexdigest()
    cache[f"{specs[1].url}.CHECKSUM"] = _response(f"{digest}  {specs[1].filename}\n".encode(), f"{specs[1].url}.CHECKSUM")

    result = collect_snapshot("delivery_curve", "BTCUSDT", day, raw_root=root, normalized_root=normalized, fetch=lambda url: cache[url], now=datetime(2026, 7, 17, 12, tzinfo=UTC))

    assert result["result_comparison_blocked"] is True
    assert len(list((root / "delivery_curve" / "BTCUSDT" / day.isoformat()).glob("*/snapshot.json"))) == 2
    assert list((root / "delivery_curve" / "BTCUSDT" / day.isoformat()).glob("comparison-blocked-*.json"))


def test_bvol_snapshot_selects_last_valid_row_and_applies_historical_lag(tmp_path: Path) -> None:
    day = date(2023, 8, 1)
    result = collect_snapshot(
        "bvol",
        "ETHUSDT",
        day,
        raw_root=tmp_path / "raw",
        normalized_root=tmp_path / "normalized",
        fetch=_fixture_fetch("bvol", "ETHUSDT", day),
        now=datetime(2026, 7, 17, 10, tzinfo=UTC),
    )
    payload = json.loads(Path(result["path"]).read_text())

    assert result["audit"]["row_count"] == 86_400
    assert payload["normalized"]["bvol_index"] == 58.0
    assert payload["normalized"]["available_at"] == "2023-08-03T00:00:00Z"


def test_snapshot_rejects_bad_checksum_and_duplicate_bvol_timestamp(tmp_path: Path) -> None:
    day = date(2023, 8, 1)
    specs = build_requests("bvol", "BTCUSDT", day)
    spec = specs[0]
    body = _zip_csv("bvol.csv", "1690848000000,BTCBVOLUSDT,BTCBVOL,USDT,60\n1690848000000,BTCBVOLUSDT,BTCBVOL,USDT,59\n")
    digest = hashlib.sha256(body).hexdigest()
    mapping = {
        spec.url: _response(body, spec.url),
        f"{spec.url}.CHECKSUM": _response(f"{digest}  {spec.filename}\n".encode(), f"{spec.url}.CHECKSUM"),
    }
    with pytest.raises(ValueError, match="unique"):
        collect_snapshot("bvol", "BTCUSDT", day, raw_root=tmp_path / "raw", normalized_root=tmp_path / "normalized", fetch=lambda url: mapping[url], now=datetime(2026, 7, 17, tzinfo=UTC))

    mapping[f"{spec.url}.CHECKSUM"] = _response(f"{'0' * 64}  {spec.filename}\n".encode(), f"{spec.url}.CHECKSUM")
    with pytest.raises(ValueError, match="checksum mismatch"):
        collect_snapshot("bvol", "BTCUSDT", day, raw_root=tmp_path / "raw2", normalized_root=tmp_path / "normalized2", fetch=lambda url: mapping[url], now=datetime(2026, 7, 17, tzinfo=UTC))


def test_bvol_snapshot_rejects_an_intraday_second_gap(tmp_path: Path) -> None:
    day = date(2023, 8, 1)
    with pytest.raises(ValueError, match="every UTC second"):
        collect_snapshot(
            "bvol",
            "BTCUSDT",
            day,
            raw_root=tmp_path / "raw",
            normalized_root=tmp_path / "normalized",
            fetch=_fixture_fetch(
                "bvol",
                "BTCUSDT",
                day,
                missing_bvol_second=42,
            ),
            now=datetime(2026, 7, 17, tzinfo=UTC),
        )


def test_quarter_selection_rolls_at_expiry_boundary() -> None:
    before = select_quarterly_contracts("BTCUSDT", date(2022, 3, 24))
    expiry_day = select_quarterly_contracts("BTCUSDT", date(2022, 3, 25))

    assert before[0][0] == "BTCUSDT_220325"
    assert expiry_day[0][0] == "BTCUSDT_220624"
    assert before[0][1].hour == 8


def test_range_download_records_failure_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[date] = []

    def collect(_kind: str, _asset: str, data_day: date, **_kwargs):
        calls.append(data_day)
        if data_day == date(2023, 8, 1):
            raise ValueError("intraday gap")
        return {"data_date": data_day.isoformat(), "valid": True}

    monkeypatch.setattr(snapshot_module, "collect_snapshot", collect)
    result = snapshot_module.main(
        [
            "--kind",
            "bvol",
            "--asset",
            "BTCUSDT",
            "--start-date",
            "2023-08-01",
            "--end-date",
            "2023-08-02",
            "--download",
            "--raw-root",
            str(tmp_path / "raw"),
            "--normalized-root",
            str(tmp_path / "normalized"),
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 2
    assert calls == [date(2023, 8, 1), date(2023, 8, 2)]
    assert report["valid_snapshot_count"] == 1
    assert report["failed_date_count"] == 1
    assert report["failures"][0]["desired_state"] == "flat"
    assert report["failures"][0]["snapshot_written"] is False

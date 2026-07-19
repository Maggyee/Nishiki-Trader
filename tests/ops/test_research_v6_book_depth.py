from __future__ import annotations

import ast
import hashlib
import io
import json
import shutil
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import apps.ops.research_v6_book_depth as collector_module
from apps.ops.research_v6_book_depth import (
    ASSETS,
    QUALIFICATION_DATE,
    HttpResponse,
    PermanentQualificationError,
    RetryableDownloadError,
    _clean_locked_commit,
    _persist_http_200,
    build_requests,
    collect_asset,
    parse_book_depth,
    parse_mark_price,
    qualification_audit,
    request_plan,
    run_qualification,
    storage_summary,
    verify_asset_snapshot,
    verify_evidence_root,
)

DAY = QUALIFICATION_DATE
NOW = datetime(2026, 7, 19, 2, 30, tzinfo=UTC)
COMMIT = "a" * 40


def _zip_csv(name: str, rows: list[list[object]]) -> bytes:
    output = io.BytesIO()
    text = "\n".join(",".join(map(str, row)) for row in rows) + "\n"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)
    return output.getvalue()


def _mark_price(minute: int) -> Decimal:
    return Decimal("100") + Decimal(minute) / Decimal(1000)


def _book_body(
    asset: str,
    *,
    group_minutes: list[int] | None = None,
    mutate=None,
    header: list[str] | None = None,
) -> bytes:
    spec = build_requests(asset, DAY)[0]
    minutes = group_minutes or list(range(15, 1_426, 15))
    rows: list[list[object]] = [
        header or ["timestamp", "percentage", "depth", "notional"]
    ]
    for minute in minutes:
        timestamp = datetime.combine(DAY, datetime.min.time(), UTC) + timedelta(
            minutes=minute
        )
        mark = _mark_price(minute)
        for percentage in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5):
            weighted = mark * (Decimal(1) + Decimal(percentage) / Decimal(100))
            rows.append(
                [
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    percentage,
                    "1",
                    format(weighted, "f"),
                ]
            )
    if mutate is not None:
        mutate(rows)
    return _zip_csv(spec.filename.removesuffix(".zip") + ".csv", rows)


def _mark_body(
    asset: str,
    *,
    row_count: int = 1_440,
    unit: str = "ms",
    mutate=None,
) -> bytes:
    spec = build_requests(asset, DAY)[1]
    multiplier = {"ms": 1, "us": 1_000, "ns": 1_000_000}[unit]
    close_adjustment = {"ms": 0, "us": 999, "ns": 999_999}[unit]
    start_ms = int(datetime.combine(DAY, datetime.min.time(), UTC).timestamp() * 1000)
    rows: list[list[object]] = []
    for minute in range(row_count):
        open_ms = start_ms + minute * 60_000
        close_ms = open_ms + 60_000 - 1
        price = _mark_price(minute)
        rows.append(
            [
                open_ms * multiplier,
                format(price, "f"),
                format(price + 1, "f"),
                format(price - 1, "f"),
                format(price, "f"),
                "0",
                close_ms * multiplier + close_adjustment,
                "0",
                "0",
                "0",
                "0",
                "0",
            ]
        )
    if mutate is not None:
        mutate(rows)
    return _zip_csv(spec.filename.removesuffix(".zip") + ".csv", rows)


def _response(body: bytes, url: str, *, status: int = 200) -> HttpResponse:
    return HttpResponse(
        body=body,
        status=status,
        final_url=url,
        headers={"etag": "synthetic-v6"},
    )


def _fixture_mapping(
    asset: str,
    *,
    book_body: bytes | None = None,
    mark_body: bytes | None = None,
) -> dict[str, HttpResponse]:
    specs = build_requests(asset, DAY)
    bodies = {
        specs[0].url: book_body or _book_body(asset),
        specs[1].url: mark_body or _mark_body(asset),
    }
    mapping: dict[str, HttpResponse] = {}
    for spec in specs:
        body = bodies[spec.url]
        digest = hashlib.sha256(body).hexdigest()
        mapping[spec.url] = _response(body, spec.url)
        checksum_url = f"{spec.url}.CHECKSUM"
        mapping[checksum_url] = _response(
            f"{digest}  {spec.filename}\n".encode(), checksum_url
        )
    return mapping


def _repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    contract = repo / "docs/progress/phase-2-research-v6-data-sources.json"
    contract.parent.mkdir(parents=True)
    shutil.copyfile(
        Path("docs/progress/phase-2-research-v6-data-sources.json"), contract
    )
    (repo / ".collector-git-sha").write_text(f"{COMMIT}\n")
    monkeypatch.setenv("TRADER_GIT_SHA", COMMIT)
    return repo


def test_request_plan_locks_urls_date_and_offline_empty_root(tmp_path: Path) -> None:
    data_root = tmp_path / "qualification"
    plan = request_plan("all", DAY, data_root)

    assert plan["assets"] == list(ASSETS)
    assert plan["archive_request_count"] == 4
    assert plan["checksum_request_count"] == 4
    assert plan["http_request_count"] == 8
    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["data_root_empty"] is True
    assert all(row["url"].startswith("https://data.binance.vision/data/") for row in plan["requests"])
    assert all(row["checksum_url"] == f"{row['url']}.CHECKSUM" for row in plan["requests"])
    assert not data_root.exists()

    with pytest.raises(PermanentQualificationError, match="only qualification date"):
        request_plan("all", date(2026, 7, 16), data_root)


def test_dry_run_checks_commit_contract_and_empty_root_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_root(tmp_path, monkeypatch)
    data_root = tmp_path / "data"
    report = run_qualification(
        asset_selector="all",
        data_day=DAY,
        action="dry-run",
        data_root=data_root,
        expected_git_commit=COMMIT,
        repo_root=repo,
    )

    assert report["runtime_identity"]["identity_mode"] == "immutable_image_marker"
    assert report["provider_contract_audit"]["valid"] is True
    assert report["network_accessed"] is False
    assert not data_root.exists()

    data_root.mkdir()
    (data_root / "unexpected").write_text("x")
    with pytest.raises(PermanentQualificationError, match="empty qualification data root"):
        run_qualification(
            asset_selector="all",
            data_day=DAY,
            action="dry-run",
            data_root=data_root,
            expected_git_commit=COMMIT,
            repo_root=repo,
        )


def test_asset_collection_preserves_raw_http_audit_and_is_idempotent(
    tmp_path: Path,
) -> None:
    mapping = _fixture_mapping("BTCUSDT")
    calls: list[str] = []

    def fetch(url: str) -> HttpResponse:
        calls.append(url)
        return mapping[url]

    first = collect_asset(
        "BTCUSDT",
        DAY,
        data_root=tmp_path,
        expected_git_commit=COMMIT,
        fetch=fetch,
        clock=lambda: NOW,
    )
    second = collect_asset(
        "BTCUSDT",
        DAY,
        data_root=tmp_path,
        expected_git_commit=COMMIT,
        fetch=lambda url: (_ for _ in ()).throw(AssertionError(url)),
        clock=lambda: NOW + timedelta(hours=1),
    )

    assert len(calls) == 4
    assert first["idempotent"] is False
    assert first["http_requests_made"] == 4
    assert second["idempotent"] is True
    assert second["http_requests_made"] == 0
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    assert first["audit"]["timestamp_group_count"] == 95
    assert first["audit"]["book_depth_row_count"] == 950
    assert first["audit"]["mark_price_row_count"] == 1_440
    assert first["audit"]["band_violation_count"] == 0
    assert first["audit"]["factor_values_saved"] is False
    assert storage_summary(tmp_path) == {
        "snapshot_count": 1,
        "audit_parquet_count": 1,
        "raw_zip_count": 2,
        "checksum_count": 2,
        "cached_http_200_count": 4,
        "conflict_count": 0,
        "permanent_http_blocker_count": 0,
    }


def test_timeout_or_5xx_retry_fetches_only_the_missing_response(tmp_path: Path) -> None:
    mapping = _fixture_mapping("BTCUSDT")
    mark_checksum_url = f"{build_requests('BTCUSDT', DAY)[1].url}.CHECKSUM"
    first_calls: list[str] = []

    def first_fetch(url: str) -> HttpResponse:
        first_calls.append(url)
        if url == mark_checksum_url:
            return _response(b"unavailable", url, status=503)
        return mapping[url]

    with pytest.raises(RetryableDownloadError, match="retryable HTTP 503"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=first_fetch,
            clock=lambda: NOW,
        )
    assert len(first_calls) == 4
    assert storage_summary(tmp_path)["cached_http_200_count"] == 3

    second_calls: list[str] = []

    def second_fetch(url: str) -> HttpResponse:
        second_calls.append(url)
        return mapping[url]

    result = collect_asset(
        "BTCUSDT",
        DAY,
        data_root=tmp_path,
        expected_git_commit=COMMIT,
        fetch=second_fetch,
        clock=lambda: NOW + timedelta(minutes=5),
    )
    assert second_calls == [mark_checksum_url]
    assert result["http_requests_made"] == 1
    assert result["valid"] is True


def test_http_4xx_is_persisted_as_a_non_retryable_blocker(tmp_path: Path) -> None:
    spec = build_requests("BTCUSDT", DAY)[0]
    calls = 0

    def fetch(url: str) -> HttpResponse:
        nonlocal calls
        calls += 1
        return _response(b"not found", url, status=404)

    with pytest.raises(PermanentQualificationError, match="permanent blocker"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=fetch,
            clock=lambda: NOW,
        )
    with pytest.raises(PermanentQualificationError, match="already recorded"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=lambda url: (_ for _ in ()).throw(AssertionError(url)),
            clock=lambda: NOW,
        )
    assert calls == 1
    assert storage_summary(tmp_path)["permanent_http_blocker_count"] == 1
    assert spec.filename in request_plan("BTCUSDT", DAY, tmp_path)["requests"][0]["filename"]


def test_different_saved_http_content_records_conflict_without_overwrite(
    tmp_path: Path,
) -> None:
    spec = build_requests("BTCUSDT", DAY)[0]
    first = _response(b"first immutable body", spec.url)
    second = _response(b"different body", spec.url)
    saved = _persist_http_200(
        tmp_path, "BTCUSDT", DAY, spec, "archive", first, NOW
    )

    with pytest.raises(PermanentQualificationError, match="vintage conflict"):
        _persist_http_200(
            tmp_path,
            "BTCUSDT",
            DAY,
            spec,
            "archive",
            second,
            NOW + timedelta(minutes=1),
        )

    assert saved.body_path.read_bytes() == first.body
    marker = next((tmp_path / "conflicts").rglob("conflict.json"))
    assert json.loads(marker.read_text())["result_comparison_blocked"] is True
    assert next(marker.parent.glob("*.zip")).read_bytes() == second.body


def test_checksum_schema_failure_is_cached_and_never_redownloaded(tmp_path: Path) -> None:
    bad_book = _book_body(
        "BTCUSDT", header=["timestamp", "percentage", "depth", "wrong"]
    )
    mapping = _fixture_mapping("BTCUSDT", book_body=bad_book)
    calls: list[str] = []

    with pytest.raises(PermanentQualificationError, match="exact locked header"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=lambda url: (calls.append(url), mapping[url])[1],
            clock=lambda: NOW,
        )
    assert len(calls) == 4
    with pytest.raises(PermanentQualificationError, match="exact locked header"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=lambda url: (_ for _ in ()).throw(AssertionError(url)),
            clock=lambda: NOW,
        )

    checksum_url = f"{build_requests('BTCUSDT', DAY)[0].url}.CHECKSUM"
    checksum_path = next(
        (tmp_path / "responses/BTCUSDT/2026-07-17/book_depth/checksum").glob(
            "*.CHECKSUM"
        )
    )
    checksum_path.write_text(f"{'0' * 64}  {build_requests('BTCUSDT', DAY)[0].filename}\n")
    with pytest.raises(PermanentQualificationError, match="body hash mismatch"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=lambda url: (_ for _ in ()).throw(AssertionError((checksum_url, url))),
            clock=lambda: NOW,
        )


def test_official_checksum_mismatch_blocks_after_preserving_both_responses(
    tmp_path: Path,
) -> None:
    mapping = _fixture_mapping("BTCUSDT")
    spec = build_requests("BTCUSDT", DAY)[0]
    checksum_url = f"{spec.url}.CHECKSUM"
    mapping[checksum_url] = _response(
        f"{'0' * 64}  {spec.filename}\n".encode(), checksum_url
    )

    with pytest.raises(PermanentQualificationError, match="official checksum mismatch"):
        collect_asset(
            "BTCUSDT",
            DAY,
            data_root=tmp_path,
            expected_git_commit=COMMIT,
            fetch=lambda url: mapping[url],
            clock=lambda: NOW,
        )
    assert storage_summary(tmp_path)["cached_http_200_count"] == 4


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda rows: rows[1].pop(), "row width"),
        (
            lambda rows: rows[1].__setitem__(0, "2026-07-16 00:15:00"),
            "exact UTC format on 2026-07-17",
        ),
        (lambda rows: rows.pop(1), "exact ten-row grid"),
        (lambda rows: rows[10].__setitem__(1, "-5"), "duplicated"),
        (lambda rows: rows[1].__setitem__(2, "NaN"), "finite and positive"),
        (lambda rows: rows[1].__setitem__(3, "Infinity"), "finite and positive"),
        (lambda rows: rows[1].__setitem__(2, "0"), "finite and positive"),
        (lambda rows: rows[1].__setitem__(3, "-1"), "finite and positive"),
    ],
)
def test_book_depth_rejects_schema_group_and_numeric_drift(
    mutate, match: str
) -> None:
    spec = build_requests("BTCUSDT", DAY)[0]
    with pytest.raises(PermanentQualificationError, match=match):
        parse_book_depth(
            _book_body("BTCUSDT", mutate=mutate),
            filename=spec.filename,
            data_day=DAY,
        )


@pytest.mark.parametrize(
    "minutes,match",
    [
        ([16, *range(30, 1_426, 15)], "later than 00:15"),
        ([*range(15, 1_411, 15), 1_424], "earlier than 23:45"),
        ([15, *range(45, 1_426, 15)], "exceeds 900 seconds"),
    ],
)
def test_book_depth_rejects_coverage_boundaries_and_missing_group(
    minutes: list[int], match: str
) -> None:
    spec = build_requests("BTCUSDT", DAY)[0]
    with pytest.raises(PermanentQualificationError, match=match):
        parse_book_depth(
            _book_body("BTCUSDT", group_minutes=minutes),
            filename=spec.filename,
            data_day=DAY,
        )


def test_book_depth_rejects_a_repeated_timestamp_group() -> None:
    spec = build_requests("BTCUSDT", DAY)[0]

    def mutate(rows: list[list[object]]) -> None:
        repeated_timestamp = rows[1][0]
        for row in rows[21:31]:
            row[0] = repeated_timestamp

    with pytest.raises(PermanentQualificationError, match="unique and strictly increasing"):
        parse_book_depth(
            _book_body("BTCUSDT", mutate=mutate),
            filename=spec.filename,
            data_day=DAY,
        )


@pytest.mark.parametrize("unit", ["ms", "us", "ns"])
def test_mark_price_requires_all_1440_minutes_and_accepts_locked_units(unit: str) -> None:
    spec = build_requests("BTCUSDT", DAY)[1]
    parsed = parse_mark_price(
        _mark_body("BTCUSDT", unit=unit), filename=spec.filename, data_day=DAY
    )
    assert len(parsed.closes_by_minute_ns) == 1_440

    with pytest.raises(PermanentQualificationError, match="exactly 1,440"):
        parse_mark_price(
            _mark_body("BTCUSDT", row_count=1_439),
            filename=spec.filename,
            data_day=DAY,
        )


def test_mark_price_rejects_locked_row_width_drift() -> None:
    spec = build_requests("BTCUSDT", DAY)[1]
    with pytest.raises(PermanentQualificationError, match="row width"):
        parse_mark_price(
            _mark_body("BTCUSDT", mutate=lambda rows: rows[42].pop()),
            filename=spec.filename,
            data_day=DAY,
        )


def test_same_minute_mark_close_and_outer_tolerance_boundaries_pass() -> None:
    book_spec, mark_spec = build_requests("BTCUSDT", DAY)

    def mutate(rows: list[list[object]]) -> None:
        mark = _mark_price(15)
        rows[5][3] = format(mark * Decimal("0.98"), "f")  # -1% row is index 5
        rows[6][3] = format(mark * Decimal("1.02"), "f")  # +1% row is index 6

    book = parse_book_depth(
        _book_body("BTCUSDT", mutate=mutate),
        filename=book_spec.filename,
        data_day=DAY,
    )
    mark = parse_mark_price(
        _mark_body("BTCUSDT"), filename=mark_spec.filename, data_day=DAY
    )
    audit = qualification_audit(book, mark, asset="BTCUSDT", data_day=DAY)

    assert audit["band_rows_checked"] == 950
    assert audit["bid_rows_checked"] == audit["ask_rows_checked"] == 475
    assert audit["mark_minute_matches"] == 95


@pytest.mark.parametrize(
    "row_index,multiplier",
    [
        (5, Decimal("1")),  # bid may not touch/cross mark
        (6, Decimal("1")),  # ask may not touch/cross mark
        (5, Decimal("0.939999")),  # bid beyond outer tolerance
        (6, Decimal("1.020001")),  # ask beyond outer tolerance
        (5, Decimal("1.01")),  # known wrong-side/misalignment simulation
    ],
)
def test_side_band_rules_fail_closed_for_every_row(
    row_index: int, multiplier: Decimal
) -> None:
    book_spec, mark_spec = build_requests("BTCUSDT", DAY)

    def mutate(rows: list[list[object]]) -> None:
        rows[row_index][3] = format(_mark_price(15) * multiplier, "f")

    book = parse_book_depth(
        _book_body("BTCUSDT", mutate=mutate),
        filename=book_spec.filename,
        data_day=DAY,
    )
    mark = parse_mark_price(
        _mark_body("BTCUSDT"), filename=mark_spec.filename, data_day=DAY
    )
    with pytest.raises(PermanentQualificationError, match="misalignment risk reproduced"):
        qualification_audit(book, mark, asset="BTCUSDT", data_day=DAY)


def test_raw_envelope_and_parquet_tampering_fail_offline_verification(
    tmp_path: Path,
) -> None:
    mapping = _fixture_mapping("BTCUSDT")
    result = collect_asset(
        "BTCUSDT",
        DAY,
        data_root=tmp_path,
        expected_git_commit=COMMIT,
        fetch=lambda url: mapping[url],
        clock=lambda: NOW,
    )
    archive = next(
        (tmp_path / "responses/BTCUSDT/2026-07-17/book_depth/archive").glob("*.zip")
    )
    original = archive.read_bytes()
    archive.write_bytes(original + b"tamper")
    with pytest.raises(PermanentQualificationError, match="body hash mismatch"):
        verify_asset_snapshot(
            tmp_path, "BTCUSDT", DAY, expected_git_commit=COMMIT
        )
    archive.write_bytes(original)

    parquet = Path(result["audit_path"])
    frame = pd.read_parquet(parquet)
    frame.loc[0, "band_violation_count"] = 1
    frame.to_parquet(parquet, index=False)
    with pytest.raises(PermanentQualificationError, match="Parquet differs"):
        verify_asset_snapshot(
            tmp_path, "BTCUSDT", DAY, expected_git_commit=COMMIT
        )


def test_all_asset_batch_and_readonly_verify_have_exact_evidence_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_root(tmp_path, monkeypatch)
    data_root = tmp_path / "evidence"
    mapping = {
        **_fixture_mapping("BTCUSDT"),
        **_fixture_mapping("ETHUSDT"),
    }
    report = run_qualification(
        asset_selector="all",
        data_day=DAY,
        action="download",
        data_root=data_root,
        expected_git_commit=COMMIT,
        repo_root=repo,
        fetch=lambda url: mapping[url],
        clock=lambda: NOW,
    )

    assert report["complete"] is True
    assert report["recommendation"] == "provider_qualification_passed"
    assert report["storage"] == {
        "snapshot_count": 2,
        "audit_parquet_count": 2,
        "raw_zip_count": 4,
        "checksum_count": 4,
        "cached_http_200_count": 8,
        "conflict_count": 0,
        "permanent_http_blocker_count": 0,
    }
    review = verify_evidence_root(
        data_root, "all", DAY, expected_git_commit=COMMIT
    )
    assert review["network_accessed"] is False
    assert review["data_written"] is False
    assert review["recommendation"] == "provider_qualification_passed"


def test_commit_marker_drift_and_collector_dependency_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / ".collector-git-sha"
    marker.write_text(f"{COMMIT}\n")
    monkeypatch.setenv("TRADER_GIT_SHA", COMMIT)
    assert _clean_locked_commit(COMMIT, tmp_path)["valid"] is True

    monkeypatch.setenv("TRADER_GIT_SHA", "b" * 40)
    with pytest.raises(ValueError, match="internal SHA marker"):
        _clean_locked_commit(COMMIT, tmp_path)

    tree = ast.parse(Path(collector_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("apps.bridge") for name in imported)
    assert not any("nautilus" in name for name in imported)
    assert not any("freqtrade" in name for name in imported)
    assert not any("research_v5" in name for name in imported)


def test_isolated_image_compose_and_no_timer_boundaries() -> None:
    dockerfile = Path("infra/research-v6/Dockerfile").read_text()
    compose = Path("infra/research-v6/compose.yml").read_text()
    source = Path(collector_module.__file__).read_text()

    assert "org.opencontainers.image.revision" in dockerfile
    assert "/app/.collector-git-sha" in dockerfile
    assert "USER 1002:1002" in dockerfile
    assert "research_v6_book_depth.py" in dockerfile
    assert "nautilus" not in dockerfile.lower()
    assert "signal" not in dockerfile.lower()
    assert "research_v5" not in dockerfile

    assert "network_mode: none" in compose
    assert ":/data/research-v6:ro" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "ports:" not in compose
    assert "docker.sock" not in compose
    assert not list(Path("infra/research-v6").rglob("*.timer"))
    assert not list(Path("infra/research-v6").rglob("*.service"))

    assert "median(" not in source
    assert "imbalance =" not in source
    assert '"buy"' not in source
    assert '"flat"' not in source

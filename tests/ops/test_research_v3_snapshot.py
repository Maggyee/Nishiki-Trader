from __future__ import annotations

import ast
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import apps.ops.research_v3_snapshot as snapshot_module
from apps.ops.research_v3_snapshot import (
    PROVIDER_CONTRACT,
    PROVIDER_CONTRACT_SHA256,
    build_requests,
    collect_snapshot,
    main,
    request_plan,
    verify_snapshot,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _hashrate_payload() -> dict:
    return {
        "status": "ok",
        "name": "Hash Rate",
        "unit": "TH/s",
        "period": "day",
        "description": "Estimated network hash rate",
        "values": [
            {"x": 1783900800, "y": 800_000_000.0},  # 2026-07-13
            {"x": 1783987200, "y": 810_000_000.0},  # 2026-07-14
            {"x": 1784073600, "y": 805_000_000.0},  # 2026-07-15
            {"x": 1784160000, "y": 815_000_000.0},  # 2026-07-16, incomplete
        ],
    }


def _stooq_csv(*, last_date: str = "2026-07-16") -> bytes:
    rows = [
        "Date,Open,High,Low,Close,Volume",
        "2026-07-13,100.0,101.0,99.5,100.5,10",
        "2026-07-14,100.5,101.5,100.0,101.0,11",
        "2026-07-15,101.0,102.0,100.5,101.5,12",
        f"{last_date},101.5,102.5,101.0,102.0,13",
    ]
    return ("\n".join(rows) + "\n").encode()


def _raw_for(kind: str) -> bytes:
    return _json_bytes(_hashrate_payload()) if kind == "hashrate" else _stooq_csv()


def test_provider_contract_matches_exact_credential_free_request_builders() -> None:
    raw = PROVIDER_CONTRACT.read_bytes()
    contract = json.loads(raw)
    assert f"sha256:{hashlib.sha256(raw).hexdigest()}" == PROVIDER_CONTRACT_SHA256

    for kind in ("hashrate", "dxy", "vix"):
        specs = build_requests(kind)
        assert len(specs) == 1
        spec = specs[0]
        assert {
            "name": spec.name,
            "url": spec.url,
            "params": spec.params,
        } == contract["providers"][kind]["requests"][0]
        assert contract["providers"][kind]["authentication"] == "none"


def test_dry_run_exposes_requests_without_network_or_writes(capsys) -> None:
    plan = request_plan("vix")
    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert plan["requests"][0]["url"].endswith("s=%5Evix&i=d")
    assert set(plan["boundaries"].values()) == {False}

    assert main(["--kind", "hashrate", "--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["network_accessed"] is False


@pytest.mark.parametrize("kind", ["hashrate", "dxy", "vix"])
def test_snapshot_round_trip_preserves_exact_bytes_and_safe_boundaries(
    tmp_path: Path, kind: str
) -> None:
    raw = _raw_for(kind)
    path, envelope = collect_snapshot(
        kind,
        output_dir=tmp_path,
        fetch=lambda _: raw,
        now=NOW,
    )

    review = verify_snapshot(path)

    assert review["valid"] is True
    assert review["snapshot_sha256"] == envelope["snapshot_sha256"]
    assert envelope["requests"][0]["payload_raw_base64"]
    assert set(envelope["boundaries"].values()) == {False}
    assert review["audit"]["row_count"] == 4
    if kind == "hashrate":
        assert review["audit"]["completed_utc_day_count"] == 3
        assert review["audit"]["incomplete_current_utc_day_count"] == 1
        assert review["audit"]["unit"] == "TH/s"
    else:
        assert review["audit"]["publication_lag_eligible_row_count"] == 3
        assert review["audit"]["not_yet_eligible_row_count"] == 1
        assert review["audit"]["last_session"] == "2026-07-16"


def test_snapshot_creation_is_no_overwrite_and_july_only(tmp_path: Path) -> None:
    collect_snapshot(
        "hashrate",
        output_dir=tmp_path,
        fetch=lambda _: _json_bytes(_hashrate_payload()),
        now=NOW,
    )
    with pytest.raises(FileExistsError):
        collect_snapshot(
            "hashrate",
            output_dir=tmp_path,
            fetch=lambda _: _json_bytes(_hashrate_payload()),
            now=NOW,
        )
    with pytest.raises(ValueError, match="July 2026"):
        collect_snapshot(
            "hashrate",
            output_dir=tmp_path / "august",
            fetch=lambda _: _json_bytes(_hashrate_payload()),
            now=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_verifier_rejects_raw_parsed_audit_and_request_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "dxy",
        output_dir=tmp_path,
        fetch=lambda _: _stooq_csv(),
        now=NOW,
    )
    payload = json.loads(path.read_text())
    payload["requests"][0]["payload"]["rows"][0]["Close"] = "999"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="differs from raw bytes"):
        verify_snapshot(path)

    path, _ = collect_snapshot(
        "hashrate",
        output_dir=tmp_path / "audit",
        fetch=lambda _: _json_bytes(_hashrate_payload()),
        now=NOW,
    )
    payload = json.loads(path.read_text())
    payload["audit"]["row_count"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="audit summary"):
        verify_snapshot(path)

    path, _ = collect_snapshot(
        "vix",
        output_dir=tmp_path / "request",
        fetch=lambda _: _stooq_csv(),
        now=NOW,
    )
    payload = json.loads(path.read_text())
    payload["requests"][0]["url"] = "https://example.invalid/revised"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="request identity"):
        verify_snapshot(path)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda payload: payload["values"].append(
                {"x": payload["values"][-1]["x"], "y": 1.0}
            ),
            "unique and increasing",
        ),
        (
            lambda payload: payload["values"][0].update({"y": float("nan")}),
            "non-standard JSON numeric constant",
        ),
        (
            lambda payload: payload["values"][-1].update({"x": 1784246400}),
            "future UTC day",
        ),
    ],
)
def test_hashrate_validation_fails_closed(mutate, match: str, tmp_path: Path) -> None:
    payload = _hashrate_payload()
    mutate(payload)
    with pytest.raises(ValueError, match=match):
        collect_snapshot(
            "hashrate",
            output_dir=tmp_path,
            fetch=lambda _: _json_bytes(payload),
            now=NOW,
        )


@pytest.mark.parametrize(
    "raw,match",
    [
        (
            b"Date,Open,High,Low,Volume\n2026-07-15,1,2,0.5,10\n",
            "lacks locked OHLC",
        ),
        (
            b"Date,Open,High,Low,Close\n2026-07-15,1,0.5,0.7,2\n",
            "OHLC bounds",
        ),
        (
            b"Date,Open,High,Low,Close\n2026-07-15,1,2,0.5,1\n"
            b"2026-07-15,1,2,0.5,1\n",
            "unique and increasing",
        ),
        (
            b"Date,Open,High,Low,Close\n2026-07-17,1,2,0.5,1\n",
            "future session",
        ),
    ],
)
def test_stooq_validation_fails_closed(raw: bytes, match: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=match):
        collect_snapshot("dxy", output_dir=tmp_path, fetch=lambda _: raw, now=NOW)


def test_collector_has_no_trading_or_credential_dependency() -> None:
    tree = ast.parse(Path(snapshot_module.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(name.startswith("apps.bridge") for name in imported)
    assert not any("nautilus" in name for name in imported)
    assert not any("freqtrade" in name for name in imported)
    assert not any("psycopg" in name for name in imported)

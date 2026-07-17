from __future__ import annotations

import ast
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import apps.ops.research_v4_snapshot as snapshot_module
from apps.ops.research_protocol_v4 import (
    DEFAULT_PROTOCOL,
    validate_protocol,
)
from apps.ops.research_protocol_v4 import (
    validate_file as validate_protocol_file,
)
from apps.ops.research_v4_snapshot import (
    PROVIDER_CONTRACT,
    PROVIDER_CONTRACT_SHA256,
    build_requests,
    collect_snapshot,
    main,
    request_plan,
    verify_snapshot,
)

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _fred_csv(series_id: str, *, last_date: str = "2026-07-16") -> bytes:
    rows = [
        f"observation_date,{series_id}",
        "2026-07-13,100.5",
        "2026-07-14,.",
        "2026-07-15,101.25",
        f"{last_date},102.0",
    ]
    return ("\n".join(rows) + "\n").encode()


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_protocol_lock_is_valid_and_fingerprinted() -> None:
    review = validate_protocol_file()
    assert review["valid"] is True
    assert review["candidate_count"] == 2
    assert review["protocol_sha256"].startswith("sha256:")


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda payload: payload["data_access_disclosure"].update(
                {"documentation_search_exposed_limited_current_rows": False}
            ),
            "disclosure",
        ),
        (
            lambda payload: payload["candidates"][0]["parameters"].update(
                {"usd_return_observations": 19}
            ),
            "parameters",
        ),
        (
            lambda payload: payload["candidates"][1].update(
                {"model_version": "vix-retuned"}
            ),
            "identity",
        ),
        (
            lambda payload: payload["implementation_boundary"].update(
                {"writes_signal_store": True}
            ),
            "implementation boundary",
        ),
    ],
)
def test_protocol_mutations_fail_closed(mutate, match: str) -> None:
    payload = copy.deepcopy(_payload())
    mutate(payload)
    with pytest.raises(ValueError, match=match):
        validate_protocol(payload)


def test_provider_contract_matches_exact_credential_free_requests() -> None:
    raw = PROVIDER_CONTRACT.read_bytes()
    contract = json.loads(raw)
    assert f"sha256:{hashlib.sha256(raw).hexdigest()}" == PROVIDER_CONTRACT_SHA256
    for kind in ("broad_usd", "vix"):
        spec = build_requests(kind)[0]
        assert {
            "name": spec.name,
            "url": spec.url,
            "params": spec.params,
        } == contract["providers"][kind]["requests"][0]
        assert contract["providers"][kind]["authentication"] == "none"


def test_dry_run_exposes_date_limited_requests_without_network_or_writes(capsys) -> None:
    plan = request_plan("broad_usd")
    assert plan["network_accessed"] is False
    assert plan["data_written"] is False
    assert "id=DTWEXBGS" in plan["requests"][0]["url"]
    assert "cosd=2026-07-01" in plan["requests"][0]["url"]
    assert "coed=2026-07-31" in plan["requests"][0]["url"]
    assert set(plan["boundaries"].values()) == {False}
    assert main(["--kind", "vix", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["network_accessed"] is False


@pytest.mark.parametrize(
    "kind,series_id",
    [("broad_usd", "DTWEXBGS"), ("vix", "VIXCLS")],
)
def test_snapshot_round_trip_preserves_exact_bytes_and_safe_boundaries(
    tmp_path: Path,
    kind: str,
    series_id: str,
) -> None:
    raw = _fred_csv(series_id)
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
    assert review["audit"]["observed_row_count"] == 3
    assert review["audit"]["missing_value_row_count"] == 1
    assert review["audit"]["available_at"] == "2026-07-17T12:00:00Z"


def test_snapshot_creation_is_no_overwrite_and_july_only(tmp_path: Path) -> None:
    raw = _fred_csv("VIXCLS")
    collect_snapshot("vix", output_dir=tmp_path, fetch=lambda _: raw, now=NOW)
    with pytest.raises(FileExistsError):
        collect_snapshot("vix", output_dir=tmp_path, fetch=lambda _: raw, now=NOW)
    with pytest.raises(ValueError, match="July 2026"):
        collect_snapshot(
            "vix",
            output_dir=tmp_path / "august",
            fetch=lambda _: raw,
            now=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_verifier_rejects_raw_parsed_audit_and_request_tampering(tmp_path: Path) -> None:
    path, _ = collect_snapshot(
        "broad_usd",
        output_dir=tmp_path,
        fetch=lambda _: _fred_csv("DTWEXBGS"),
        now=NOW,
    )
    payload = json.loads(path.read_text())
    payload["requests"][0]["payload"]["rows"][0]["DTWEXBGS"] = "999"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="differs from raw bytes"):
        verify_snapshot(path)

    path, _ = collect_snapshot(
        "vix",
        output_dir=tmp_path / "audit",
        fetch=lambda _: _fred_csv("VIXCLS"),
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
        fetch=lambda _: _fred_csv("VIXCLS"),
        now=NOW,
    )
    payload = json.loads(path.read_text())
    payload["requests"][0]["url"] = "https://example.invalid/revised"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="request identity"):
        verify_snapshot(path)


@pytest.mark.parametrize(
    "raw,match",
    [
        (
            b"DATE,VIXCLS\n2026-07-15,10\n2026-07-16,11\n",
            "header must be exactly",
        ),
        (
            b"observation_date,VIXCLS\n2026-07-15,10\n2026-07-15,11\n",
            "unique and increasing",
        ),
        (
            b"observation_date,VIXCLS\n2026-07-16,10\n2026-07-18,11\n",
            "future observation",
        ),
        (
            b"observation_date,VIXCLS\n2026-06-30,10\n2026-07-01,11\n",
            "outside July",
        ),
        (
            b"observation_date,VIXCLS\n2026-07-15,nan\n2026-07-16,11\n",
            "finite and positive",
        ),
        (
            b"observation_date,VIXCLS\n2026-07-15,0\n2026-07-16,11\n",
            "finite and positive",
        ),
        (
            b"observation_date,VIXCLS\n2026-07-15,.\n2026-07-16,11\n",
            "at least two observed",
        ),
    ],
)
def test_fred_validation_fails_closed(raw: bytes, match: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=match):
        collect_snapshot("vix", output_dir=tmp_path, fetch=lambda _: raw, now=NOW)


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

from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v6 import (
    DEFAULT_FINGERPRINTS,
    DEFAULT_PROTOCOL,
    DEFAULT_SOURCES,
    load_and_validate_protocol,
    validate_protocol,
)


def _load(path):
    return json.loads(path.read_text())


def test_v6_protocol_and_candidate_fingerprint_are_locked() -> None:
    result = load_and_validate_protocol()

    assert result["valid"] is True
    assert result["archive_bodies_accessed"] is False
    assert result["signals_written"] is False
    assert result["pnl_computed"] is False
    assert result["candidate_fingerprint"]["features_hash"].startswith("sha256:")


def test_v6_rejects_identity_or_parameter_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed = copy.deepcopy(protocol)
    changed["candidates"][0]["model_version"] = "retuned-after-data"
    with pytest.raises(ValueError, match="model_version"):
        validate_protocol(changed, sources, fingerprints)

    changed_fingerprints = copy.deepcopy(fingerprints)
    changed_fingerprints["candidates"][0]["parameters"]["percentage_magnitude"] = 2
    with pytest.raises(ValueError, match="parameters"):
        validate_protocol(protocol, sources, changed_fingerprints)


def test_v6_rejects_window_or_future_blind_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed = copy.deepcopy(protocol)
    changed["partitions"]["historical_development"]["folds"][0]["start"] = "2023-02-01"
    with pytest.raises(ValueError, match="folds"):
        validate_protocol(changed, sources, fingerprints)

    changed = copy.deepcopy(protocol)
    changed["partitions"]["final_future_blind"]["access_status"] = "opened"
    with pytest.raises(ValueError, match="future blind"):
        validate_protocol(changed, sources, fingerprints)


def test_v6_rejects_archive_schema_or_semantics_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed_sources = copy.deepcopy(sources)
    changed_sources["datasets"]["book_depth_factor"]["locked_columns"] = [
        "timestamp",
        "depth",
        "notional",
    ]
    with pytest.raises(ValueError, match="columns"):
        validate_protocol(protocol, changed_sources, fingerprints)

    changed_sources = copy.deepcopy(sources)
    changed_sources["datasets"]["book_depth_factor"][
        "archive_to_rest_mapping_status"
    ] = "assumed"
    with pytest.raises(ValueError, match="semantics"):
        validate_protocol(protocol, changed_sources, fingerprints)


def test_v6_rejects_removed_data_quality_gate() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed = copy.deepcopy(protocol)
    changed["gates"]["provider_qualification"][
        "known_public_misalignment_issue_must_not_reproduce"
    ] = False
    with pytest.raises(ValueError, match="misalignment"):
        validate_protocol(changed, sources, fingerprints)

    changed = copy.deepcopy(protocol)
    changed["gates"]["hard_blockers"].remove("mark_price_consistency_failure")
    with pytest.raises(ValueError, match="mark-price"):
        validate_protocol(changed, sources, fingerprints)


def test_v6_rejects_unsafe_boundary_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed_sources = copy.deepcopy(sources)
    changed_sources["boundaries"]["archive_bodies_accessed"] = True
    with pytest.raises(ValueError, match="boundaries"):
        validate_protocol(protocol, changed_sources, fingerprints)

    changed_protocol = copy.deepcopy(protocol)
    changed_protocol["boundaries_effect"]["resumes_testnet"] = True
    with pytest.raises(ValueError, match="boundaries"):
        validate_protocol(changed_protocol, sources, fingerprints)

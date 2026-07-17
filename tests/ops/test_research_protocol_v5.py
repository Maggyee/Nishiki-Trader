from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v5 import (
    DEFAULT_FINGERPRINTS,
    DEFAULT_PROTOCOL,
    DEFAULT_SOURCES,
    load_and_validate_protocol,
    validate_protocol,
)


def _load(path):
    return json.loads(path.read_text())


def test_v5_protocol_and_candidate_fingerprints_are_locked_to_implementation() -> None:
    result = load_and_validate_protocol()

    assert result["valid"] is True
    assert result["historical_bodies_accessed"] is False
    assert len(result["candidate_fingerprints"]) == 2
    assert all(row["features_hash"].startswith("sha256:") for row in result["candidate_fingerprints"])


def test_v5_protocol_rejects_identity_fold_and_safety_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed = copy.deepcopy(protocol)
    changed["candidates"][0]["model_version"] = "retuned-after-data"
    with pytest.raises(ValueError, match="model_version"):
        validate_protocol(changed, sources, fingerprints)

    changed = copy.deepcopy(protocol)
    changed["partitions"]["curve_fast_track"]["folds"][0]["start"] = "2021-07-01"
    with pytest.raises(ValueError, match="folds"):
        validate_protocol(changed, sources, fingerprints)

    changed_sources = copy.deepcopy(sources)
    changed_sources["boundaries"]["credentials_loaded"] = True
    with pytest.raises(ValueError, match="boundaries"):
        validate_protocol(protocol, changed_sources, fingerprints)


def test_v5_protocol_rejects_fingerprint_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)
    fingerprints["candidates"][1]["features_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="fingerprints"):
        validate_protocol(protocol, sources, fingerprints)


def test_v5_protocol_rejects_provider_path_or_gate_drift() -> None:
    protocol = _load(DEFAULT_PROTOCOL)
    sources = _load(DEFAULT_SOURCES)
    fingerprints = _load(DEFAULT_FINGERPRINTS)

    changed_sources = copy.deepcopy(sources)
    changed_sources["datasets"]["bvol"]["archive_request"] = "unregistered/{date}.zip"
    with pytest.raises(ValueError, match="provider contract differs"):
        validate_protocol(protocol, changed_sources, fingerprints)

    changed_protocol = copy.deepcopy(protocol)
    changed_protocol["gates"]["curve_fast_track"]["closed_positions_at_least"] = 29
    with pytest.raises(ValueError, match="protocol differs"):
        validate_protocol(changed_protocol, sources, fingerprints)

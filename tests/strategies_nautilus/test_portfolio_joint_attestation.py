"""Independent native signatures, input substitution and offline CLI persistence."""

import base64
import copy
import json
import os
import socket
import subprocess
import sys

import pytest
from nautilus_trader.core.nautilus_pyo3 import ed25519_signature

from apps.ops.portfolio_joint_attestation import main
from apps.strategies_nautilus import portfolio_joint_attestation as proof
from apps.strategies_nautilus.portfolio_joint_admission import CONTRACT_SHA256, sha
from apps.strategies_nautilus.portfolio_rate_evidence import RateEvidenceError
from apps.strategies_nautilus.portfolio_stream import canonical
from tests.strategies_nautilus.test_portfolio_joint_admission import MONO, NOW, S, candidate

SCOPE = "joint-authorship-fixture-v1"


def b64(raw):
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture(scope="module")
def keys():
    result = {}
    for role in (*proof.ROLES, "foreign"):
        seed = os.urandom(32)
        public = subprocess.run(
            ["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"],
            input=bytes.fromhex("302e020100300506032b657004220420") + seed,
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
        assert public.startswith(proof.ED25519_SPKI)
        result[role] = seed, public[len(proof.ED25519_SPKI) :]
    return result


def selected(keys, *, value=None, policy_change=None, claim_change=None):
    value = candidate() if value is None else value
    policy = {
        "schema_version": proof.POLICY_SCHEMA,
        "purpose": "offline_authorship_review_only",
        "contract_sha256": CONTRACT_SHA256,
        "scope_id": SCOPE,
        "not_before_ns": NOW - 30 * S,
        "not_after_ns": NOW + 30 * S,
        "bindings": copy.deepcopy(value["ledger"]["bindings"]),
        "public_keys": {r: b64(keys[r][1]) for r in proof.ROLES},
    }
    if policy_change:
        policy_change(policy)
    policy_raw, candidate_raw = canonical(policy), canonical(value)
    bundle = {"schema_version": proof.BUNDLE_SCHEMA}
    for role in proof.ROLES:
        payload = {
            "schema_version": proof.CLAIM_SCHEMA,
            "role": role,
            "contract_sha256": CONTRACT_SHA256,
            "policy_sha256": sha(policy_raw),
            "scope_id": SCOPE,
            "candidate_sha256": sha(candidate_raw),
            "component_sha256": sha(canonical(value["samples" if role == "source" else "ledger"])),
            "issued_at_ns": NOW,
            "expires_at_ns": NOW + 5 * S,
        }
        if claim_change:
            claim_change(role, payload)
        data = canonical(payload)
        bundle[role] = {
            "payload_b64": b64(data),
            # Native Rust signing is independently checked by OpenSSL in production code.
            "signature_b64": ed25519_signature(keys[role][0], (proof.DOMAIN + data).decode()),
        }
    bundle_raw = canonical(bundle)
    return {
        "candidate_raw": candidate_raw,
        "candidate_sha256": sha(candidate_raw),
        "policy_raw": policy_raw,
        "policy_sha256": sha(policy_raw),
        "bundle_raw": bundle_raw,
        "bundle_sha256": sha(bundle_raw),
        "scope_id": SCOPE,
        "at_ns": NOW,
        "monotonic_ns": MONO,
    }


def mutate(inputs, name, update):
    value = json.loads(inputs[name + "_raw"])
    update(value)
    inputs[name + "_raw"] = canonical(value)
    inputs[name + "_sha256"] = sha(inputs[name + "_raw"])


def assert_blocked(report):
    for field in (
        "source_authenticated",
        "shared_egress_verified",
        "network_admitted",
        "capacity_reserved",
        "scope_consumed",
    ):
        assert report[field] is False
    assert report["venue_requests_made"] == 0
    assert not any(report["qualification"].values())
    assert all(
        v is None
        for k, v in report.items()
        if k.startswith("qualified_") or k == "common_account_market_revision"
    )


def test_native_signatures_verify_with_selected_keys_without_qualifying_authorities(keys):
    inputs = selected(keys)
    original = copy.deepcopy(inputs)
    report = proof.review(**inputs)
    assert inputs == original
    assert_blocked(report)
    assert all(r["selected_signer_signature_verified"] for r in report["signatures"].values())
    assert "selected_signer_authorities_not_independently_qualified" in report["blockers"]
    assert "market_connection_charge_unresolved" in report["blockers"]
    assert "gateway_traffic_completeness_and_future_enforcement_unverified" in report["blockers"]
    assert len(report["blockers"]) == 6
    for name in ("candidate", "policy", "bundle"):
        assert report[name + "_sha256"] == inputs[name + "_sha256"]


def test_known_rfc8032_vector_and_corrupted_signature():
    key = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
    sig = bytes.fromhex(
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
    )
    proof._verify(key, sig, b"\x72")
    with pytest.raises(proof.AttestationError, match="signature_invalid"):
        proof._verify(key, bytes([sig[0] ^ 1]) + sig[1:], b"\x72")


@pytest.mark.parametrize("component", ["candidate", "policy", "bundle"])
def test_original_selection_hash_cannot_be_replaced(keys, component):
    inputs = selected(keys)
    inputs[component + "_raw"] += b" "
    with pytest.raises(proof.AttestationError, match="bytes_changed"):
        proof.review(**inputs)


@pytest.mark.parametrize("role", proof.ROLES)
def test_signature_from_foreign_key_fails_even_when_bundle_rehashed(keys, role):
    inputs = selected(keys)

    def substitute(bundle):
        payload = base64.b64decode(bundle[role]["payload_b64"])
        bundle[role]["signature_b64"] = ed25519_signature(
            keys["foreign"][0], (proof.DOMAIN + payload).decode()
        )

    mutate(inputs, "bundle", substitute)
    with pytest.raises(proof.AttestationError, match="signature_invalid"):
        proof.review(**inputs)


def test_source_and_gateway_envelopes_cannot_be_swapped(keys):
    inputs = selected(keys)

    def swap(bundle):
        bundle["source"], bundle["gateway"] = bundle["gateway"], bundle["source"]

    mutate(inputs, "bundle", swap)
    with pytest.raises(proof.AttestationError, match="binding_changed"):
        proof.review(**inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "other"),
        ("role", "other"),
        ("contract_sha256", "0" * 64),
        ("policy_sha256", "0" * 64),
        ("scope_id", "different-scope"),
        ("candidate_sha256", "0" * 64),
        ("component_sha256", "0" * 64),
    ],
)
def test_correctly_signed_wrong_bindings_fail(keys, field, value):
    inputs = selected(
        keys, claim_change=lambda role, p: p.update({field: value}) if role == "source" else None
    )
    with pytest.raises(proof.AttestationError, match="binding_changed"):
        proof.review(**inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("issued_at_ns", NOW + 1),
        ("expires_at_ns", NOW),
        ("expires_at_ns", NOW + 5 * S + 1),
        ("issued_at_ns", NOW - 2 * S),
        ("issued_at_ns", True),
        ("expires_at_ns", 1.2),
    ],
)
def test_signed_future_expired_overlong_or_predating_claims_fail(keys, field, value):
    inputs = selected(keys, claim_change=lambda role, p: p.update({field: value}))
    with pytest.raises((proof.AttestationError, RateEvidenceError)):
        proof.review(**inputs)


def test_claim_cannot_precede_sample_even_inside_five_second_window(keys):
    inputs = selected(
        keys,
        claim_change=lambda role, p: p.update(issued_at_ns=NOW - 2 * S, expires_at_ns=NOW + 2 * S),
    )
    with pytest.raises(proof.AttestationError, match="predates_selected_samples"):
        proof.review(**inputs)


def test_signed_gateway_history_cannot_extend_beyond_signing_time(keys):
    inputs = selected(
        keys,
        claim_change=lambda role, p: p.update(issued_at_ns=NOW - S, expires_at_ns=NOW + 4 * S),
    )
    with pytest.raises(proof.AttestationError, match="predates_observed_gateway_coverage"):
        proof.review(**inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("purpose", "network_admission"),
        ("not_before_ns", NOW + 1),
        ("not_after_ns", NOW),
        ("scope_id", "other"),
        ("contract_sha256", "f" * 64),
        ("not_before_ns", False),
    ],
)
def test_independent_policy_boundaries(keys, field, value):
    inputs = selected(keys, policy_change=lambda p: p.update({field: value}))
    with pytest.raises((proof.AttestationError, RateEvidenceError)):
        proof.review(**inputs)


def test_external_scope_selection_cannot_be_taken_from_bundle(keys):
    inputs = selected(keys)
    inputs["scope_id"] = "another-run"
    with pytest.raises(proof.AttestationError, match="policy_scope"):
        proof.review(**inputs)


def test_same_key_cannot_attest_both_roles(keys):
    inputs = selected(
        keys, policy_change=lambda p: p["public_keys"].update(gateway=p["public_keys"]["source"])
    )
    with pytest.raises(proof.AttestationError, match="distinct_source_and_gateway"):
        proof.review(**inputs)


def test_destination_egress_selection_is_independent_of_signed_candidate(keys):
    inputs = selected(
        keys, policy_change=lambda p: p["bindings"]["market"].update(egress_ip="198.51.100.2")
    )
    with pytest.raises(proof.AttestationError, match="destination_or_egress_drift"):
        proof.review(**inputs)


@pytest.mark.parametrize("where", ["policy", "bundle", "source_envelope", "claim"])
def test_self_authentication_fields_never_override_boundary(keys, where):
    inputs = selected(keys)
    if where == "policy":
        mutate(inputs, "policy", lambda p: p.update(authority_qualified=True))
    elif where == "bundle":
        mutate(inputs, "bundle", lambda p: p.update(network_admitted=True))
    elif where == "source_envelope":
        mutate(
            inputs, "bundle", lambda p: p["source"].update(public_key_b64=b64(keys["foreign"][1]))
        )
    else:
        inputs = selected(keys, claim_change=lambda role, p: p.update(source_authenticated=True))
    with pytest.raises(proof.AttestationError, match="exact_fields"):
        proof.review(**inputs)


def test_full_rehash_of_changed_raw_rate_cannot_reuse_signatures(keys):
    inputs = selected(keys)
    mutate(
        inputs, "candidate", lambda p: p["samples"]["rest"][0]["headers"][0].__setitem__(1, "71")
    )
    with pytest.raises(proof.AttestationError, match="binding_changed"):
        proof.review(**inputs)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("exhausted", "remaining_scope_or_other_clients_exceed_limit"),
        ("missing_coverage", "egress_coverage_gap_or_other_callers_missing"),
        ("other_clients", "other_client_reservation_horizon_incomplete"),
        ("missing_usage", "usage_and_other_client_upper_bound_missing"),
    ],
)
def test_valid_signatures_cannot_remove_capacity_or_coverage_failures(keys, change, reason):
    value = candidate()
    if change == "exhausted":
        value["ledger"]["usage_bounds"][0]["used_upper_bound"] = 6000
    elif change == "missing_coverage":
        value["ledger"]["all_callers"] = False
    elif change == "other_clients":
        value["ledger"]["future_through_ns"] = NOW + S
    else:
        value["ledger"]["usage_bounds"].pop(1)
    report = proof.review(**selected(keys, value=value))
    assert_blocked(report)
    assert any(reason in b for b in report["blockers"])


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("openssl", 5)])
def test_missing_or_timed_out_verifier_fails_closed(keys, monkeypatch, error):
    inputs = selected(keys)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(proof.subprocess, "run", fail)
    with pytest.raises(proof.AttestationError, match="verifier_unavailable"):
        proof.review(**inputs)


@pytest.mark.parametrize(
    "kind",
    [
        "signature_size",
        "signature_base64",
        "key_size",
        "noncanonical_payload",
        "duplicate_json",
        "oversized",
    ],
)
def test_malformed_selected_proofs_fail(keys, kind):
    inputs = selected(keys)
    if kind.startswith("signature"):
        mutate(
            inputs,
            "bundle",
            lambda p: p["source"].update(
                signature_b64=b64(b"x") if kind == "signature_size" else "!?"
            ),
        )
    elif kind == "key_size":
        mutate(inputs, "policy", lambda p: p["public_keys"].update(source=b64(b"x")))
    elif kind == "noncanonical_payload":
        mutate(
            inputs,
            "bundle",
            lambda p: p["source"].update(
                payload_b64=b64(base64.b64decode(p["source"]["payload_b64"]) + b" ")
            ),
        )
    else:
        inputs["policy_raw"] = (
            b'{"a":1,"a":2}' if kind == "duplicate_json" else b" " * (proof.MAX_PROOF + 1)
        )
        inputs["policy_sha256"] = sha(inputs["policy_raw"])
    with pytest.raises((proof.AttestationError, RateEvidenceError)):
        proof.review(**inputs)


def cli_inputs(tmp_path, inputs):
    args = []
    for name in ("candidate", "policy", "bundle"):
        path = tmp_path / (name + ".json")
        path.write_bytes(inputs[name + "_raw"])
        path.chmod(0o600)
        args.extend(["--" + name, str(path), "--" + name + "-sha256", inputs[name + "_sha256"]])
    return args + [
        "--scope-id",
        inputs["scope_id"],
        "--at-ns",
        str(NOW),
        "--monotonic-ns",
        str(MONO),
    ]


def test_cli_has_no_network_credentials_activation_or_reservation(keys, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline attestation tried networking")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    args = cli_inputs(tmp_path, selected(keys))
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    output = tmp_path / "report.json"
    assert main(args + ["--report", str(output)]) == 2
    assert_blocked(json.loads(output.read_bytes()))
    assert output.stat().st_mode & 0o777 == 0o600
    assert set(tmp_path.iterdir()) == {*before, output}
    assert all(p.read_bytes() == data for p, data in before.items())
    original = output.read_bytes()
    assert main(args + ["--report", str(output)]) == 1
    assert output.read_bytes() == original


def test_two_fresh_reviews_reproduce_all_selected_hashes_and_original_bytes(keys, tmp_path):
    args = cli_inputs(tmp_path, selected(keys))
    reports = []
    for i in range(2):
        output = tmp_path / f"report-{i}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_joint_attestation",
                *args,
                "--report",
                str(output),
            ],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 2, proc.stdout + proc.stderr
        reports.append(output.read_bytes())
    assert reports[0] == reports[1]
    assert_blocked(json.loads(reports[0]))


def test_concurrent_report_publication_has_one_winner(keys, tmp_path):
    args = cli_inputs(tmp_path, selected(keys))
    output = tmp_path / "report.json"
    command = [
        sys.executable,
        "-m",
        "apps.ops.portfolio_joint_attestation",
        *args,
        "--report",
        str(output),
    ]
    processes = [
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)
    ]
    for process in processes:
        process.communicate(timeout=30)
    assert sorted(p.returncode for p in processes) == [1, 2]
    assert_blocked(json.loads(output.read_bytes()))


@pytest.mark.parametrize(
    "kind", ["input_alias", "output_symlink", "public_input", "input_symlink", "bad_signature"]
)
def test_cli_failure_never_overwrites_inputs_or_publishes_success(keys, tmp_path, kind):
    inputs = selected(keys)
    if kind == "bad_signature":
        mutate(inputs, "bundle", lambda p: p["source"].update(signature_b64=b64(b"x" * 64)))
    args = cli_inputs(tmp_path, inputs)
    output = tmp_path / "report.json"
    if kind == "input_alias":
        output = tmp_path / "candidate.json"
    elif kind == "output_symlink":
        output.symlink_to(tmp_path / "candidate.json")
    elif kind == "public_input":
        (tmp_path / "policy.json").chmod(0o644)
    elif kind == "input_symlink":
        (tmp_path / "policy.json").rename(tmp_path / "original-policy.json")
        (tmp_path / "policy.json").symlink_to(tmp_path / "original-policy.json")
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(args + ["--report", str(output)]) == 1
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_failed_durable_publication_returns_failure_and_does_not_retry(keys, tmp_path, monkeypatch):
    from apps.strategies_nautilus import portfolio_session_transport

    args = cli_inputs(tmp_path, selected(keys))
    output = tmp_path / "report.json"

    def fail(fd):
        raise OSError("fixture fsync failure")

    monkeypatch.setattr(portfolio_session_transport.os, "fsync", fail)
    assert main(args + ["--report", str(output)]) == 1
    original = output.read_bytes()
    assert main(args + ["--report", str(output)]) == 1
    assert output.read_bytes() == original

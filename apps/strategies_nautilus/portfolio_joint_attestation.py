"""Offline authorship checks for joint source/egress claims, never a permit.

Public keys are selected outside the signed bundle. Valid signatures identify
the selected signers; they do not qualify those signers as exchange collectors or
complete, enforcing gateways. No deployed trust root is selected by this module.
"""

from __future__ import annotations

import base64
import binascii
import re
import subprocess
import tempfile
from pathlib import Path

from apps.strategies_nautilus import portfolio_joint_admission as admission
from apps.strategies_nautilus.portfolio_rate_evidence import _body, _integer
from apps.strategies_nautilus.portfolio_stream import canonical

POLICY_SCHEMA = "portfolio.joint_attestation_policy.v1"
BUNDLE_SCHEMA = "portfolio.joint_attestation_bundle.v1"
CLAIM_SCHEMA = "portfolio.joint_attestation_claim.v1"
DOMAIN = b"trader/portfolio/joint-attestation/v1\x00"
MAX_PROOF = 64 * 1024
ROLES = ("source", "gateway")
# RFC 8410 SubjectPublicKeyInfo for an Ed25519 raw public key (no parameters).
ED25519_SPKI = bytes.fromhex("302a300506032b6570032100")


class AttestationError(ValueError):
    """Selected evidence cannot be attributed to the selected signers."""


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise AttestationError("attestation_exact_fields_required")


def _selected(raw, expected, limit):
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= limit
        or not isinstance(expected, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        or admission.sha(raw) != expected
    ):
        raise AttestationError("selected_attestation_bytes_changed")
    return _body(raw)


def _decode(value, *, size=None):
    if not isinstance(value, str) or len(value) > MAX_PROOF:
        raise AttestationError("invalid_attestation_base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AttestationError("invalid_attestation_base64") from exc
    if base64.b64encode(raw).decode("ascii") != value or (size is not None and len(raw) != size):
        raise AttestationError("noncanonical_attestation_base64_or_size")
    return raw


def _verify(public, signature, message):
    """Use the existing OpenSSL executable; missing/failed verification is fatal.

    These temporary inputs contain public keys, signatures and bounded claims,
    never trading credentials. No shell, network, private key or key discovery.
    """
    with tempfile.TemporaryDirectory(prefix="trader-joint-attestation-") as directory:
        root = Path(directory)
        (root / "public.der").write_bytes(ED25519_SPKI + public)
        (root / "signature").write_bytes(signature)
        (root / "message").write_bytes(message)
        try:
            result = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-keyform",
                    "DER",
                    "-rawin",
                    "-inkey",
                    str(root / "public.der"),
                    "-sigfile",
                    str(root / "signature"),
                    "-in",
                    str(root / "message"),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AttestationError("attestation_verifier_unavailable") from exc
        if result.returncode != 0:
            raise AttestationError("attestation_signature_invalid")


def review(
    candidate_raw,
    *,
    candidate_sha256,
    policy_raw,
    policy_sha256,
    bundle_raw,
    bundle_sha256,
    scope_id,
    at_ns,
    monotonic_ns,
):
    """Authenticate selected claim authorship and independently recheck capacity.

    ``scope_id`` and the policy hash must be selected independently of the bundle.
    Historical replay is allowed; it cannot consume a scope or reserve capacity.
    All timestamps use integer Unix ns except the candidate's local monotonic ns.
    """
    _integer(at_ns, positive=True)
    _integer(monotonic_ns, positive=True)
    if (
        not isinstance(scope_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", scope_id) is None
    ):
        raise AttestationError("independent_scope_id_required")
    policy = _selected(policy_raw, policy_sha256, MAX_PROOF)
    _fields(
        policy,
        "schema_version purpose contract_sha256 scope_id not_before_ns not_after_ns bindings public_keys",
    )
    if (
        policy["schema_version"] != POLICY_SCHEMA
        or policy["purpose"] != "offline_authorship_review_only"
        or policy["contract_sha256"] != admission.CONTRACT_SHA256
        or policy["scope_id"] != scope_id
    ):
        raise AttestationError("attestation_policy_scope_or_purpose_changed")
    start = _integer(policy["not_before_ns"], positive=True)
    end = _integer(policy["not_after_ns"], positive=True)
    if not start <= at_ns < end:
        raise AttestationError("attestation_policy_not_current_at_review")
    _fields(policy["bindings"], "rest account market")
    for role in admission.ENDPOINTS:
        admission.binding(policy["bindings"][role], role)
    _fields(policy["public_keys"], "source gateway")
    keys = {role: _decode(policy["public_keys"][role], size=32) for role in ROLES}
    if keys["source"] == keys["gateway"]:
        raise AttestationError("distinct_source_and_gateway_keys_required")

    candidate = _selected(candidate_raw, candidate_sha256, admission.MAX_INPUT)
    capacity = admission.review(
        candidate_raw, expected_sha256=candidate_sha256, at_ns=at_ns, monotonic_ns=monotonic_ns
    )
    # Authorship needs both roles' actual inputs, even when arithmetic was blocked.
    if candidate["ledger"] is None or any(not candidate["samples"][r] for r in ("rest", "account")):
        raise AttestationError("complete_signed_components_required")
    if policy["bindings"] != candidate["ledger"]["bindings"] or any(
        sample["binding"] != policy["bindings"][role]
        for role, samples in candidate["samples"].items()
        for sample in samples
    ):
        raise AttestationError("attestation_policy_destination_or_egress_drift")
    bundle = _selected(bundle_raw, bundle_sha256, MAX_PROOF)
    _fields(bundle, "schema_version source gateway")
    if bundle["schema_version"] != BUNDLE_SCHEMA:
        raise AttestationError("attestation_bundle_profile_changed")
    verified = {}
    for role in ROLES:
        envelope = bundle[role]
        _fields(envelope, "payload_b64 signature_b64")
        payload_raw = _decode(envelope["payload_b64"])
        payload = _body(payload_raw)
        _fields(
            payload,
            "schema_version role contract_sha256 policy_sha256 scope_id candidate_sha256 component_sha256 issued_at_ns expires_at_ns",
        )
        component = candidate["samples" if role == "source" else "ledger"]
        expected = {
            "schema_version": CLAIM_SCHEMA,
            "role": role,
            "contract_sha256": admission.CONTRACT_SHA256,
            "policy_sha256": policy_sha256,
            "scope_id": scope_id,
            "candidate_sha256": candidate_sha256,
            "component_sha256": admission.sha(canonical(component)),
        }
        if canonical(payload) != payload_raw or any(payload[k] != v for k, v in expected.items()):
            raise AttestationError("attestation_claim_binding_changed")
        issued = _integer(payload["issued_at_ns"], positive=True)
        expires = _integer(payload["expires_at_ns"], positive=True)
        if not start <= issued <= at_ns < expires <= end or expires - issued > 5 * admission.SECOND:
            raise AttestationError("attestation_claim_expired_future_or_overlong")
        if any(s["received_ns"] > issued for rows in candidate["samples"].values() for s in rows):
            raise AttestationError("attestation_predates_selected_samples")
        # Map the claimed signing time through each retained server-clock anchor.
        # A signature over future *observed* gateway coverage is not admissible
        # evidence, even though future enforcement bounds are allowed separately.
        if any(
            candidate["ledger"]["covered_through_ns"]
            > rows[-1]["server_time_ns"][1] + issued - rows[-1]["received_ns"]
            for rows in candidate["samples"].values()
        ):
            raise AttestationError("attestation_predates_observed_gateway_coverage")
        _verify(keys[role], _decode(envelope["signature_b64"], size=64), DOMAIN + payload_raw)
        verified[role] = {
            "selected_key_sha256": admission.sha(keys[role]),
            "payload_sha256": admission.sha(payload_raw),
            "component_sha256": expected["component_sha256"],
            "issued_at_ns": issued,
            "expires_at_ns": expires,
            "selected_signer_signature_verified": True,
        }
    return {
        "schema_version": "portfolio.joint_attestation_review.v1",
        "status": "selected_authorship_verified_network_blocked",
        "scope_id": scope_id,
        "contract_sha256": admission.CONTRACT_SHA256,
        "candidate_sha256": candidate_sha256,
        "policy_sha256": policy_sha256,
        "bundle_sha256": bundle_sha256,
        "reviewed_at_ns": at_ns,
        "reviewed_monotonic_ns": monotonic_ns,
        "signatures": verified,
        "capacity_review": capacity,
        "blockers": sorted(
            set(capacity["blockers"])
            | {
                "selected_signer_authorities_not_independently_qualified",
                "gateway_traffic_completeness_and_future_enforcement_unverified",
            }
        ),
        "source_authenticated": False,
        "shared_egress_verified": False,
        "network_admitted": False,
        "capacity_reserved": False,
        "scope_consumed": False,
        "venue_requests_made": 0,
        "qualification": capacity["qualification"],
        **{
            k: v
            for k, v in capacity.items()
            if k.startswith("qualified_") or k == "common_account_market_revision"
        },
    }

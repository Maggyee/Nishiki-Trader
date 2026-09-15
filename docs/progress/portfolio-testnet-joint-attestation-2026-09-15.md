# Offline joint source/gateway authorship review — 2026-09-15

The joint evidence path can now verify two independently selected Ed25519
signatures before attributing rate samples and gateway claims to their signers.
It binds both signatures to the exact candidate, selected policy, intended scope
and observed destination/egress addresses, then retains the original capacity
review and every blocker. Previously, the input format could express claims but
could not verify their authorship.

This is an **offline authorship interface**, not an installed source collector,
gateway, authority registry or admission permit. There are no selected real
signer authorities or actual signed gateway records in this increment. Two keys
do not prove organizational independence or complete traffic coverage. A signed
`all_callers=true` remains a claim about coverage, and a signed future upper bound
does not enforce it. The real capture draft stays unchanged at SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.

## Selection and signed format

`apps/strategies_nautilus/portfolio_joint_attestation.py` takes three original
byte inputs and their independently selected SHA256s, an expected scope ID, and
UTC/monotonic review times. The existing candidate format is unchanged.

| Input | Required fields and meaning |
|---|---|
| Policy | `schema_version=portfolio.joint_attestation_policy.v1`, `purpose=offline_authorship_review_only`, fixed `contract_sha256`, `scope_id`, `not_before_ns`, `not_after_ns`, `bindings` for REST/account/market, and `public_keys` for source/gateway. Bindings use the existing exact endpoint/IP/address-family format. Public keys are canonical base64 of 32 raw Ed25519 bytes and must differ. |
| Bundle | `schema_version=portfolio.joint_attestation_bundle.v1`, plus `source` and `gateway` envelopes. Each envelope contains only `payload_b64` and `signature_b64`; it cannot supply or replace its verification key. |
| Claim payload | `schema_version=portfolio.joint_attestation_claim.v1`, `role`, `contract_sha256`, `policy_sha256`, `scope_id`, `candidate_sha256`, `component_sha256`, `issued_at_ns`, `expires_at_ns`. Source commits to canonical candidate `samples`; gateway commits to canonical `ledger`. Both also commit to the entire original candidate. |

Payload bytes must equal the existing sorted-key, compact JSON `canonical()`
encoding. The signature covers the exact bytes
`b"trader/portfolio/joint-attestation/v1\x00" + payload_raw`.
Policy/bundle inputs are capped at 64 KiB each; the candidate retains its 16 MiB
cap. Unknown fields, duplicate JSON keys, noncanonical base64, wrong sizes and
noninteger times fail. No signature issuer, policy path or public key is discovered
from the bundle or environment. The policy's hash and expected scope must be
selected separately; choosing them alone does not qualify a deployment authority.

Claims must lie within the policy validity interval and have lifetimes at most
five seconds. The review instant must be at/after issuance and strictly before
expiry. Signatures cannot predate selected sample receipts or claim already
observed gateway coverage later than their signing time, mapped through each
retained server-clock uncertainty interval. These are signed timestamp consistency
checks, not independent clock authentication. Existing sample age, server-clock,
bucket, usage and coverage checks are rerun from original candidate bytes.

Verification uses the existing installed OpenSSL executable with fixed Ed25519
SubjectPublicKeyInfo encoding and `pkeyutl -verify`, without shell execution.
Missing OpenSSL, verification failure or a five-second subprocess timeout fails
closed. Temporary verification inputs live in a private temporary directory and
contain public keys, bounded claims and signatures only. No package is installed,
no trading private key is read, and no credential discovery is added. Acceptance
uses ephemeral keys, native Nautilus/Rust signatures and a published RFC 8032
test vector independently verified by OpenSSL.

## Report and CLI

```bash
.venv/bin/python -m apps.ops.portfolio_joint_attestation \
  --candidate SELECTED-CANDIDATE.json --candidate-sha256 ORIGINAL-CANDIDATE-SHA256 \
  --policy SELECTED-POLICY.json --policy-sha256 INDEPENDENTLY-SELECTED-POLICY-SHA256 \
  --bundle SELECTED-BUNDLE.json --bundle-sha256 ORIGINAL-BUNDLE-SHA256 \
  --scope-id INDEPENDENTLY-SELECTED-SCOPE \
  --report data/NEW-JOINT-AUTHORSHIP-REVIEW.json
```

`--at-ns UTC-NS --monotonic-ns MONOTONIC-NS` selects a historical review instant;
both must be provided together. Each report records that instant, all three
original hashes, per-role key/payload/component hashes, validity intervals and
the complete underlying capacity review. Verification is relative to the recorded
instant, not a promise of freshness when the CLI finishes or the report is read.
The executable fixture format is `selected()` in
`tests/strategies_nautilus/test_portfolio_joint_attestation.py`; its generated keys
and documentation IPs are not real trust configuration.

Return code **2** means authorship was verified and a new private blocked report
was written. Code **1** means verification or publication failed. Usage errors
are handled by argparse. Reports have mode 0600, exclusive creation, file fsync
and directory fsync. Input aliases, symlinks, public input permissions and existing
outputs are refused. Failed fsync leaves the file for inspection; another invocation
cannot overwrite it. Concurrent publication permits only one writer.

Reports always retain `source_authenticated=false`, `shared_egress_verified=false`,
`network_admitted=false`, `capacity_reserved=false`, `scope_consumed=false` and
zero venue requests. A per-role `selected_signer_signature_verified=true` proves
only authorship under the selected public key. All six qualification flags remain
false; qualified equity/loss and common account/market revision remain null.
Historical review is repeatable into new output files: it is deliberately not
a durable real one-shot activation or a gateway capacity reservation.

## Verification and remaining work

**58 new tests / 164 focused tests pass.** Coverage includes native signatures and
the RFC vector, original-hash and full-rehash substitutions, wrong keys/roles/scope,
expired/future/overlong claims, observation-before-signing consistency, malformed
proofs, verifier failure, and correctly signed insufficient capacity/coverage.
Socket/DNS guards verify no networking. Two fresh CLI processes produce identical
blocked reports; concurrent publication, private inputs, symlinks and failed fsync
exercise the actual filesystem boundary. Full offline regression passes
**3,206 tests, 12 deselected in 311.78 seconds**
(`-m 'not network and not postgres'`). The Postgres integration cases have no
dedicated test DSN. Ruff for apps/tests/notebooks, changed-file formatting,
research registry, 121 local documentation links and diff checks pass. The
original capture contract hash is unchanged. `docs/project-status.md` records
the same results.

The next integration still needs independently qualified source and gateway
authorities, actual source-bound records covering every caller and failed/uncertain
operation, and enforceable future usage bounds. Bind the verified claims to those
records before implementing per-dispatch durable reservations and the separate
real one-shot capture profile. Unresolved market-connection charges, missing
pre-existing fresh usage and full-account/UTC/flow/reset evidence remain blockers.
The interface does not supply missing records, grant a bootstrap probe, or consume
or reset the existing ADR-017/public-depth scopes. Strict continuity stays **0/14**.

Changed files: both new `portfolio_joint_attestation.py` modules, their strategy
test file, both app READMEs, `docs/agent-reading-list.md`, `docs/project-status.md`,
and this report. No upstream code, execution runner, SourcePolicy, schedule,
SignalEvent contract or live trading path changed.

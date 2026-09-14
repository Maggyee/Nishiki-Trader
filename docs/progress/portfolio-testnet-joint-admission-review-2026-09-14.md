# Offline joint first-request admission review — 2026-09-14

A new offline reviewer now turns the first-request requirements of the
[fixed real capture draft](portfolio-testnet-joint-capture-contract-2026-09-14.md)
into executable capacity and refusal checks. It reparses original REST/WS rate
bytes, reviews candidate coverage and usage bounds, and reports missing evidence
before any network operation. It does not authenticate gateway records or enable
the real capture profile. The [local TLS transport](portfolio-testnet-joint-tls-transport-2026-09-14.md)
remains a separate fixture profile.

The draft JSON remains byte-identical at SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
No existing scope, credential, private checkpoint, network policy or execution
runner is modified. The public v1/v2 attempts and ADR-017 scope stay consumed.

## Implemented calculation

`apps/strategies_nautilus/portfolio_joint_admission.py` reviews the maximum scope
**before its first dispatch**. It reserves all **17 GETs / 468 documented weight**
and two WebSocket connections, including the early metadata GET. It does not
subtract an assumed completed request, choose cheaper routes, replace later route
metadata with the early sample, or implement per-dispatch durable reservations.

REST metadata and ordered header pairs are reparsed by `rest_rate_evidence`;
account WS replies are reparsed by `ws_rate_evidence` with their original request
IDs. A caller cannot supply an already normalized rate report. Original body,
header-pair and candidate hashes remain in the report. All advertised intervals
are retained, with REST and WS counts kept separate even when their values agree.

Each sample declares UTC/monotonic receipt times, a server-time uncertainty
interval and an exact destination/egress/address-family binding. These declarations
are untrusted candidate inputs. The reviewer rejects future receipts, clock
inconsistency and changed source/time ordering. The newest sample must be no more
than five seconds old. For fixed-window rates, the full sample and review-time
uncertainty intervals must occupy the same accounting bucket. Histories reject
changed definitions, crossed buckets and regressing counters; no reset is inferred.

Candidate usage bounds cover the entire applicable interval through the review
instant and include all callers and failed/uncertain operations. The calculation
requires declared full interval coverage and separate upper bounds for other
callers through the 120-second capture plus five-second shutdown horizon. A bound
below an observed server count is rejected, not silently replaced by a preferred
counter. Coverage extending into the observed future is invalid.

For each weight interval, the conditional calculation is:

`headroom = limit - candidate_used_upper_bound - other_clients_upper_bound - 468`

Reserving the whole documented REST/WS weight against each weight scope is a
conservative arithmetic check; it does not establish that provider scopes merge.
REST RAW_REQUESTS reserves 17 requests and requires its own full-interval bound;
missing usage remains null. Account ORDERS cannot use an IP ledger. Unknown
operation costs/scopes are explicit blockers. Equality at zero headroom fits the
stated arithmetic; negative headroom fails. The unresolved market connection
request-weight charge remains a blocker even with positive documented headroom.

Connection attempts retain IDs, endpoint roles, server-time intervals and outcomes.
Succeeded, failed and uncertain attempts all count. Duplicate IDs and attempts
outside the declared observed interval fail. An uncertain timestamp overlapping
the preceding 300-second window is conservatively counted. The reviewer preserves
separate account/market counts and also reserves their union, both remaining
connections and both other-client upper bounds against the documented 300 limit.
Missing endpoint usage bounds leave the union/headroom null. This union does not
claim a provider-shared connection counter. The documented market limit is not
labelled as a fresh authenticated sample.

## Candidate format and trust boundary

The input schema is `portfolio.joint_admission_candidate.v1`. Input bytes must be
selected by their original SHA256 and are limited to 16 MiB. The exact top-level
fields are `schema_version`, `contract_sha256`, `samples` and `ledger`.

| Field | Required contents |
|---|---|
| `samples.rest`, `samples.account` | At most 16 original sample envelopes each; empty lists remain missing evidence. |
| Sample envelope | `binding`, `received_ns`, `monotonic_ns`, `server_time_ns: [low, high]`, `raw_b64`, `body_sha256`, and either REST `headers` or account `request_id`. |
| Binding | Exact draft `endpoint`, canonical `destination_ip`, canonical public-egress claim `egress_ip`, and consistent integer `address_family` (4/6). Names and IP claims are never resolved or authenticated. |
| Ledger coverage | `bindings` for all three roles; `covered_from_ns`, `covered_through_ns`, `future_through_ns`, `all_callers`. Times use the declared server clock; future coverage is a claimed reservation horizon, not observed traffic. |
| `usage_bounds` | At most 128 entries: `role`, `rate_limit_type`, `interval_seconds`, `used_upper_bound`, `other_clients_upper_bound`. Counters are nonnegative integers, never booleans. Unknown or duplicate dimensions fail. Weight/RAW_REQUESTS cover fixed buckets; CONNECTIONS cover the preceding rolling interval. |
| `connection_attempts` | At most 4,096 entries: unique `id`, `role` (account/market), `server_time_ns: [low, high]`, `outcome` (succeeded/failed/uncertain). No outcome grants a refund. |

The executable example builder is `candidate()` in
`tests/strategies_nautilus/test_portfolio_joint_admission.py`. Its IPs and inputs
are synthetic documentation fixtures. No fixture is installed as actual evidence.

The ledger format expresses candidate bounds; it is **not a gateway evidence or
attestation protocol**. This increment does not implement independent collection,
cryptographic authentication, complete traffic reconstruction, or enforcement of
other callers' future usage. A hash, matching endpoint/IP claim, `all_callers=true`
or a full-looking list cannot establish those properties. Unknown fields such as
`source_authenticated=true` cannot override the input contract.

Every report keeps `source_authenticated`, `shared_egress_verified` and
`network_admitted` false. The blockers always include missing authenticated source
and egress adapters, unresolved market connection charge, and the unimplemented
real capture profile/durable activation. The report contains no permit object and
has no connection to a dispatch function. All six qualification flags stay false;
qualified equity/loss fields and common account/market revision remain null, and
strict continuity stays **0/14**.

## Offline CLI and verification

The missing-input review requires no credentials or candidate file:

```bash
.venv/bin/python -m apps.ops.portfolio_joint_admission \
  --report data/NEW-JOINT-ADMISSION-REVIEW.json
```

For candidate replay, add `--candidate FILE --candidate-sha256 ORIGINAL-SHA256`.
Select both `--at-ns UTC-NS --monotonic-ns MONOTONIC-NS` to reproduce a historical
calculation; otherwise the CLI uses current clocks. Historical review times cannot
turn the report into a current permit. Files use existing private read/new-write
helpers; reports cannot overwrite inputs, existing outputs or symlinks.

Return code **2** means a review was written and admission is blocked. Return code
**1** means review failed; no successful report is published. There is no successful
admission return code, capture option, credential discovery, activation write or
network fallback. The actual no-input CLI run returned the six expected blockers,
`blocked_before_first_request` and zero venue requests.

**55 new tests and 51 existing rate tests pass (106 focused).** Cases cover full
remaining scope, equality/overrun, other callers, independent endpoint counters,
unknown usage, every connection outcome, uncertain rolling edges, incomplete
coverage/horizon, sample ages, clock/bucket boundaries, history regression,
malformed fields, source drift, fake authentication fields and original hashes.
Socket and DNS guards cover missing and complete-looking candidates. Two fresh
CLI processes produce byte-identical reports while returning blocked, and input
bytes remain unchanged. The private output cannot be reused. Full offline
regression: **3,148 passed, 12 deselected in 311.52 seconds**
(`-m 'not network and not postgres'`). The 12 Postgres integration cases lack a
dedicated test DSN. Ruff for apps/tests/notebooks, changed-file formatting,
research registry, new progress links and diff checks pass.
`docs/project-status.md` records these results; older verification details remain
in their linked progress reports.

Next establish an actual source/gateway trust and evidence mechanism and obtain
fresh pre-existing samples, complete bound-egress records and enforceable other
caller bounds. Then wire authenticated inputs into per-dispatch durable reservations
and the separate real one-shot activation/profile. No unbudgeted seed probe,
new service, scope reset or default-zero usage is enabled by this work.

Changed files: the strategy and ops `portfolio_joint_admission.py` modules,
`tests/strategies_nautilus/test_portfolio_joint_admission.py`, both app READMEs,
`docs/agent-reading-list.md`, `docs/project-status.md`, and this report. Upstream,
SignalEvent v1, research policy and the live order path are unchanged.

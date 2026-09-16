# Dedicated IPv4 preparation and prospective REST bootstrap

## Decision and current delivery

On September 16 the operator selected **a dedicated public IPv4 for collection,
preserving the existing personal proxy's source and availability**. Reusing the
current shared public address is no longer the default implementation choice.
This selects a topology, not a cloud purchase, an installed guard or a network
attempt. Cloud capacity, address assignment and cost are still unknown.

The project now includes a system-Python host snapshot tool and a separate
[machine-readable bootstrap proposal](portfolio-dedicated-egress-bootstrap-2026-09-16.json).
The proposal is Draft: it has no transport implementation or activation authority.
It makes the first-request policy choice explicit instead of requiring missing
historical gateway records indefinitely. The old joint contract and its admission
reviewer retain their original strict semantics.

## Deployment inputs and implementation order

| Order | Deliverable | Acceptance and boundary |
|---|---|---|
| 1 | Oracle secondary private IPv4 on the existing VNIC, associated with a distinct public IPv4 | First check tenancy capacity and cost. Retain the VNIC/private-IP/public-IP association and subnet Internet Gateway route from the console/export with capture time and provenance. Do not replace the primary address or infer the public mapping from host `ip address`. |
| 2 | Explicit collector identity and source routing | Select a dedicated unprivileged collector UID, namespace and secondary private source; route/SNAT only its traffic through that source. Keep proxy, Docker and other workloads on their existing source. Reject use of the secondary source by other host/forwarded callers. Disable IPv6 only inside the collector namespace and refuse proxies, redirects and fallback. |
| 3 | Guard and durable controller | Keep independent OUTPUT/FORWARD enforcement. Bind the actual source, authorized caller and destination to a controller that owns all transport dispatch. Exercise routing, NAT, reused sockets, bypass attempts, shutdown and expiry in a staging topology before host changes. Stop the collector before rollback; remove only owned resources. Existing isolated checks are reusable but do not qualify cloud routing or production enforcement. |
| 4 | Fixed storage root | Proposed location: `/var/lib/trader/egress`, outside this checkout and temporary storage. Administrator-owned parent, fixed collector-owned 0700 leaf, exclusive activation, fsync and private journals. Bind the selected filesystem/mount, UID and directory identity in deployment evidence. No path-override/resume interface in a real runner. Missing/replaced storage or uncertain recovery stops dispatch. Power-loss and backup rollback still need explicit treatment. |
| 5 | Review and implement the separate bootstrap | Bind the selected source/mapping, destination IPv4, deployment evidence, code revision and one fixed scope. Validate transport and crash/consumption behavior locally first. Only an explicit activation of this new contract may perform its one public GET. |
| 6 | Review the resulting evidence before a new joint capture decision | Successful discovery is not a joint collector permit. Full-interval usage, current clocks, other scope dimensions and the undocumented market-WS charge remain separate requirements. |

Cloud association records may contain tenant/resource IDs and addresses. Keep raw
records in private ignored local storage, with their original hashes; do not commit
them, API credentials or private keys. A captured configuration record binds what
was observed at that time, not historical usage or permanent routing guarantees.
Root/cloud administrators remain trusted; mapping, route or policy changes revoke
the asserted binding and halt collection.

The concrete external input is the secondary-private/public-IP pair and its VNIC
association. The current environment has no `oci` executable and this task has no
selected cloud API access. Provisioning therefore remains an operator cloud-console
step after checking cost/capacity. Installing a cloud SDK is unnecessary just to
record these bindings. The snapshot tool does not query instance metadata or a
public-IP service.

## Proposed first-request exception: one public REST discovery

The frozen joint draft requires current authenticated capacity **before even its
first GET**. That evidence is unavailable. A firewall, a new address or waiting
cannot prove the missing historical usage. A seed request cannot satisfy that rule
retroactively.

This separate proposal instead permits, **if explicitly accepted and activated
after deployment acceptance**, one bounded discovery operation while acknowledging
that prior provider usage and current limits are unknown. This is a prospective
policy exception accepting possible rejection/ban, not a proof of unused quota.
A recycled dedicated address may retain provider-side usage or restrictions.
The operator has selected the topology; that choice alone does not accept or
activate this first-request exception.

The complete proposed operation is:

```text
GET https://testnet.binance.vision/api/v3/exchangeInfo
No query parameters, credentials, API-key header, order request or WebSocket.
```

- One fixed scope, one TCP connection attempt, one TLS handshake and at most one
  HTTP GET. The pinned September 14 documentation budgets **20 REQUEST_WEIGHT**
  and one REST request; this is a documented cost, not a measured current limit.
- No separate time/ping request, discovery fallback, retry, reconnect or redirect.
  The transport receives an explicitly selected destination IPv4 and retained
  hostname-resolution evidence; it performs no DNS request. TLS still verifies
  `testnet.binance.vision` using trusted system roots and the correct SNI.
- Consume the fixed scope durably before any socket attempt. A failed handshake,
  uncertain send, timeout, process exit or archive failure consumes the attempt;
  there is no refund, reset or second address/filename to bypass the marker.
- One ten-second end-to-end deadline, with at most two more seconds to close and
  archive. Bound headers to 64 KiB, body to 8 MiB and archive to 16 MiB including a
  4 KiB incident reserve. Bound HTTP framing before buffering; malformed framing,
  redirects and oversized responses terminate the attempt.
- Retain original HTTP status, headers and body, TLS certificate/verification and
  destination/source binding, plus UTC/monotonic dispatch/receipt times. No HTTP
  authorization fields exist for this request. Error responses, including 418/429
  and Retry-After, are retained and end the attempt without automatic retry.
- Only a successful, complete response is passed to the existing
  `rest_rate_evidence` parser. Preserve missing RAW_REQUESTS/connection usage as
  unknown. Receipt clocks and HTTP Date do not become qualified server-clock
  uncertainty intervals or UTC account baselines.

This proposal does **not** add 20 weight to the old 468-weight scope and claim it
is runnable. It is a separate public-only observation. By the time its evidence is
reviewed, it may be stale for the joint contract's five-second requirement. A later
contract must explicitly connect continuous source-bound accounting, clock evidence
and fresh observations; this draft promises no automatic transition or further
requests. The unknown market-stream connection charge remains unresolved.

## Implemented read-only host snapshot

Run from the checkout using a new report filename:

```bash
/usr/bin/python3 -I infra/egress-guard/inspect_host.py \
  --nft-via-sudo \
  --storage-root /var/lib/trader/egress \
  --report data/NEW-EGRESS-HOST-SNAPSHOT.json
```

The explicit sudo option uses only the existing optional read grant:
`sudo -n /usr/sbin/nft -j list ruleset`. Without it the tool tries nft as the
current user. It never prompts for a password or installs sudoers entries.
Missing tools, permissions, timeout, invalid output and namespace changes remain
explicit failures; unreadable data never becomes an empty/zero result.

Seven fixed local read commands retain links, addresses, IPv4/IPv6 routes and
policy rules, and nft rules. Each has a five-second timeout and retains up to
4 MiB per stdout/stderr stream with hashes. Metadata checks walk storage ancestors
without following symlinks and never create or claim that root. Output is exclusive
0600, cannot overwrite a report/symlink, and leaves partial output on failure.
Use a trusted existing parent directory for the report. This reporting file is not
the fsynced directory/activation journal of a real controller.

Console output includes only counts, blockers and the report hash. Full addresses,
rules and command errors stay private. This is a non-atomic point-in-time snapshot
in the caller's network namespace; matching start/end namespace IDs cannot prove
that intermediate rules/routes were stable or that this is every host namespace.
No cloud mapping, continuous ledger, provider budget or deployment permit follows.
Exit **2** means a report was written and deployment inputs remain incomplete;
exit **1** means report creation failed. There is no admission-success exit code.

## Actual local evidence and verification

The September 16 invocation above successfully read all seven sources, including
the existing read-only sudo rule. It found 27 interfaces, two IPv4 default-route
entries, one IPv6 default-route entry, 27 nft base chains and no nft flowtable
entries. Multiple route entries do not mean multiple public sources. The primary
NIC currently shows one private IPv4; no dedicated cloud binding is established.
The proposed `/var/lib/trader/egress` root is missing. Zero testnet requests were
made and no host rules, routes, credentials or proxy configuration changed.

Private local report: `data/egress-host-inspection-2026-09-16.json`, SHA256
`81d5a5bd64a0e8cb4eea8f476293c482baccfed89c801a76046eab64e1de6870`.
This observed-now hash selects this snapshot only; it is not historical gateway
provenance. The raw report is ignored and excluded from the commit.

The **24 new tests** verify read-command enforcement, incomplete/malformed
observations, timeout and output limits, namespace changes, storage ownership and
symlinks, private output, sanitized console output and refusal to overwrite.
**195 focused tests pass** with the existing controller, rate parser and joint
admission suites. Ruff/formatting, local documentation links, original snapshot
output hashes, proposal cost against the pinned operation and frozen-contract
hash/diff checks pass. Full application regression was not rerun for this standalone
inspector and draft. No namespace fixture code or application runtime was changed.

The old joint draft remains SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
ADR-017 and both public-depth scopes remain consumed. Full-account/UTC/flow/reset
qualification, real fills/cleanup and strict continuity **0/14** are unchanged.
No upstream source or live trading path is touched. The next entrypoint is the
actual Oracle binding and staging acceptance for its source-routing/controller
integration, followed by the separate bootstrap transport implementation/review.

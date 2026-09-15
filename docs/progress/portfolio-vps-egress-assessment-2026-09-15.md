# VPS egress assessment — 2026-09-15

The operator confirms this is their own VPS, its sing-box proxy serves their own
devices, and Oracle assigns the public IPv4 to its VNIC with a subnet default
route through an Internet Gateway. This resolves the reported cloud topology;
it does not provide a historical all-caller audit or prove each collector
connection uses that address. Actual gateway audit records remain unavailable.

The [offline reservation rehearsal](portfolio-testnet-joint-reservation-2026-09-15.md)
is complete. This assessment proposes the host boundary needed for a future
gateway ledger. No firewall, service, route, cloud resource or collector is
installed or activated by this documentation change.

## Observations and evidence limits

| Source | Finding | Limit |
|---|---|---|
| Read-only host inspection | Oracle/KVM host; primary NIC has private IPv4 and global IPv6, with default routes; multiple Docker bridges and Tailscale routing exist. | Route/configuration snapshots do not prove every future destination's actual public source. |
| Operator's Oracle console confirmation | Public IPv4 is bound to the VNIC; default subnet route uses Internet Gateway. | Operator testimony, not a retained cloud configuration export or interval-bound mapping record. No shared NAT Gateway is reported on this path. |
| Sanitized sing-box configuration inspection and operator confirmation | Public proxy listeners, direct outbound configuration, personal-device use; no configured TUN auto-route. | Remote personal clients still generate host egress. Other processes can use other proxies or policy routes. Ownership does not establish zero traffic. |
| Operator-pasted active nftables rules | IPv4 OUTPUT accepts by default, with a link-local service chain. Docker bridges have MASQUERADE rules. IPv6 OUTPUT accepts by default. | Docker NAT confirms host-side translation, not the cloud public mapping or complete API accounting. |
| Same rules, FORWARD path | Tailscale is evaluated before DOCKER-USER. Docker forwarding accepts established traffic and bridge-originated traffic. DOCKER-USER has only an unrelated source block. IPv6 forwarding chain policy accepts. | A rule only in DOCKER-USER misses host OUTPUT and can miss an earlier Tailscale accept. Current disabled IPv6 forwarding does not cover host IPv6 or future changes. |
| Same rules, Orca guard | Existing project-independent guard restricts an inbound local UI port. | It supplies no egress control or audit. |
| Operator-pasted Docker inventory | Multiple applications, proxies, storage/download services and databases use named bridge networks. | Container names do not establish contacted domains or consumption of the testnet quota. |
| Prior bounded proxy-log inspection | The sampled final 1 MiB had no selected testnet endpoint or `binance.com` match; two other `binance` text matches existed. | No complete timeframe or traffic coverage was established. Neither API usage nor its absence follows from these matches. |

The pasted rules and inventory are operator-supplied transcripts, not independently
captured, hash-pinned original evidence. Raw addresses, listener configuration,
full inventories, proxy credentials and unrelated traffic are deliberately not
copied into the repository. Existing packet/byte counters are aggregates; they
contain neither complete failed attempts nor logical request weights and times.

## Proposed host boundary

Use a project-owned `inet` table with independent OUTPUT and FORWARD base chains
to cover IPv4 and IPv6. Host clients and a host proxy's outbound sockets traverse
OUTPUT; ordinary bridge-container and routed traffic traverse FORWARD. Define
priorities deliberately and verify them in disposable network namespaces before
deployment. An accept in an earlier base chain does not prevent a later base
chain from dropping the packet. This permits a separate guard without editing
Docker/Tailscale-managed chains. Inspect offload/flowtable and namespace paths
before claiming completeness; the supplied snapshot alone is insufficient.

Preserve existing input policies, Docker, Tailscale, fail2ban and cloud link-local
services. Never flush or restore the entire ruleset as an implementation shortcut.
Existing connections must be covered too: a blanket established-connection bypass
cannot establish exclusive access. A proposed rollback removes only newly owned
resources and stops the collector; it cannot leave collection running unguarded.

Two deployment choices remain proposals:

| Choice | Concrete implementation | Tradeoff |
|---|---|---|
| Reuse the current public IPv4 | Identify and enforce the entire applicable provider quota scope across host processes, containers, proxy clients and forwarded traffic. Put permitted calls behind one serialized accounting boundary; block or bound every other caller in that scope. | Avoids another public address, but changes may restrict ordinary personal proxy usage. A list of three destination hostnames/IPs is insufficient to prove provider-wide exclusivity. |
| Give collection its own public IPv4 on this VPS | If Oracle capacity and mapping support it, map a secondary private IPv4 to a separate public IPv4. Bind an isolated collector namespace to that source using explicit routing/SNAT; prevent other callers from using that source. Retain mapping and guard evidence for the capture interval. | Provides a clearer boundary while other services keep their existing source. Cloud availability, cost, privileges and routing behavior must be checked before provisioning. A new address has no automatically qualified usage history. |

Prefer evaluating the separate-address design when preserving personal proxy
access is required. A namespace alone does not provide a separate public IP.
If the collector uses IPv4 only, disable IPv6 inside that namespace and reject
fallback; do not globally disable host IPv6. Other callers and any potentially
shared quota dimensions still require explicit scope analysis. Root/cloud
administrators remain trusted controllers: changes to their mapping/rules must
invalidate the asserted coverage rather than silently retain qualification.

The draft selects `testnet.binance.vision`,
`ws-api.testnet.binance.vision/ws-api/v3`, and
`stream.testnet.binance.vision/stream`. DNS rotation, alternate provider endpoints,
shared CDN addresses, IPv6, proxy routes and socket reuse make a destination-IP
allowlist an incomplete API quota boundary. TLS destination verification does not
reveal the post-cloud-NAT source address. A generic public-IP lookup likewise
does not establish destination-specific routing for the collector.

## Implementation sequence and acceptance entrypoints

1. Retain a sanitized cloud mapping/route record and host network snapshot with
   timestamps, original-byte hashes and declared provenance. Select the egress
   design and exact identities/interfaces; current confirmation resolves topology
   but does not substitute for interval-bound evidence.
2. Build the guard generator and verification harness under an existing
   project-owned infrastructure boundary, or add a README if creating a directory.
   First use disposable namespaces and local fixture peers. Test host OUTPUT,
   bridge FORWARD, an earlier Tailscale-style accept, IPv6/fallback, reused sockets,
   source spoofing, rule removal and rollback. No real testnet destination is
   needed. A syntax check alone is not enforcement acceptance.
3. Define the gateway ledger adapter beside the existing project-owned joint
   admission/reservation modules. Bind caller identity, operation, destination,
   address family, mapped public source, clocks, policy version and durable
   preparation to transport outcomes. Conservatively retain failed/uncertain
   dispatches without refunds. Keep endpoint connection ledgers and their required
   conservative union distinct; detect record loss, restarts and guard changes.
   Packet/SYN counts corroborate network behavior but cannot substitute for
   REQUEST_WEIGHT, RAW_REQUESTS or logical connection attempts.
4. Connect fresh authenticated observations to actual dispatch through an enforced
   lease and continuously maintained ledger. A signed old snapshot reissued with
   a new timestamp does not cover the observation-to-dispatch gap. Reserve the
   remaining capture and bounded other callers atomically before each send.
5. Only after local enforcement/accounting acceptance and the first-request policy
   are resolved, prepare a separately reviewable deployment with bounded scope,
   rollback and evidence collection. Neither running-system deployment nor actual
   joint collection is performed here.

## First-request blocker is unchanged

The frozen [capture draft](portfolio-testnet-joint-capture-contract-2026-09-14.md)
requires fresh pre-existing authenticated usage, current applicable limits and
bound egress evidence **before the first time GET**. Those records are absent.
Installing a firewall, owning the address, waiting five minutes or signing local
claims cannot manufacture the required historical source evidence. The market
WebSocket connection's unspecified request-weight charge remains unresolved.

The next policy step must therefore obtain qualifying pre-existing evidence or
define a separate prospective bootstrap contract with its own limits, evidence
semantics and scope. This assessment does not revise the frozen draft or authorize
a seed probe. Its SHA256 remains
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
The 17-GET / 468-documented-weight plan, consumed ADR-017 and public-depth scopes,
full-account/UTC/flow/reset blockers and strict continuity **0/14** remain intact.

## Verification and boundaries

This change is documentation only: local link resolution, diff checks and the
frozen JSON hash are verified. No namespace/firewall acceptance was run; those
tests are future implementation work. The prior **3,242 passed / 12 deselected**
offline regression belongs to the reservation implementation and was not rerun.
No upstream source, order path, live trading behavior, credentials, schedule or
runtime configuration changed. The reading index and project status are updated.

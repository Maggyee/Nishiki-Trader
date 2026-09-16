# Current IPv4 reuse and shared-egress bootstrap revision

The operator revised the topology selection on September 16: **reuse the current
public IPv4; do not obtain a second address**. This supersedes the dedicated-source
selection in the [earlier proposal](portfolio-dedicated-egress-bootstrap-2026-09-16.md).
Its original bytes remain historical. The current machine-readable proposal is
[shared-egress bootstrap](portfolio-shared-egress-bootstrap-2026-09-16.json).

## Implementation change

- Remove secondary-private/public-IP provisioning from the critical path. Reuse
  the existing VNIC and primary source. Existing operator confirmation of Oracle
  VNIC/Internet Gateway topology remains valid context; there is no need to ask
  for a second address or repeat that confirmation.
- The collector may use an isolated namespace and dedicated unprivileged caller,
  but that namespace still shares the public source with host processes, Docker,
  Tailscale-forwarded traffic and the personal proxy. It does not get a separate
  quota just because its process or namespace is separate.
- Preserve ordinary proxy availability as the implementation target. During a
  bounded collection window, every other caller in the applicable provider quota
  scope must either use the serialized accounting boundary or be blocked. Other
  proxy traffic should remain usable. Exact provider coverage and proxy bypass
  behavior must be tested before asserting this selective policy is sufficient.
- Three destination hostnames or their current IPs are not a complete provider
  scope: alternate endpoints, DNS changes, reused sockets, IPv6 and forwarded or
  proxied routes need coverage. If selective coverage cannot be established,
  report that concrete limitation and propose a bounded maintenance window. Do not
  silently stop the proxy, Docker, Tailscale or all host egress to obtain exclusivity.
- Retain independent OUTPUT/FORWARD checks and continuous records for the selected
  source. Kernel packet counts do not supply logical request weights. Failed or
  uncertain API attempts count, and uncontrolled changes invalidate coverage.

## Next work and inputs

1. Reuse the implemented local host snapshot and existing topology evidence to
   specify shared-source caller paths and the exact selective interception policy.
   Retain an actual current VNIC/public mapping record before deployment; do not
   confuse a local private address with the externally mapped source. No new cloud
   resource or SDK is required for this design.
2. Stage host/proxy/container paths against local peers with the selected shared
   source. Verify that covered competing callers are denied or accounted, existing
   sockets cannot bypass, and unrelated proxy traffic still works. Bind transport
   dispatch to durable controller preparation and fixed storage.
3. Prepare the concrete rules, rollout and rollback for review before deployment.
   Host inspection is read-only; no host guard or service has been installed.
4. Implement and review the separate one-GET bootstrap after that source/caller
   boundary is qualified. Preserve its exclusive activation before any socket and
   no-retry behavior. Its unknown-prior-usage exception remains a Draft; changing
   source selection does not itself activate a request.

The revised bootstrap still proposes exactly one public
`GET https://testnet.binance.vision/api/v3/exchangeInfo`: documented weight 20,
no credentials, WebSockets, retry or fallback, and the same time/archive bounds.
Prior usage and restrictions of the **existing shared source** remain unknown.
A prospective exclusion window constrains future callers; it cannot create missing
historical records or prove initial headroom. The explicit first-request exception
would accept this uncertainty only within its separately activated scope.

A successful response remains a post-request observation, not pre-request capacity
proof or authority for the frozen joint collector. Current limits, complete
intervals, clock uncertainty, market-WS charge and a later fresh joint observation
remain separate issues. Waiting alone and a process-local lock are insufficient.

## Verification and boundaries

The host inspector's missing-source blocker is now topology-neutral:
`selected_source_and_authorized_caller_binding_missing`. Its commands, private
output behavior and always-false admission semantics are unchanged. The 24 existing
inspector tests pass; Ruff, format, documentation links, proposal consistency and
diff checks pass. No new host snapshot or full application regression is needed
for this source-selection/documentation change.

The old dedicated proposal is byte-identical. The frozen 17-GET / 468-weight joint
contract remains SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
No external probe, credential access, host policy change, upstream edit or live
trading change occurred. Consumed scopes and strict continuity **0/14** remain.
The status dashboard, reading index and infrastructure README now direct the next
implementation to shared-source caller coverage instead of new-IP provisioning.

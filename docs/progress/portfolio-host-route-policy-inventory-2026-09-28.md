# Read-only host route and policy inventory

Observed: 2026-09-28. The namespace inventory now emits v2 and retains every
bounded IPv4/IPv6 route and policy rule in each visible network namespace,
alongside the original default-route and Docker PID reconciliation. Only fixed
`nsenter ... ip -j route show table all` and `ip -j rule show` reads were added;
the command whitelist rejects mutation. Each representative PID's namespace,
the namespace list and Docker list are reread around the census. Full raw
routes, marks, PIDs and container IDs are private and excluded from git.

The ignored 0600 report `data/host-namespace-inventory-2026-09-28-r2.json`
has SHA256 `f99d3935b2296fe1d4bd6353a18bdef10eddb7da1a790f50a00ccfa2d4e4b3cf`.
It records 20 namespaces, 16 running Docker containers mapped to routed
namespaces, 17 IPv4 and one IPv6 default-route namespaces, 64 IPv4 and 44 IPv6
policy-rule rows, and no read failure or observed census drift. One namespace,
the host, has marked policy rules in both families. Its three marked rules per
family use Tailscale's `0x80000/0xff0000` match. No currently observed Docker
namespace has an `fwmark` policy rule; this does not prove mark ownership in
iptables/nft, a process's socket options or future containers. The full route
tables include non-default entries that the v1 report discarded.

The separate ignored 0600 host inspection
`data/egress-host-inspection-2026-09-28-r1.json`, SHA256
`c4440a24f0d788f679fe40f0ac583cc49f7c8b33dca3d3cc8fc56cfb0a7bfe1e`,
read seven local sources successfully. It reports two IPv4 and one IPv6
default-route entries, 27 nft base chains and no flowtable. Existing Docker and
Tailscale nft tables coexist with `inet orca_guard`; the joint nft table is
absent. Its JSON rules include opaque `xt` expressions, so this snapshot alone
cannot prove exact mark restore, NAT and proxy behavior. The proposed storage
root does not satisfy the inspector's ownership/mode check; no storage was
created or changed.

These two reads were separate point-in-time snapshots, not one protected
transaction. Namespace route tables and policy rules may change immediately;
neither tool enumerates socket-bound sources, host/proxy application routing,
the cloud public-to-private association, or provider-visible source. To qualify
a future host controller, bind a selected destination/address family and source
to actual host OUTPUT, container FORWARD and WAN paths, including Tailscale
mark restoration and Docker NAT. Inventory existing and future callers and
proxy forwarding under a protected continuous lifecycle; refuse drift and
unreadable paths. Then separately prove installation/startup custody and an
uninterrupted exclusion history before contemplating a gated network scope.
No blackout, permit, collector, venue request or trading operation occurred.

Verification: five focused inventory tests pass, including non-default route
and mark preservation, failed route/policy reads returning unknown counts, and the
read-only command whitelist. The v2 host run exited 2 with all admission
fields false. The original v1 report remains a historical snapshot.

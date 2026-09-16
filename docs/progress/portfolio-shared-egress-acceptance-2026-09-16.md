# Shared IPv4, local proxy and controller acceptance

The isolated Linux harness now exercises actual SNAT and TCP proxy forwarding for
the operator-selected existing-public-IPv4 design. **49 new kernel checks pass,
105 total**, together with **104 focused Python tests** (80 controller/harness and
24 host-inspector cases). No host guard, cloud configuration, real proxy or venue
connection was changed.

## What the network exercise establishes

All peers live inside the existing disposable user/network/mount/PID isolation.
There are no external or default routes. In addition to the original collector
bridge and dual-stack peer, the harness creates a competing routed namespace and
a real TCP proxy process in the isolated router's namespace. The proxy has all
capabilities dropped and no-new-privs. Its outbound sockets traverse OUTPUT;
collector and competing namespace traffic traverse FORWARD before IPv4 SNAT.

The peer reports the source it actually sees. Direct host, collector and competing
caller traffic, plus host-originated and forwarded-client proxy traffic, all report
the same fixture source `198.51.100.1`. This validates local NAT behavior, not
Oracle's public mapping. The proxy is a small bounded local tunnel fixture, not
sing-box, SOCKS, TLS interception or a production proxy implementation.

The separate guard table has later base-chain priorities than the earlier
unconditional accepts. It blocks the selected IPv4/IPv6 destination for other
callers, across TCP/UDP, without an established-connection exemption. A dedicated
collector bridge is limited to its exact IPv4 source, permitted destination and
TCP port. Its other destinations, IPv6 and access to the router's proxy listener
are refused. A competing ingress cannot use the collector's allowed source tuple.
The fixture has no untrusted caller on the collector bridge; deployment must bind
that interface/namespace ownership rather than assuming a source IP authenticates
a process.

Actual traffic checks cover:

- Selected destinations are denied for new and pre-existing direct/proxied sockets;
  each refusal must increase the intended kernel counter.
- Other fixture destinations remain reachable via direct and proxy TCP on IPv4
  and IPv6. Direct host and forwarded UDP controls also succeed.
- Granting the collector's expiring permission does not admit host proxy or other
  forwarded callers. The existing persistent controller records and fsyncs its
  preparation before the actual collector send, whose observed SNAT source matches
  the other clients. The fixture uses one prepared persistent TCP connection.
- Terminal revocation blocks both that already-open collector socket and a new
  connection. The retained journal replays one preparation and terminal revocation.
  Existing crash/reopen acceptance remains in the same harness and Python suite.
- After terminal revocation and closing collector sockets, removing only the owned
  guard/NAT tables restores selected target and cohosted-service connectivity and
  preserves the earlier independent policy. No production rollback is performed.

The proxy validates literal fixture addresses and two fixture ports before creating
any upstream socket. It cannot resolve hostnames or dial arbitrary destinations.
Bounded line parsing, malformed/foreign target refusal and capability dropping are
covered by the 15 added Python cases. Source embedding now carries the original
script once to child interpreters, avoiding duplication toward the Linux per-argument
size limit; the worker still checks namespace isolation before every setup sequence.

UDP echo sockets bind each fixture address explicitly. This preserves the reply
source when a connected client targets a secondary address; a wildcard listener's
primary-address reply would not be valid control evidence. The final kernel run
passes the UDP controls with the correct tuple.

## Proven limits of a selective destination list

Two deliberate counterexamples also pass and remain explicit in the result:

1. A reachable alternate fixture endpoint absent from the destination list remains
   usable by both direct and proxied callers, with the same SNAT source. Blocking
   listed IPs therefore cannot establish an exhaustive provider quota boundary.
2. An unrelated service on a different port of the protected IP is reachable before
   enforcement, blocked by the address rule, and reachable again after rollback.
   Address filtering cannot promise preservation of every cohosted service.

These checks demonstrate possible failure modes, not a finding that Binance has
these exact endpoint or cohosting arrangements. The JSON explicitly reports
`fixture_shared_snat_verified=true`, while `provider_destination_coverage_qualified`,
`colocated_service_preservation_qualified`, `gateway_coverage_qualified` and
`capture_admitted` remain false. Positive selected-target checks must not overwrite
these negative coverage results.

Packet counters still do not count API operations or prove interval completeness.
The fixture does not reproduce sing-box protocol handling, actual Docker/Tailscale
rule sets, tunnels, DNS rotation, offload, cloud NAT, power loss or arbitrary
privileged mutation. Other processes in an authorized collector namespace are not
made trustworthy by a firewall rule. Persistent storage here is the private fixture
tmpfs; earlier disk process-crash acceptance does not become power-loss evidence.

## Next implementation decision

Continue with the existing IPv4; no second address is requested. Before deployment,
either establish a justified provider-wide endpoint/caller policy and test its
effect on the actual proxy paths, or prepare an explicitly bounded maintenance
window with broader egress restrictions, a watchdog and rollback. Preserve the
operator's proxy-availability target; this evidence does not authorize silently
stopping services or applying broad host rules. A selective rule generator based
only on three current hostname resolutions would not resolve the demonstrated gap.

Bind actual source/caller/storage identities and enforce durable dispatch in that
selected deployment. The separate [shared-source REST bootstrap proposal](portfolio-shared-egress-bootstrap-2026-09-16.md)
remains unimplemented and unactivated. Future traffic exclusion cannot reconstruct
past usage; the proposed one-GET exception still requires its own explicit review.
The fixed 17-GET / 468-weight joint draft, consumed ADR-017/public-depth scopes,
account/UTC/flow/reset qualification and strict continuity **0/14** are unchanged.

## Verification

```bash
/usr/bin/python3 -I infra/egress-guard/selftest.py
uv run pytest -q tests/ops/test_egress_guard_selftest.py tests/ops/test_egress_host_inspection.py
uv run ruff check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
uv run ruff format --check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
```

Final kernel-tested script SHA256:
`47f240408848c5d69119f2de97a45320f788498d76603526e15293e0efc717e5`.
The original 56 kernel checks and 65 controller tests remain passing. The final
Python total is 104 including the separate 24 inspector tests. Ruff/format,
documentation links, frozen proposal/contract hashes and diff checks pass. Full
application regression was not rerun for this standalone infrastructure fixture.

Changed files: `infra/egress-guard/selftest.py`, its README,
`tests/ops/test_egress_guard_selftest.py`, this report, `docs/agent-reading-list.md`
and `docs/project-status.md`. No upstream source or live order path was touched.

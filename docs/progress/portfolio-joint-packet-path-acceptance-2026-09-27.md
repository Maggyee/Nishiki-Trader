# Isolated joint collector packet-path acceptance

Date: 2026-09-27. The disposable user/mount/PID/network namespace test in
`tests/ops/test_egress_window_packets.py` passed against real local nft and
veth traffic. It checks the exact selected inet and netdev rules with both
30-second IPv4/IPv6 blackouts and initially empty permits. After installing
two local 25-second permits for `198.51.100.2`, a capability-dropped collector
connected to the local TCP/443 peer across its veth, the FORWARD mark, SNAT
and the netdev WAN egress hook. The peer reported the expected post-NAT source
`198.51.100.1`; separate counters increased for the selected mark at FORWARD
and WAN egress.

Drop counters increased for all eight refusal cases: an empty permit set,
host OUTPUT, an unrelated forwarded caller, wrong collector source, wrong
TCP port, UDP, collector INPUT to the router, and a privileged host socket
carrying the selected mark. Both blackout and permit timers were still active
after the refusal checks. A separate unit test confirmed that direct invocation
with the caller's own namespace identities stops before any network mutation.
The local addresses are documentation subnets; no external peer, venue request
or host firewall modification was involved. The peer retained namespace-local
bind privilege for TCP/443, while both client processes dropped capabilities.
The test's namespace process group is terminated on its 50-second timeout.

Verification: the two tests in the packet-path module passed in 5.51 seconds;
the five related window modules passed **60 tests** in 6.26 seconds. Ruff,
formatting and diff checks passed. The prior sandbox blocked Netlink, so this
acceptance comes from the subsequent unrestricted run, not the earlier staged
test. The fixture's two permits do not grant real network admission.

This proves only the selected local packet path under these disposable rules.
The joint controller, selection and witness are not installed on the host.
Neither provider-visible source authentication, mark ownership against other
privileged writers, all host/container/proxy caller coverage, nor uninterrupted
host exclusion across the required history and horizon has been established.
Fresh provider intervals and usage, unknown market charge, full-account
coverage and per-dispatch budget reservations remain prerequisites to any
separately gated real collection. All admission and trading permissions remain
false.

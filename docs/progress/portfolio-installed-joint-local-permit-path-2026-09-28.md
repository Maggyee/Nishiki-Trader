# Installed-source joint fixture with a local permitted packet

Date: 2026-09-28. The disposable root installation fixture now extends the
[empty-permit collector denial](portfolio-installed-joint-collector-denial-2026-09-28.md)
within the same private mount/network/PID namespaces. The protected base
verifier selects the six installed joint source bytes, and the selected
activation controller consumes its fsynced intent, writes one 10-second
dual-stack nft blackout and records one held observation with empty permits.
The capability-free installed-account caller first fails at the selected
collector FORWARD drop counter. Repeated activation is refused and the
witness closes before the packet grant test begins.

The fixture then adds a five-second permit for only its local `198.51.100.2`
peer, outside the installed controller. A local SNAT rule maps the selected
`192.0.2.2` collector to `198.51.100.1`; separate counters observe the selected
mark after FORWARD and on WAN egress. A peer bound inside another private
network namespace receives one TCP/443 request, reports the post-SNAT source
`198.51.100.1` and responds. The installed kernel observer refuses an
observation while either permit set is populated. Both permits are flushed
atomically and checked empty before fixture teardown. These addresses are
documentation subnets, with no external route or venue request.

The ignored, private, write-once report
`data/joint-window-isolated-2026-09-28-r7.json` has SHA256
`97b3afd3868c62db80efd4fb6bd1d36b50bedb703b21a4ce449be28741ea0e05`.
It records 40 base and 20 joint checks, the empty-permit refusal, local
post-NAT source and marked hooks, unchanged host observations, zero venue
requests and all admission fields false. The related window suite passed
106 tests; lint, format and diff checks passed. Subsequent read-only host
checks found neither inet nor netdev `trader_joint_window_v1` table; the
installed fixed entry still exits 2 as unqualified.

This establishes one permitted packet only in the selected local fixture.
The fixture's permit writer and NAT/trace rules are not installed authority;
the protected observer explicitly rejects active permits. It does not prove
host startup, crash/restart custody, effective mark/source ownership against
Docker/Tailscale and privileged writers, complete dual-stack host/container/
proxy callers or uninterrupted 425-second exclusion. Provider-visible source
and fresh provider bounds are still absent. No host firewall, collector
service, credentials, venue request or live trading path changed; admission
remains blocked.

# Read-only host marked route and local source review

Observed: 2026-09-28. The existing host inspector now pins the joint collector
mark `0x6f720002` and obtains IPv4/IPv6 `ip -j route get` results for fixed
documentation destinations, plus both families' `iptables-save` mangle/NAT
views. The read-only command allowlist rejects arbitrary destinations and
mutations; all raw routes, source addresses and rules stay in the ignored
0600 report. The selected mark is checked against the joint kernel constant
in tests. The inspector joins the route's preferred source to the actual
address list on the returned interface and compares marked policy rules using
their masks. Malformed, failed or missing reads remain unknown rather than
being counted as zero. The console omits interface names and addresses.

The write-once private report `data/egress-host-inspection-2026-09-28-r2.json`
has SHA256 `74c5ecf4f0046283280bb000bc7c342afade410eda5a1d704310117e3ba7d83c`.
All 13 reads succeeded. Both documentation destinations currently route via
the host WAN with a preferred source assigned on that interface; zero host
policy-rule matches use the collector mark in either family. The IPv4 route
JSON echoes the selected numeric mark; the IPv6 route JSON omits that field,
so the latter is only an observed result of the marked query. Two CONNMARK
rules per family save/restore masked connection bits, while 12 IPv4 and one
IPv6 POSTROUTING rules coexist in the compatibility view. The host still has
no joint nft table. All network-admission and provider-source fields remain
false; the inspector exits 2. Focused tests, lint, formatting and diff checks
passed.

`ip route get` is a hypothetical local route lookup for documentation addresses.
It runs with the inspector's UID, not the installed collector's UID, and does
not execute collector FORWARD, SNAT or WAN hooks, prove a venue-bound
route, constrain privileged mark writers or future Docker/Tailscale changes,
observe provider-visible public IP, or establish uninterrupted exclusion.
The saved compatibility tables are point-in-time evidence and can contain
rules not parsed as an ownership proof; nft JSON still has opaque xt entries.
The next implementation boundary is a protected host activation/startup and
crash lifecycle with complete dual-stack host/container/proxy source and
mark custody. No rules, collector, venue request, credentials or trading
path changed.

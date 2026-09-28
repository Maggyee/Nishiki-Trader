# Isolated joint window proxy and policy packet paths

Date: 2026-09-28. The disposable user/mount/PID/network namespace packet test
now includes the host-observed IPv4/IPv6 CONNMARK masks, the Tailscale
`0x80000/0xff0000` policy rule priorities and table 52, Tailscale's
`0x40000/0xff0000` NAT match, and a Docker-like forwarded MASQUERADE rule.
The proxy is a small unprivileged fixture process, not the running host proxy.
The fixture peer and collector use documentation subnets; representative
Tailscale CIDRs attach only to a disposable dummy interface. No actual host
firewall, route, proxy, venue or trading state was changed.

The fixed collector mark remains `0x6f720002`: its `0x720000` masked bits do
not equal either Tailscale match value. Under the simulated policy rules an
`ip -j route get` with that mark still selects the fixture WAN. The existing
selected collector packet crosses the FORWARD mark, local SNAT and WAN hook;
the local peer observes `198.51.100.1`. Thirteen denial checks now include
the previous nine cases plus host and forwarded proxy requests and traffic
over direct and proxy sockets established before the blackout. Each refusal
has a corresponding increased kernel drop counter; the IPv6 host OUTPUT case
still returns `EPERM`. The peer accepts multiple messages per connection to
exercise reuse of the preexisting sockets instead of reconnecting.

This tests coexisting rule shapes and representative proxy/connection paths,
not the full running Docker/Tailscale/sing-box rule order. Tailscale table 52
and the Docker NAT rule are simplified local fixtures; a successful marked
route lookup is not a proof of unique mark writer, effective source after
cloud NAT, provider-visible public IP or continuous coverage. The host still
lacks the joint nft table and protected activation controller. A future host
gate must pin and protect all relevant rule order, routing and source custody
across restarts and future containers/proxies, then establish an uninterrupted
425-second exclusion and fresh provider bounds before any separate network
decision. No permission, collector or trade follows this fixture.

Verification: both packet-path tests pass in a fresh disposable namespace;
the real packet scenario returns 13 denials, marked WAN routing and false
admission. This result is local acceptance only.

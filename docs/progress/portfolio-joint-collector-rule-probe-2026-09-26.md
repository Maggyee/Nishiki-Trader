# Isolated joint collector rule probe

Date: 2026-09-26. The read-only joint kernel observer now accepts an optional
root-held collector selection: host-side veth name, child IPv4 and expected
post-NAT WAN source IPv4. With this selection it checks exact inet OUTPUT,
INPUT and FORWARD rules plus netdev WAN egress. OUTPUT drops the dedicated
mark before its loopback exception. FORWARD accepts only the selected veth to
WAN, selected child IPv4 to an empty `@permits` set on TCP/443, then sets the
mark; the return rule requires an established connection from a permitted
source to the child. All other traffic on that veth is dropped. WAN egress
requires the mark, selected source, permitted destination and TCP/443; other
marked packets are dropped before the general blackout drop. This checks
static rule shape, not route ownership or the origin of every marked packet.

The held-selection adapter checks the collector fields against the pinned
observer source before any observation and passes them through. A disposable
`unshare -Urn` nft test installed these rules with five-second IPv4/IPv6
blackouts and empty permit sets, observed real nft JSON, and rejected five
self-pinned bypass/condition mutations. Staged tests cover invalid selections
and selected-field forwarding. No permit was populated, destination contacted,
host rule modified, activation journal installed or real collector launched.

These checks do not establish full host/Docker/proxy egress coverage, NAT and
provider-visible source identity, protection against other privileged mark
writers, rule priority across independent tables, or uninterrupted exclusion
since activation. In particular an nft snapshot cannot prove the required
300-second history and 125-second future horizon. Root installation, one-shot
activation custody, fresh authenticated provider intervals and usage, unknown
market charge, and per-dispatch budget reservations remain prerequisites to a
separately gated collection. Every source, coverage and admission flag remains
false; the live trading path and consumed scopes are unchanged.

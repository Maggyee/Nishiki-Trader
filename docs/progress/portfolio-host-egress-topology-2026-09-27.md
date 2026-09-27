# Read-only host egress topology snapshot

Observed: 2026-09-27 04:12 UTC. `ip -j link/route/rule`, `lsns -t net -J`,
`docker ps -q`, `nft -j list ruleset`, and the iptables/ip6tables-save
compatibility views were read without changing host state. A fresh
`/usr/local/lib/trader-egress/helper_entry.py --check` returned
`installation_verified_inactive`, exit 2. The joint entry and manifest are
absent, as are the selected `inet` and `netdev` joint nft tables.

The host has IPv4 and IPv6 default routes on `enp0s6` and a separate
`tailscale0` interface. Twenty network namespaces were visible: the host,
16 others with IPv4 defaults on `eth0` through six currently present Docker
bridges, and three without defaults at this instant. Docker reported 16
running containers. Only the host namespace showed an IPv6 default route
in this sample. Namespace/process membership and routes can change; these
counts do not enumerate every future caller or prove proxies cannot egress.

The current nft inventory contains `ip`/`ip6` tables with Docker and
Tailscale chains plus an unrelated `inet orca_guard` input chain, but no
joint OUTPUT, FORWARD or WAN blackout. Several rules appear as opaque `xt` expressions
in nft JSON. The compatibility view shows mangle OUTPUT saving nonzero
mark bits under mask `0xff0000` for NEW connections, and PREROUTING restoring
that mask for established traffic. The proposed collector mark
`0x6f720002` has masked bits `0x720000`; Tailscale routing uses a separate
`0x80000/0xff0000` selection and its postrouting NAT uses
`0x40000/0xff0000`. Docker uses multiple MASQUERADE rules. Distinct
Tailscale match values do not prove mark ownership or rule-order safety;
the existing connmark rules must be included in the fixed packet-path
review. Neither private WAN address nor NAT configuration attests the
provider-visible public source.

This snapshot changes the next acceptance target: bind the selected WAN and
both IP-family host OUTPUT/FORWARD paths while accounting for Docker bridge
forwarding and Tailscale routing/mark restoration; then demonstrate exclusive
collector mark/source custody and complete host/container/proxy caller
coverage over the full prospective exclusion interval. The earlier isolated
veth acceptance tests one path, not this live topology. No 425-second
continuous blackout, permit, venue request or trading operation occurred.

Same-day disposable follow-up added the observed IPv4/IPv6 CONNMARK
save/restore rule shape to the veth fixture. The selected IPv4 packet still
traversed FORWARD mark, SNAT and WAN egress; nine denials passed, including
an IPv6 host UDP send refused with `EPERM` and an increased selected OUTPUT
blackout drop counter. Both packet-path tests pass. This establishes local
coexistence under the copied mangle rule shape, not exact host rule order,
all-caller coverage, mark ownership or provider-visible source authority.

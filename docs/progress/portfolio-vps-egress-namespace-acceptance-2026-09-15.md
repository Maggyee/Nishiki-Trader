# VPS egress namespace acceptance — 2026-09-15

The first real Linux hook acceptance now passes **23 checks** in disposable
namespaces on this VPS. IPv4/IPv6 host OUTPUT and bridge FORWARD are blocked by
the later independent guard even after an earlier unconditional accept, including
TCP sockets established before the guard was installed. This validates the hook
mechanism proposed in the [VPS assessment](portfolio-vps-egress-assessment-2026-09-15.md).
It does not deploy a host guard or qualify provider-wide traffic coverage.

## Implementation and acceptance

The standalone [fixture](../../infra/egress-guard/selftest.py) uses system Python
3.10 and existing `unshare`, `nsenter`, `ip` and `nft` binaries. It runs as the
ordinary `orca` user. This VPS supports unprivileged user namespaces, so host sudo
is unnecessary for the test. A new user/network/mount/PID namespace encloses a
router, bridge client and echo peer; only fixture routes and interfaces exist.
Namespace identity and empty topology/rules checks precede mutations. Absolute
commands, isolated child Python and a fixed environment avoid loading project
or user configuration into the child interpreters.

| Actual Linux checks | Count | Result |
|---|---:|---|
| Establish host and bridge TCP connections over IPv4 and IPv6 | 4 | All echo exchanges succeed before installing the guard. |
| Reject fresh and already-connected traffic after earlier accepts | 8 | Each failure increments the intended guard counter. |
| Preserve connectivity to an unblocked fixture destination | 4 | Both paths and address families still exchange data. |
| Reject an unauthorized fixture source on the bridge | 2 | Both source checks increment their intended counters. |
| Delete only the owned guard table and restore connectivity | 4 | Both paths and address families work again. |
| Preserve the earlier independent rules through rollback | 1 | Rule structure matches, excluding changing packet/byte counts. |

The successful script SHA256 is
`e1e126310cf2727650b475e45cf156bc05c97ea3b59621da88eb05d5ea1750f7`.
The JSON stdout report marks `capture_admitted` and `gateway_coverage_qualified`
false and records zero external requests. Its packet counts are observations of
fixture traffic, not API weights or exact logical attempt counts.

**13 focused Python tests** also pass. They cover inherited namespace refusal,
unexpected interfaces/routes/rules, no mutations after isolation refusal, rejecting
host-root execution and CLI arguments, and bounded child/process-group cleanup.
The worker has a 90-second alarm and the parent a 100-second timeout. Child control
pipes close at exit, with bounded kill fallback; the enclosing PID namespace
releases remaining child processes and network resources. No named namespace,
host network interface, service, package or runtime configuration is installed.

## Independently read host snapshot

The operator granted sudo access. The actual grant is unrestricted passwordless
sudo; this task uses it only for read-only nftables inspection. The
[README](../../infra/egress-guard/README.md) also documents an optional exact-command
read-only grant. This work does not install or change sudoers.

At **2026-09-15 09:15:01 UTC**, `sudo -n /usr/sbin/nft -j list ruleset` retained
59,116 original bytes in the ignored local file
`data/vps-egress-nft-2026-09-15.json` with mode 0600 and SHA256
`33536840ac3ac595530663bfc000a2fe221255affdaca14e9aaf3a5b059fc337`.
This is a direct local read, beyond the previous operator-pasted transcript.
It confirms the previously described OUTPUT/FORWARD structure and contains no
nftables flowtable declaration. A subsequent host read matches the original rule
structure after excluding changing counters and nft metadata. Host IPv6 forwarding
remains disabled; the fixture enabled it only inside its disposable namespace.
Raw host rules are not committed.

The snapshot establishes current host configuration at the read, not historical
all-caller usage, failed API attempts, actual cloud source identity for each
destination, or future enforcement. No claim of complete flow coverage follows
from an absent nftables flowtable declaration.

## Remaining implementation boundary

The fixture models hook behavior and source checks. It does not implement actual
Docker NAT/Tailscale integration, UDP/QUIC/proxy traffic, provider endpoint scope,
DNS changes, cloud public-source binding or production caller authorization.
Its rollback intentionally restores fixture traffic. A deployed collector would
need a guard lease/loss detector and must stop before its guard is removed.

Next choose and model the real source/identity design, verify the actual cloud
mapping, and implement continuous guard/ledger coverage including failed and
uncertain attempts. Authenticated observations must remain bound through dispatch;
a new signature timestamp cannot refresh old evidence. The frozen first-request
contract still needs pre-existing usage evidence or a separately scoped prospective
bootstrap revision. Sudo and a successful kernel test do not solve that requirement.
Market-WS connection weight remains unspecified. No new testnet request, seed probe,
joint capture, BUY or live order is enabled; consumed scopes remain consumed.

Ruff lint/format, focused tests, documentation links, diff checks and the frozen
capture JSON hash are checked. The historical **3,242 passed / 12 deselected**
application regression was not rerun for this standalone infrastructure fixture.
No upstream code or live order path changed. Project status, reading index and
infrastructure documentation are updated; strict continuity remains **0/14**.

# Installed joint collector selection and empty-permit denial

Date: 2026-09-28. The disposable root installation fixture now extends the
[installed-source activation integration](portfolio-installed-joint-activation-integration-2026-09-28.md)
with a collector-selected packet path. After installing the reviewed base and
all six joint sources in private mount/network/PID namespaces, it creates two
further local network namespaces connected by collector and WAN veths. The
observer/custody/witness/activation bytes come from the installed manifest
through the fixed entry's protected base verifier. A root-owned 0600 plan
selects `gw-jc1`, fixture child `192.0.2.2`, WAN `wan` and fixture source
`198.51.100.1`. These selections and static rule digests are fixture
generated, not independent host deployment authority.

The exact collector-aware INPUT/FORWARD/OUTPUT/netdev rules start with empty
inet and netdev permit sets. One fsynced activation intent precedes a real
10-second dual-stack nft transaction in the disposable namespace; the held
observer records one active snapshot. The installed base account's UID/GID
then runs a capability-free, no-new-privileges TCP connect toward a local
documentation-subnet peer without a listener. The socket does not connect,
and the selected collector FORWARD drop counter rises; the counter, not the
socket error alone, identifies the rule that denied it. Both permit sets
remain empty, a second activation refuses before a writer can run, and the
journal remains unchanged. There was no grant, accepted packet or transport
to an external address.

The final private 0600 write-once report
`data/joint-window-isolated-2026-09-28-r6.json` has SHA256
`e3830e6e3b26ffe0a46c809e697233857e36c4687a77aac67ebff578ca856630`.
It records 40 base and 19 joint checks, the collector refusal, unchanged host
observations, zero venue requests and false source, caller-coverage,
activation-history and network-admission fields. A post-run host nft read
again found no `trader_joint_window_v1` table; the installed entry still
returns exit 2 and remains unqualified. The earlier `r5` report documents
the loopback-only integration, not this collector path.

This is selected denial in an isolated topology, not evidence that a permitted
collector packet would keep its mark and selected source through real Docker/
Tailscale rules, SNAT and cloud mapping. A test-only permitted local packet
path has passed separately, but it has not been joined to this installed-source
controller. Protected host startup, crash/restart custody, all future callers
and uninterrupted 425-second exclusion remain open. No host firewall, proxy,
collector service, venue request, credential or live trading operation changed.

Verification: the fresh-process installation integration test and the
independent CLI report pass; source and manifest drift checks still fail
closed after the packet probe. The private report is ignored by git.

# Private persistent-deny expiry experiment

Date: 2026-09-28. The existing installed-source joint-window rule shape uses
expiring blackout elements; its ordinary caller OUTPUT and FORWARD rules
accept traffic once those elements expire. A disposable successor experiment
installs a persistent default-deny `inet` OUTPUT/FORWARD and `netdev` WAN
egress table before it creates a three-second dual-stack blackout lease. The
fixture runs as an unprivileged user that creates private user, mount, network
and PID namespaces; it refuses inherited namespace identities, links or
preexisting nft rules before writing. No host nft transaction is part of this
experiment.

Two local veths link the private parent to separate caller and peer network
namespaces. Before installing the deny table, IPv4 and IPv6 local OUTPUT and
forwarded caller connections all reach the local peer. After baseline
installation, all four are denied. A forked owner atomically adds both IPv4
and IPv6 lease elements in `inet` and `netdev` and exits. Both sets remain
active with two elements after its exit; all four connection attempts still
fail. After both sets expire, the persistent table's static rule digests are
unchanged, all four attempts still fail, and OUTPUT and FORWARD fallback-drop
counters increase. The local peer and documentation addresses are only test
fixtures; no venue, account or external route is involved.

The write-once ignored report `data/joint-window-failclosed-2026-09-28-r1.json`
has SHA256 `6267d5032e919ad98f00e74658a56e276c7e9003af3b29728eca6041be24ae36`.
It records four reachable pre-baseline paths, four denials after owner exit,
four denials after expiry, unchanged permanent rules and false admission.
The report is a private-fixture observation, not independent attestation of
the host nft state.

The strengthened, write-once `data/joint-window-failclosed-2026-09-28-r2.json`
report has SHA256
`030ee3dede13d8d28107e6d66bf5b165d7f1e4f2aeb8d8cae610425a82f818f9`.
The private observer now checks the exact table, timeout set, chain hooks,
default-drop policies and ordered drop expressions in actual nft JSON; a
separate text read binds the netdev egress hook to `wan`, because nft 1.0.2
omits that device from JSON. After expiry, two AF_PACKET frames emitted
directly on the private WAN make the netdev fallback-drop counter increase,
covering a path that the earlier `inet` OUTPUT/FORWARD drops could not exercise.
Inserted `accept` rules in both hook families are independently rejected;
the fixture deletes each test mutation and checks its original static hashes
and empty sets before reporting. Synthetic policy and device drift are also
rejected. The 111 related Python tests pass, along with Ruff and diff checks.

The final strengthened report is the separate write-once
`data/joint-window-failclosed-2026-09-28-r4.json`, SHA256
`e032a32328a5b00d2d226e2ec22db83f80bc9605acf027360c320e5a2666297b`.
It records fixture source SHA256
`edbdfadf3f3176c2310ff8abfa0c40acc6a564309a438e371fd4a92efe50eb8c`
for traceability, not independent startup selection. The observer now rejects
unexpected or duplicate IPv4/IPv6 or EtherType lease elements even when the
count is unchanged. The kernel may still list an element with `expires=0`;
the expiry check waits for both sets to be empty before requiring OUTPUT and
FORWARD fallback counters. Intermediate `r3` produced identical output to
`r2` but predates this source-hash field and is not the final report. Related
tests now pass 113/113.

This new table is not selected by the protected installed six-source manifest
or the existing `gateway_window_kernel.py` rule inspector; it has no grant,
restart, deployment or `guard.verify()` interface. It establishes a kernel
fail-closed fallback shape for a future version, not continuous 425-second
coverage: another privileged writer, namespace changes, device changes, new
containers, proxy forwarding, actual source/mark ownership and reboot remain
outside this experiment. A new independently pinned installation and policy
review would be needed before a host controller could use this rule shape.
No existing protected installation was replaced; collection and trading stay
blocked.

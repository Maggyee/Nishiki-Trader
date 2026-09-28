# Installed-source post-write crash boundary in a private namespace

Date: 2026-09-28. The disposable installed-source fixture now exercises an
owner crash at the uncertain point between a successful nft transaction and
its first held observation. After the prior
[local packet-path check](portfolio-installed-joint-local-permit-path-2026-09-28.md)
closes its witness and the first ten-second blackout expires, a separate root
process selects the installed joint sources through the protected base
verifier, constructs a fresh held selection and consumes a distinct 0700
witness scope. Its activation code fsyncs the `activation_prepared` intent and
writes an eight-second, four-element dual-stack blackout in one nft
transaction. The fixture forces the owner process to exit immediately when
that write succeeds, before `witness.observe()` can run.

The parent observes exit 23 and replays the original scope bytes: one
prepared intent binds the selected plan and rule digests, with zero recorded
observations. Both nft blackout sets still contain active timers, both permit
sets are empty, and the selected kernel observer remains unqualified. A
different process cannot create the same one-shot scope again; its failed
attempt leaves the archive unchanged. A capability-free collector connection
is then refused by the selected FORWARD drop counter, even though its original
owner has exited. All of this takes place inside private mount/network/PID
namespaces with only a local documentation-subnet target.

The ignored, write-once private report
`data/joint-window-isolated-2026-09-28-r8.json` has SHA256
`d0eb5dd29cbd819404798b0a3289ba19991412a15f73695f1141fb9dbafb835b`.
It records 40 base and 21 joint checks, unchanged host observations, zero
venue requests and all admission fields false. The related window suite
passed 106 tests; lint, format and diff checks passed. Read-only host checks
still find neither joint nft table; the installed entry exits 2 unqualified.

This proves the consumed-scope and short kernel-lease behavior after one
process death, not power-loss durability, protected host startup/restart,
source and mark ownership or uninterrupted 425-second exclusion. The scope
cannot be retried after a crash and the kernel lease will expire; it does not
become an operational guard or `guard.verify()`. Host/container/proxy
coverage, provider-visible source and fresh provider bounds remain missing.
No host firewall, service, credential, venue request or trading path changed.

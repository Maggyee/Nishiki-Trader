# Protected joint-window probe in nested private namespaces

Date: 2026-09-28. `gateway_window_isolated_probe.py` is a fixed-path,
single-use activation probe. Its outer process checks the protected
`/run/trader-egress-window-startup-v1/startup-check.py` hash, its own protected
`/run/trader-egress-window-probe-v1/probe.py` path and the selected installed
six-source inventory against a separately supplied base-manifest SHA256. It
then creates private mount, network and PID namespaces. The inner PID 1 checks
an empty network namespace with loopback only, mounts private manifest and
temporary storage, reselects the protected sources, and uses their installed
observer, custody, witness and activation code for one five-second dual-stack
nft blackout with empty permit sets. The probe returns exit 2 with network
admission false even when its private activation succeeds. Checkout execution,
non-private PID and malformed arguments refuse before nft writes.

The disposable installation fixture stages the probe at its fixed protected
path inside an already private root, then exercises its nested namespaces.
The correct selection observes one activation; an incorrect base hash refuses.
The write-once ignored report `data/joint-window-isolated-2026-09-28-r10.json`
has SHA256 `b17badc54972f03f4daf1e9cb242f45dcbe8e29e0167ac3a0e60286e8e01ec2e`.
It records 40 base and 26 joint checks, unchanged host observations, zero
venue requests, and false admission. All 109 related Python tests, Ruff lint,
format and diff checks passed. The report's probe hash is
`ea82995600baebb66dab834ca5487c925bbac3d5e45b0aee77d702d11e322026`;
the fixture selected it from its own checkout, so that hash is not independent
host startup attestation.

No probe has been staged or executed against the host's installed sources by
this report. The existing protected startup script remains a read-only check;
there is no host joint nft controller, service or persistent activation
journal. A five-second private lease and one observation cannot establish
uninterrupted 425-second exclusion. Full host/container/proxy caller coverage,
mark and public source ownership, fresh provider bounds and trading admission
remain blocked. Any separate host invocation must first verify the committed
probe hash independently, the previously selected base/joint manifest hashes,
the protected target path and the absence of the host joint nft table; it may
only execute the outer probe, which creates its own private namespaces.

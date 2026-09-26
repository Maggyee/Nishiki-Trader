# One-shot local joint-window witness

Date: 2026-09-26. `gateway_window_witness.py` consumes a private, exclusive
`joint-window-witness-v1` directory before asking a held selection for any nft
snapshot. It fsyncs a `claimed` record first, then journals each selected
snapshot with a hash-linked sequence, fixed selection and rule pins, bounded
monotonic clock, and a nonincreasing conservative expiry (allowing only the
one-second nft JSON rounding interval). The directory includes its own README
and cannot be reopened. Record tampering, selection drift, timer extension,
clock regression and persistence uncertainty permanently stop the object.
Read-only replay accepts the original complete bytes only against an expected
hash; a caller-chosen hash does not authenticate the source.

Staged tests join the actual held-selection adapter and observer with offline
nft JSON. Crash-before-snapshot leaves only the consumed `claimed` record;
fsync failure and foreign owner do not permit retry. Even after a simulated
300-second lookback with more than 125 seconds of timer remaining, the report
keeps `activation_history_verified`, source authentication, caller coverage and
network admission false. No host directory, nft table, network path or venue
socket was created by this work.

This journal records samples, **not continuous activation**. There is no
protected installation of the witness, atomic nft activation, immutable
one-shot kernel lease, watchdog, complete mark/route/NAT/Docker/proxy coverage
or provider-visible source proof. Rules can be removed and restored between
samples, including with a timer expiry that appears unchanged after rounding.
The witness cannot implement `guard.verify()` or authorize the 425-second
host exclusion, the first joint request or trading. Next bind a protected root
controller to an actual one-shot kernel activation and durable stop state,
independently verify all callers and source, then acquire fresh provider
interval/usage bounds before considering a separately gated collection.

Verification: 63 related tests pass, including two real nft probes in disposable
user/network namespaces and an independent process exiting immediately after
the fsynced claim. Ruff, formatting and diff checks pass. Power-loss durability
and actual protected host installation were not exercised.

# Installed response delivery: stalled consumer and terminal ordering

Date: 2026-09-17. Review of `66cef1e`; disposable fixture only.

Continued inspection found and fixed two additional boundary cases:

- Root set a socket timeout before `send`, then reused that timeout for `receive`.
  A blocked send therefore allowed the receive wait to extend beyond the remaining
  five-second transfer budget. The later health check still refused a successful
  ledger outcome, and the kernel permit was already revoked. The fix recomputes
  the remaining time between every data/final send and its acknowledgement wait.
- Receipt replay validated the active preparation prefix and outcome ordering,
  but omitted subsequent `aborted`/`closed` records when no outcome existed.
  Rehashed inputs could place a ledger termination before an acknowledged receipt
  and still pass. Both UTC and monotonic terminal timestamps must now follow the
  last receipt record. A legitimate acknowledgement followed by lost outcome
  persistence and later termination remains accepted with
  `attempt_outcome_recorded=false` and the original pending attempt intact.

Four new failing regressions reproduced these issues before the fix. Two further
positive regressions preserve the valid acknowledgement-without-outcome case.
**276 focused tests pass**, including all six additions, in 20.52 seconds with no
warnings. The seven test modules cover receipt/TLS, installed gateway, joint IPC,
ledger gateway, attempt ledger and collector launch. Ruff/format/diff checks pass.

The installed namespace harness adds `receipt_child_stopped`: after complete TLS,
revoked kernel permission and durable receipt preparation, the trusted parent
sends SIGSTOP through a pidfd and verifies the child is actually stopped. Root
must time out, kill and reap that child, and preserve a pending attempt plus only
a prepared receipt. A pidfd exit observation and absent `/proc` process entry
verify cleanup; no SIGCONT or retry revives the consumer. Existing kernel denial,
protected state, original-sentinel and fresh-process no-reopen checks still run.

All eleven response-delivery scenarios pass with the corrected held
sources. Current originals and source copies are retained under
`data/installed-tls-receipt-stall-2026-09-17/`. Fresh offline processes also replay
the previously selected 37 scenario sets with the corrected reader, checking exact
pins and original report equality with socket creation and DNS disabled. Both
independent replay outputs match all 48 new/historical result sets exactly.
The [JSON report](portfolio-installed-tls-receipt-stall-2026-09-17.json) records exact
acceptance/replay results and hashes. Historical evidence is not modified.

These are fixture reliability and replay-consistency fixes, not a new network or
trading admission. Timing checks do not preempt synchronous filesystem work or OS
scheduling. The base installer/launcher, nine-source v4 manifest inventory, wire
protocol and journal schemas stay unchanged. The fresh fixture pins the new source.
No host installation, real venue request, upstream edit, live path, SignalEvent,
SourcePolicy or schedule change occurred. Full native signed REST/WS integration
and real source/coverage/rate/clock qualification remain pending.

# Installed response delivery: deadline and replay review

Date: 2026-09-17. Review of `fd1bb98`; fixture-only fixes, no venue requests.

Two findings were reproduced and fixed in `gateway_tls_receipt.py`.

1. **The fixed single-request reviewer accepted broader or contradictory ledgers.**
   It checked the selected preparation prefix's pending index/count, but omitted
   its terminal state and the complete companion's attempt count. A valid generic
   ledger with a second preparation was accepted as a companion to one receipt.
   A rehashed receipt could also reference an aborted/closed prefix with pending
   index 0. Finally, changing the ledger outcome to `failed` or `uncertain` still
   produced `acknowledged` with `attempt_outcome_recorded=true`.
   The reader now requires exactly one full-ledger attempt, an active incomplete
   prefix, and a matching successful outcome if an outcome exists. A missing
   outcome remains explicitly incomplete bookkeeping; it is never manufactured.
2. **The consumer could acknowledge after parsing exceeded its total deadline.**
   The deadline was checked before receive, but not after validating the completed
   response. A deterministic clock-advance test reproduced a late `accepted:`
   message and a successful consumer return. The receiver now refreshes the socket
   timeout from the original deadline before each partial/final acknowledgement,
   checks after parsing and checks again before returning completed bytes.

The gateway already checked its own deadline after the final acknowledgement;
that check kept the attempt pending in the reproduced late-parse case. Kernel
permission was already revoked before transfer. These fixes strengthen the
consumer contract and offline consistency checking; they do not close a discovered
live trading or network-permission bypass. Rehashed-input tests deliberately
construct inconsistent evidence. Pinned historical originals were not modified.
Synchronous parsing/storage cannot be preempted by these checks; late completion
now fails when control returns, without a late consumer acknowledgement.

## Verification

All six added regressions failed against the prior implementation and pass after
the fix. **270 focused tests pass** in 20.60 seconds, covering the receipt, TLS,
installed gateway, joint IPC, ledger gateway, attempt ledger and collector launcher.
This focused batch had no warnings. The prior 828-test full joint batch remains
historical evidence; unrelated native joint modules were not changed or rerun.

The unchanged installed namespace harness passes against the corrected source for
all ten response-delivery scenarios. New originals and exact protected sources are
retained under `data/installed-tls-receipt-review-2026-09-17/`. The old 27 selected
scenario sets also pass replay with the corrected reviewer. Two independent
isolated system-Python processes verify the selected original hashes and compare
results with their original reports, while denying socket creation and DNS. All 37 result sets match exactly.
Exact results and pins are in the [JSON](portfolio-installed-tls-receipt-review-2026-09-17.json).

The nine-source fixture manifest stays v4: inventory and wire/journal schemas did
not change; the new source digest is selected in the fresh disposable installation.
The base installer and launcher are unchanged. Old evidence, scopes, source copies
and replay drivers stay immutable. There is no retry, reset or host deployment.

Changed files: receipt implementation and its tests, infrastructure README,
agent reading index, current status and this MD/JSON report. Upstream source,
SignalEvent, execution runners, source policies and live order paths are untouched.
Full native signed REST/WS integration remains the next implementation step;
real authority, all-caller coverage, unknown provider charges and trading remain
unqualified. No new phase or trading permission follows this review.

# Source-bound cancellation recovery — 2026-09-11

The fixed ADR-017 session now has an explicit **`--recover-cancel`** operation.
It reconciles the original native checkpoint against a new signed subscription,
complete account-wide balances/orders, original client order IDs and exact trades.
A qualified active order can enter a separate cancellation-only native runtime.
A terminal order produces a read-only result and leaves `native.json` unchanged.
The prior `--recover` command remains GET-only.

The actual engineering BUY/cancel already completed on `6d7c43b`, without fills.
Its activation and BUY allowance remain consumed. This increment does not create
a new session, retry that BUY, force a fill, or authorize a cleanup SELL.

## Admission and durable restoration

Only the fixed matching LiveClock profile, selected key/source and existing lease
are accepted. The CLI requires clean code synchronized with the current upstream.
There is no alternate scope, checkpoint, order ID, amount or endpoint flag. The
existing collector rejects changed source/fences, inconsistent complete balances,
missing trades, foreign orders, incomplete pages or observations beyond its history
bound. Native recovery restores actual event lineage; remote balances never replace
native accounting and no inferred fills are allowed.

After signed numerical reconciliation, a cancellation candidate must be the sole
ACCEPTED or PARTIALLY_FILLED original order. Its native Submitted event and original
submit-attempt receipt must exist. Any old cancellation intent or attempt blocks a
new cancellation, including a crash between durable preparation and actual I/O.
Terminal orders need no writer or execution client. A full fill while the recovered
controller waits also finishes without DELETE and retains the owned BTC.

For an active candidate, the original checkpoint lock remains held while native
currencies, CASH account, orders, positions, cache and portfolio are rebuilt on
LiveClock. Session identity, original baseline/instrument, deadline, signals,
intents, dispatches and halt history must remain identical. The recovered native
state and source/evidence provenance are atomically persisted before native order
cancellation is enabled. The fixed checkpoint receives a permanent
`recovery_cancel_only` marker, which also blocks the original matching ledger's
new-order method. Failed publication leaves no permission to send in that process.

Historical transport-related halt entries are retained, not cleared. Only these
known histories may accompany fresh cancellation qualification:

- `submit_attempt_failed_or_unknown`
- `matching_runner_aborted_requires_reconciliation`
- `matching_source_or_lease_lost`
- `order_ack_or_cancel_confirmation_timeout`
- `cancel_recovery_interrupted`

Other halt reasons, including unexplained account changes, block active admission.
A new error in the recovered process halts that process. A prior cancel attempt
stays consumed regardless of later responses; recovery never retries it.

## Native cancellation and callbacks

The native Strategy retains its original identity and can only request cancellation.
Its signal consumer, ledger preparation, execution-engine command routing, adapter
submission and HTTP POST paths all reject new orders. Native RiskEngine is present
and HALTED for new trading. The execution engine accepts only a CancelOrder with
the exact original strategy, instrument, client and venue IDs. The native Binance
serializer, PendingCancel event and durable dispatch barrier remain in use.

The fresh receipt/fence is checked before cancellation preparation, dispatch and
network entry. The default two-second delay after native acknowledgement remains;
if acknowledgement was recovered from signed evidence, this waits two seconds after
that native recovery event. The original 180-second **new-order** deadline is never
renewed; cancellation of an existing order can occur after it. Source drift or an
expired receipt blocks sending, and there is no reconnect loop or blind retry.

Recovered trade history seeds the callback cumulative quantities, quote totals,
venue IDs and deduplication keys. Every seed is checked against the signed original
trade's ID, amounts, commission currency and timestamp. The original exchange
millisecond timestamp is preserved; the native timestamp is compared using Nautilus's
own millisecond conversion instead of assuming every native nanosecond value is an
exact multiple of one million. This avoids a floating-conversion rounding mismatch
without rewriting native events or exchange evidence.

Exact historical duplicates remain deduplicated. Newly arriving or late partial
fills still settle through native accounting and remain session-owned. Account
updates are correlated without patching balances. Final complete signed native
reconciliation is mandatory; a timeout leaves PendingCancel uncertain and consumed.
No BUY allowance, SELL cleanup permission, fee policy, SourcePolicy, full-account
portfolio qualification or production readiness is restored.

## Verification and files

Tests use actual LiveClock/native queues and a synthetic Ed25519 network boundary.
They cover accepted, partially filled, missed-fill and missed-acknowledgement recovery;
exact original-ID DELETE; cumulative duplicate/late-fill settlement; retained halt
and BUY allowance; full fill before cancellation; unexplained funds or missing
trades; old cancel intent; missing submit receipt; source/receipt expiry; archive,
checkpoint, PendingCancel and dispatch durability failure; and uncertain DELETE
without retry. A complete CLI test recovers an active order, reconciles its late
fill/cancel, then invokes the command again and observes no action or file mutation.

A subprocess fixture exits abruptly inside the recovered DELETE transport, after
its dispatch receipt is durable. Two independent new processes then reconcile the
terminal venue evidence. They produce identical views and preserve both original
attempt receipts, halt history and the fixed checkpoint bytes. All I/O in this
crash fixture is synthetic; it does not create an exchange order.

Changed files:

- `apps/strategies_nautilus/portfolio_session_cancel_recovery.py` — cancellation-only restoration/runtime.
- `apps/strategies_nautilus/portfolio_session_runtime.py` — persistent recovered-scope new-order guard.
- `apps/ops/portfolio_session_run.py` — explicit CLI mode and terminal/full-fill outcomes.
- `tests/strategies_nautilus/test_portfolio_session_cancel_recovery.py` and
  `tests/ops/test_portfolio_session_run.py` — native, CLI and subprocess acceptance.
- Application READMEs, agent reading list, ADR-017 and project status — boundaries and operation.

No upstream source, dependency, service, schedule or production path changed.
**21 new tests** pass; full offline regression: **2,563 passed, 12 deselected**
(131.44 seconds). The 12 Postgres integration tests require a dedicated DSN, which
is unavailable. Ruff, registry and whitespace checks pass. The actual terminal
no-action check will use the clean committed implementation.

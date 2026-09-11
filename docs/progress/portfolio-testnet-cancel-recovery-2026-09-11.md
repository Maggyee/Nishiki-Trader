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

## Actual terminal-session acceptance — 2026-09-11 12:55 UTC

Clean pushed code **`9d797f6b3f2b1715bf0f9b50c2468f00e78293c6`** ran
`apps.ops.portfolio_session_run --recover-cancel` against the existing selected
account and fixed session. A new signed subscription and **six signed GETs**
reconciled all **502 assets**, the original **CANCELED** order and **zero trades**.
There were **zero account-wide open orders** and **zero owned BTC**.

The command returned **`terminal_session_no_action`**. The journal contains no
matching attempt, POST, DELETE, cancellation-runtime publication or business event.
The two dispatch receipts are the prior trial's original BUY/cancel receipts;
this invocation added none. The BUY allowance remains consumed. No new execution
client or ledger writer was constructed on the terminal branch.

The fixed `native.json` stayed byte-for-byte unchanged at SHA256
`08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f`.
Separate private immutable artifacts under the same fixed state directory:

| File | SHA256 |
|---|---|
| `cancel-recovery-9c1359b2b5f4-report.json` | `d6fdd413c8d8d052885362b39443467bc430410b31a1eadf4a7c6091c1e825d9` |
| `cancel-recovery-9c1359b2b5f4-stream.jsonl` | `63eab354a2b2130eba3af4743cda2b62eaf47a5a4f2ec7ad255a279b372e9ca2` |
| `cancel-recovery-9c1359b2b5f4-evidence.json` | `5ca0213543cb9110eb353bf3f02c048649be97e205b246ab665fb1299e842b65` |
| `cancel-recovery-9c1359b2b5f4-recovered.json` | `d097a49e24edb32729846241c89f491e20c4e0fce99c21cd05b71d56da362b07` |

This verifies the real terminal branch and its non-mutation guarantee. Active-order
recovered cancellation, late fills and crash recovery remain synthetic acceptance;
no new active order was created to test them. Actual fills, fee settlement and
owned cleanup remain outstanding. Any future recovered cleanup must retain the
original SELL allowance, zero-fee/fresh-rule checks and 180-second new-order bound;
the current cancellation-only marker grants no such order permission. Strict
continuity, full-account portfolio qualification and production gates are unchanged.

# Bounded LiveClock matching runtime — 2026-09-11

The ADR-017 fixture now has a separate wall-clock execution profile and one-shot
CLI: `apps.ops.portfolio_session_run --execute`. This joins the fixed account lease,
complete native CASH baseline, signed stream archive, native Strategy/RiskEngine/
queued execution adapter and durable one-attempt HTTP boundary. It is exclusively
Binance Spot testnet. The existing offline bridge and GET-only probe keep their
original guards. Production, SourcePolicy and portfolio qualification are unchanged.

## Admission and execution

The CLI requires clean committed code equal to the current branch's upstream.
There is no alternate state-root, session-ID, symbol, quantity or price override.
It uses the existing selected account artifact and Ed25519 configuration. Fresh
complete account observations, zero commissions and effective filters precede
activation. Full native-vs-signed reconciliation precedes each new order. All rule
inputs must still be within five seconds at the actual submit boundary.

`MatchingRuntimeLedger` explicitly requires LiveClock and permits at most one second
between native order initialization and validation. The original TestClock ledger
still requires exact time equality. The matching profile cannot convert a probe
checkpoint. Activation is exclusive and precedes the fixed `native.json`; errors
never delete it, replace session IDs or replenish allowances.

The deterministic engineering SignalEvent v1 feeds the existing native strategy.
The first BUY remains exactly 0.0001 BTC, at the newly observed best bid minus one
price tick, with at most 10 existing free test USDT allocated. Native RiskEngine
also enforces a 10-USDT per-order cap. No fill is guaranteed or forced.

Native Submitted or PendingCancel and the single dispatch receipt must be fsynced
before the exact matching request is signed and sent. The HTTP client allows only
POST/DELETE `/api/v3/order` with the original native terms/IDs. It pins the testnet
host, verifies the selected key, refuses direct transport calls, and never calls
the upstream signed-query logging path. Unsigned attempt selectors and raw HTTP
responses are retained privately. Any unknown response remains uncertain; no
synthetic rejection, resubmission, amendment or replacement is generated.

The lifecycle requests cancellation once, two seconds after native acknowledgement,
if the order remains active. A 20-second acknowledgement/terminal wait bounds the
controller; native HTTP has a 10-second timeout. A disconnected stream or uncertain
native history halts admission and requires original-ID reconciliation. It does not
blindly cancel through an unqualified replacement connection. This first runner
has no executable recovery/reconnect or automatic reduction after such a halt.

After a confirmed terminal BUY, complete signed orders/trades/balances must agree
with the native view before cleanup. Only whole effective steps of owned net BTC
can be offered in one SELL, at the newly observed best bid. Below-minimum residuals
are retained. All new orders retain the original 180-second deadline. SELL proceeds
cannot finance a second BUY; pre-existing BTC and every unrelated asset are retained.

Account notifications are correlated against native balance observations and never
assigned to the account. Pending notifications block new admission and successful
review. Complete signed final reconciliation is still mandatory; callback correlation
and stable REST bracketing do not prove global gap-free stream delivery.

## Recovery and operational limits

`apps.ops.portfolio_session_run --recover` opens a new signed subscription and reads
only the fixed matching checkpoint's original order IDs, their trades and complete
account-wide balances/orders. The native numerical reconciler writes a separate
immutable recovered checkpoint/report. It neither replaces the fixed matching
checkpoint nor sends an order/cancel, clears a halt, renews budget or claims readiness.
Missing original orders or ambiguous evidence remain blocked. It can be used after
an interrupted run; active-order reduction after recovery remains a later explicit
implementation, within the same fixed scope and original consumed allowances.

No services, schedules, dependencies, credential/permission changes, old execution
runners or production endpoints are added. Strict continuity remains 0/14; ADR-013
and ADR-015/016 full-account baseline/equity gates stay unqualified. This engineering
fixture is not a research promotion, portfolio allocation or real-money trial.

## Verification

The new tests exercise the actual LiveClock native queues and Ed25519 signer with a
stubbed network boundary: pre-send checkpoint receipts, exact parameters/signature,
RiskEngine denial, full owned cleanup, late fills during timed cancellation,
account callbacks before native settlement, disk/archive failures, transport timeout,
source/lease loss, stale evidence, forbidden routes, unknown reports and fixed-scope
reuse denial. Whole CLI tests run both an unfilled BUY/cancel and a filled BUY/SELL,
then open a separate GET-only recovery invocation and prove no further writes.
Existing offline partial-fill and abrupt-exit recovery tests remain applicable.

**31 new tests** and the full offline suite pass: **2,542 passed, 12 deselected**
(114.73 seconds; no dedicated Postgres integration DSN). Ruff, registry and whitespace
checks pass. The independent Ed25519 signature check uses existing OpenSSL; no
dependency was added. Actual testnet results will
be appended here after running the committed implementation; this implementation
section alone is not evidence that a matching order or cancellation was accepted.

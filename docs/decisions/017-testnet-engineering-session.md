# ADR-017: Independent testnet engineering session and capability validation

- **Status**: Accepted for the separate engineering scope, diagnostics and implementation
- **Date**: 2026-09-11
- **Authority**: After the proposed sequence (independent 10 test-USDT engineering
  scope, capability checks, native recovery, bounded lifecycle), the operator said
  “你来操作，api好像权限都是有的”. This authorizes the technical work and
  non-matching validation below. It is not evidence that every key permission exists.
- **Policy ID**: `testnet-engineering-session-v1-20260911`

## 1. Resolve scope without fabricating a portfolio baseline

The full faucet account has 502 assets, including two without supported quotes.
ADR-015/016 full-account equity, UTC day-open, cash-flow history and strict readiness
remain unqualified. Those requirements still apply to portfolio/production admission.

Define a separate single-session engineering budget: earmark **10 existing free
test USDT** from a fresh complete signed account observation; this is an allocation
ceiling, not total equity, a deposit, a UTC baseline or an amendment of daily risk.
The first implementation scope requires **all standard, special and tax commission
components to be zero**, before both validation and any future matching submission.
Positive or missing fees block this scope; no BNB or unrelated asset may pay them.
No assumed stablecoin peg or zero mark is assigned to unrelated holdings.

The future session ledger starts with zero owned BTC and at most 10 allocated
test USDT. Preserve the entire native account separately. Only actual net fills
of the session BUY create session BTC ownership. Unfilled SELL proceeds cannot
finance anything, and SELL receipts never renew the one-BUY allowance.
This is logical bookkeeping isolation, not an exchange subaccount or a guarantee
against venue faults. Any external/reset/unexplained account delta halts admission.
An observation anchor starts prospectively; historical reset facts remain unknown.

## 2. Bounded lifecycle and required native implementation

- BTCUSDT LIMIT, fixed **0.0001 BTC**, total BUY debit at most **10 test USDT**.
- At most one BUY and one owned-inventory cleanup SELL; one outstanding order.
- Session bound 180 seconds, cancellation requested two seconds after acknowledgement.
- No automatic resubmit, replacement, amendment, second BUY, budget recycling or dust sweep.
- A fixed order that misses price, quantity, notional, balance or fee bounds is rejected.
- Cleanup uses whole owned steps; below-minimum residuals remain owned and reported.
- Persist session ID, allocation, client order IDs, prepared intent, native events,
  fills/fees, residual ownership and halt state before any submit. A crash or unknown
  submit/cancel cannot replenish budget or erase the original BUY intent.
- A recovered process must reconcile account-wide orders/balances and query its
  original order IDs, then restore native state before any permitted reduction.
  Missing or ambiguous evidence blocks action; no blind retry is allowed.

These are implementation requirements. The new contract function and validator
do **not** implement an execution runner or the durable native session ledger.
Before any matching session, verify the ledger through partial/full fills, late
fills during cancellation and fresh-process native adapter recovery; bind a distinct
reviewed engineering fixture through SignalEvent v1 and the native strategy/risk/
execution path. Existing research source policies and quantities are unchanged.
Launching the old portfolio/testnet runners cannot substitute for that integration.

## 3. Capabilities and non-matching validation

Use only the already-selected local Ed25519 key and `https://testnet.binance.vision`.
The dedicated GET client pins exact paths and BTCUSDT parameters. Capture full
account and account-wide open orders before/after commission, myFilters,
exchangeInfo, referencePrice, avgPrice and bookTicker reads (ten GETs, ≤60 seconds).
Bind the source to the immutable initial account bytes, UID and key fingerprint.
Retain raw response bytes/hashes, statuses and capture times privately. UID agreement
is observed-source continuity, not independent authentication of historical records.

Use the existing native venue parser for private/public filter intersection and
reference-price precedence. An explicit testnet-only opt-in accepts a null discount
asset **only when every nonnegative commission component and discount rate is zero**.
The original parser default continues rejecting that shape. Do not rewrite raw
responses or claim that a discount-only flag proves an actual fee currency.

The official [Spot testnet REST specification](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/rest-api.md#test-new-order-trade)
defines `POST /api/v3/order/test` as TRADE security and says it does not send orders
to the matching engine. A separate exact-whitelist client may invoke this diagnostic
once with the fixed BUY quantity, a freshly checked LIMIT price and
`computeCommissionRates=true`. It rejects `/api/v3/order`, DELETE, other symbols,
MARKET, extra parameters, other hosts and a notional exceeding 10 test USDT.
No execution engine is bypassed: this endpoint performs validation only and creates
no executable order, fill, native order acknowledgement or SignalEvent.

Require stable complete balances/empty orders, at least 10 free test USDT, account
`canTrade`, successful native rule parsing, zero fee bound, basic filters and effective
BUY price bands. The capture must have completed within five seconds of validation.
Persist input evidence before the diagnostic, retain its receipt and verify full
balances/empty account-wide orders afterwards. Timeout/failure has no automatic retry.

An HTTP 200 with the requested zero fee response establishes acceptance of that
TRADE validation request at that time. It does not prove all API restrictions,
matching-order acknowledgement, actual fee settlement, stream business-event delivery,
or native recovery. Keep those claims separate. Unsupported `/sapi` remains unknown.

## 4. Completion boundary

The implementation entrypoint is `portfolio_testnet_session.py`; the diagnostic CLI
is `apps.ops.portfolio_testnet_capabilities --validate-order`. No matching-order
runner, long-running service, schedule, dependency or credential mutation is added.
No production account is accessed. Strict continuity remains 0/14; neither this
engineering validation nor a later single lifecycle trial proves the 14-day gate,
promotes research identities, accepts ADR-013 or authorizes real-money trading.

## 5. Offline implementation addendum — 2026-09-11

The [native session ledger/recovery increment](../progress/portfolio-testnet-session-recovery-2026-09-11.md)
now implements durable preparation, full-account conservation, owned-only cleanup,
partial-fill CASH locks and crash/replay acceptance with the native report engine.
This is TestClock/offline-only and is not an execution deployment. Checkpoint hashes
bind selected bytes and policy; they do not authenticate exchange observations.
The submission/cancellation bridge and actual stream callbacks are still unwired.

An active order with no persisted native Submitted receipt remains blocked without
resubmission. Exact persisted initialization may be reconciled only to terminal
reports in the explicit engineering profile, with original native event lineage.
The future bridge must persist Submitted before an outbound request. No second BUY,
new-ID restart, budget recycling or native account balance repair is allowed.
The 180-second bound stops new orders; recording cancellation of an already-owned
outstanding order may continue to reduce risk, without assuming acknowledgement.

## 6. Queued adapter implementation addendum — 2026-09-11

The [offline queued bridge acceptance](../progress/portfolio-testnet-session-bridge-2026-09-11.md)
now wires the dedicated fixture Strategy, native RiskEngine, queued execution engine
and native Binance serializers/callbacks. A native Submitted/PendingCancel event
must be captured durably before its one dispatch receipt and adapter attempt.
Timeout remains uncertain; a failed disk write forbids sending. Dispatch records
survive abrupt-exit native recovery without restoring either order allowance.

This remains TestClock/in-memory only. It does not qualify a real source, signed
stream/account fence, fixed global account lease or LiveClock bootstrap. The next
real-testnet profile must supply those integrations and fresh fees/filters before
the already bounded matching lifecycle; existing source policies and portfolio
qualification are unchanged. No matching or production request was made here.

## 7. Real-clock read-only bootstrap addendum — 2026-09-11

The [source-bound session transport](../progress/portfolio-testnet-session-transport-2026-09-11.md)
now supports complete account/original-order/trade GET collection and actual native
LiveClock bootstrap. The fixed private account/scope manifest owns a single session
ID across invocations; matching activation must be exclusive and precede its native
checkpoint. A missing checkpoint after activation cannot renew the allowance.

Read-only probes have separate files and never activate or consume the matching
scope. Two actual processes reconciled all 502 assets through new subscriptions,
with zero orders, trades or business events. The probe forbids prepare/dispatch/
cancel and execution-client registration. This advances account-source and numerical
recovery evidence, not matching permission or active-order recovery. The bounded
matching client, LiveClock strategy/risk integration and timed cancellation remain
the next implementation. Portfolio qualification and the 14-day gate are unchanged.

## 8. Bounded matching runtime addendum — 2026-09-11

The [separate matching LiveClock runtime](../progress/portfolio-testnet-session-runtime-2026-09-11.md)
now implements the fixed engineering fixture with native risk/execution, exact
single-attempt Ed25519 POST/DELETE, durable receipts and acknowledgement timers.
BUY price remains observed best bid minus one tick; one owned cleanup SELL uses a
fresh best bid. Fills are not guaranteed. Every new order still requires zero fees,
fresh effective rules and signed complete native reconciliation. Original offline
and read-only profiles remain guarded.

The bounded CLI has no automatic reconnect or executable recovery. Its separate
`--recover` command performs signed original-ID/account/trade reconciliation only;
it cannot renew allowances, replace the matching checkpoint or resume a halted
session. Unknown active outcomes require recovery before a later reduction path.
This is still the same one engineering scope, not a portfolio or production gate.

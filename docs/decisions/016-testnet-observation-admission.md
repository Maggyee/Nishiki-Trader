# ADR-016: Testnet observation admission and prospective baseline rules

- **Status**: Accepted for read-only review and offline test preparation
- **Date**: 2026-09-11
- **Authority**: Operator instruction to advance admission, valuation/baseline and
  lifecycle-test preparation in order. No order run or live deployment is opened.
- **Policy ID**: `testnet-observation-admission-v1-20260911`

## 1. Admission scope

Use only the existing Ed25519 configuration and Binance Spot testnet endpoints.
Bind each new observation to the actual bytes/hash of the selected initial
observation, its observed UID and API-key fingerprint. A new archive must match
that selected source on every row. Never infer a replacement identity from the
new archive's first row or silently accept a changed key/UID. An explicit new
selection is required after such changes.

The operator confirms no other program/manual trading; independent account
records are unavailable and faucet/reset history remains unknown. This context
supports ongoing read-only diagnostics. It does not independently authenticate
UID, prove absence of trading history or establish a recovery baseline.

Successful signed `/api` reads, signed WS subscriptions and account `canTrade`
are separate observations. None proves API-key trading restrictions. Spot testnet
does not expose `/sapi`; keep those restrictions unknown. The strict production/
dedicated-account collector is unchanged. No fabricated permissions or promotion
flags may bridge the gap. This review's `testnet_order_ready` and `runtime_ready`
remain false even if every numeric/consistency check passes.

## 2. Prospective observation anchor

A completed, selected full-account collection can be recorded as an immutable
**prospective observation reference**, with its exact balances, completion time,
source-binding digest, input hashes and deterministic anchor ID. This permits
later comparisons starting at that observation; it does not certify the earlier
account history, a UTC day-open value or an execution checkpoint.

The reference retains all assets and free/locked balances, including zero rows,
faucet assets and currencies with no market. It never substitutes the provisional
500 USDT capital or discards assets to imitate the BTC/USDT simulation fixture.

Day-open equity, daily loss and effective daily loss limit remain null until an
independently qualified UTC baseline, complete valuation and cash-flow history
exist. Do not initialize midnight from the first later quote. If a reset, external
cash flow, source change or unexplained balance/order delta occurs, hold admission
and require review/new evidence. Matching endpoints cannot prove none occurred
between observations. Old anchors remain historical, never silently rebased.

ADR-015 continues to require min(25 USDT, 5% of qualified day-open equity), the
separate fixed 250 USDT peak-loss ceiling and persistent stops. This ADR does not
weaken those rules or claim that a sampled/partial valuation can enforce them.

## 3. Full-account indicative valuation

Pin the original account archive, selected collection, initial source artifact
and public market capture. The latter must bind that exact account collection.
Public requests must be testnet `exchangeInfo` then all-symbol `ticker/bookTicker`,
after account collection, with non-regressing receipt clocks and a combined
account/market capture span of at most 60 seconds in one UTC day. These are local
capture-order checks, not current quote freshness or an atomic account revision.

Use explicit listing asset precisions to verify the complete native balance map
in an isolated process. Numerical equality is necessary but is not valuation.

For indicative USDT marks:

- USDT is the accounting denomination; no other stablecoin gets an assumed peg.
- Base-to-quote uses a positive bid with positive bid quantity; quote-to-base
  uses a positive ask and positive ask quantity, at 1/ask. A missing opposite
  side does not erase a usable side; crossed positive books are rejected.
- Only spot-enabled TRADING listings are usable. Prefer a direct conversion to
  USDT, otherwise at most two legs through BTC/ETH/BNB/USDC/FDUSD. Break ties by
  lexical path identity. Do not optimize for the highest mark or chase longer
  paths after viewing the result.
- Value total free plus locked quantity, preserve the complete conversion path
  and compare input quantity with each leg's top-book capacity. Shared capacity
  is not allocated across holdings; even passing individual bounds cannot prove
  simultaneous liquidation. Fees/slippage are not liquidation estimates here.
- Missing marks remain null. Expose a clearly named priced subtotal; expose a
  full indicative mark only if every nonzero asset has a supported price path.
  An unquoted zero balance contributes zero without fabricating a price.

REST bookTicker has no qualified event timestamp in this capture. Retain
`individual_quote_age_verified=false`, `valuation_qualified=false` and
`liquidation_value_verified=false`. Market captures occur after the account
observation stream has closed; account/market atomicity is explicitly unverified.
Future qualified valuation requires synchronized native account/price evidence.

## 4. Minimal order lifecycle proposal

Prepare a separate engineering-only test proposal; no legacy identity is revived
and no research allocation changes. The proposed first session is BTCUSDT LIMIT,
fixed 0.0001 BTC, at most 10 test USDT total buy debit including fees, one BUY and
at most one owned-inventory cleanup SELL, one outstanding order at a time, and a
180-second session bound. Request cancellation two seconds after acknowledgement.
An illustrative price one tick below the selected bid is not a guarantee against
fills. If it fills, preserve exact fees/residuals and apply the reviewed whole-step
reduction policy; never sweep unrelated faucet balances or pretend dust is flat.

No automatic resubmit, replacement, amendment or second BUY is permitted by the
proposal. A fixed-size order that fails filters/budget is rejected, not resized.
Full-fill, cancel-race and abrupt-restart scenarios remain acceptance obligations;
one quiet cancellation cannot qualify all of them. Subsequent sessions need their
own scope and evidence review.

The proposal's public PRICE_FILTER / LOT_SIZE / NOTIONAL check is only an offline
preparation check. Actual key permission evidence, commissions, effective myFilters,
percent-price references, complete account/day-open risk, fixture identity, native
execution integration and uncertain-submit/cancel recovery are still required.
Only the `SignalEvent v1 -> Nautilus Strategy -> RiskEngine -> ExecutionEngine`
path may execute a separately qualified test. No executable runner is added here.

## 5. Boundaries

No new service, schedule, dependency, SourcePolicy or upstream modification.
No credential changes, order/cancel request or production account access.
ADR-013 remains Draft, strict continuity remains 0/14, and existing research
identities, immutable results and the future blind stay unchanged. CLI exit 0
means a read-only review completed, not baseline qualification or order permission.

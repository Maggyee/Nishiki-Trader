# Binance portfolio venue-input adapter — 2026-09-09

Status: **offline response parsing and preflight integration implemented**.
This follows the [synthetic lifecycle acceptance](portfolio-simulation-acceptance-2026-09-09.md).
Captured account responses are synthetic in acceptance tests. No real account,
credentials, exchange order endpoint or retained research prices were accessed.

## Material finding: commission currency

The existing synthetic fixture charges 15 bps in USDT on both sides. Binance's
Spot commission documentation instead calculates fees on the received asset:
BTC for BTCUSDT BUY, USDT for SELL, with possible BNB payment when the discount
is enabled. Ordinary nonzero BUY fees therefore do **not** satisfy the current
quote-only portfolio accounting contract. Treating them as USDT would overstate
owned BTC and could make a later full-sleeve reduction impossible.

`portfolio_venue.py` computes a conservative total rate over standard, tax and
special commission components, maker/taker liquidity and buyer/seller additions.
It takes the maximum complete rate across those possibilities, without assuming
a discount or sufficient BNB. Nonzero base fees and potentially BNB-paid fees
are explicitly unsupported by preflight. An active order with unsupported fee
currency blocks the entire snapshot, including reductions: its accounting cannot
be guessed. With no such active order, an owned quote-fee SELL can still pass.
A zero-fee side is compatible with quote accounting; the shared rate bound may
still reserve extra quote conservatively due to the opposite side's fee.

This increment neither changes the existing synthetic fee setting nor resizes
orders to cover fees. Supporting received-asset fees requires a separate reviewed
execution-accounting change, native net inventory/commission reconciliation, and
an explicit treatment of quantity-step dust. No live trading is enabled.

## Inputs and implemented constraints

The adapter consumes immutable `CapturedResponse` body strings for:

- Public `GET /api/v3/exchangeInfo`.
- Private `GET /api/v3/account/commission`.
- Private `GET /api/v3/myFilters`, including explicit symbol, exchange and asset
  filter lists. Public exchangeInfo alone cannot establish account limits.

Every body has its own receipt timestamp. Both private envelopes must identify
the same expected account and requested BTCUSDT symbol: myFilters itself does
not echo the request symbol. Each response is independently checked for freshness
and hashed. The oldest response or effective price-reference timestamp becomes
the resulting rule timestamp; later evaluation cannot refresh it. Envelope
metadata is a collector assertion, not an authentication or atomic revision proof.

Implemented for a dedicated BTC/USDT account and ordinary unamended LIMIT orders:

- TRADING status, spot availability, base/quote identity and LIMIT support.
- PRICE_FILTER (zero disables its individual components), LOT_SIZE and the
  intersection of MIN_NOTIONAL/NOTIONAL. An absent notional maximum is `None`,
  never a fabricated finite ceiling or nonfinite Decimal.
- PERCENT_PRICE and PERCENT_PRICE_BY_SIDE with inclusive side-specific bounds.
  Callers must attach the exact configured average window and fresh effective
  reference. Official reference-price precedence is explicit; weighted-average
  or last-price fallback requires a known-absent reference price. A bid, midpoint
  or 24-hour ticker average is not silently substituted. Both filters apply when
  both exist; reference metadata is retained in the diagnostic output.
- Symbol/exchange MAX_NUM_ORDERS, taking their minimum. The same complete-set
  gate runs during deterministic funded selection and its final preflight.
  Submitted/partial/pending-cancel orders count until terminal acknowledgement;
  selecting a sell consumes a slot and does not pre-credit a future release.
- MAX_POSITION counts settled BTC plus pending and proposed BUY remainders;
  pending sells cannot reduce exposure. MAX_ASSET intersects BTC quantity or
  USDT notional ceilings with symbol rules.
- Unknown filters, duplicate JSON keys/filter types, inconsistent public/private
  definitions, nonfinite/negative inputs and missing required data fail closed.
  Filters affecting only MARKET/iceberg/algo/trailing/amend/list instructions are
  explicitly reported as inapplicable to this narrow consumer.

`InstrumentRules` gained optional side fee currencies, price bands, order-count
and position bounds. Existing synthetic defaults keep their previous behavior.
SignalEvent v1, frozen allocation/size/priority, SourcePolicy and runtime loss
settings are unchanged. V1/v2 plan artifacts and prior acceptance records remain
immutable. No paper/testnet/live runner loads captured response bundles.

## Read-only diagnostic and reproduction

```bash
.venv/bin/python -m apps.ops.portfolio_venue_check /path/to/captured-bundle.json
# For deterministic offline replay, set the original evaluation nanosecond time:
.venv/bin/python -m apps.ops.portfolio_venue_check /path/to/captured-bundle.json --now-ns 1767225600000000000
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_venue.py tests/strategies_nautilus/test_portfolio_preflight.py tests/strategies_nautilus/test_portfolio_simulation.py tests/ops/test_portfolio_execution_plan.py
```

Bundle shape (`body` is the exact captured JSON response string, not a pathname):

```json
{
  "schema_version": "portfolio.venue_inputs.v1",
  "account_id": "expected-account-identity",
  "exchange_info": {"body": "<exchangeInfo JSON>", "received_ns": 1767225600000000000},
  "commission": {"body": "<commission JSON>", "received_ns": 1767225600000000000, "account_id": "expected-account-identity", "requested_symbol": "BTCUSDT"},
  "my_filters": {"body": "<myFilters JSON>", "received_ns": 1767225600000000000, "account_id": "expected-account-identity", "requested_symbol": "BTCUSDT"},
  "references": []
}
```

For each percent-price filter, `references` needs `filter_type`, Decimal string
`price`, `ts_ns`, `average_minutes`, `kind` (`reference_price`, `weighted_average`
or `last_price`) and `reference_price_known_absent` when using fallback. Empty
references are accepted only when no percent-price filter needs them.

The CLI never fetches data or reads credentials. It emits derived constraints,
response hashes and fee compatibility, without raw private bodies or account ID.
Exit 2 means invalid inputs or unsupported fee currency; exit 0 means parsing and
fee compatibility only. **`runtime_ready` and `account_reconciled` remain false.**

Tests cover independent freshness, request identity, invalid/unknown inputs,
disabled price components, fee accounting, exact price-band boundaries, position
and account asset caps. All 120 input permutations preserve selection under an
order-count limit. Nautilus injection tests prove base-fee orders are blocked
before submit and a two-order cap selects only v16/v18, reserving 200.30 USDT
under the synthetic conservative fee bound.

Verification: **54 new adapter tests** and **1,887 full offline tests** passed;
12 Postgres integration tests were deselected because no dedicated DSN was
provided. Ruff, changed-file formatting and the research registry check passed.
No upstream code was touched; this change does not affect live execution.

## Remaining work

1. Decide and implement the net-of-base-fee inventory/dust contract without silent
   size changes or changes to frozen research signals. BNB accounting remains
   unsupported. Verify actual native commission events, including partial fills.
2. Build the authoritative read-only collector and native account reconciliation:
   permissions, complete open orders, balances, receipt identity and stable account
   revision across concurrent REST/stream updates. Response receipt times alone
   cannot prove one atomic account revision. Dedicated-account assumptions still
   require enforcement against actual venue state.
3. Attach the exact exchange price-reference source and any additional execution
   rules (including `executionRules` price-range behavior), plus request-rate and
   submit-time revalidation. This parser is not a complete exchange validator.
4. Complete full process recovery with durable native state and uncertain-submit
   resolution. Warm restart evidence does not prove cold recovery. Reconcile the
   offline 50 USDT daily budget with the binding runtime 5% ADR before deployment.

Official sources consulted on 2026-09-09:
[filters](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md),
[Spot REST API](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md),
[commission FAQ](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/commission_faq.md).
Only documentation was retrieved; no private API call was made.

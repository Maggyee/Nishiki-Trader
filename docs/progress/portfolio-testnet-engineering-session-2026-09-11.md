# Independent testnet scope and actual TRADE validation — 2026-09-11

The existing Ed25519 key successfully completed **POST /api/v3/order/test** with
TRADE security, HTTP 200 and zero standard/special/tax order fee rates. This is
Binance's non-matching validation endpoint: no matching order, cancellation or
fill occurred. Subsequent full-account comparison retained the same **502 asset
balances** and no account-wide open orders. The operator need not provide the
Key again or answer another general permissions questionnaire.

## Scope and code

[ADR-017](../decisions/017-testnet-engineering-session.md) explicitly separates
the engineering session from ADR-015/016 full-account portfolio admission.
The scope is one fixed **0.0001 BTC** BUY, at most **10 existing test USDT** total
debit, at most one owned-inventory cleanup SELL, one outstanding order, 180 seconds,
and cancellation requested two seconds after acknowledgement. The first scope
requires exactly zero fees. No retry, replacement, second BUY, proceeds recycling
or unrelated-asset sweep is permitted.

`portfolio_testnet_session.py` exposes that contract and a strictly bounded
non-matching validator. It does **not** implement the native durable session ledger
or an execution runner. All full-account balances remain preserved; two unquoted
faucet assets are neither omitted nor declared worthless. The independent budget
is not a qualified UTC baseline, total equity, production permission or relaxation
of ADR-015. Strict testnet continuity remains 0/14.

`portfolio_testnet_capabilities.py` provides a separate exact-path GET client and
diagnostic parser. A maximum 60-second capture brackets public and private BTCUSDT
conditions with full account and account-wide open-order reads. The source is
bound to the selected initial observation bytes, observed UID and existing key.
The public requests omit the API-key header. Captures preserve response bodies,
hashes, statuses and timing; logs/stdout exclude keys, signatures and balances.

The native venue parser initially refused the testnet response: both discount
flags true, `discountAsset=null`, discount zero, all twelve commission components
zero. An explicit `allow_testnet_zero_fee_null_discount=True` profile now accepts
that exact mathematical zero-fee case without rewriting the raw response. The
default still refuses it; any positive standard/special/tax fee with a null
discount asset fails even with the opt-in. Nonzero BNB fees retain their actual
third-asset classification and cannot enter the first zero-fee session scope.

The optional `--validate-order` client only permits POST to `/api/v3/order/test`
with the fixed BTCUSDT BUY/LIMIT/GTC parameters and computed rates requested.
It refuses matching `/order`, cancellation, MARKET, SELL, changed size, excess
notional, extra fields and production hosts. It requires a fresh stable complete
account, free funds, zero fees, effective public/private order filters and BUY
price bands. A missing dedicated price reference cannot be replaced by a ticker;
fallback average-price windows and event times are checked explicitly.

## Actual network evidence

Two explicit diagnostic runs were made, with **22 GETs and one non-matching POST**
in total. No `/sapi` request, matching order, cancellation, production endpoint,
credential/permission mutation, service or schedule was used.

The first ten-GET run returned 200 for every endpoint and exposed the zero-fee
null-discount parser incompatibility. The second run used fresh captures after
that fix. Its ten-GET collection spanned about **1.337 seconds**, followed by the
validation POST and two signed account/open-order checks.

| Observed check | Result |
|---|---|
| Selected UID/key continuity | Matched |
| Account `canTrade` | true |
| Account, commission, myFilters and public/reference endpoints | HTTP 200 |
| Native fee/filter parser with explicit zero-fee profile | Passed |
| Validation quantity | 0.0001 BTC |
| Historical diagnostic price | 77,415.25 USDT/BTC |
| Historical diagnostic notional | 7.741525 test USDT |
| POST `/api/v3/order/test`, `computeCommissionRates=true` | HTTP 200 |
| Standard, special and tax maker/taker rates for the request | All zero |
| Full asset balance comparison after validation | 502 unchanged |
| Account-wide open orders after validation | Empty |
| Matching-order / fill / cancellation / native recovery evidence | Not obtained |
| All API-key restrictions / full UTC portfolio baseline / runtime readiness | Unqualified |

The historical price is evidence only and must never be reused as a current
order. `canTrade` and TRADE validation acceptance are separate from a matching
acknowledgement or complete key-restrictions inventory. The capability `review`
describes the GET collection before the optional validation; the distinct
`validation_summary` records the subsequent accepted TRADE request.

The latest code replays the original second capture and reproduces its selected
price, including the later explicit effective quantity/notional/position checks.
No second POST was used for replay. The actual inputs and earlier diagnostic
reports remain immutable.

Private mode-0600 ignored artifacts:

| Path under `data/` | SHA256 |
|---|---|
| `spot-testnet-capabilities-20260911-session-scope.json` | `8d42ab2ddf63c07ed676a9edfbcbfa66a1d7df99cf56a677b884237c05c67605` |
| `spot-testnet-trade-validation-20260911-session-scope.json` | `cccfc81180745aaa0abaab86f0c76a4b354e9ccd466bb3cbd545e2fe53a6f2c4` |
| `spot-testnet-engineering-replay-20260911.json` | `f91b9a5d744485b35ab4e80ed9487979236d3fd21caac210f723859bb91e1670` |

The initial selection stays `spot-testnet-initial-account-20260911T014024Z.json`,
SHA256 `205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc`.
Diagnostics ran while developing from `a2bcb6a`; captures record `code_dirty=true`
and diagnostic module hashes. They are diagnostic evidence, not a clean-code
strategy session, promotion bundle or retrospective execution qualification.

## Verification and next implementation

**45 new tests** cover complete-account retention, fees, default-versus-opt-in
parsing, third-asset fees, absent/stale price references, private limits, capture
corruption, production/matching endpoint denial, fixed-size/debit bounds, changed
accounts/orders, stale captures, source mismatch and scoped validation outcomes.
Full offline regression: **2,386 passed, 12 PostgreSQL integration tests deselected**
because no dedicated integration DSN was supplied. Ruff, the family registry and
whitespace checks pass. The final parser replays the actual retained input without
another network request.

The next technical task is the **native durable session ledger and recovery harness**:
persist budget/owned inventory/IDs/prepared intents before submit; reconcile the
original order after disconnect or uncertain submit/cancel; cover partial/full/late
fills in a fresh native process; then bind an engineering fixture via SignalEvent v1
and wire the bounded matching lifecycle. Do not launch a legacy runner to bypass it.
This code still has no matching-order execution entrypoint.

Changed files: the ops capability CLI, capability/session modules, native venue
parser and new tests; ADR-017 and this report; both application READMEs, reading
list and project status. No upstream source or existing execution runner was touched.
The production/live path and strict portfolio parser default remain unchanged.

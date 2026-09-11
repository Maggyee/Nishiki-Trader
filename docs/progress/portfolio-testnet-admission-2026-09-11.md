# Testnet admission, valuation and lifecycle preparation — 2026-09-11

The operator requested advancing the agreed sequence. [ADR-016](../decisions/016-testnet-observation-admission.md)
now defines the read-only admission and prospective observation-reference rules.
The new review binds actual initial-observation bytes, observed UID/key fingerprint,
a selected signed account collection and explicitly selected market captures.
It does not infer identity from whichever source appears in a new archive.

## Step 1: Rules and review implemented

`apps.ops.portfolio_testnet_admission` checks the original initial artifact, all
archive receipts and collection identity, testnet endpoints, market body hashes,
request ordering and a maximum 60-second combined capture span within one UTC day.
Changed UID/key, invalid initial hashes, swapped captures, stale/future relative
times or market/account identity mismatches fail before producing a report.

An immutable prospective observation reference records all free/locked balances,
completion time, source-binding hash and deterministic anchor ID. It is useful
for later comparisons. It is not an independent baseline, a UTC midnight value,
an execution checkpoint or a reconstructed no-trade history. Existing strict
account collectors and readiness gates remain unchanged.

Unavailable `/sapi` key restrictions remain unknown, regardless of signed-read
success or account `canTrade`. Independent records remain unavailable; the
operator's no-other-trading confirmation is retained as context, not authentication.
Unknown faucet/reset history is not converted to "no reset".

## Step 2: Full-account valuation and baseline qualification attempted

A new bounded signed observation run from clean commit `8630df6` completed four
502-asset collections with zero business events. It used the existing local key.
After the observation stream closed, unsigned testnet exchangeInfo and all-symbol
bookTicker were captured in order. Public requests spanned about 0.643 seconds;
receipt proximity does not prove quote event freshness or account/market atomicity.

The selected exchangeInfo contains 1,363 symbols and its precisions map all
502 observed asset balances exactly in the existing isolated native process.
Of 1,363 books, 1,357 initially have positive uncrossed bid and ask sides. The
valuer correctly permits a usable bid even if the ask side is empty, or vice versa.

Final selected result:

| Check | Result |
|---|---|
| Full observed assets retained | 502 |
| Assets with indicative USDT marks | 500 |
| Nonzero assets without a supported mark | 2 |
| Assets exceeding at least one conversion leg's top-book quantity | 65 |
| Full indicative account mark | null |
| Qualified UTC day-open equity / daily loss / effective daily threshold | null / null / null |
| Testnet order readiness / runtime readiness | false / false |

Both unpriced test assets have only their shared test trading pair, whose bid and
ask are empty. A third asset has a usable bid but no ask and is correctly included
using the bid. No unsupported stablecoin peg, zero valuation for a nonzero asset,
longer conversion path, production quote or historical last price was substituted.
Free plus locked quantities are marked; each route is retained for review.

The 500-asset subtotal stays private and is explicitly not total equity or
liquidation proceeds. Shared book capacity is not reserved across assets; even a
per-asset depth pass would not prove simultaneous liquidation. Current quantities
cannot establish UTC midnight history or distinguish cash flows from trading PnL.
**Step 2's tools are complete; the actual account baseline remains unqualified.**

## Step 3: Concrete proposal prepared, execution blocked

The review generates the [machine-readable lifecycle proposal](portfolio-testnet-lifecycle-plan-2026-09-11.json).
Scope: BTCUSDT, fixed **0.0001 BTC**, maximum **10 test USDT total BUY debit**
including fees, one BUY and at most one owned-inventory cleanup SELL, one order
outstanding, at most 180 seconds. Request cancel two seconds after acknowledgement.
No automatic retry, amendment, replacement or second BUY. Unexpected fills require
native fee accounting and exact residual ownership; no unrelated balances are sold.

The captured illustrative BUY limit is **77,165.99 USDT/BTC**, giving
**7.716599 USDT** notional. It passes the captured public price/quantity/notional
filters only. This historical price is never sent to an order API and must not
be reused as a current preflight. Unknown commission currency and effective
myFilters/percent-price references still prevent a complete fee/risk check.

The quantity belongs only to this separate engineering proposal; existing research
sleeves remain 0.001 BTC and no source identity or SourcePolicy is promoted.
No execution runner is wired. Actual native adapter recovery, persisted uncertain
submission/cancel handling, fixture consumer admission and the baseline/permission
requirements must be qualified before the proposed session can start. The draft
does not claim that one cancel run would prove every full/partial-fill scenario.

## Evidence and verification

Private selected artifacts under `data/` remain ignored and mode 0600:

| Artifact | SHA256 |
|---|---|
| `spot-testnet-baseline-20260911T054139Z.jsonl` | `0b4638db102fa21f7d574d0184c6ba27ebdde9d653b6fca33dc8f6f276bd78c3` |
| `spot-testnet-baseline-20260911T054139Z-summary.json` | `16e74434adb38345e41e4043ccca40cee889b8dbf0f4606e63d5c385e533a83c` |
| `spot-testnet-baseline-20260911T054139Z-market.json` | `0b8606a2165c84b7cefb05bd7e460ab510765a3d9ef7c4a37a5b030413a4380d` |

The selected final collection is `acd69464-4f34-4741-bbfd-46fe585b2e11`.
The initial account selection remains
`205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc`.
The selected final review is `spot-testnet-admission-review-20260911T054139Z.json`;
its SHA256 is recorded in the committed lifecycle proposal. Earlier diagnostic
outputs from this task stay private and are not the selected final report.

**28 focused tests passed**: bid/inverse-ask accounting, one-sided books, zero
balances, missing stablecoin prices, two-leg/direct priority, depth limits,
invalid/duplicate data, initial source binding, capture hashes/order/time,
prospective-versus-day-open distinction, bounded fixed-size proposal and private
CLI output/no-overwrite behavior. Full offline regression: **2,341 passed**,
12 Postgres integration tests deselected because no dedicated integration DSN
was supplied. Ruff, the research family registry and whitespace checks pass.
The real pinned inputs were replayed through the final review code; output remains
`testnet_order_ready=false` and `runtime_ready=false`.

Changed files: the admission CLI, valuation and order-plan modules, their test
file, ADR-016, this report and the lifecycle JSON, the application READMEs,
`docs/agent-reading-list.md` and `docs/project-status.md`. No upstream source,
credentials, order/cancel API, strict gate, SourcePolicy, schedule, ADR-015 rule,
production account or live trading path was changed/accessed.

## Next dependency

Actual order admission is blocked on genuine account/price/history and adapter
evidence, not an additional copy of the Key. Empty-book test assets cannot be
declared worthless or omitted to manufacture a qualified full-account baseline.
Before further order work, resolve the full-account valuation scope and obtain
qualified UTC/cash-flow and permission evidence; any differently scoped test-only
risk contract must be explicit and must preserve the existing strict gate.
The 14-day qualification clock has not started.

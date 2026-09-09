# Deterministic funded admission — 2026-09-09, revision 2

Status: implemented **offline selection and preflight only**. The operator
approved replacing rejection of all five proposed buys for a small cash shortfall
with a deterministically selected affordable subset. No runtime deployment,
SourcePolicy change, capital increase, automatic resizing or promotion is implied.

This revision supersedes only the admission policy in the
[v1 contract](portfolio-execution-contract-2026-09-09.md). That document and its
JSON remain immutable historical evidence. Current machine contract:
`portfolio-execution-plan-2026-09-09-v2.json`.

## Fixed rule

1. Validate the reconciled account snapshot, effective LIMIT rules and existing
   reservations. Invalid account/rules reject the whole proposal set.
2. Require unique order IDs, signal IDs and sleeves within the proposed batch.
   Ambiguous duplicates or malformed lineage/priority metadata reject the whole
   batch rather than selecting whichever copy arrived first.
3. Sort owned SELL reductions first, then by ascending SignalEvent event time,
   then frozen sleeve order **v16, v18, v22, v34, v36**, then order ID. Unknown
   sleeves never become eligible by appearing in the input. No PnL ranking,
   price ranking, randomness, implicit rotation or input-order dependence.
4. Skip future or expired signals (at the expiry timestamp, admission rejects).
   For each remaining candidate, run the existing complete `check_batch` on
   previously selected orders plus that candidate. Keep it only if every check
   passes. Continue after a skipped candidate; do not shrink its quantity.
5. Run the complete-set check once more. Return selected proposals, per-order
   skipped reasons, signal IDs, required/available cash/base, account snapshot
   time and evaluation time. **No orders are submitted and no funds are locked.**

`select_funded_batch` is greedy by fixed priority, not a search maximizing order
count or return. Simultaneous signals favor earlier sleeves in the frozen list;
this can systematically exclude later sleeves when funding is persistently
tight. That bias is explicit and must be measured in later simulated acceptance,
not hidden by claiming that all five receive equal executed allocations.

## Cash and risk invariants

- Budget remains 500 USDT, planned daily loss 50 USDT, peak-loss amount 250 USDT.
  Sleeve size and portfolio caps remain unchanged. Fees, live risk ADRs and
  actual account equity are not inferred or modified.
- Each trial checks the **whole selected set** against the same immutable
  snapshot, so independent candidates cannot spend the same funds or fee/risk
  headroom. Pending buys, partial remainders and pending cancels still reserve.
- Selecting a sell does not settle it: its proceeds never increase funds for a
  buy in that evaluation, nor does its quantity reduce projected buy exposure.
- Daily/peak losses, projected entry fees, latched risk, position caps, quantity/
  price steps, notional checks and persisted order-ID replay rejection all remain
  active. Reductions still require fresh, reconciled owned inventory.
- Skipped candidates have no retry queue. Reconsideration requires a new caller
  decision against updated account state and revalidated, still-effective signals.
  Additional cash cannot revive an expired signal.

`AdmissionCandidate` is consumer-owned proposal/lineage metadata, not a new signal
protocol. The upstream bridge remains SignalEvent v1. Source/model authorization,
signal-to-side/expiry mapping, confidence, deduplication and superseded/out-of-order
signal handling remain the Nautilus consumer's responsibility; supplying a
`signal_id` alone does not prove those checks. This selector is not an allowlist.

## Acceptance and reproduction

At the **synthetic** price 100,000 USDT/BTC and quote fee bound 15 bps:

- Original five-buy `check_batch`: still rejects 500.75 USDT against 500.
- New selection: four unchanged 0.001 BTC orders, 400.60 USDT required, 99.40
  USDT uncommitted headroom; fifth explicitly skipped for insufficient quote.
- All 120 input permutations produce identical selection and audit results.
- Tests cover pending cancel occupation, expired/future signals, invalid snapshots,
  ambiguous input, earlier-event priority, reductions without pre-crediting sales,
  known fee/risk accumulation, caps, replay rejection and skipped-order expiry.

```bash
.venv/bin/python -m apps.ops.portfolio_execution_plan --revision 2
.venv/bin/python -m apps.ops.portfolio_execution_plan --revision 1
.venv/bin/pytest -q tests/ops/test_portfolio_execution_plan.py tests/strategies_nautilus/test_portfolio_preflight.py
```

Default CLI output is v2. Both revisions revalidate the original six evidence
chains; absent retained bundles fail closed. Unit tests compare both committed
JSON contracts exactly and verify that existing cohort/budget fields are unchanged.

Verification: 87 focused tests passed (24 added this revision), and the full
offline suite passed **1,798 tests**. Twelve Postgres integration tests were
deselected because no dedicated integration DSN was supplied. Ruff and the
research family registry check passed; retained evidence revalidation succeeded.

## Remaining boundary

The selector does not solve check-to-submit concurrency. The future Nautilus
integration must revalidate signals and the entire selected set, atomically
reserve before submit, persist ID/risk state, and reconcile fills/cancel/restart
events. Snapshot timestamps in the result are audit context, not revision locks
or permission to submit cached output later. No runner imports the selector yet.

This revision changes which fills a portfolio would receive. The earlier basket
PnL is **not performance evidence for v2**. Nautilus simulated lifecycle testing
and separately authorized portfolio evaluation remain necessary. No retained
research results, collector schedules or sealed future PnL were modified/opened.

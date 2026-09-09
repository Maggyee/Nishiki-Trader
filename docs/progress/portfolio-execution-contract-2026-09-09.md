# Portfolio execution engineering contract — 2026-09-09

Status: **offline proposal and acceptance foundation**, not approved for paper
orders, testnet, live, or changes to existing SourcePolicy. The operator asked
to explore and advance cohort selection, a fixed execution plan, and order-level
capital/risk verification. This authorizes this engineering work, not promotion.

## 1. Fixed evidence cohort and engineering scope

`apps.ops.portfolio_execution_plan` verifies the SHA256-pinned September 8
portfolio report and revalidates its original manifests, fills, identities,
2023–2025 window, clean provenance and accounting reconciliation through the
existing evidence loader. It prints a reproducible contract; exit 0 means only
that the evidence lock is valid. Missing/changed evidence returns 2, never a
smaller basket or replacement candidate. The committed JSON is its output.

| Classification | Protocols | Meaning |
| --- | --- | --- |
| Verified retained evidence | v16, v18, v22, v34, v36, v40 | Eligible for this engineering study, not proven alpha |
| Proposed offline sleeves | v16, v18, v22, v34, v36 | One fixed 0.001 BTC maximum per sleeve |
| Duplicate observation only | v40 | Same retained execution path as v18; earliest protocol represents the pair |
| Excluded from this plan | v8, v42, v46, v48 | Missing original hash chains; v42 also has dirty manifests |

Selection uses provenance and exact duplicate paths, not return ranking or
optimized weights. In particular v22 remains in this engineering fixture despite
its negative benchmark-relative diagnostic; this does not endorse it for trading.
Historical v18/v40 equality does not prove future equivalence. V40 remains
observed, is not a fallback, and cannot silently replace v18 if their signals
diverge. Legacy ten-candidate collectors, holds and portfolio reviews stay intact.

This is **not a new alpha protocol or an out-of-sample confirmation**: historical
results were already known. No frozen identity is re-gated, retuned or ensembled
into a new SignalEvent source. Portfolio-level alpha review under ADR-014 is
still required before any simulated-order promotion. No sealed 2026–2027 PnL,
new research prices or collectors are opened by this work.

## 2. Fixed proposed execution semantics

- Instrument BTCUSDT.BINANCE, spot long/flat, no borrowing/leverage or compounding.
- Five separately attributed sleeves, 0.001 BTC each, aggregate ceiling 0.005 BTC.
  A flat signal reduces only its sleeve; no cross-sleeve inventory transfer or
  internal netting. Same-sleeve outstanding order blocks replacement until its
  terminal acknowledgement and account reconciliation.
- Planning cash 500 USDT; requested daily loss 50 USDT; drawdown amount 250 USDT.
  For this offline contract, daily loss means current UTC day-open marked equity
  minus current equity, and drawdown means running peak equity minus current
  equity, with a **fixed 250 USDT limit**, not 50% of a rising peak. No deposits,
  withdrawals or unrelated account assets are supported by these fixtures.
- Inclusive thresholds block entries and require a latched risk state. No
  automatic midnight/restart reset is authorized. Reconciled owned reductions
  remain possible; cash sufficiency does not override risk rejection.
- Admission is an all-or-nothing batch. No automatic quantity rounding, resizing,
  priority selection, same-batch sell credit or assumed immediate fills.
- Bounded LIMIT checks only in the new offline preflight. This does **not** change
  the existing baseline's MARKET execution. Actual order-style integration,
  timeout/cancel handling and changed fill behavior need separate acceptance.
- Fees in this checker must be bounded in quote currency (USDT); base/BNB fees
  are unsupported and rejected. Current exchange/account fee schedules are not
  inferred from the historical 12/15 bps combined fee/slippage diagnostic.

The 50 USDT planning daily budget is preserved exactly. It is not substituted
with 5%, and it is not deployed: it conflicts with the existing ADR runtime rule.
An explicit policy reconciliation is required before wiring new runtime behavior.

## 3. Implemented snapshot preflight

`apps.strategies_nautilus.portfolio_preflight.check_batch` is a pure checker, not
an execution engine, order ledger, simulator or authorization artifact. It creates
no orders/fills and is not imported by current trading runners.

- Finite Decimal arithmetic; invalid quantities/prices/rules fail closed.
- Complete sleeve attribution must equal settled account BTC; free balances
  cannot exceed settled totals. Unknown order states/IDs or reconciliation drift
  block the batch. Persisted used IDs reject duplicate submissions after restart.
- Pending-cancel orders continue reserving funds; partial fills reserve only the
  remaining quantity. Terminal rows release reservation only with zero remainder.
- Buy reservation is remaining quantity × limit price × (1 + quote fee bound).
  Spendable quote is the smaller of reported venue-free quote and settled total
  minus all known buy reservations. Sell orders reserve their sleeve's owned BTC.
  Unfilled sell proceeds cannot finance buys, even within the same batch.
- Existing and proposed buy quantities count toward sleeve and portfolio caps;
  pending sells cannot reduce projected long exposure until actually settled.
- Current daily/peak losses and the conservative additional entry-cost bound
  (including pending buys) block entries at inclusive limits. The cost bound does
  not predict price gaps, guarantee maximum loss or replace a live kill switch.
- Snapshot, mark, risk baselines and effective rules must share a reconciled
  account revision; timestamps must be no more than 60 seconds old, never future.
  UTC day-open equity must be for the current UTC date.

The effective LIMIT quantity/price step and notional checks follow the categories
in [Binance's official filter documentation](https://developers.binance.com/en/docs/products/spot/filters),
consulted September 9. The tests use **synthetic values**, not current BTCUSDT
exchangeInfo. This is deliberately not a complete exchange filter validator:
dynamic price bands, order-count limits, disabled filter normalization and venue
trading status still require an adapter and tests; unbounded MARKET is rejected.

## 4. Integration obligations — not yet implemented

1. Feed validated SignalEvent v1 identities through a reviewed Nautilus strategy;
   map each sleeve to Nautilus-owned inventory and order tags. Research must never
   supply order quantities. The offline plan is not a SourcePolicy allowlist.
2. Obtain one atomic Nautilus/account-cache revision containing total/free assets,
   all pending orders (including submit/cancel in flight), current marks, daily
   baseline and peak. The account must be dedicated to these BTC/USDT sleeves,
   with no unaccounted locks, other instruments, transfers or external orders.
   `reconciled=True` is a caller assertion today, not an implemented reconciler.
3. Serialize admission plus reservation within the Nautilus event loop and
   invalidate snapshots after updates. Independent calls against the same snapshot
   do not reserve anything. Re-read cash after actual fills/cancel acknowledgements.
4. Persist order-ID deduplication and risk latch, restore them across restarts,
   reconcile partial/late/out-of-order fills, and test unknown-order shutdown.
5. Attach fresh authoritative instrument/account rules and fees; implement the
   remaining venue constraints. Exercise all this with Nautilus simulated
   execution and synthetic SignalEvent inputs first, not credentials or live data.
6. Review portfolio-level strategy evidence and reconcile risk policy before any
   wall-clock paper promotion. Testnet and live gates remain unchanged.

## 5. Reproduction and acceptance

```bash
.venv/bin/python -m apps.ops.portfolio_execution_plan
.venv/bin/pytest -q tests/ops/test_portfolio_execution_plan.py tests/strategies_nautilus/test_portfolio_preflight.py
```

The evidence command needs ignored retained bundles in this checkout. On a
checkout without them it must fail closed; unit tests use the committed anchor
and synthetic snapshots and do not require those bundles or network access.

Synthetic capital boundary: at 100,000 USDT/BTC with a 15 bps quote fee bound,
five 0.001 BTC buys require **500.75 USDT**. Each fits a 500 USDT account alone;
the complete batch correctly fails. This is a scenario, not a current market
quote, a revised capital recommendation or a claim about historical performance.

Verification: **1,774 offline tests passed**, including 63 new cohort/preflight
tests; 12 Postgres tests deselected because no dedicated integration DSN was
supplied. The evidence CLI revalidated all six original bundles in this checkout.
Remaining work is summarized in `docs/project-status.md`.
Neither upstream checkout, SourcePolicy, collector deployment, runtime risk
settings nor any live trading path changes in this increment.

# Retained-fill portfolio evidence study — 2026-09-08

Operator-authorized strategy repair follow-up; evaluation only, not a tradable
identity, parameter search, promotion, or new execution engine.

## Fixed method before evaluation

- Window: already-opened confirmation 2023-01-01 through 2025-12-31 UTC only.
  No 2026 prices, future-blind PnL, model training, or strategy changes.
- Requested cohort: the ten current shadow identities from their frozen contracts.
- Accept a bundle only if its manifest and fills hashes match the committed
  confirmation result, its identity/window/clean-git metadata match, fills are
  finite positive fixed 0.001 BTC trades, and it ends flat without ever shorting.
  Missing cryptographic evidence excludes the candidate explicitly; do not select
  another convenient run or extrapolate a partial cohort to all ten.
- Lineage compatibility: the existing `BaselineNautilusStrategy.on_stop` writes
  an untagged terminal close. Only a final SELL at the exact 2025-12-31 23:00 UTC
  bundle end may have an empty signal ID, and it must flatten a prior correctly
  attributed long position. Report that exception count; reject other blank IDs.
- Prices: retained BTC daily closes referenced and SHA256-pinned by the existing
  v49 provider qualification. Reusing market prices does not reopen the v49 model.
  Require an exact daily grid, including 2022-12-31 for the initial mark.
- Accounting only: signed cash flows and cumulative BTC quantities from the
  already-executed Nautilus fills, marked at daily closes. No synthetic fills,
  new orders, execution simulator, or modified backtest bundles.
- Report gross and 12/15 bps per-fill fee-plus-slippage scenarios. Costs replace,
  not supplement, recorded commissions. Reconcile final base/stress PnL to the
  committed results before including a candidate.
- Report daily-marked absolute-USDT drawdown, elapsed-time holding fraction,
  pairwise daily-PnL correlation, holdings overlap, and leave-one-out contribution.
  Drawdown is daily sampled, not an intraday maximum. Net leverage, percentage
  return and risk-adjusted account ratios remain unavailable without verified
  account capital/equity; do not invent an account size.
- Compare each sleeve with 0.001 BTC buy-and-hold on the same window and the
  elapsed-time-exposure-scaled benchmark, with both entry/exit cost scenarios.
  Exposure matching is a diagnostic, not a significance test or risk matching.
- Identify exact duplicate fill paths by timestamp/side/quantity/price. Show the
  raw arithmetic basket and an illustrative duplicate-normalized basket (each
  exact-path cluster totals one 0.001 BTC sleeve). This is linear diagnostic
  attribution only, not a proposed SourcePolicy or authorized allocation.
- No thresholds are selected from results, no gates are retroactively changed,
  and no survivor is promoted or demoted. Historical research remains immutable.

Entrypoint: `apps.ops.research_portfolio_evidence`; append-only versioned reports.

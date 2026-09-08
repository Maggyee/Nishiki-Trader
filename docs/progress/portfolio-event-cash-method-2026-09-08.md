# Retained execution-event cash bounds — 2026-09-08

This extends the current 500 USDT planning review from daily sampled cash to
recorded execution-event cash. It is ledger accounting only, not a simulator,
new backtest, allocation decision or permission to trade.

- Use only the same hash-verified primary Nautilus confirmation fills accepted
  by `research_portfolio_evidence`, on 2023–2025. Recheck their hashes and lineage.
  The four excluded candidates stay excluded. No 2026 returns are opened.
- Preserve original 0.001 BTC sleeves, both existing diagnostic weight sets and
  gross/12/15 bps per-fill costs. Keep 500 USDT / 50% / 50 USDT as planning inputs.
- Cash outflow for a recorded buy is weighted quantity × price × (1 + cost);
  inflow for a recorded sell is weighted quantity × price × (1 - cost). Costs
  replace original commissions. Retain profits/losses as cash; no withdrawals,
  collateral, lending, account transfers or added orders are inferred.
- Aggregate at exact recorded UTC nanosecond timestamps. Separate backtests
  do not establish cross-strategy order at equal timestamps. Report both a
  sell-before-buy lower cash requirement and a buy-before-sell upper cash
  requirement for those ties; do not invent a preferred ordering.
- Initial cash required is the nonnegative magnitude of the lowest cumulative
  cash balance, including the initial zero balance. Check both bounds against
  planned capital. Their final cash must reconcile to the existing basket PnL;
  event cash needs cannot be less than the corresponding daily sampled needs.
- These bounds apply only to settlement of the retained fills. Open-order
  reservations, rejected orders, exchange quantity/minimum-notional constraints,
  transfer delays and balances across separate actual accounts are not modeled.
  Unfilled orders can reserve additional cash. Intraday market-value drawdown
  remains unverified without an eligible intraday price/equity path.
- Append a schema-v3 follow-up report with event cash bounds and refreshed
  prospective integrity checks. Preserve all older reports and frozen results.
  No new collector job, promotion, parameter tuning or risk-setting change.

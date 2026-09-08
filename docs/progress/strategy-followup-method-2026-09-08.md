# Ordered strategy follow-up method — 2026-09-08

Scope: operator-requested evidence recovery, prospective pipeline acceptance,
then portfolio risk diagnostics. This is not a new strategy or permission review.

1. Inventory only retained v8/v42/v46/v48 confirmation bundles. Record current
   manifest/fills hashes as **observed now**, never original proof. Inspect the
   original result's Git history and search reachable historical code/docs for
   those hashes or run IDs at the fixed pre-follow-up tip
   `f5963cdef902908e00a601a1eb8fef345e545b87`. A text hit is a review lead, not
   automatic provenance approval. Missing evidence and dirty manifests block
   inclusion. Do not overwrite or rerun frozen confirmation results.
2. Read current collector journals/status/SQLite, verify repaired v22/v34/v36
   snapshot and BTC hashes, authoritative identity, closed timestamps, distinct
   prospective counts and preserved anomalies. Verify the existing cron against
   its deployment receipt. No manual duplicate collection earns elapsed time;
   no new schedule is added. Report point-in-time acceptance separately from
   the still-incomplete 7-day OR 50-signal gate, which is not alpha evidence.
3. Use only candidates accepted by the existing retained-fill evaluator, on its
   unchanged 2023–2025 window and gross/12/15 bps accounting. Keep the raw basket
   and already-defined duplicate-normalized diagnostic; do not select weights.
   Daily marked inventory notional is aggregate BTC quantity times daily close.
   Cash funding required is inventory notional minus cumulative marked PnL;
   compare its nonnegative maximum to planned capital. This is a daily sampled
   lower bound on cash needs, not an intraday or executable sizing guarantee.
   Report daily PnL increments, worst sampled loss and drawdown, plus breaches of
   the fixed diagnostic loss amount. Do not simulate a kill switch or new fills.
   Compare absolute drawdown with 50% of planned initial capital (50 USDT),
   explicitly not with a verified account's running-peak equity denominator.

Operator inputs received this turn: planned capital **100 USDT**, requested
maximum drawdown **50%**, requested daily loss **50 USDT**. These are preferences,
not verified account balances or approved trading limits. The daily request is
50% of initial capital and conflicts with ADR-001's binding 5% daily auto-stop.
For diagnostic comparison only, the existing rule gives **5 USDT on the planned
initial 100 USDT**. Actual runtime drawdown uses its own verified equity baseline;
this fixed historical comparison is not a runtime risk-engine test. A 50% total
drawdown preference does not override phase gates or capital-ladder constraints.
Record the conflict; do not alter any risk setting or imply the 50 USDT daily
request is accepted. No actual account return/leverage can be inferred.

Outputs are append-only. Four missing histories, insufficient elapsed forward
time, account verification and the incompatible daily budget remain explicit
blockers until genuinely resolved. Existing automatic collectors continue.

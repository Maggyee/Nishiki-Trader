# Ordered strategy repairs — 2026-09-08

Operator authorization: fix the strategy-review findings in order. No new
strategy, parameter search, allocation decision, or trading permission is implied.

## 1. Signal correctness — repaired and deployed

V22/v34/v36 supplied a 2026 generator start but inherited a 2022 default end,
silently producing empty signals despite successful collection. All three now
pass an explicit observation-date end. Their generators reject reversed ranges.
The portfolio monitor obtains source/model identities from frozen contracts,
correcting v36 to `rule_cboe_vpn_expansion_v1` /
`cboe-vpn-diff5-positive-lag1d-v1` without changing that research identity.

For these three pipelines, successful corrected runs establish a v2 epoch.
Earlier attempts remain immutable and do not count as qualified generation days;
historical backfill does not count as new prospective signals. Historical anomaly
blockers are retained. A valid constant factor can still produce zero events.

Code commit `1727408c3b2e960e5b2d544117ee820fcf0375fe` was pushed and deployed
to the existing ten collector jobs, with the same cadences and data roots.
The installer retained the previous crontab. Active deployment is recorded in
`data/collector-deployments/active.json`; no new jobs were authorized or added.

Real smoke results around 01:28 UTC (counts are a point-in-time observation):

| Pipeline | Generated signals | Corrected qualified dates | New forward signals | Retained legacy attempts |
| --- | ---: | ---: | ---: | ---: |
| v22 | 37 | 1 | 0 | 14 |
| v34 | 36 | 1 | 0 | 20 |
| v36 | 45 | 1 | 0 | 20 |

All three latest attempts had no new blockers and their identities matched their
contracts. This does not clear old anomalies or satisfy a promotion gate.

## 2. Portfolio accounting — implemented, cohort remains partial

The fixed [method](portfolio-evidence-study-2026-09-08.md) was committed before
numerical evaluation. It only reads existing Nautilus fills from the already-
opened 2023–2025 confirmation window. A documented terminal-close exception
accommodates the existing baseline's untagged final flattening order; no other
missing signal lineage is accepted. No new fills or backtests are generated.

The [report](portfolio-evidence-review-2026-09-08.md) and matching JSON contain
hash verification, daily-marked cash accounting, PnL correlation, daily holdings
overlap, exact duplicate groups and leave-one-out contributions. Six candidates
reconcile to their original base/stress PnL. V18/v40 have identical execution
paths and are therefore not independent exposure. Duplicate normalization is
illustrative accounting, not a deployed weight change.

V8/v42/v46/v48 lack original confirmation references containing both manifest
and fills hashes. They are explicitly excluded, not assigned zero returns or
reclassified as rejected. A fresh local hash alone cannot restore historical
provenance. The CLI returns 2 for this honest partial-cohort result.

## 3. Fair benchmarks and costs — implemented for verified candidates

Retained BTC closes match the pre-existing v49 qualification hash; reusing these
prices does not reopen the v49 model. All comparisons use the same window and
0.001 BTC original sleeves, with gross and 12/15 bps per-fill base/stress costs.
Exposure matching scales buy-and-hold by elapsed time in market, including
proportional entry/exit costs; it does not match volatility or prove significance.

V22's base excess is -10.41 USDT; v16's is only +0.43 USDT. These selected-sample
diagnostics warrant caution, not automatic retuning or promotion. Without verified
account equity, actual leverage and percentage account returns remain null.
Daily sampled drawdowns are not claimed to measure intraday maximum loss.

## Verification and boundaries

- Ten signal-pipeline regression tests cover full collection/generation/storage,
  date bounds, future suffix invariance, deduplication, legitimate flat factors,
  prospective counting and all ten authoritative identities.
- Twenty portfolio tests cover accounting, costs, exposure, drawdown, invalid
  fills, hash tampering, complete historical benchmark coverage, terminal lineage,
  bundle reconciliation, duplicate normalization and immutable output paths.
- Ruff and the unchanged 154-identity family registry check passed.
- Full offline suite: 1,679 passed, 12 Postgres integration tests deselected
  (no dedicated integration DSN supplied).
- Corrected collectors and the read-only portfolio monitor were smoke-tested;
  the dashboard snapshot was refreshed with all write/trading capabilities false.
- Upstream source was not touched. Nautilus remains the sole execution engine;
  SignalEvent v1 remains the bridge. No LLM enters the order path.
- No live/testnet permission, SourcePolicy, frozen parameter, or scheduler cadence
  changed. The 2026-09..2027-01 future blind remains sealed for PnL.
- `docs/project-status.md`, the reading list and shared collector README were updated.

## Changed file groups

- Collectors: `apps/ops/research_v{22,34,36}_shadow_daily.py`,
  `research_shadow_runtime.py`, `research_portfolio_monitor.py`.
- Generator guards: `apps/strategies_freqtrade/research/{option_surface,treasury_yield,option_strategy}_signals.py`.
- Diagnostics: `apps/ops/research_portfolio_evidence.py`.
- Tests: `tests/ops/test_shadow_signal_pipeline.py`,
  `test_research_v{22,34,36}_shadow_daily.py`, `test_research_portfolio_evidence.py`.
- Documentation: project status, agent reading list, shared collector README,
  this acceptance record, fixed study method and versioned JSON/Markdown report.

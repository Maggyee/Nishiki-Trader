# Ordered strategy follow-up audit — 2026-09-08

Status: available checks completed; evidence recovery, elapsed forward acceptance
and executable portfolio approval remain incomplete. Machine evidence is in the
matching JSON; the [fixed method](strategy-followup-method-2026-09-08.md) defines
the scope. No strategy, risk setting, schedule or permission was changed.

## 1. Original evidence recovery

Eight local confirmation manifests were inventoried, two per candidate. Their
current hashes were searched with their run IDs across historical code/docs at
`f5963cdef902908e00a601a1eb8fef345e545b87`. No reference leads were found.
The four original confirmation-result files each have one recorded revision:

| Candidate | Original result commit | Local clean-git metadata | Disposition |
| --- | --- | --- | --- |
| v8 | `19207fb` | both clean | original manifest/fills hash references missing |
| v42 | `0501aac` | **both dirty** | missing original hashes AND dirty-code evidence |
| v46 | `f19d19a` | both clean | original manifest/fills hash references missing |
| v48 | `bd03715` | both clean | original manifest/fills hash references missing |

The retained v8 `review.json` records run paths but no corresponding manifest/
fills hashes; its committed paper-entry hash describes a different dry-run bundle,
not these confirmation fills. The v42/v46/v48 confirmation readers persisted
metrics without bundle hash references. V42's local manifests explicitly carry
`git_dirty=true` at `33fb2aa7b3859afff5e07c652b630d5ee2887b1f`.
The v42 review aggregates performance without propagating the analyzed bundle's
evidence blockers into its pass condition. This is a historical evidence defect,
not permission to rewrite its old verdict or rerun its frozen research.

Current hashes are recorded only as **observed-now inventory**, not restored
historical proof. Identical local replay bytes do not supply an external historic
anchor. All four remain excluded from the verified portfolio. A backup/original
audit reference may change this conclusion; this search cannot establish that
no evidence exists outside the current checkout and reachable history.

## 2. Repaired forward pipeline acceptance

The pinned checkout remains clean at `1727408`; all ten existing cron entries
match the deployment receipt and rendering, with unchanged cadences. No manual
repeat collection was run to inflate prospective evidence.

| Pipeline | Stored signals | Corrected qualified dates | New forward signals | Snapshot/BTC/identity/count checks |
| --- | ---: | ---: | ---: | --- |
| v22 | 37 | 1 | 0 | passed |
| v34 | 36 | 1 | 0 | passed |
| v36 | 45 | 1 | 0 | passed |

For each repaired pipeline the read-only audit reconciled status to immutable
journals, validated original factor and BTC hashes, checked stored SignalEvent
identity and timestamps, and checked prospective IDs against the repair epoch.
Historical `btc_hourly_gap` / `git_dirty` anomalies remain visible. No candidate
currently has unblocked review eligibility. Detailed counts for all ten appear
in the JSON; stored/backfilled totals are not newly observed signal totals.

The 7-distinct-day OR 50-new-signal threshold is not yet met by these three.
Existing cron jobs must accumulate genuine future observations; a point-in-time
check cannot complete elapsed time. Threshold completion alone is neither
performance evidence nor permission for promotion.

## 3. Planned 100 USDT risk diagnostics

Operator inputs: 100 USDT planned capital, 50% maximum drawdown preference,
50 USDT requested daily loss. This is not a verified account-equity attachment.
The daily request is 50% of initial capital and conflicts with ADR-001's binding
5% daily stop. The diagnostic comparison therefore uses 5 USDT on initial planned
capital, without changing runtime settings. Operator confirmation is still needed
on the incompatible request. The 50% total drawdown preference is represented as
a static 50 USDT loss budget, not a running-peak account drawdown calculation.

Only six already-verified 2023–2025 sleeves are included. Each original sleeve
trades 0.001 BTC; duplicate normalization is the previously fixed illustration,
not proposed executable sizing. Base costs are 12 bps per fill.

| Daily-sampled diagnostic | Raw six-sleeve basket | Duplicate-normalized basket |
| --- | ---: | ---: |
| Minimum starting cash required at sampled marks (USDT) | 387.14 | 308.85 |
| Maximum marked inventory notional (USDT) | 733.39 | 611.16 |
| Maximum marked drawdown (USDT) | 98.78 | 80.21 |
| Worst sampled daily loss (USDT) | 27.13 | 22.61 |
| Days with sampled loss at least 5 USDT | 119 | 92 |

Neither fixed-size diagnostic can be funded with 100 USDT at even the daily
sampled checks, and both exceed the static 50 USDT drawdown budget. **These are
not realized losses or account returns on a 100 USDT account**: the historical
paths are not cash-feasible at that capital. No leverage is proposed to bridge
the shortfall. Daily samples are lower bounds on intraday funding/loss demands;
they do not test actual exchange minimums, quantity steps or stop execution.
Gross/base/stress details are recorded in JSON, not used to choose new weights.

## Verification, changed files and remaining handoff

- Added `apps/ops/research_strategy_followup.py` and 17 tests in
  `tests/ops/test_research_strategy_followup.py`; reused existing evidence,
  snapshot, collector-summary and deployment helpers without modifying them.
- Tests cover current-hash vs original-proof distinction, dirty-code blockers,
  repeated-day counting, future/backfilled/duplicate/missing events, budget
  validation, fee-inclusive cash needs and rejection of a daily-rule override.
- Ruff and registry check passed. The real read-only audit completed with CLI
  status 2, intentionally reporting incomplete evidence/time/budget requirements.
- Full offline suite: **1,696 passed**, 12 Postgres tests deselected (no dedicated
  integration DSN supplied). The JSON reproduced exactly apart from its timestamp.
- Added this JSON/Markdown evidence and method; updated project status and reading
  list. No upstream source touched, live path impact, schedules changed, frozen
  strategy reopened, or future-blind PnL evaluated.
- Next: obtain original audit/backup proof (plus eligible clean evidence for v42),
  let existing schedules accumulate real dates, confirm the daily-limit conflict,
  and provide verified equity if actual account-level assessment is required.
  Smaller executable sizing needs a separate reviewed specification; these
  results do not authorize allocation or deployment changes.

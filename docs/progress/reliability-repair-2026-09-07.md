# Reliability repair acceptance — 2026-09-07

The operator authorized fixes in priority order. The changes are operational
reliability repairs, not a new research identity, promotion, or trading campaign.

## Delivered

1. Postgres tests require an explicitly named test database and isolated temporary
   schemas. No default business database connection or shared-table TRUNCATE.
   The offline suite refuses unmarked external socket connections.
2. Portfolio monitoring opens SQLite read-only and fails closed on missing,
   corrupted, stale or inconsistent inputs. Runtime status is authoritative;
   committed legacy statuses remain historical evidence.
3. Ten existing collector schedules are pinned to a clean pushed code checkout.
   No cadence or additional jobs were introduced. BTC captures are reconstructed
   from hash-verified retained raw bodies without requalifying failed dates.
4. V40/v42/v46/v48 now count distinct qualified observation dates, not invocations.
   Immutable snapshots/factors, locks, revision checks and atomic statuses are
   shared. The legacy run counters are not imported as qualified evidence.
5. Binance forward data uses verified cached month archives and closed day archives.
   The June 2026 monthly archive omitted one day; its exact official daily archive
   recovered the gap. Cboe gap validation is limited to the 90-day factor window;
   an October 2012 closure no longer blocks current observations.
6. Removed inferred leverage, zero-filled missing signal days and undefined
   correlations reported as zero. Sparse direction correlations now disclose
   paired-day counts and are explicitly not holding or return correlations.
7. Dashboard consumes the saved ten-candidate runtime report with freshness,
   roster, identity, boundary and shape checks. Bad inputs contribute to top-level
   attention; browser paths remain read-only.
8. Meta-analysis v2 appends current registry context: 154 identities, 116 PnL
   opened, ten legacy survivors. The historical 108-identity null is separate
   from v49+ Gates-v2 models. Original v1 numbers and report bytes are preserved.
9. Frontend transitive dependencies were updated within existing version ranges;
   npm audit changed from three findings to zero. No framework-major migration.

## Deployed state and smoke evidence

Pinned runtime commit: `fd56d7a9b6cda9d368c633d07588a4e91e025cb5`.
Deployment and original cron backups are recorded in the gitignored
`data/collector-deployments/active.json`. All ten scheduled commands were
verified after installation; unrelated cron entries and schedules are preserved.

| Protocol | Qualified UTC dates | Latest source observation | Latest attempt |
| --- | ---: | --- | --- |
| v8 | 8 | 2026-09-04 | passed |
| v16 | 4 | 2026-09-04 | passed |
| v18 | 3 | 2026-09-04 | passed |
| v22 | 2 | 2026-09-04 | passed |
| v34 | 5 | 2026-09-04 | passed |
| v36 | 5 | 2026-09-04 | passed |
| v40 | 1 | 2026-09-04 | passed |
| v42 | 1 | 2026-09-04 | passed |
| v46 | 1 | 2026-09-06 | passed |
| v48 | 1 | 2026-09-06 | passed |

All latest blocker lists were empty. Historical anomaly lists remain intact
and all ten candidates still report review_eligible=false. Repeated same-day
strict runs did not increase distinct-day counts. Historical failed dates were
not retroactively credited.

The local portfolio status/report and frontend snapshot were refreshed under
`data/research-portfolio/` and `data/frontend/`. These are generated local
artifacts, not tracked research results. The temporary HTTP verification server
was stopped after both language checks.

## Verification

- Python offline full regression: **1,649 passed**, 12 Postgres tests deselected.
- Postgres tests were not run against a real service: no dedicated test DSN supplied.
- Ruff and research-family registry checks passed.
- Frontend typecheck and production build passed.
- npm audit --audit-level=moderate: **zero vulnerabilities**.
- Local production HTTP: English and Simplified Chinese both returned 200 and
  contained the portfolio panel and candidate rows.
- All ten real collector smoke invocations exited 0 from the pinned checkout.
- git diff --check passed. No upstream source changes.

## Remaining constraints, not silently marked complete

- Online GitHub CI is not enabled: the credential lacks workflow scope. The
  workflow template and installation instructions are in `infra/ci/`.
- Full portfolio net-return/drawdown/actual-leverage and matched-exposure benchmark
  analysis need verified Nautilus fills and account equity attached for already
  opened historical windows. The monitor reports these as unavailable.
- The historical benchmark CSV is absent locally. Meta-analysis v2 is an explicit
  registry-context-only refresh, not a numerical rerun; v1 did not record full
  cohort membership, so its identity list cannot be independently reverified here.
- Historical anomalies require human review; no automatic clearing or promotion.
- Testnet continuity remains 0/14; live and testnet remain blocked. Future-blind
  PnL remains sealed. LLMs never enter the order path.

## Changed files

The implementation commits are `c802b05`, `f8c997a`, and `fd56d7a`.
The following tracked files changed from pre-repair `355eb52`; this acceptance
record is added by the final documentation commit.

- `apps/frontend/README.md`
- `apps/frontend/app/dashboardData.ts`
- `apps/frontend/app/page.tsx`
- `apps/frontend/package-lock.json`
- `apps/ops/dashboard_snapshot.py`
- `apps/ops/install_shadow_collectors.py`
- `apps/ops/research_forward_archives.py`
- `apps/ops/research_meta_analysis.py`
- `apps/ops/research_portfolio_monitor.py`
- `apps/ops/research_portfolio_snapshot.py`
- `apps/ops/research_shadow_daily.py`
- `apps/ops/research_shadow_runtime.py`
- `apps/ops/research_v16_shadow_daily.py`
- `apps/ops/research_v18_shadow_daily.py`
- `apps/ops/research_v22_shadow_daily.py`
- `apps/ops/research_v34_shadow_daily.py`
- `apps/ops/research_v36_shadow_daily.py`
- `apps/ops/research_v40_shadow_daily.py`
- `apps/ops/research_v42_shadow_daily.py`
- `apps/ops/research_v46_shadow_daily.py`
- `apps/ops/research_v48_shadow_daily.py`
- `apps/ops/research_v8_shadow_daily.py`
- `docs/agent-reading-list.md`
- `docs/progress/phase-2-research-v22-paper-shadow-status.json`
- `docs/progress/phase-2-research-v40-paper-shadow-status.json`
- `docs/progress/phase-2-research-v42-paper-shadow-status.json`
- `docs/progress/phase-2-research-v46-paper-shadow-status.json`
- `docs/progress/phase-2-research-v48-paper-shadow-status.json`
- `docs/progress/project-status-archive-2026-09-07.md`
- `docs/progress/research-program-meta-analysis-v2.json`
- `docs/progress/research-program-meta-analysis-v2.md`
- `docs/project-status.md`
- `infra/ci/README.md`
- `infra/ci/checks.yml`
- `infra/research-shadow/README.md`
- `pyproject.toml`
- `tests/README.md`
- `tests/bridge/test_postgres_store.py`
- `tests/conftest.py`
- `tests/ops/test_research_forward_archives.py`
- `tests/ops/test_research_meta_analysis.py`
- `tests/ops/test_research_portfolio_monitor.py`
- `tests/ops/test_research_portfolio_snapshot.py`
- `tests/ops/test_research_shadow_runtime.py`
- `tests/ops/test_research_v40_shadow_daily.py`
- `tests/ops/test_research_v42_shadow_daily.py`
- `tests/ops/test_sync_signals_to_postgres.py`

`docs/project-status.md` was updated with current progress, blockers, verification
and next steps. Its previous long historical content is preserved in the linked
archive. The five pre-existing collector status-file modifications were retained
as final historical snapshots, not overwritten or presented as current runtime.

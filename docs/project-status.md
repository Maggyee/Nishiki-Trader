# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-08
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Repair strategy signal correctness, then evaluate retained portfolio evidence.
- **Source of truth**: Runtime status under `data/`; immutable research evidence and ADRs under `docs/`.

## Current Focus

The operator authorized the ordered 2026-09-08 strategy-review repairs.
V22/v34/v36 had passed collection smoke checks while their generators silently
used a 2022 end-date with a 2026 start-date, producing no signals. Explicit
forward date ranges and reversed-range rejection now fix this defect.
End-to-end tests cover nonempty transitions, legitimate flat periods, future
suffix invariance, duplicate runs, and backfill-vs-prospective counts.

The monitor now derives all ten identities from frozen shadow contracts,
including the corrected v36 VPN expansion identity. For the three repaired
pipelines, prior empty-generation attempts remain immutable history; a separate
v2 epoch counts only corrected attempts and excludes backfilled signals.

Next is a fixed-method retained-fill study over already-opened 2023–2025 data.
No parameters, frozen research identities, source policies or trading permissions
are changed. The study does not select allocations or grant promotions.

## Milestones

- SignalEvent v1 bridge, Nautilus backtests, risk/audit paths and read-only frontend exist.
- Ten legacy candidates remain paper_shadow dry-run. Protocols through v53 are registered.
- Registry: 154 identities, 116 PnL opened; v49–v53 have 12 identities and no survivors.
- Existing ten collector cron jobs use pinned clean pushed code; no new schedules.
- The 2026-09-07 reliability repairs and their full verification are archived below.

## Next Steps

1. Deploy and smoke-test corrected signal generation, not merely successful data collection.
2. Evaluate hash-verified retained fills against same-window and exposure-matched
   benchmarks; explicitly disclose missing cohort evidence and account equity.
3. Review evidence as a portfolio before considering any separately authorized
   new identity or promotion. Do not retune closed v49/v53 identities.

## Blocked / Deferred

- Testnet/live remain blocked; strict testnet continuity is 0/14.
- ADR-013 and first-live-day runbook remain Draft. No live runner is wired.
- The 2026-09..2027-01 future blind stays sealed for PnL; forward observations only.
- Historical collector anomalies are not cleared or retroactively qualified.
- External-index relief is saturated; closed identities cannot be reopened.
- V12 has no recurring schedule authorization.
- Online CI is not enabled: credential lacks workflow scope; template is in `infra/ci/`.
- No verified account-equity attachment; actual leverage/account return remain unknown.
- Nautilus is the only execution engine; LLMs never enter the order path.

## Latest Verification

- Signal repair: 1,659 offline tests passed; 12 Postgres integration tests deselected.
- Ten new end-to-end/time-consistency/identity tests passed.
- Ruff passed. Deployment and retained-fill study are pending this clean pushed commit.
- Previous repair: frontend typecheck/build, zero-vulnerability audit and bilingual
  HTTP checks passed; see its acceptance record for scope and limitations.

## References

- [2026-09-07 reliability acceptance](progress/reliability-repair-2026-09-07.md).
- [Fixed retained-fill study method](progress/portfolio-evidence-study-2026-09-08.md).
- [Collector deployment](../infra/research-shadow/README.md).
- [Research rules](decisions/014-research-program-v2.md), [warnings](research-program-warnings.md).
- [Registry](progress/research-mechanism-family-registry.json), [meta-analysis context](progress/research-program-meta-analysis-v2.md).
- [Historical status archive](progress/project-status-archive-2026-09-07.md).

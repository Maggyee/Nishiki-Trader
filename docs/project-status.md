# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-08
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Evaluate the confirmed operator budget and accumulate genuine forward evidence.
- **Source of truth**: Runtime status under `data/`; immutable research evidence and ADRs under `docs/`.

## Current Focus

The ordered signal repairs corrected v22/v34/v36 date windows and the monitor's
v36 identity. All ten identities now come from frozen contracts. Separate v2
epochs count corrected attempts only; backfill and legacy empty-pipeline attempts
do not become new prospective evidence. Historical anomalies remain preserved.

The repair is deployed at pinned commit `1727408`: v22/v34/v36 generated
37/36/45 signals respectively, each with one corrected qualified date and zero
new forward signals. No schedules or historical attempt records were changed.

A fixed-method retained-fill study now covers 6/10 candidates over 2023–2025.
V18/v40 have identical execution paths. V22 is 10.41 USDT below its exposure-
matched base-cost benchmark; v16 exceeds it by only 0.43 USDT (0.001 BTC sleeves).
V8/v42/v46/v48 lack original manifest-and-fills hash references and are excluded.
Follow-up found no historical reference leads for their eight retained bundles;
v42 additionally has two dirty-code manifests, so hashes alone cannot qualify it.
The repaired pipelines pass read-only integrity checks but remain at one date.

The operator delegated the increased capital amount. The provisional planning
budget is now **500 USDT / 50% drawdown / 50 USDT daily loss**, without changing
positions or runtime execution settings. On the six verified candidates, the
raw fixed-size basket requires 395.66 USDT cash at daily stress-cost marks,
leaving 104.34 USDT of sampled headroom; its stress drawdown is 100.38 USDT.
Both fixed diagnostics fit these sampled budgets, not a full ten-candidate or
intraday guarantee. No deposit/live trading is recommended now; missing evidence
and prospective acceptance remain blockers. Planned capital is not actual equity.
No frozen strategy parameters, research identities, source policies or trading permissions
are changed. The study does not select allocations or grant promotions.

## Milestones

- SignalEvent v1 bridge, Nautilus backtests, risk/audit paths and read-only frontend exist.
- Ten legacy candidates remain paper_shadow dry-run. Protocols through v53 are registered.
- Registry: 154 identities, 116 PnL opened; v49–v53 have 12 identities and no survivors.
- Existing ten collector cron jobs use pinned clean pushed code; no new schedules.
- The 2026-09-07 reliability repairs and their full verification are archived below.

## Next Steps

1. Accumulate genuinely prospective observations under existing collector schedules;
   review retained anomalies without clearing them retroactively.
2. Obtain original audit/backup references for v8/v42/v46/v48 and clean eligible
   evidence for v42; freshly hashing local files cannot prove history.
3. Use the provisional 500 USDT / 50% / 50 USDT research budget; attach verified
   account equity before assessing actual leverage/account returns.
   Any allocation change, new identity or promotion needs separate review/authority.
   Do not retune closed v49/v53 identities.

## Blocked / Deferred

- Testnet/live remain blocked; strict testnet continuity is 0/14.
- ADR-013 and first-live-day runbook remain Draft. No live runner is wired.
- The 2026-09..2027-01 future blind stays sealed for PnL; forward observations only.
- Historical collector anomalies are not cleared or retroactively qualified.
- External-index relief is saturated; closed identities cannot be reopened.
- V12 has no recurring schedule authorization.
- Online CI is not enabled: credential lacks workflow scope; template is in `infra/ci/`.
- No verified account-equity attachment; actual leverage/account return remain unknown.
- Full ten-candidate portfolio assessment is blocked on four missing evidence chains.
- Full ten-candidate and intraday funding feasibility remain unverified.
- Nautilus is the only execution engine; LLMs never enter the order path.

## Latest Verification

- Full planning-budget suite: 1,700 offline tests passed; 12 Postgres integration tests
  deselected (no dedicated integration DSN supplied).
- Ten new end-to-end/time-consistency/identity tests passed.
- Retained-fill diagnostics: 20 targeted tests passed; Ruff and registry check passed.
- Follow-up: 17 targeted tests passed; original-evidence search, three pipeline
  hash/count checks and all ten pinned cron entries verified. No collector rerun.
- Budget v2: 20 targeted tests passed; exact operator inputs and inclusive loss
  thresholds verified. Versioned output preserves v1 evidence.
- Real corrected-collector smoke and read-only monitor refresh passed. Historical
  accounting reconciles all six included candidates to committed base/stress PnL.
- Previous repair: frontend typecheck/build, zero-vulnerability audit and bilingual
  HTTP checks passed; see its acceptance record for scope and limitations.

## References

- [2026-09-07 reliability acceptance](progress/reliability-repair-2026-09-07.md).
- [Fixed retained-fill study method](progress/portfolio-evidence-study-2026-09-08.md).
- [Partial portfolio diagnostics](progress/portfolio-evidence-review-2026-09-08.md).
- [2026-09-08 strategy repair acceptance](progress/strategy-repair-2026-09-08.md).
- [Follow-up evidence and 100 USDT budget audit](progress/strategy-followup-audit-2026-09-08.md).
- [Historical 100 USDT v2 audit](progress/strategy-followup-audit-2026-09-08-v2.md).
- [Current provisional 500 USDT budget](progress/strategy-budget-500usdt-2026-09-08.md).
- [Collector deployment](../infra/research-shadow/README.md).
- [Research rules](decisions/014-research-program-v2.md), [warnings](research-program-warnings.md).
- [Registry](progress/research-mechanism-family-registry.json), [meta-analysis context](progress/research-program-meta-analysis-v2.md).
- [Historical status archive](progress/project-status-archive-2026-09-07.md).

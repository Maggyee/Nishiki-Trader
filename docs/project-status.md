# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-09
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Validate the fixed offline portfolio contract, then integrate atomic Nautilus reservations without promoting strategies.
- **Source of truth**: Runtime status under `data/`; immutable research evidence and ADRs under `docs/`.

## Current Focus

An offline engineering plan locks six evidence-verified candidates and five
proposed 0.001 BTC sleeves: v16/v18/v22/v34/v36. V40 is observation-only within
this proposal because its retained execution path duplicates v18. All ten legacy
collector policies remain unchanged. The CLI revalidates original hashes and
fails rather than silently changing the cohort. This is not an alpha verdict.

A pure batch preflight now checks pending-order cash/base reservations, partial
fills, cancel acknowledgements, duplicate IDs, effective LIMIT filters, fresh
reconciled snapshots, exposure caps and inclusive daily/peak loss limits.
It is NOT wired into runners: atomic reservation, Nautilus sleeve attribution,
persistent risk/restart reconciliation and complete venue constraints remain next.

The prior signal repairs corrected v22/v34/v36 date windows and monitor v36
identity. Separate v2 epochs count corrected attempts only. The last inspected
September 8 morning snapshot had one qualified date and zero new forward signals
for these three pipelines; it is not a September 9 runtime health observation.
Historical anomalies and all existing collector schedules remain unchanged.

A fixed-method retained-fill study now covers 6/10 candidates over 2023–2025.
V18/v40 have identical execution paths. V22 is 10.41 USDT below its exposure-
matched base-cost benchmark; v16 exceeds it by only 0.43 USDT (0.001 BTC sleeves).
V8/v42/v46/v48 lack original manifest-and-fills hash references and are excluded.
Follow-up found no historical reference leads for their eight retained bundles;
v42 additionally has two dirty-code manifests, so hashes alone cannot qualify it.

The operator delegated the increased capital amount. The provisional planning
budget is now **500 USDT / 50% drawdown / 50 USDT daily loss**, without changing
positions or runtime execution settings. On the six verified candidates, the
raw fixed-size basket requires up to 398.19 USDT for retained-fill settlement
under stress costs and buy-before-sell timestamp ties, leaving 101.81 USDT
headroom. This refines the daily sampled 395.66 USDT figure. Both fixed
diagnostics fit the tested cash bounds, not a full ten-candidate or open-order
reservation guarantee. No deposit/live trading is recommended; missing evidence
and prospective acceptance remain blockers. Planned capital is not actual equity.
No frozen strategy parameters, research identities, source policies or trading permissions
are changed. The September 8 study does not select allocations or grant promotions;
the September 9 five-sleeve proposal is offline engineering only.

## Milestones

- SignalEvent v1 bridge, Nautilus backtests, risk/audit paths and read-only frontend exist.
- Ten legacy candidates remain paper_shadow dry-run. Protocols through v53 are registered.
- Registry: 154 identities, 116 PnL opened; v49–v53 have 12 identities and no survivors.
- Existing ten collector cron jobs use pinned clean pushed code; no new schedules.
- The 2026-09-07 reliability repairs and their full verification are archived below.

## Next Steps

1. Integrate the fixed offline contract into Nautilus simulated acceptance using
   synthetic SignalEvent v1 inputs: sleeve attribution, atomic check/reservation,
   partial/late fills, cancel acknowledgements, restart and latched risk recovery.
   Do not change current SourcePolicy or runtime loss settings as part of wiring.
2. Attach authoritative effective venue filters/fees and reconciled account inputs;
   current tests use synthetic LIMIT rules. Reconcile the requested 50 USDT daily
   planning budget with existing runtime ADRs before any runtime policy change.
3. Accumulate genuinely prospective observations under existing collector schedules;
   review retained anomalies without clearing them retroactively.
4. Obtain original audit/backup references for v8/v42/v46/v48 and clean eligible
   evidence for v42; freshly hashing local files cannot prove history.
   Their absence need not block the separately scoped five-sleeve engineering work.
5. Complete portfolio-level alpha/forward review before simulated-order promotion.
   Deployed allocation changes, new identities or promotions need separate review/authority.
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
- Full ten-candidate funding and intraday equity drawdown remain unverified.
  Offline reservation checks exist; actual Nautilus reservation lifecycle and
  account/venue integration remain unverified. No real account was accessed.
- Nautilus is the only execution engine; LLMs never enter the order path.

## Latest Verification

- Portfolio-contract suite: 1,774 offline tests passed; 12 Postgres integration tests
  deselected (no dedicated integration DSN supplied).
- 63 new cohort/preflight tests; six-candidate original evidence revalidation
  succeeded. Five synthetic simultaneous buys need 500.75 USDT at 100,000
  USDT/BTC and a 15 bps quote fee bound: correctly blocked against 500 USDT.
- Ten new end-to-end/time-consistency/identity tests passed.
- Retained-fill diagnostics: 20 targeted tests passed; Ruff and registry check passed.
- Follow-up: 17 targeted tests passed; original-evidence search, three pipeline
  hash/count checks and all ten pinned cron entries verified. No collector rerun.
- Budget v2: 20 targeted tests passed; exact operator inputs and inclusive loss
  thresholds verified. Versioned output preserves v1 evidence.
- Event-cash extension: 32 focused tests passed; final cash reconciles to all
  six candidates' basket PnL. Latest natural cron attempts and monitor verified.
- Real corrected-collector smoke and read-only monitor refresh passed. Historical
  accounting reconciles all six included candidates to committed base/stress PnL.
- Previous repair: frontend typecheck/build, zero-vulnerability audit and bilingual
  HTTP checks passed; see its acceptance record for scope and limitations.

## References

- [Fixed offline portfolio contract and integration obligations](progress/portfolio-execution-contract-2026-09-09.md).
- [Revalidated machine-readable plan](progress/portfolio-execution-plan-2026-09-09.json).
- [2026-09-07 reliability acceptance](progress/reliability-repair-2026-09-07.md).
- [Fixed retained-fill study method](progress/portfolio-evidence-study-2026-09-08.md).
- [Partial portfolio diagnostics](progress/portfolio-evidence-review-2026-09-08.md).
- [2026-09-08 strategy repair acceptance](progress/strategy-repair-2026-09-08.md).
- [Follow-up evidence and 100 USDT budget audit](progress/strategy-followup-audit-2026-09-08.md).
- [Historical 100 USDT v2 audit](progress/strategy-followup-audit-2026-09-08-v2.md).
- [Current provisional 500 USDT budget](progress/strategy-budget-500usdt-2026-09-08.md).
- [Latest forward and event-cash progress](progress/strategy-progress-2026-09-08-v3.md).
- [Collector deployment](../infra/research-shadow/README.md).
- [Research rules](decisions/014-research-program-v2.md), [warnings](research-program-warnings.md).
- [Registry](progress/research-mechanism-family-registry.json), [meta-analysis context](progress/research-program-meta-analysis-v2.md).
- [Historical status archive](progress/project-status-archive-2026-09-07.md).

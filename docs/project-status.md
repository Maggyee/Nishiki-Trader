# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-09
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Qualify a dedicated read-only account source, stream/archive boundary and native adapter recovery after synthetic cross-process acceptance.
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
Operator-approved offline v2 admission now selects an affordable subset: reductions
first, then signal event time and frozen sleeve order. Each addition and the final
selected set pass the same complete risk check; skipped orders get reasons and
are not queued. The selector never resizes proposals or credits unfilled sales.
It now feeds a synthetic-only Nautilus acceptance strategy: native sleeve positions,
serialized durable preparation before submit, native partial/late fills and cancel
acknowledgements, warm strategy restart, persistent deduplication and loss latches.
The explicit recovery mode now persists native events with the strategy journal
and passes abrupt-exit/fresh-process acceptance, including partial orders, dust,
deduplication and loss latches. Missing/drifting/uncertain state fails closed.
Real account/adapter recovery and runtime policy reconciliation remain next. Existing
paper/testnet/live runners and SourcePolicy are unchanged.

The offline Binance adapter parses exchangeInfo, commission and myFilters with
freshness/account/request checks and effective price/order/asset constraints.
A new explicit synthetic mode now reconciles native BTC BUY fees at eight-place
accounting precision while preserving the 0.000001 BTC order step. Four buys
settle to 100 USDT / 0.003994 BTC. Each full fill leaves 0.00000050 BTC off-grid;
default full exits are refused without rounding. Explicit offline `whole_steps_v1`
now sells whole-step reductions through full preflight, retaining exact native
residual ownership and equity across partial/late fills, cancellation and warm
restart. Four exits leave 498.60120 USDT / 0.00000200 BTC, explicitly not flat.
Residuals still block fixed-size re-entry; no sweep or retry is enabled. Default
quote-only/exact-exit modes and BNB rejection remain. Private responses are still
synthetic. A signed GET-only collector and exact balance/lock/order/trade/fee
comparison now exist; real-account attachment remains unqualified. REST agreement
does not establish an atomic stream boundary or authorize live admission.

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

1. Qualify a dedicated read-only account source, complete archive/user-stream
   boundary and effective venue references. Signed collection and exact comparison
   now exist; fresh-process native restoration passes synthetic acceptance.
   Exercise real adapter execution-report recovery for drift and uncertain commands.
   Reconcile downtime risk history and the 50 USDT planning loss with runtime ADRs.
2. Review the explicit offline residual-exit policy before promotion and resolve
   re-entry with retained dust. Whole-step reductions now pass native acceptance;
   fixed BUY size, SignalEvent identities and SourcePolicy remain unchanged.
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
  Synthetic Nautilus reservation lifecycle and abrupt fresh-process recovery pass;
  real account/venue integration, stream continuity and live recovery remain unverified.
  No real account was accessed.
- Nautilus is the only execution engine; LLMs never enter the order path.

## Latest Verification

- **61 new account/recovery tests** passed: 48 native/account tests and 13 signed
  read-only collector tests. Combined portfolio regression: 137 passed. Two actual
  worker processes preserve partial orders, exact dust and risk latches without
  resubmission. No real HTTP/account was used; REST-only readiness stays false.
- Full offline suite: **1,990 tests passed**; 12 Postgres integration tests
  deselected (no dedicated integration DSN supplied).
- **22 residual-exit tests** passed: durable sizing audit, exact native ownership,
  min/max filters, sub-notional retention, partial/late fills, pending cancellation,
  fixed-size re-entry refusal, loss latches, replay and restart boundaries. Both
  fee modes produce reproducible whole-step exit reports; Ruff and registry pass.
- **19 received-asset inventory tests** passed: native BTC commission adjustments,
  eight-place precision, partial/late fills, exact aligned exits, retained dust,
  conservative per-fill rounding, mode fingerprints and warm restart. Both CLI
  accounting modes, Ruff and registry check passed.
- **55 venue-adapter tests** passed: official response shapes, account/request
  identity, independent freshness, fee-currency rejection, inclusive price bands,
  order/position/asset caps and native pre-submit injection. Read-only CLI, Ruff
  and registry check passed. No actual account reconciliation is claimed.
- **35 synthetic Nautilus lifecycle tests** passed: durable batch reservations,
  partial/late fills, cancel acknowledgements, native risk denial, sleeve attribution,
  interrupted submits, checkpoint failure, warm restart/cold refusal and latched
  daily/peak risk. CLI smoke is reproducible; Ruff and registry check passed.
- 87 focused cohort/preflight tests (24 added this revision); six-candidate
  evidence revalidation succeeded. At synthetic 100,000 USDT/BTC and 15 bps,
  whole-batch checks still reject 500.75 USDT; v2 selects four buys requiring
  400.60 USDT, leaving 99.40 USDT. All 120 input permutations agree.
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

- [Read-only account reconciliation and native process recovery](progress/portfolio-account-recovery-2026-09-09.md).
- [Explicit offline residual-exit policy and acceptance](progress/portfolio-residual-exit-2026-09-09.md).
- [Native base-fee accounting, precision and no-rounding exit acceptance](progress/portfolio-base-fee-acceptance-2026-09-09.md).
- [Binance rule adapter, fee-currency blocker and remaining work](progress/portfolio-venue-adapter-2026-09-09.md).
- [Synthetic Nautilus lifecycle acceptance and remaining integration](progress/portfolio-simulation-acceptance-2026-09-09.md).
- [Current v2 funded admission and integration obligations](progress/portfolio-funded-admission-2026-09-09.md).
- [Current revalidated machine-readable plan](progress/portfolio-execution-plan-2026-09-09-v2.json).
- [Original v1 offline portfolio contract](progress/portfolio-execution-contract-2026-09-09.md).
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

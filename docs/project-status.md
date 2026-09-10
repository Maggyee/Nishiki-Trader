# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-10
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Qualify actual account/price archives, cash flows and strategy policy after checkpoint recovery and read-only downtime breach review.
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
Native Binance signing and report converters now pass offline acceptance, including
submitted orders and pending cancels with late actual-fee fills. A durable stream
journal binds source, subscription epoch and REST fences; disconnects and new events
invalidate prior observations. A dedicated read-only native WS transport now binds
confirmed signed subscriptions, preserves envelopes and checks actual socket state
at every fence. Real Rust WebSocket I/O passes loopback acceptance; no Binance
account or external WS was connected. Account HTTP requests have a GET whitelist
and avoid signed-URL debug logging. Local receipts cannot prove global gap-free
continuity. An isolated numeric-venue checkpoint path now combines native event
reconstruction, Binance report reconciliation and exact account comparison; three
processes verify abrupt exit and replay with original state/latches preserved.
A read-only downtime reviewer now binds native account/bid observations to both
checkpoints and retains observed 5% breaches through a rebound. It reports the
25 USDT versus 50 USDT daily-rule mismatch at a 500 USDT day-open baseline. Sparse
or dense samples cannot prove complete coverage; UTC rollover needs a qualified
new baseline. Opaque strategy state is not activated. Existing execution runners,
5% runtime rule and SourcePolicy remain unchanged.

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

1. Obtain the explicit environment, credential variable names/config path, expected
   UID and independent account baseline for real read-only acceptance; no secret
   values in chat. Isolated native adapter checkpoint reconstruction/reconciliation
   and three-process replay now pass. Qualify actual endpoint permissions, stream
   receipts, archive coverage and venue references, then validate real strategy
   state/policy fingerprints before any execution bootstrap. The downtime reviewer
   detects observed breaches but cannot clear missing account/price coverage, cash
   flows or UTC day-open history. Resolve actual runtime telemetry semantics and
   the 50 USDT planning loss versus the binding 5% rule without weakening it.
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

- **33 downtime-risk tests** passed. A synthetic 499.95 → 473.35 → 499.75 USDT
  path retains its 26.65 USDT daily-loss observation despite the rebound. Inclusive
  5% boundaries agree with the existing baseline strategy; the planning rule stays
  separate. Coverage, source, UTC baseline and immutable-input checks pass.
- Full offline suite: **2,151 passed**, 12 Postgres integration tests deselected
  (no dedicated integration DSN). Ruff, registry and whitespace checks pass.
- Prior abrupt-exit/fresh-process recovery and exact account comparison remain
  green. Private account responses are synthetic; no Binance HTTP/WS account
  connection, real adapter process recovery, atomic stream boundary or live readiness.
- Earlier portfolio, collector and reliability verification is archived in the
  linked progress records; it is not a current runtime-health observation.

## References

- [Read-only downtime risk review and remaining evidence boundaries](progress/portfolio-downtime-risk-2026-09-10.md).
- [Native adapter checkpoints and three-process acceptance](progress/portfolio-adapter-checkpoint-2026-09-10.md).
- [Native read-only transport, loopback acceptance and integration entrypoint](progress/portfolio-readonly-transport-2026-09-10.md).
- [Source binding, user stream and native adapter qualification](progress/portfolio-source-stream-adapter-2026-09-10.md).
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

# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-12
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Preserve the consumed ADR-017 scope; cleanup admission now handles spent quote cash correctly and passes synthetic fill/fee/residual recovery. Interrupted cleanup SELL recovery now passes native/CLI/crash acceptance. Local operator status and unresolved-order runbook are implemented; next qualify historical replay of retained session evidence. Actual fills/cleanup and full-account portfolio qualification remain unverified.
- **Source of truth**: Runtime status under `data/`; immutable research evidence and ADRs under `docs/`.

## Current Focus

Operator-delegated risk policy is now **ADR-015 / offline plan v3**: daily loss
**min(25 USDT, 5% of qualified UTC day-open equity)**, with the separate fixed
250 USDT peak-loss ceiling. Preflight, synthetic risk latching and downtime review
share the calculation. Rebound/midnight/restart cannot clear the latch; old-policy
checkpoints fail configuration matching. Legacy runner equivalence and actual
account qualification remain required; no execution deployment is authorized.

The operator-selected **Binance Spot testnet** now has a successful **matching
BUY/cancel trial under ADR-017**, beyond the prior GET and non-matching validation.
Clean pushed code `6d7c43b` used the existing selected Ed25519 key/UID, fresh zero
commissions and effective filters. One **0.0001 BTC LIMIT at 76,908.15 USDT**
(7.690815 test-USDT notional) was accepted. The deterministic native lifecycle
requested cancellation **2.036 seconds after acknowledgement**; cancellation succeeded.
**No fills, cleanup SELL or residual inventory** resulted. All **502 assets**
reconcile exactly; account-wide open orders, spent funds and reservations are zero.
A separate process opened a new signed subscription, queried the original order
and reproduced the identical native terminal view. There were no retries or halts.

The separate **LiveClock matching runtime** now joins the fixed account lease,
full native CASH baseline, fixture SignalEvent v1, Strategy, RiskEngine, queued
execution adapter and exact Ed25519 POST/DELETE. Durable native events and single
attempt receipts precede network I/O. Two execution reports and two account
reservation/release updates were received and correlated without balance patching.
Actual partial/final fills, fee settlement and owned cleanup remain unverified;
those paths currently have synthetic acceptance only. The original-process cleanup
now uses SELL capability checks, without requiring another 10 free USDT after BUY.
Whole-CLI acceptance covers low cash, partial exits, dust and fee halts through
terminal read-only recovery. Interrupted cleanup SELL recovery now also passes
native and whole-CLI acceptance, including late/duplicate fills, exact base locks,
fee halts, no-retry refusals and two independent recoveries after abrupt exit.
These are synthetic tests; original deadline/allowances remain intact.
`--status` now reads fixed local records without credentials, network or writes,
showing original IDs, consumed intents/dispatches, recorded ownership and history
expiry. Success and failure reports distinguish signed observation from local
records. The actual local check confirms the same terminal checkpoint and an
expired 24-hour history window; it is not a fresh exchange observation.
Explicit `--recover-cancel`
now restores a qualified active original order into a cancellation-only native
runtime after fresh signed reconciliation. Historical halts and all allowances
remain intact; an old cancellation intent/attempt blocks another send. Terminal
orders leave the fixed checkpoint unchanged. `--recover` remains GET-only; new
BUY/SELL and cleanup after recovery stay disabled. On clean `9d797f6`, the real
`--recover-cancel` invocation made six signed GETs, reconciled all 502 assets and
returned `terminal_session_no_action`; no order/cancel was sent and the fixed
checkpoint hash remained unchanged.

The fixed session activation and **one-BUY allowance are consumed**, including
for this unfilled canceled order. Preserve all state and original IDs; do not rerun
`--execute`, reset the scope or create a second BUY to force a fill. Native ownership,
partial CASH locks, uncertain outcomes and persistent fee halts are covered offline.
No SourcePolicy, service, schedule, credential permission or production path changed.

ADR-016's full-account indicative valuation still covers **500/502 assets**;
two lack quotes and 65 exceed a conversion leg's top-book depth. Full equity,
UTC day-open and daily-risk fields remain null. The operator confirms no other
trading; independent records are unavailable and reset history remains unknown.
ADR-017 does not qualify this baseline or relax ADR-015 portfolio risk.
Strict gates, SourcePolicy, execution runners and production accounts are unchanged.

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
at every fence. Real Rust WebSocket I/O passes loopback acceptance and the separate
testnet observation above. Account HTTP requests have a GET whitelist
and avoid signed-URL debug logging. Local receipts cannot prove global gap-free
continuity. An isolated numeric-venue checkpoint path now combines native event
reconstruction, Binance report reconciliation and exact account comparison; three
processes verify abrupt exit and replay with original state/latches preserved.
A read-only downtime reviewer now binds native account/bid observations to both
checkpoints and retains observed 5% breaches through a rebound. It now applies ADR-015
while retaining the independent 5% diagnostic and explicit unqualified policy status. Sparse
or dense samples cannot prove complete coverage; UTC rollover needs a qualified
new baseline. Opaque strategy state is not activated. Existing execution runners,
5% runtime rule and SourcePolicy remain unchanged.
Stream-bound REST collection retains raw responses and seals successful records.
One collection owns each journal; a 60-second async deadline and per-read clock,
source and fence checks bound collection. Failure records an abort before explicit
reuse; failed disk writes keep it blocked. Local replay reproduces evidence for
detached native comparison but cannot restore a stream fence or fill old hash-only
archives. Abrupt exit, pagination, receipt integrity and interrupted retries pass.

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
capital remains **500 USDT**. ADR-015 supersedes the daily planning amount
with min(25 USDT, 5% of qualified day-open equity); the peak-loss ceiling remains
250 USDT. Existing positions and execution runners are unchanged. The following
September 8 cash figures are historical, not a v3 risk/performance evaluation.
On the six verified candidates, the
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

1. Preserve the completed fixed ADR-017 scope. Interrupted cleanup SELL recovery
   now passes synthetic native/CLI/crash acceptance. Local status and the unknown-
   order runbook are implemented. Next qualify offline replay of retained private
   session evidence after the collector window expires, without representing it
   as current source/venue confirmation. Recovered new SELL remains
   disabled; actual active recovery/fills/cleanup remain unverified. Continue
   ADR-016 full-account/UTC/cash-flow qualification separately; strict continuity
   stays 0/14.
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
  Real full-account testnet observations/reconnect pass; no production account was accessed.
- Nautilus is the only execution engine; LLMs never enter the order path.

## Latest Verification

- Operator status: **18 new tests**, **31 focused tests** pass. Local inspection
  and report summaries preserve unknown outcomes,
  consumed preparation/dispatch and recorded inventory. No credential/network/write
  occurs in `--status`; actual inspection preserves the original checkpoint hash.

- September 12 interrupted SELL recovery: **17 additional tests**, **29 focused
  tests** pass. Native/CLI acceptance covers two original
  orders, missed/late/duplicate fills, exact owned residuals, fee halts, invalid
  evidence, disk failures and uncertain-cancel refusal. Abrupt-exit producer plus
  two fresh processes preserve the same terminal state and all three dispatches.
  Application code and the actual fixed session are unchanged.

- September 12 cleanup gate: **23 additional tests**, **71 focused tests** pass.
  Whole CLI now exercises actual capability validation,
  native settlement and separate terminal recovery for low quote cash, partial
  fills/SELLs, below-minimum residuals and BTC/USDT fee halts. No actual exchange
  requests or fixed private checkpoint changes in this increment.

- Cancellation-only recovery: **21 new tests** pass, covering LiveClock/native
  restoration, late/duplicate fills, missed acknowledgement, durability failure,
  timeout/no-retry, whole CLI and three-process abrupt-exit acceptance. Actual
  clean-code terminal recovery used six signed GETs, reconciled 502 assets and
  preserved the original checkpoint hash, with no POST/DELETE or new dispatch.

- Bounded LiveClock matching runtime: **31 new tests** pass, including native
  queue/Ed25519 signature, failure, timed cancellation and whole-CLI matching/recovery.
  Actual clean-code matching POST and DELETE returned 200; four business events
  and full 502-asset reconciliation passed. A fresh process independently recovered
  the one CANCELED order, zero trades and zero account-wide open orders.

- September 11 actual session transport: **34 new tests**; 12 signed GETs plus one
  public metadata GET in two actual process invocations, each with a new signed
  subscription. Both native comparisons preserve all 502 assets; zero orders/trades/
  business events. Fixed matching scope remains unactivated. See the report below.

- September 11 queued session bridge: **44 new tests**, **91 combined bridge/ledger
  tests**. Native risk denial, durable pre-send events/attempts, partial/late/duplicate
  fills, uncertain timeouts, disk failures and two three-process adapter crash/replays
  pass. All 502 synthetic assets retained; no credentials or exchange I/O.

- September 11 native session ledger/recovery: **47 new tests**; two independent
  three-process crash/replay scenarios each preserve 502 synthetic assets, exact
  native fills and consumed BUY/cancel intents. Active partial locks, owned cleanup,
  dust, unexpected fee halts and failed fsync pass. No exchange I/O in this increment.

- September 11 ADR-017 engineering diagnostics: **45 new tests**; existing-key
  TRADE `/api/v3/order/test` accepted with zero fees, 502 balances unchanged and
  no account-wide open orders. Final replay reproduces price/effective filters;
  matching/native recovery remains unwired. Detailed evidence is archived below.

- September 11 ADR-016 admission/valuation: 28 focused tests passed; real selected
  captures retain 502 assets, price 500, and refuse total equity/day-open risk
  qualification. A fixed bounded lifecycle draft passes captured basic filters
  only; no testnet order or production request.

- September 11 full-account mapping: 78 focused tests passed. New four-collection
  archive replays in a fresh process; all 502 assets map exactly using selected
  testnet metadata in an isolated native process. Cross-session endpoint balances
  and orders agree; zero business events, no trading readiness.

- September 11 risk unification: 177 focused tests passed; v3 generation
  revalidated all six original evidence chains. Four selected testnet archive
  collections replayed with 502 assets each; independent identity/baseline remain
  unqualified. No new network observation or trading runner was started.

- September 11: two actual signed testnet WS subscriptions, four 502-asset
  collections, six ping confirmations, explicit reconnect/old-fence rejection and
  detached replay pass. Zero business events were observed. **49 new tests** cover
  full-account validation, interrupted collection/retry, raw events, archive
  integrity, strict-gate separation and bounded ops cleanup. Independent UID,
  baseline, API restrictions and actual adapter process recovery remain unqualified.
- **130 collector/stream/archive tests** passed, including 12 new concurrency,
  cancellation, timeout, source/clock and abort-persistence regressions. Explicit
  retries produce independently replayable evidence; failed collections stay rejected.
- Full offline regression after operator status/runbook integration: **2,621 passed**,
  12 Postgres integration tests deselected (no dedicated integration DSN; 179.54 seconds).
  Ruff, registry and whitespace checks pass.
- Prior abrupt-exit/fresh-process recovery and exact account comparison remain
  green. Recovery fixtures remain synthetic; the separate testnet observations
  do not qualify adapter process recovery, an atomic stream boundary or live readiness.
- Earlier portfolio, collector and reliability verification is archived in the
  linked progress records; it is not a current runtime-health observation.

## References

- [Fixed-session unknown-order and recovery runbook](runbook-testnet-session-recovery.md),
  [operator-status implementation and actual local inspection](progress/portfolio-testnet-operator-status-2026-09-12.md).

- [Interrupted cleanup SELL recovery acceptance](progress/portfolio-testnet-sell-recovery-2026-09-12.md).

- [Owned cleanup gate correction and fee/residual recovery acceptance](progress/portfolio-testnet-cleanup-gate-2026-09-12.md).

- [Source-bound cancellation-only recovery](progress/portfolio-testnet-cancel-recovery-2026-09-11.md).

- [Bounded LiveClock matching runtime and original-ID recovery](progress/portfolio-testnet-session-runtime-2026-09-11.md).

- [Actual LiveClock account bootstrap, fixed scope and signed recovery](progress/portfolio-testnet-session-transport-2026-09-11.md).

- [Queued native session strategy/adapter bridge and remaining real transport](progress/portfolio-testnet-session-bridge-2026-09-11.md).

- [Native session ledger, partial CASH locks and crash/replay acceptance](progress/portfolio-testnet-session-recovery-2026-09-11.md).

- [Independent engineering scope](decisions/017-testnet-engineering-session.md), [actual TRADE validation and remaining native integration](progress/portfolio-testnet-engineering-session-2026-09-11.md).

- [Testnet admission/baseline rules](decisions/016-testnet-observation-admission.md), [implementation and actual blockers](progress/portfolio-testnet-admission-2026-09-11.md), [bounded lifecycle proposal](progress/portfolio-testnet-lifecycle-plan-2026-09-11.json).

- [Operator account context, fresh observations and isolated full-account mapping](progress/portfolio-testnet-account-mapping-2026-09-11.md).

- [Unified risk decision](decisions/015-portfolio-risk-policy.md), [implementation and next account inputs](progress/portfolio-risk-unification-2026-09-11.md), [current v3 plan](progress/portfolio-execution-plan-2026-09-11-v3.json).

- [Full-account testnet observations, real signed WS reconnect and detached replay](progress/portfolio-testnet-observation-2026-09-11.md).
- [Ed25519 credentials, native signatures and first signed testnet account read](progress/portfolio-testnet-ed25519-2026-09-11.md).
- [Selected Spot testnet environment, verified incompatibility and required inputs](progress/portfolio-spot-testnet-selection-2026-09-11.md).
- [Collection concurrency, time limits and interruption recovery](progress/portfolio-collection-lifecycle-2026-09-10.md).
- [Raw account response archive and offline collection replay](progress/portfolio-account-archive-2026-09-10.md).
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
- [Historical v2 machine-readable plan](progress/portfolio-execution-plan-2026-09-09-v2.json).
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

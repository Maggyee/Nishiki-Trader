# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-16
- **Current phase**: Phase 5 entry — read-only monitoring; live trading blocked.
- **Current objective**: Reuse the existing public IPv4. The isolated maintenance fixture now persists one-shot window consumption before kernel activation; process crashes retain uncertain activation and fresh processes cannot reopen the scope. Collector permission expires before ordinary traffic resumes. Next bind actual source/caller/fixed storage and external paths, then prepare the privileged helper and rollout. The 12-second collector / 20-second blackout candidate would interrupt unrelated egress and is not approved or deployed. No bootstrap or consumed scope is activated.
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
The standalone archive reviewer now verifies pinned original bytes, collection
identity, complete raw response chain and evidence seal before historical native
reconciliation. September 13 replay reproduces the original September 11 evidence
hash and terminal view across all 502 assets with zero venue requests. Historical
review never refreshes source confirmation or creates an execution checkpoint.
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
The combined historical review now replays all five pinned inputs and finds zero
missing assets, unexplained endpoint net deltas or reference-to-session lock changes
across 502 assets after native fills/fees. The reference is September 11 05:42 UTC,
not midnight; equal endpoints do not prove complete external-flow/reset history.
Qualified current/day-open/peak equity and losses remain null.
Official provider review confirms periodic unannounced resets preserve API keys,
JSON bookTicker lacks event time, and diff depth provides E/U/u without a common
account revision. No documented reset-history or missed-user-event replay interface
closes those gaps. The 499 historical valuation routes would require 124,750 weight
for 5,000-level snapshots; full-account bootstrap cannot fit the existing capture
window at the recorded limit. The first public v1 attempt stopped at its explicit
`U=L+1` bootstrap refusal and remains failed. The separately frozen v2 interpretation
applies the pinned update algorithm to the first remaining event (`U<=L+1<=u`).
On clean pushed `cf4612c`, its single 20-second-budget attempt completed in 18.265
seconds: five GETs/weight 28, one stream, 21 frames and 20 native QuoteTicks.
Three clock samples passed; the closed archive and two fresh-process replay reports
match exactly. This proves a bounded locally linked BTCUSDT segment only. Both
one-shot scopes are consumed; no repeat, service, account/valuation/baseline or
trading qualification follows. The v1 default and its original bytes stay intact.
The new offline planner replays the initial/account/market/depth originals and
preserves all 502 assets. BTC/ETH/BNB's historical routes select three streams;
496 assets remain outside the pilot and two unpriced. Two complete four-GET
account collections plus routing/time/depth/WS operations cost 448 weight (16 GETs).
All 499 routes cost 2,928 weight even at 100 levels; deeper snapshots, side/depth
availability and unverified throughput remain blockers. The synthetic joint journal
now implements shared pending/archive limits, durable receipt/dispatch times,
independent symbol gaps/ages and full-account intervals.
The separate loopback profile now binds selected source bytes, derives routes from
same-run account/metadata/books and checks durable dispatch budgets. Native signed
WS/HTTP fixture reads, combined-stream callbacks, burst/closure failures and two
fresh native replays pass. The separate draft testnet contract now budgets an
early metadata GET (17 GETs / 468 documented weight) and a two-second linked
observation. Original REST/WS rate fields parse offline, preserving unknown
connection/RAW_REQUESTS usage and separate endpoint scopes. The distinct local TLS
joint profile now records certificate verification and raw HTTP/WS chunks before
interpretation, binds reconstructed messages to semantic callbacks, handles text
fragments and control frames, and reproduces native reports in fresh processes.
It uses project-owned stdlib TLS/framing with native signing/account/quote mapping;
18 local TLS connections retain the fixture's 16 GET / 448-weight budget.
The offline first-request reviewer now reparses original rates, checks clock/bucket
and history consistency, calculates full-scope plus other-client reservations, and
retains separate/union connection calculations. Missing or self-reported evidence
returns a blocked report with no network I/O. Actual source/gateway authentication,
complete shared-egress records and per-dispatch durable admission remain missing.
Selected source/gateway signatures bind original candidates, policy, scope and time.
The operator confirms gateway records are unavailable and authorized an offline
21-step rehearsal joining those signatures to remaining-budget checks and durable
local consumption. Failure/uncertainty retains attempts; abrupt exit preserves a
replayable pending step and the original archive cannot be reopened. Independent
replays match. This is local accounting only: signer authority, coverage and
unknown-charge blockers remain, no gateway capacity is reserved, and no transport
consumes the records or activates a real one-shot scope.
The real profile is not enabled and no baseline qualification follows.
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

Detailed depth implementation, retained hashes and next review:
[public depth acceptance](progress/portfolio-testnet-public-depth-2026-09-13.md),
[v2 bootstrap decision](progress/portfolio-testnet-public-depth-v2-contract-2026-09-13.md),
[actual v2 capture and replay](progress/portfolio-testnet-public-depth-v2-2026-09-13.md),
[joint-observation coverage/budget design](progress/portfolio-testnet-joint-observation-design-2026-09-13.md),
[synthetic joint journal acceptance](progress/portfolio-testnet-joint-observation-acceptance-2026-09-14.md),
[original-route/native loopback integration](progress/portfolio-testnet-joint-transport-2026-09-14.md),
[rate evidence and draft capture contract](progress/portfolio-testnet-joint-capture-contract-2026-09-14.md),
[local TLS/Upgrade provenance](progress/portfolio-testnet-tls-provenance-2026-09-14.md),
[joint TLS transport acceptance](progress/portfolio-testnet-joint-tls-transport-2026-09-14.md),
[offline first-request admission review](progress/portfolio-testnet-joint-admission-review-2026-09-14.md),
[selected source/gateway authorship](progress/portfolio-testnet-joint-attestation-2026-09-15.md),
[offline per-step reservation rehearsal](progress/portfolio-testnet-joint-reservation-2026-09-15.md),
[VPS egress assessment and isolation proposal](progress/portfolio-vps-egress-assessment-2026-09-15.md),
[actual isolated Linux hook acceptance](progress/portfolio-vps-egress-namespace-acceptance-2026-09-15.md),
[kernel expiry and observed-loss acceptance](progress/portfolio-vps-egress-lease-acceptance-2026-09-15.md),
[controlled revocation and sender ownership](progress/portfolio-vps-egress-controller-2026-09-15.md),
[fixed-scope persistence and crash replay](progress/portfolio-vps-egress-persistence-2026-09-16.md),
[historical dedicated IPv4 proposal](progress/portfolio-dedicated-egress-bootstrap-2026-09-16.md),
[current shared IPv4 revision](progress/portfolio-shared-egress-bootstrap-2026-09-16.md),
[actual shared-source NAT/proxy acceptance](progress/portfolio-shared-egress-acceptance-2026-09-16.md),
[bounded maintenance alternative](progress/portfolio-maintenance-window-2026-09-16.md),
[durable window activation and crash replay](progress/portfolio-maintenance-persistence-2026-09-16.md).

## Next Steps

1. Preserve the completed fixed ADR-017 scope and pinned private evidence. Local
   status, unknown-order handling and expired-window historical replay are implemented.
   V2 public depth acceptance and both actual independent replays are complete;
   its single-attempt scope is consumed. The fixed three-pivot coverage/budget and
   independent-interval journal now passes synthetic native replay, shared-buffer,
   delayed-dispatch, interleaving and one-symbol failure acceptance. Original-input
   route fixation and native loopback transport integration now also pass.
   The distinct testnet draft and original rate-field parser are now implemented.
   Local TLS joint frame/control/lifecycle capture and detached replay now pass,
   with real endpoints refused before networking. Offline first-request capacity
   and missing-evidence review now also pass; untrusted candidate bounds never admit.
   Selected source/gateway authorship and durable blocked reports now pass;
   actual authority qualification and gateway enforcement remain unverified.
   The operator confirms no gateway records are available; the authorized offline
   21-step remaining-budget/durable-preparation rehearsal now passes, including
   incomplete crash replay and refusal to reopen the original archive.
   Disposable acceptance now covers dual-stack hooks, expiring permissions and
   observed rule/route/audit loss. Controlled revocation now serializes with sends;
   queued requests stop and senders lack administration capabilities. Controller
   death still relies on TTL expiry; uncontrolled privileged mutation remains
   unclosed. Fixed-scope disk persistence now passes process-crash acceptance:
   initialization consumes the directory, replay retains uncertain preparations,
   and every reopen is refused. Next bind actual source/caller authorization and
   qualify the selected storage root and deployed crash/revocation behavior.
   No host guard or complete audit is deployed. The operator now selects the
   existing public IPv4; no second address is required. Local SNAT/proxy acceptance
   now verifies five caller paths and durable collector dispatch, with other-address
   controls preserved. Unlisted targets and cohosted-service counterexamples keep
   provider-wide coverage false. The bounded maintenance alternative now passes
   kernel timer/crash/pause checks: collector permission expires before ordinary
   traffic resumes. A separate fixed window journal now persists consumption before
   kernel activation; six process-crash stages retain state and refuse reopening.
   This does not prove host power-loss durability or prevent storage rollback.
   Next bind actual source/caller/fixed-storage/external paths, then prepare the privileged
   helper and rollout. Its proposed 20-second interruption is not accepted or
   deployed. Do not silently stop services; the host inspector remains read-only.
   The separate one-GET REST bootstrap proposal acknowledges unknown prior usage;
   review/implement it before any activation. It cannot satisfy or silently amend
   the frozen joint draft; waiting alone still supplies no historical evidence.
   Obtain qualified signer/source records, fresh initial usage/limits and complete
   enforced egress records; then wire authenticated per-dispatch
   reservations, durable one-shot activation and separate real profile replay.
   No new capture, seed probe or default-zero connection count is permitted by the draft.
   Keep unpriced/insufficient-depth assets explicit; neither prior depth outcome
   qualifies equity or a UTC baseline.
   Full-account/UTC/flow/reset qualification remains separate and blocked.
   Do not reset the completed session to obtain fills; actual active recovery,
   fills/fees/cleanup remain unverified. Strict continuity stays 0/14.
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

- Persistent maintenance-window fixture: **151 Linux checks / 149 focused Python
  tests pass** (11 additional kernel checks, 23 additional Python cases). Window
  preparation is fsynced before kernel activation; separate journals distinguish
  uncertain activation from uncertain requests. Six process-crash stages, two fresh
  replays, no-reopen refusal, failure cleanup and ordered kernel expiry pass.
  Actual host deployment, fixed storage authority and power-loss durability remain
  unqualified. Ruff/format, links, frozen hashes and diff checks pass; full application
  regression was not rerun. No host or venue changes.

- Shared-source NAT/proxy fixture: **105 Linux checks / 104 focused Python tests
  pass** (49 new kernel checks, 15 new Python cases). Actual local SNAT, direct and
  proxy paths, TCP/UDP/IPv6 refusals, durable collector dispatch, existing-socket
  revocation and rollback pass. Unlisted-endpoint reachability and cohosted-service
  collateral blocking are explicit counterexamples, not coverage qualification.
  Ruff/format, links, frozen hashes and diff checks pass; full application regression
  was not rerun. No host rules, real proxy or venue requests were changed.

- Earlier source selection and read-only host inspection are archived in the
  linked proposals; all seven host reads passed and fixed storage was absent.
  Those snapshots do not establish current runtime health or cloud mapping.

- Isolated VPS egress fixture: **56 Linux checks / 65 focused Python tests pass**.
  Four additional kernel checks and 25 Python cases cover fixed-scope ownership,
  directory/file fsync ordering, five process-crash stages, fresh detached replay,
  restart refusal and storage loss/tampering. Host `/tmp` uses ext4; kernel fixture
  storage remains private tmpfs. Power-loss/rollback and real source authority are
  unqualified. Ruff, documentation links, diff and frozen hash checks pass;
  prior application regression was not rerun. No host deployment or venue request.

- Offline reservation rehearsal: **36 new / 200 focused tests pass**. All 21
  preparations consume exactly 17 GETs / 468 documented weight / two connections.
  Exact-limit remaining budgets, signed-bound omissions, failures, uncertain
  outcomes, clocks, disk errors, rehashed tampering and fresh-process crash replay
  pass. Two fresh CLI reports match and remain blocked; all evidence is synthetic.

- Source/gateway authorship and first-request capacity reviews remain covered by
  regression. Their detailed acceptance results are in the linked progress reports.

- Joint TLS transport: **118 focused tests pass**, with **78 added cases** across
  framing, source/age binding, early control frames and end-to-end collection.
  The 25 transport scenarios cover both native/plain and TLS profiles; TLS retains
  18 connections, nine independently verified signatures and 7 normal / 304 burst
  native quotes. Two fresh CLI replays match exactly. Six fully rehashed tampering
  checks reject changed message/source/close evidence. Old synthetic archive and
  real draft hashes stay unchanged; all network peers are local fixtures.

- Earlier TLS primitive, rate parser, original-route transport, synthetic journal
  and observation-planner acceptance remain covered by the full regression.
  Detailed historical counts and evidence live in their linked progress reports.
  The original 448-weight fixture and separate 468-weight draft stay unchanged.

- V2 depth: **107 focused tests pass** (44 additional cases), including 15 snapshot
  alignments versus an unbatched reference book and v1 byte-compatible archives.
  Actual clean `cf4612c` probe: five public GETs, 21 frames, **20 native quotes**;
  three clock samples pass and two independent replay reports are byte-identical.
  All six qualification flags remain false. V1 failure and fixed session hashes
  are unchanged; the new actual evidence is recorded in the linked progress report.
- Full offline regression: **3,242 passed, 12 deselected** in 318.76 seconds.
  The 12 Postgres integration tests lack a dedicated DSN.
  Ruff for apps/tests/notebooks, changed-file formatting, research registry,
  new progress links and diff checks pass.
- Combined baseline review: **20 new tests** cover pinned-input replay, native
  fills/fees versus endpoint deltas, missing zero assets, locks, source/time/hash
  refusals and UTC nonqualification. Actual historical comparison preserves 502
  assets with zero unexplained endpoint net delta; full baseline remains blocked.
- Historical session replay: **56 tests** cover archive integrity and detached
  native BUY/SELL/fee/residual reconstruction. Actual selected replay reproduces
  the original evidence hash and 502-asset terminal view with no venue requests.
- Operator status and interrupted cleanup/cancel/native crash recovery remain
  covered by regression. Actual testnet evidence remains one accepted/canceled
  BUY with zero fills and subsequent terminal GET reconciliation; synthetic
  fills/fees/cleanup and active recovery are not actual venue acceptance.
- Original private checkpoints and pinned artifacts remain unchanged. Earlier
  verification details live in the linked immutable progress reports below;
  historical test results are not current runtime health or readiness.

## References

- [Provider coverage and prospective evidence contract](progress/portfolio-testnet-provider-coverage-2026-09-13.md),
  [pinned sources and machine-readable contract](progress/portfolio-testnet-provider-coverage-2026-09-13.json).

- [Full-account, UTC and cash-flow gap review](progress/portfolio-testnet-baseline-gap-2026-09-13.md).

- [Historical fixed-session archive replay and actual retained evidence](progress/portfolio-testnet-session-archive-2026-09-13.md).

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

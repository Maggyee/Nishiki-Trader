# Spot testnet provider coverage and prospective evidence contract — 2026-09-13

The official interfaces support a better **local market-depth reconstruction**,
but they do not close all ADR-015/016 baseline gaps. The next implementation is a
bounded, public BTCUSDT depth diagnostic, starting with offline native fixtures.
It is not an account-equity collector, a new order session or a qualification clock.
The subsequent account/market evidence requirements below remain prospective.

## Sources and what was actually checked

On September 13, five official Binance Spot testnet documents were fetched at
repository revision `b8a0f61e088c65d18a157f2e11a8e273826b6c08`
(committed September 9, 2026). Paths, retrieval times, byte counts and SHA256s are in
[the source and contract manifest](portfolio-testnet-provider-coverage-2026-09-13.json).
All links below pin that revision. These are documentation findings, not newly
observed account behavior, endpoint availability or live permission evidence.

- [G: general information](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/general-info.md)
- [R: REST API](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/rest-api.md)
- [M: market streams](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/web-socket-streams.md)
- [U: user events](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/user-data-stream.md)
- [W: WebSocket API](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/web-socket-api.md)

## Provider coverage versus qualification

| Evidence | Documented interface and fields | Supported conclusion / remaining limit |
| --- | --- | --- |
| Full account balances | R “Account information”: `GET /api/v3/account`, `omitZeroBalances=false`, UID, free/locked, `updateTime`; Memory → Database | Current response can retain all assets. It has no historical as-of selector or market-stream revision binding; `updateTime` does not create a UTC midnight snapshot. |
| Account-wide active orders | R “Current open orders”: omit symbol to include all symbols; weight 80 | Endpoint coverage includes all active symbols. Empty current orders do not establish prior absence of orders/trades. |
| Prior trades/orders | R “All orders” and “Account trade list”: required symbol, maximum 1,000 rows, cursors and time filters | Per-symbol records can reconcile identified trades/fees. Latest/default pages or one owned BTCUSDT order are not account-wide funding history. A full page needs pagination/completeness handling. |
| Prospective account changes | U: `outboundAccountPosition` has `E`, account update time `u`, and possibly changed assets; `executionReport` has order/trade IDs, `E`, `T`, quantity/price/commission | Archive raw envelopes and reconstruct native business events where qualified. `u` here is a **timestamp**, unlike market-depth `u`. These documents specify no common market/account sequence or durable replay cursor for missed user events. |
| Balance/lock changes | U: `balanceUpdate` has `E`, asset `a`, signed delta `d`, clear time `T`; `externalLockUpdate` has asset/delta/time | A received delta is an observation. The examples do not promise a complete testnet reset journal or a unique funding transaction ID. Do not deduplicate funding by timestamp or treat it as an extra balance patch on top of account snapshots. |
| Testnet funds/reset behavior | G “funds transfer” and “periodic reset”: virtual balances cannot move in/out of Spot testnet; resets erase pending/executed orders and replenish assets about monthly, without prior notification; keys are preserved | Ordinary external transfers are documented as unavailable. This does not prove no reset/replenishment occurred in a selected interval. A stable API-key fingerprint does not identify a reset generation. The reviewed interfaces provide no documented reset ID/history endpoint. |
| Key restrictions | G explicitly excludes `/sapi`; W signed subscription returns a subscription ID | Existing Ed25519 signed subscription is compatible. Signature success, `canTrade`, account permissions or subscription state cannot substitute for `/sapi/v1/account/apiRestrictions`. Do not probe that unsupported endpoint or request another Key. |
| JSON best bid/ask | M “Individual Symbol Book Ticker Streams”: `u,s,b,B,a,A`; R bookTicker has prices/quantities | Neither shown payload has event time `E`. Local arrival alone cannot qualify quote-event freshness. Switching from REST to this JSON stream does not fix that gap. |
| Timestamped depth | M “Diff. Depth Stream”: `E,s,U,u,b,a`; R `GET /api/v3/depth`: `lastUpdateId`, bids/asks | Snapshot plus correctly linked deltas can reconstruct a symbol's locally observed book and expose event time. It does not bind account revisions or guarantee complete depth/liquidation value. A depth event's `E` is not each untouched level's last modification time. |
| UTC/clock observations | R `/api/v3/time`; M/W explicit timestamp-unit configuration | Server time plus local send/receive times can bound a sample's apparent offset/RTT. Network symmetry, trusted clock discipline, midnight equity and account atomicity are not established by this request. |

The 24-hour REST `startTime`–`endTime` restriction is a **query-span constraint**.
It is not proof that all history is retained for exactly 24 hours, and it does not
relax the project's separate fixed-session 24-hour collection bound. Resets can
remove orders. Existing fixed-session history/activation rules remain unchanged.
The deposit/transfer examples in U do not override G's testnet funding restrictions
or prove that reset events will appear as `balanceUpdate`.

## Full-account capacity finding

The originally pinned admission report (SHA256
`14852d00fcc7599cf976c032377c7bfce009efe50173a45b5fc12f2732c0b564`) contains
**499 distinct route symbols for 500 priced assets**, with two assets unpriced.
Its bound original market capture (SHA256
`0b8606a2165c84b7cefb05bd7e460ab510765a3d9ef7c4a37a5b030413a4380d`) recorded a
6,000-per-minute REQUEST_WEIGHT limit. This is historical capacity, not a current
rate allowance. R now documents depth weights of 5/25/50/250 for limits
1–100 / 101–500 / 501–1,000 / 1,001–5,000 respectively.

| Hypothetical bootstrap for the 499 historical routes | Depth weight alone |
| --- | --- |
| 100 levels each | 2,495 |
| 5,000 levels each | 124,750 |

The latter exceeds 20 historical one-minute weight allowances, before account,
metadata, time or other clients' requests. It cannot fit a 60-second joint-capture
window even across a minute boundary. A smaller snapshot does not prove enough
liquidity, and staged snapshots do not magically share an account revision.
499 streams are below M's 1,024-stream connection limit, but that numerical fact
says nothing about consumer throughput, memory, stale symbols or full valuation.
No full-account fan-out is started or implied by this calculation.

## First implementation contract: public BTCUSDT depth diagnostic

This contract defines project-owned offline work and a later bounded public read
probe after its checks pass. It is not an executable config consumed by current
runners. No new service, schedule, private account query or trading permission is
created. The immutable machine-readable parameters are in the linked JSON manifest.

1. **Scope and source.** One symbol `BTCUSDT`, one market stream
   `wss://stream.testnet.binance.vision/ws/btcusdt@depth@100ms`, default millisecond
   payloads. REST allowlist: testnet `/api/v3/time`, `/api/v3/exchangeInfo` for this
   symbol, and `/api/v3/depth?symbol=BTCUSDT&limit=100`. No production/data-stream
   fallback, credentials, POST/DELETE, order client or execution engine. Use
   Nautilus's existing native WebSocket transport and native QuoteTick objects.
2. **Bounds.** One connection, 120-second maximum run, 15-second bootstrap deadline,
   10-second per-request timeout, 5-second bounded shutdown. At most three time
   requests, one exchangeInfo and one depth request: five GETs and weight 28 at
   the pinned documentation rates. Fetch current limits and account for shared-IP
   usage; inability to establish budget stops the probe. No automatic reconnect,
   repeated snapshot or HTTP retry in this first diagnostic. Ping/pong handling
   must respect M's documented control-message limits.
3. **Durable source evidence.** Archive raw successful responses/frames before
   parsing or native conversion, request selectors without signatures, receive UTC
   and monotonic times, source endpoint, symbol, timestamp unit, process/connection
   epoch, prior-row hash and sequence. Pin metadata, original closed archive and
   successful completion hashes. Failed/unfinished runs cannot produce a success
   seal. Separate observational artifacts never overwrite `native.json`, activation,
   the baseline reference or other fixed-session files.
4. **Buffer and link.** Subscribe and buffer deltas before requesting the snapshot.
   If its `L=lastUpdateId` is below the first buffered `U`, stop as unlinked. Discard
   buffered events with `u<=L`. The pinned bootstrap text explicitly requires the
   first remaining event to contain L in `[U;u]`; conservatively accept `U<=L<u`.
   The common `U=L+1` first-event case does **not** satisfy that sentence: record
   `bootstrap_boundary_unqualified` for review rather than silently relaxing the
   contract. This is a known documentation boundary, not a claim that the venue
   cannot produce such events. Later events use `U<=L+1<=u`; `U>L+1` is a gap.
   Retain/ignore obsolete events without changing the book; conflicting payloads
   for an identical update range are invalid. Numeric IDs are integers, not bools.
5. **Book semantics.** Quantity updates replace levels, zero deletes, and prices/
   quantities must be finite and nonnegative (price strictly positive). Reject
   malformed/duplicate levels, wrong symbols, ranges, epochs or units. Preserve
   the snapshot's finite coverage frontier: if the apparent best bid/ask depends
   on unseen levels beyond it after deletions, mark coverage exhausted and emit no
   qualified quote. Do not fill absent depth or missing prices. Crossed/empty sides
   remain unusable. No full-account or simultaneous-liquidation claim follows.
6. **Time and native output.** Retain venue E separately from local receipt time;
   never stamp an old snapshot with its arrival time or a ping. A candidate native
   QuoteTick uses original `E × 1,000,000` as `ts_event` and receipt UTC as `ts_init`,
   only after book linkage and local age checks. Reject future E or local age over
   5 seconds; unchanged/quiet books can therefore expire. Retain each time sample's
   UTC/monotonic send and receive times and serverTime; RTT over 500 ms, wall versus
   monotonic elapsed discrepancy over 50 ms, or sample offset inconsistent with
   ±250 ms local UTC stops qualification. With serverTime in milliseconds, require
   the entire sample offset interval `[S-receiveUTC, S+1ms-sendUTC]` to fit within
   ±250 ms; do not assume symmetric latency or carry this bound across an unobserved
   clock step. Those are conservative diagnostic
   thresholds, not proof of trusted UTC or a risk-policy amendment. Do not rewrite E.
7. **Failure and output.** Any reconnect, `serverShutdown`, gap, clock regression,
   buffer/size limit, disk failure or deadline ends the segment without readiness.
   Limits: 1 MiB/frame, 16 MiB/4,096 buffered events (whichever first), 64 MiB total
   archive. Preserve already written evidence; never silently drop frames and keep
   a healthy label. Summaries expose observed counts, IDs, age and failure reasons.
   `current_account_verified`, `account_market_atomic_revision_verified`,
   `valuation_qualified`, `baseline_qualified`, `runtime_ready` and
   `new_orders_authorized` stay false. A local linked book is a narrower result.

The first code entrypoint should be a pure project-owned
`apps/strategies_nautilus/portfolio_market_depth.py`, with offline tests, followed
by a separate bounded public CLI. No implementation exists at this commit.
Acceptance must cover snapshot overlap, the documented boundary above, missed/
obsolete/duplicate/conflicting updates, deletions and exhausted coverage, malformed
frames, wrong source/unit, future/stale/quiet data, clock steps, buffer/disk failure,
interruption and two fresh-process replays with identical numeric native quotes.
Transport tests must prove only the allowlisted public requests occur.

## Subsequent account/market evidence contract

After single-symbol acceptance, size a fixed route set from a fresh selected full
account plus metadata using ADR-016's existing deterministic route policy. Preserve
all assets and unpriced exclusions, aggregate REST/control-message budget across
the actual shared IP, and demonstrate bounded stream throughput and memory before
fan-out. No old price/route snapshot becomes fresh just because it is replayable.

Reuse the existing read-only user stream and observation journal in a **separate
observation profile**, not SessionJournal with native order callbacks. Bind the
selected initial UID/key/endpoint; retain all full account/open-order snapshots and
raw account/fee/funding/lock/termination events. Archive a raw event before any
classification. Existing observation code already preserves supported envelopes;
it does not provide a funding ledger or account/market synchronization protocol.
Do not add `balanceUpdate` to snapshot balances as a second settlement operation.
Timestamp/amount equality is insufficient to identify or deduplicate funding.

Represent combined observations as intervals and a vector of independent receipt/
market-update references, never as one invented common revision. Account `u`,
execution `T`, depth `U/u` and local journal seq have different meanings. Account
and market equality tests can fail closed on drift, but cannot certify atomicity.
Any disconnect, unknown event, asset/source change, unexplained delta or suspected
reset marks the interval unqualified and retains the incident; no automatic rebase.

A future midnight experiment must preselect its UTC boundary, begin recording
before it, retain both sides and all relevant event/receipt times, and report exact
coverage and uncertainty. First-after-midnight quotes cannot initialize qualified
day-open equity. Without a complete independent baseline, valuation and flow/reset
history, current/day-open/peak equity and daily/peak losses remain null. Recording
more samples may improve diagnostics but cannot close undocumented provider guarantees.
Provider-independent evidence or a separate explicit qualification/scope decision
is still required; this document changes neither ADR-015/016 nor the 0/14 gate.

## Verification and boundaries

Five official revision-pinned source files were retrieved and their hashes checked.
The 499-route count and both depth-weight calculations were recomputed from the
original hash-pinned private artifacts; no private contents or Key were published.
Source/contract JSON, local document links and whitespace were checked. This is a
documentation/contract increment; no application code changed and the prior
**2,697 passed / 12 deselected** regression remains the latest code verification.
No new tests or full-suite rerun are warranted for these documentation changes.
No exchange endpoint, credentials, upstream source, execution path, service,
schedule, fixed session or production account was accessed or changed.

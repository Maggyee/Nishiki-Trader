# Prospective public depth v2 bootstrap decision — 2026-09-13

**Decision:** provide an explicitly selected `testnet_public_depth_evidence_v2`
profile whose first remaining depth event must contain the **next unseen update
ID, `L+1`**. The v1 default, contract, historical reports and failed archive remain
unchanged. This decision is a local public-market engineering interpretation under
the operator's delegated continuation; it does not amend ADR-015/016/017 or qualify
account equity, UTC baselines, flow/reset history or trading readiness.

The frozen [v2 contract JSON](portfolio-testnet-public-depth-v2-contract-2026-09-13.json)
is SHA256 `885a636f4fd2daf8dbd1282e47639bcc12e10db60d685f8d452e0eb664789a04`.
It binds the original contract SHA256
`376eebff8fd2309027df2334f39d3ec73fd017f6a8afff1b3f0e3ea3023d879e`,
the pinned source and the original failure that motivated this review.

## Source reconciliation

The previously retrieved official
[testnet stream documentation](https://github.com/binance/binance-spot-api-docs/blob/b8a0f61e088c65d18a157f2e11a8e273826b6c08/testnet/web-socket-streams.md#how-to-manage-a-local-order-book-correctly)
was rechecked against SHA256
`13428b2e5f4d9dc7654331d4c65e6befea776d2b7408fe5980343708f72d96e6`.
No newly retrieved documentation, exchange request or upstream confirmation was
needed for this interpretation. Relevant statements in that exact file are:

| Line | Official wording | Consequence |
| --- | --- | --- |
| 612–613 | `U`: first update ID; `u`: final update ID | Update ranges are inclusive. |
| 634 | Discard `u <= lastUpdateId`; the first remaining event “should now have `lastUpdateId` within its `[U;u]` range.” | Read literally, this excludes the exact successor. V1 deliberately froze that interpretation. |
| 635–636 | Set local book/update ID to the snapshot, then “Apply the update procedure below to all buffered events, and then to all subsequent events received.” | The detailed algorithm expressly applies to bootstrap events too. |
| 642–644 | `U` greater than local update ID + 1 means missed events; normally next `U` equals previous `u + 1`. | The algorithm accepts a range starting at `L+1`. |
| 645–648 | Set quantities, delete zero quantities, then set local update ID to `u`. | Updates are absolute level replacements, not amounts to add. |

These statements are internally inconsistent at one boundary. V2 prioritizes the
explicit application algorithm over the first-event expectation in line 634.
**This is a project interpretation, not an upstream erratum or a claim that Binance
has confirmed the change.** The failed observation is corroborating boundary data;
it is not itself proof of global market continuity or provider guarantees.

After ignoring `u<=L`, integer `u` is at least `L+1`. Therefore the missing-update
check `U>L+1` leaves precisely `U<=L+1<=u` as the acceptable range. Starting at
`L+1` omits no update after the selected snapshot. Overlapping ranges can be
applied because quantities replace values; replay never sums repeated quantities.
A jump past `L+1` remains a hard gap even during the first application.

The other bootstrap prerequisite is unchanged: if snapshot `L` is below the
**first buffered** `U`, stop without fetching another snapshot. Thus a first buffer
beginning at 101 with snapshot 100 still fails this separate conservative guard.
V2 accepts the exact-successor case after a qualifying earlier buffered event has
been covered by the snapshot, as happened in the retained v1 observation.

## Explicit revision and evidence boundary

Only three fields differ in the inherited diagnostic specification: profile name,
first remaining range condition, and the meaning of the `U=L+1` boundary. Source,
symbol, timestamps, precision, finite-depth/frontier gates, five-second age,
clock thresholds, public selectors, limits, zero retries/reconnects, durable raw
persistence and the six permanently false qualification flags are unchanged.

`--revision 2` must be supplied for either a v2 probe or replay. Omission retains
v1 behavior. Every journal row carries the selected profile; the start and summary
seal bind its contract hash. A selected original archive hash plus a different
revision cannot migrate the evidence. Unknown/noninteger/bool revisions are
rejected before archive creation. No archive relabeling, resume or success-seal
repair operation exists.

The original failed archive
`f2af2aba60ab0bbde04f37948b7f4d03b0222ec1cd07b36acadd18685eabbfed`
remains byte-identical and fails replay under **both** selections. Its bootstrap
refusal is a valid v1 result. An independently generated successful v1 fixture from
original code `16b1af6` has SHA256
`23f6baa0ca2af45e152a2cba5a6899a500b13cbb3c4543b211d31c2341c0a009`;
the updated code reproduces those exact bytes and native values without migration.

## Offline acceptance and prospective attempt

**107 focused tests pass**, including 44 additional cases. Fifteen snapshot
positions are checked against an independently maintained, unbatched reference
book; overlap and exact-successor boundaries, true initial/later gaps, obsolete
updates and the unchanged first-buffer guard are covered. Cross-revision rows,
headers, seals and incomplete segments are refused. Both revisions run through
public transport success/failure tests with the identical whitelist/budgets.
Two fresh v2 replay processes produce identical numeric native quote reports.
Existing native Rust ping/zero-reconnect and v1 failure tests still pass.

Full offline regression: **2,804 passed, 12 deselected in 218.11 seconds**
(`-m 'not network and not postgres'`). Ruff for `apps/` and `tests/` and the
research registry check pass. No upstream source is changed.

After offline acceptance and this contract/implementation are committed and pushed,
perform **one new v2 attempt** in new files and a new connection epoch. The selected
collection budget is 20 seconds (maximum five GETs/weight 28, one stream, zero
retries/reconnects; inherited 15-second bootstrap, 10-second request and 5-second
shutdown bounds). This is a new prospective diagnostic, not a continuation of the
failed v1 segment. Record failure as failure without another attempt. If completed,
pin the original archive and seal hashes and compare two fresh-process replays.
The actual outcome will be recorded in a separate progress report.

No private endpoint, Key, execution engine, service, schedule, risk/SourcePolicy
change or fixed ADR-017 session write is part of this work. Full-account valuation,
UTC/flow/reset qualification, actual fills/cleanup and strict 0/14 remain blocked.

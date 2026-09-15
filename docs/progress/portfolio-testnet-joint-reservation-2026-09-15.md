# Offline joint per-step reservation rehearsal — 2026-09-15

The operator confirmed that no readable complete gateway records are available
and selected further offline acceptance. A separate rehearsal now combines the
selected source/gateway signatures with durable preparations for the draft's
maximum request schedule. Each step rechecks the remaining budget and previously
recorded consumption. Failed, uncertain or interrupted steps cannot become fresh
attempts in the same archive.

This exercises local accounting and persistence. It does not reserve capacity at
a gateway, qualify a signer authority or invoke a transport. The real capture
draft remains unchanged at SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
The original 448-weight loopback profile and all consumed ADR-017/public-depth
scopes remain untouched.

## Maximum schedule and remaining capacity

`apps/strategies_nautilus/portfolio_joint_reservation.py` implements the separate
`portfolio.offline_joint_reservation.v1` profile. Its 21 operations are derived
from the pinned contract's maximum three-symbol budget: 17 GETs, three account
WS API operations, and one market connection. The initial time and early metadata
GET precede account connect/subscribe; routing reads precede market connect and
the three depth snapshots; unsubscribe follows the final account/time reads.
The 17 GETs include both full four-GET account collections.

The maximum remains **462 REST + six account WS API = 468 documented weight**.
The market connection has `charge_unresolved=true` and no numeric weight field.
It contributes no *documented* weight to that sum; the unknown charge remains a
blocker in every report. This is a maximum schedule exercise, without same-run
route discovery, market observation, actual account collection, or provider fills.
No cheaper route, snapshot resizing, retry or reconnect is introduced.

Before each preparation, the state machine independently verifies the candidate
and its two signatures using the original policy hash and scope selected at
archive creation. The candidate and signed bundle are retained as original bytes.
The existing authorship/full-scope review is preserved intact. A separate derived
review replaces only its full-scope capacity calculation with:

`headroom = limit - current_used_upper_bound - other_clients_upper_bound - remaining_documented_operations`

The current operation belongs to the remaining set. Its budget is consumed only
after the preparation has been persisted; an outcome never refunds it. Counts
come from the accepted archive prefix and immutable operation schedule. Callers
cannot select a smaller remaining budget, skip a preparation or change its method,
path, parameters or weight. Account/market connection bounds stay separate, with
the same conservative union calculation used by the first-request reviewer.

Each fresh signed bound must be at least the preceding signed bound plus the
intervening local preparation's applicable consumption. Both weight scopes retain
the original conservative full documented cost; connection increments apply to
their own endpoint; REST request increments apply to RAW_REQUESTS. This deliberately
rejects narrowing a previous upper bound, even if a future gateway could prove a
tighter one. A bound that omits the previous preparation fails rather than being
silently corrected. This checks supplied bounds; it does not reconstruct or
authenticate complete gateway traffic records.

Rate dimensions and limits cannot change mid-rehearsal. Observed counters cannot
regress, fixed accounting buckets cannot roll over, and server-clock anchors must
remain consistent with elapsed local time. Every existing freshness, coverage,
other-client-horizon and unknown-scope check still applies. Only the six explicit
authority/implementation/unknown-market-charge blockers are tolerated for this
offline exercise; any additional evidence or capacity blocker stops it. None of
the six is removed or turned into a dispatch permit.

## Durability, failure and detached replay

`ReservationRehearsal` creates one new 0600 archive with `O_EXCL`/`O_NOFOLLOW`,
syncs its directory, and writes hash-linked events with file fsync before returning
from each preparation. There is at most one pending operation. Only a matching
synthetic `succeeded` outcome permits another step. `failed` and `uncertain` end
the rehearsal with consumption retained. Refusals record an abort when possible;
disk failure blocks further operations even if the incident cannot be persisted.
The archive is bounded to 64 MiB including a four-KiB incident reserve; candidates
retain the 16-MiB cap and policy/bundle inputs the 64-KiB caps.

Preparations have the draft's 120-second capture deadline; outcomes have a
ten-second deadline; the complete event history has the shared 125-second outer
bound. UTC/monotonic drift beyond 50 ms is refused. These are checks at recorded
rehearsal event times. Synchronous verification/fsync is not a real dispatch fence
or a preemptible networking deadline; there is no subsequent transport call.

Creation on an existing path is refused, including after abrupt process exit.
There is no resume/reset API. Read-only replay of a valid unsealed prefix returns
`incomplete_no_resume`, preserving the prepared count and pending operation index.
Truncated, corrupt, re-ordered or semantically rewritten archives fail. A failed
fsync can leave an unusable archive, which remains unavailable for overwrite.
This guard belongs to the selected local rehearsal file; using another file for
another offline test is possible and does not implement the fixed real one-shot
scope's process-independent activation rule.

```bash
.venv/bin/python -m apps.ops.portfolio_joint_reservation \
  --archive SELECTED-REHEARSAL.jsonl --archive-sha256 ORIGINAL-ARCHIVE-SHA256 \
  --policy-sha256 INDEPENDENTLY-SELECTED-POLICY-SHA256 \
  --scope-id INDEPENDENTLY-SELECTED-SCOPE \
  --report data/NEW-REHEARSAL-REPLAY.json
```

The CLI only replays and writes a new private report; it cannot create a rehearsal,
capture, load credentials or dispatch operations. Code **2** means a report was
written with networking still blocked, including for a completed rehearsal.
Code **1** means replay/publication failed; argparse handles usage errors.
The report exposes consumed counts and the last *preparation-time* remaining
review, including the original full-scope authorship review. It keeps
`network_admitted`, `capacity_reserved`, `scope_consumed`, source/egress
qualification and all six qualification flags false; qualified equity/loss and
common account/market revision stay null. Venue requests made remain zero.

## Acceptance and next entrypoint

**36 new tests / 200 focused tests pass.** The complete 21-step replay accounts
for 17 GETs, 468 documented weight and two connections. An exact-limit scenario
finishes with zero weight headroom without counting prior consumption twice;
the original first-request review is retained and still rejects re-reserving the
whole scope late in that scenario. Other cases cover understated signed bounds,
changed limits, missing coverage, extra client usage, stale signatures, clock and
bucket changes, failed/uncertain outcomes, duplicate and reordered steps, fsync
failure, archive exhaustion, existing files/symlinks and rehashed tampering.

A subprocess exits abruptly after its first durable preparation; detached replay
finds that pending attempt and creation on the same path is refused. Two fresh
CLI processes produce identical completed reports without changing original
bytes. Socket/DNS guards cover the complete local lifecycle and CLI. All signed
inputs, outcomes and gateway bounds are synthetic. Full offline regression passes
**3,242 tests, 12 deselected in 318.76 seconds**
(`-m 'not network and not postgres'`). The Postgres integration cases have no
dedicated test DSN. Ruff for apps/tests/notebooks, changed-file formatting,
research registry, 124 local documentation links and diff checks pass. The
original capture contract hash is unchanged. `docs/project-status.md` records
the same results and keeps earlier acceptance details in their progress reports.

Next obtain and qualify actual source/gateway authorities, source-bound original
records and enforceable all-client usage bounds, then integrate them with real
dispatch-time freshness and the separately durable one-shot capture profile.
An asynchronously delivered signed snapshot must bridge its observation-to-use
gap using qualified enforced coverage; this rehearsal does not create that
missing evidence. Unknown market-connection charges and full-account/UTC/flow/reset
qualification remain blocked. Strict testnet continuity stays **0/14**.

Changed files: the two new `portfolio_joint_reservation.py` modules, their strategy
test file, both app READMEs, `docs/agent-reading-list.md`, `docs/project-status.md`,
and this report. No upstream code, execution runner, SourcePolicy, schedule,
SignalEvent contract or live order path changed.

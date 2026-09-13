# Fixed-route coverage and account/market interval design — 2026-09-13

The next engineering scope is **BTC, ETH and BNB's existing deterministic USDT
conversion routes**, capped at three distinct market streams, while retaining
full-account observations before and after the market interval. These are the
first three pivots of ADR-016's existing fixed pivot order. This is a bounded
multi-symbol transport experiment, not a new asset allocation or an account-equity
subset. Missing target routes are not replaced with convenient assets.

The new offline planner replays original account/market evidence and the closed
BTCUSDT v2 archive, computes route exclusions and complete request costs, and
writes a new private report. It makes **zero venue requests**, loads no Key and
never writes the fixed session. The [machine-readable design](portfolio-testnet-joint-observation-design-2026-09-13.json)
has SHA256 `05febee1b7b987c7cd3eb279ed7492f4988ecba5966b942fbc4d51f9c55f2ecb`
and is prospective: multi-symbol/combined-account collection is **not implemented or
authorized by the report**, and the v1/v2 single-symbol attempt scopes stay consumed.

## Original evidence and actual planning result

The planner revalidates the original initial selection, account archive/collection,
bound all-symbol metadata/bookTicker capture, and the closed v2 archive. It calls
the existing admission reviewer (including isolated native amount mapping) and
explicit v2 native replay; a saved report's success flags are not trusted as input.
The September 11 account and September 13 BTC observations are separate historical
intervals, not one joint capture or a fresh route selection.

| Selected input | SHA256 |
| --- | --- |
| Initial account observation | `205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc` |
| Account archive, collection `acd69464-4f34-4741-bbfd-46fe585b2e11` | `0b4638db102fa21f7d574d0184c6ba27ebdde9d653b6fca33dc8f6f276bd78c3` |
| Bound all-symbol market capture | `0b8606a2165c84b7cefb05bd7e460ab510765a3d9ef7c4a37a5b030413a4380d` |
| Closed public v2 depth archive | `76d93c90028719907c40eaa870192bbf255af792a49131fabc4fd38b25f8d8aa` |

The selected output is `data/spot-testnet-observation-plan-20260913.json`, SHA256
`0a00f4d27a8bc0377ef34c2b888f9e99ffb564a4ce384f0cbdd5a33cf529ca8f`.
It remains ignored and mode 0600. Per-asset coverage stays in that private report;
no account amounts, UID or credentials are published here.

| Historical coverage | Count |
| --- | ---: |
| All account assets retained | 502 |
| Assets with indicative marks, including USDT | 500 |
| Distinct required route symbols | 499 |
| Pilot route symbols / assets with all their legs selected | 3 / 3 |
| USDT requiring no market leg | 1 |
| Assets outside the pilot route set | 496 |
| Unpriced nonzero assets | 2 |
| Assets exceeding a historical top-book leg | 65 |
| Routed assets affected by an unavailable side for a native two-sided quote | 2 |

The historical pilot union is **BNBUSDT, BTCUSDT, ETHUSDT**. Its three assets have
no historical top-book capacity or two-sided-quote blockers, but this says nothing
about fresh prices or future depth. The native quote core requires both sides;
ADR-016's indicative routing may use just one side. A route's existence therefore
does not guarantee native QuoteTick availability. All omitted, unpriced and depth
exclusions remain explicit; no partial subtotal becomes account equity.

## Complete shared-IP budget

Each existing full-account collection is **account → openOrders → openOrders →
account**, with `omitZeroBalances=false` and no symbol filter on open orders.
At the pinned official weights this costs **20+80+80+20 = 200**. Two complete
collections cost 400, not 200. The design reuses this consistency check without
calling repeated reads an atomic exchange revision.

| Operation | Count | Total weight |
| --- | ---: | ---: |
| Full-account GETs | 4 | 80 |
| All-account openOrders GETs | 4 | 320 |
| All-symbol exchangeInfo GET | 1 | 20 |
| All-symbol bookTicker GET (routing only) | 1 | 4 |
| Server time GET | 3 | 3 |
| 100-level depth GET, one per pilot symbol | 3 | 15 |
| Account WS API connection | 1 | 2 |
| Signed subscription / unsubscribe | 1 each | 4 |
| **Total** | **16 GETs + WS API operations** | **448** |

There is one combined market connection and one account WS API connection.
Market ping/pong limits and account WS API request costs are distinct constraints;
market pongs echo the payload and remain within the documented per-connection
control rate. No market subscription JSON is needed with a fixed combined URL.
No HTTP/snapshot retry, reconnect or production fallback is planned. Subscribe
before the initial account collection; unsubscribe/close both transports before
sealing. Retain unsigned selectors and raw data, never signatures or a Key in logs.

The pinned REST documentation gives 5/25/50/250 depth weight at limits
100/500/1000/5000. WS API documentation charges 2 for its connection, 2 for signed
subscription, 2 for unsubscribe, and states that weight is shared per IP. The
retained official source hashes were checked again; no source file was refetched.

| Hypothetical 499-symbol snapshots | Depth weight | Including joint-observation overhead |
| --- | ---: | ---: |
| 100 levels | 2,495 | 2,928 |
| 500 levels | 12,475 | 12,908 |
| 1,000 levels | 24,950 | 25,383 |
| 5,000 levels | 124,750 | 125,183 |

Only the 100-level arithmetic fits one recorded 6,000/minute allowance, even before
other clients consume it. That does not prove enough liquidity, freshness, server
capacity or consumer throughput. The future dispatcher must observe current limits
and shared-IP usage before additional calls and preserve reserved final-account,
time and unsubscribe costs. Missing/drifting budget evidence or 429/418 ends the
attempt; old usage 28 is not a reusable reservation. Connection-attempt limits
need their own current shared-IP accounting. The planner grants no run admission.

## Memory, throughput and interval semantics

The replayed BTC segment contains 21 raw frames / 2,843 payload bytes in 18.264627
seconds. Its largest frame is 408 bytes; observed rolling-one-second maxima are
5 frames and 600 raw bytes. The entire durable archive is 108,283 bytes. This quiet
single-symbol sample does not establish throughput for ETH, BNB or 499 symbols.
The two-sided core and native transport still require multi-symbol fault/load tests.

The proposed global bounds are 120 seconds plus at most 5 seconds shutdown,
15 seconds market bootstrap from market connection, 10 seconds per request and
up to 20 seconds observation after every selected symbol links. The global deadline
wins over all phase deadlines; running out of time fails, without widening it.
Retain v2's five-second event age and clock intervals. Each symbol needs its own
snapshot, sequence, freshness and finite frontier; a healthy BTC stream cannot
refresh ETH or BNB. One symbol's gap/quiet expiry ends the combined segment.

Use a **shared** 16 MiB / 4,096-event pending budget and 64 MiB durable archive
cap across market/account callbacks, not three independent 16 MiB allowances.
Frame limit remains 1 MiB. These are serialized-byte bounds, not a process RSS
promise or a native socket allocation setting. Overflow/fsync failure must retain
an incident and stop conversion; do not drop a frame and continue with a healthy
label. Large/deep account responses must also respect the bounded archive.

A completed future archive must retain a vector of independent references:

- Selected original UID/key/endpoint binding; one signed account epoch, both full
  account collections, their local intervals and raw event/journal references.
- Each market symbol's own epoch, snapshot L, update U/u, event E, UTC/monotonic
  receipt and raw hash. Combined-frame outer stream and inner symbol must agree.
- Manifest fixation time, actual request/weight/control counters, observed incidents,
  closure state, input hashes and completion seal for detached replay.

There is **no common exchange revision**. Account `u` is a timestamp, market `u`
an update ID, and journal seq a local counter. Overlap or equal endpoint balances
cannot prove atomicity, complete flows or absence of reset. Preserve raw balance,
funding, fee, lock and termination envelopes before classification. Unsupported
or ambiguous events, asset/source changes, unexplained deltas and suspected resets
end the interval without rebase. Never apply `balanceUpdate` a second time on top
of a returned account snapshot or deduplicate funding solely by time/amount.
UTC crossing is retained as an explicit unqualified boundary; no midnight label
or first later quote initializes day-open equity. Qualified equity/loss fields
stay null and all six account/valuation/baseline/runtime/order flags stay false.

## Implementation entrypoint and verification

Implemented: `apps/strategies_nautilus/portfolio_observation_plan.py` and
`apps/ops/portfolio_testnet_observation_plan.py`. The CLI requires all four original
paths/hashes plus the selected collection; it writes one new private plan and
returns counts/hash only. Existing valuation, risk, capture and execution code
is unchanged. This task adds no network runner, service or schedule.

Next implement an **offline multi-symbol journal and combined-frame dispatcher**
with synthetic interleaved account/market callbacks. Generalize the project-owned
depth core through explicit symbol/profile selection; keep the existing BTC v1/v2
archive semantics. Demonstrate shared-buffer pressure, disk failure, one-symbol
gaps/staleness, missing assets, foreign epochs, unknown events and independent
native replays. Then review a separately bounded actual collection contract using
a fresh selected account/metadata/book route set. The present JSON is a design,
not permission to run a new joint experiment or repeat the consumed depth probes.

**16 focused tests pass**: original-byte replay and hash refusal, all-asset
exclusions, deterministic direct/two-hop routing, shared legs, missing targets,
one-sided quotes, complete private/WS costs, four full-route depth budgets,
failed-archive refusal and exclusive private CLI output with network blocked.
Full offline regression: **2,820 passed, 12 deselected in 222.07 seconds**.
Ruff for apps/tests and the research registry check pass.
No upstream source or live order path was touched. The fixed ADR-017 scope and
strict 0/14 remain unchanged. `docs/project-status.md` records this next step.

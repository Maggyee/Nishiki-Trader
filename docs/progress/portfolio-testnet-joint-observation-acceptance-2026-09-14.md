# Synthetic joint-observation acceptance — 2026-09-14

The next offline increment of the [joint design](portfolio-testnet-joint-observation-design-2026-09-13.md)
is implemented: one durable callback queue, three independent depth books, two
full-account observation intervals and detached native replay. This uses the
explicit `portfolio.synthetic_joint_observation.v1` profile. It accepts only a
synthetic UID/key/epoch binding and cannot qualify an actual account archive.
No venue request, credential load, service or new probe was performed.

## Implementation and evidence semantics

`apps/strategies_nautilus/portfolio_joint_observation.py` owns the serialized
receipt queue and evidence state. `portfolio_market_depth.py` now accepts explicit
symbol/base/quote selection; default BTCUSDT and v1/v2 archive behavior stay
unchanged. Each selected book retains its own snapshot, update sequence, event
age and finite depth frontier, and produces native Nautilus `QuoteTick` values.
The combined-frame stream name must agree with the selected inner symbol and
market epoch. One symbol's gap, stale event or quiet expiry stops the segment.

Both market and account callbacks, queued REST receipts and all pre-snapshot
market buffers share **16 MiB / 4,096 pending receipts**. Raw frames have a **1 MiB**
limit; the combined archive has a **64 MiB** cap, including a reserved **4 KiB**
incident tail. Tests may only lower these bounds. These limits count canonical
serialized receipt bytes, not Python object overhead, RSS or native socket memory.
Overflow records a reason and the rejected receipt hash; it cannot retain an
unbounded payload. Earlier queued/raw receipts remain in the failed archive.

Raw bodies are hashed, base64 encoded, flushed and fsynced before classification.
Each dequeue also persists a dispatch receipt referencing the oldest pending
receipt and recording the processing UTC/monotonic clocks. Replay reconstructs
this same queue. Freshness is checked at both receipt and processing, including
snapshot application, so a fresh-on-arrival event cannot survive a stale backlog.
Mutable caller fields are copied before persistence. A persistence error prevents
conversion and completion. If the disk cannot retain even an abort, the unsealed
or inconsistent prefix remains a failed archive; no durability guarantee is made
for failed fsync. Synchronous fsync is not preempted by the clock checks.

The synthetic schedule is the existing complete planner sequence: **16 GET
responses / three WS API operations / 448 documented weight** for three streams.
It includes both four-GET account collections, all-symbol metadata and routing
bookTicker, three depth snapshots and three clock samples. The state checks
selectors, response status, request deadlines, reserved remaining weight, one
connection per transport, account subscription, payload-echo pongs and the
five-controls-per-second limit. Bootstrap is bounded from market connection;
120-second global, 15-second bootstrap, 10-second request, 20-second post-link
and five-second closure bounds are not enlarged. These are receipt-model checks,
not observed network throughput or current shared-IP/connection-attempt admission.

Account collections retain all balances and account-wide orders, require equal
account/open-order endpoints and compare the complete asset set and free/locked
amounts with the synthetic initial selection. This first profile requires no open
orders and unchanged amounts. Market callbacks may interleave inside account
collections. Unchanged `outboundAccountPosition` callbacks are allowed between
collections; a callback during a collection invalidates it. Other balance/funding,
lock, execution, termination or unknown events are persisted then refused for
review. No amount is added to a snapshot, no event is deduplicated by time/amount,
and no fee or cash-flow interpretation is inferred.

The completion seal retains a vector of independent account intervals and market
references; local sequence, account timestamp and market update ID remain distinct.
The latest raw market reference can be obsolete; the book's separately reported
last applied ID/event time and native quotes remain authoritative for its local
reconstruction. `common_revision` is null. UTC crossing is explicit and never
initializes day-open equity. All six account/atomicity/valuation/baseline/runtime/
order qualification flags stay false, and qualified equity/loss fields stay null.

## Detached replay and verification

`apps/ops/portfolio_joint_observation.py` has only a replay mode. It requires a
selected archive hash and a new private report path, preserves original bytes,
and prints only status/report hash and qualification flags. It opens no socket
or key. Each replay reconstructs all native quotes and maps both full CASH
snapshots in separate native diagnostic processes. An unpriced or unselected
asset remains in the account; missing native metadata fails the full mapping.

```bash
.venv/bin/python -m apps.ops.portfolio_joint_observation \
  --archive data/SELECTED-SYNTHETIC-JOINT.jsonl \
  --archive-sha256 SELECTED-SHA256 \
  --report data/NEW-SYNTHETIC-REPLAY.json
```

**51 new tests pass.** They cover interleaved three-symbol/account callbacks,
shared byte/event pressure across queued and bootstrap data, exact independent
native quote expectations, two fresh-process byte-identical reports, full CASH
mapping including an unpriced asset, wrong symbols/epochs/hashes, malformed raw
frames, unknown events before refusal, missing/changed assets, lock/free deltas,
quiet expiry, sequence gaps, delayed dispatch, failed fsync, archive exhaustion,
UTC crossing, request/clock/control budgets, rechained semantic corruption and
private output overwrite refusal. The replay CLI also passes with Python socket
creation blocked. Existing v1 fixture bytes and v2 tests remain in regression.

Full offline regression: **2,871 passed, 12 deselected in 250.73 seconds**
(`-m 'not network and not postgres'`); the 12 Postgres tests lack a dedicated DSN.
Ruff for apps/tests/notebooks, formatting of changed Python files and the research
registry check pass. `docs/project-status.md` records these results and next steps.
No upstream code or live trading path was touched. The SignalEvent contract,
SourcePolicy, ADR-015 risk policy, fixed ADR-017 files, consumed v1/v2 attempts
and strict continuity **0/14** remain unchanged.

## Next implementation entrypoint

The earlier planner and its immutable historical report are unchanged. This
synthetic journal does **not** consume that report as fresh routing authority.
The retained bookTicker body is routing-only raw evidence; this profile does not
certify route selection, per-asset conversion coverage or sufficient market depth.
Before any actual joint capture, implement an offline transport integration that
binds the planner to freshly selected original account/metadata/book bytes,
accounts for current shared-IP and connection-attempt usage, and feeds this queue
from the native signed account and combined public transports. Exercise loopback
transport shutdown, callback load and failure handling with that integration.
Then review a separately bounded actual collection contract. Do not relabel this
synthetic profile or reuse the consumed single-symbol scopes. Full-account/UTC/
flow/reset qualification and actual fills/cleanup remain separate blockers.

Changed files: `apps/strategies_nautilus/portfolio_joint_observation.py`,
`apps/strategies_nautilus/portfolio_market_depth.py`,
`apps/ops/portfolio_joint_observation.py`,
`tests/strategies_nautilus/test_portfolio_joint_observation.py`,
`apps/strategies_nautilus/README.md`, `apps/ops/README.md`,
`docs/agent-reading-list.md`, `docs/project-status.md`, and this report.

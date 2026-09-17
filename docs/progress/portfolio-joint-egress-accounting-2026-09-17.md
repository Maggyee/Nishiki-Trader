# Local joint TLS collection consumes durable operation attempts

Date: 2026-09-17. Local synthetic peers only; zero venue requests.

The existing complete joint TLS collector now has an explicit
`run_accounted_tls_loopback` entrypoint. It couples its original operation
schedule and per-dispatch budget checks to the prospective attempt ledger.
The three-symbol fixture completes **20 operations, 16 GETs, 448 documented
weight and 18 TLS connections**, including both full account collections,
account subscribe/unsubscribe, routing, three depth snapshots and control frames.
Market connection and provider control charges remain unknown.

This is a local transport/accounting milestone. The collector runs in the
ordinary project Python/Nautilus process. It is **not yet connected to the
installed dedicated-UID/kernel gateway**. The installed system-Python fixture
still owns only its fixed exchangeInfo GET. No root import of project/site code,
new installed source inventory, host deployment or external endpoint is added.

## Original records and dispatch ordering

`portfolio_joint_egress.py` reuses the existing joint transport, TLS framing,
semantic/native replay and attempt writer. The new fixed ledger profile is
`portfolio.local_joint_egress_attempt_ledger.v1`, with its own consumed directory
`local-joint-egress-attempts-v1`. The old ledger profile, operation vocabulary
and directory remain unchanged; old one-shot gateway scopes cannot be reopened.

The joint state machine first validates the exact next method, selector, route
and remaining budget, then persists its operation preparation and dispatch.
Only afterward may accounting persist the corresponding attempt, including a
SHA256 of that exact joint prefix. A binding check follows fsync. Before each
TCP/TLS connection or business write, the backend checks pending ownership,
operation identity, one-time connect/write ordering, original sample freshness
and accounting buckets again. It never hands a socket to another process.
Synchronous verification/fsync is bounded by archive size but is not preempted
by async/socket deadlines. These are ordinary-process checks, not a kernel or
adversarial-caller boundary.

A validated semantic response precedes the durable successful outcome. Outcomes
select their own original joint prefixes; the next operation cannot prepare until
that outcome is persisted. Failure, cancellation, storage/manifest drift or a
refused boundary latches the ledger. Already prepared attempts remain consumed,
including when TLS fails before HTTP or a request has no accepted response.
A failed preparation fsync can leave no accepted attempt record; the directory
remains consumed and no request is sent. SIGKILL after successful preparation
preserves a pending attempt and creation on the same scope fails.
There is no resume, refund, retry, reconnect or reset API.

Pongs and close frames keep the existing original-ping, payload, control-rate and
closure checks. Accounting is rechecked immediately before those writes. Their
original preparations stay in the TLS journal; they do not become invented
zero-cost provider operations. A failed audit closes local descriptors without
sending further application control frames.

## Original counter age and offline review

The TLS backend now samples receipt time immediately after `read`, before byte
encoding or journal persistence. REST counters use the first chunk completing
the headers; account WS counters use the original complete-message receipt.
Body completion, semantic dispatch and disk delay cannot refresh those times.
A local metadata body delayed 5.2 seconds leaves the counter stale and blocks
the next operation. These timestamps remain local receipts, not provider clocks.

The existing joint replay CLI accepts a selected companion attempt ledger:

```bash
uv run python -m apps.ops.portfolio_joint_observation \
  --tls-loopback-profile --archive JOINT.jsonl --archive-sha256 JOINT_SHA256 \
  --attempt-ledger ATTEMPTS.jsonl --attempt-ledger-sha256 ATTEMPTS_SHA256 \
  --report NEW-REPORT.json
```

Successful review requires complete original TLS/native replay and all matching
ledger preparations/outcomes. It checks original prefix hashes, classifications,
caller labels, operation indices and cross-file clocks. Neither self-selected
hashes nor a valid local history authenticates the source or proves complete
traffic coverage. Partial/failed joint archives cannot claim completed review.
Their consumed attempts remain separately replayable:

```bash
uv run python -m apps.ops.portfolio_egress_ledger --joint-profile \
  --archive ATTEMPTS.jsonl --archive-sha256 ATTEMPTS_SHA256 \
  --binding-sha256 ORIGINAL_BINDING_SHA256 --report NEW-ATTEMPT-REPORT.json
```

The latter retains exit code 2: report written, network admission blocked. Both
commands are read-only replay plus exclusive report publication; neither loads
credentials, creates a capture nor performs network I/O.

## Acceptance and next entrypoint

**36 new / 762 focused tests pass** (three existing fork deprecation warnings).
The 15 accounted local TLS scenarios and one SIGKILL scope are retained under
`data/joint-egress-accounting-2026-09-17/`. Two fresh replay processes reproduce
all 16 attempt reports and all three completed native pairs exactly, matching the
original CLI success and selected failure reports.

Acceptance extends the existing real loopback TLS peer harness instead of copying
it. It verifies the pending on-disk preparation at actual socket connect, the
complete request/weight/connection totals, native signed selectors, account/market
frames, fragmented text and pongs. Failures cover untrusted TLS, duplicate counters,
usage exhaustion, stream loss, unknown events, buffer/disk limits, cancellation,
attempt preparation/outcome fsync and slow metadata bodies. Unit checks cover
binding drift, duplicate/out-of-order writes, missing responses, stale dispatch,
profile isolation, trading-method rejection and abrupt process death. Rehashed
cross-file prefix/classification/caller/time changes are refused semantically.

Exact acceptance results and retained source/evidence pins are in the
[result JSON](portfolio-joint-egress-accounting-2026-09-17.json). No ephemeral TLS
or signing private keys are exported. Two fresh CLI replays of a completed pair
match; fresh failed-attempt replays retain the same pending consumption. Existing
single-request installed-gateway suites remain in the focused regression.
The full unrelated application suite and actual namespace kernel scenarios were
not rerun for this ordinary-process integration.

Next join this complete collector to the installed gateway's authenticated IPC,
fixed-source custody, socket ownership and expiring kernel lifecycle, retaining
per-operation and control-frame checks. That requires a deliberate boundary
between project Python/Nautilus semantics and system-Python root transport;
the current binding is not a substitute. Actual all-caller history, provider
charges, fresh qualified rate/clock evidence and host rollout remain blocked.
The frozen real draft stays **17 GETs / 468 weight**, strict continuity **0/14**,
qualified equity/day-open null and live trading blocked. Consumed bootstrap,
ADR-017 and public depth scopes remain consumed. Upstream, SourcePolicy,
SignalEvent, schedules, execution runners and the live order path are untouched.

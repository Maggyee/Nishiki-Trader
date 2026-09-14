# Joint route and native loopback integration — 2026-09-14

The offline integration now freezes BTC/ETH/BNB conversion routes from the same
run's original account, metadata and bookTicker responses, then feeds those
symbols through actual native WebSocket I/O against local fixture peers. Signed
account GETs, subscription acknowledgements, interleaved market callbacks and
closure all enter the durable joint journal. This completes the next offline
integration increment; no Binance request or actual account collection was made.

The explicit profile is `portfolio.loopback_joint_observation.v1`. The original
`portfolio.synthetic_joint_observation.v1` profile keeps its default selection and
fixed synthetic identity. Neither profile is relabelled as real source evidence.
The [prior joint design](portfolio-testnet-joint-observation-design-2026-09-13.md)
and [first synthetic acceptance](portfolio-testnet-joint-observation-acceptance-2026-09-14.md)
remain historical records.

## Original-input route fixation

`portfolio_joint_routes.py` validates the selected initial artifact's original
SHA256, logical testnet endpoint, account response hash, UID and key fingerprint.
The journal manifest must match that selection; its initial route set is empty.
A changed selection, UID, key, production endpoint or prefilled symbol set fails.
The signing object's key fingerprint must also match before any local request.
Only explicit literal `127.0.0.1` HTTP/WS endpoints are callable by this runner.
There is no credential file loader, exchange capture CLI or production fallback.

After the first full four-GET account collection, the recorded all-symbol
exchangeInfo and bookTicker bytes are parsed through the existing ADR-016
`indicative_valuation` rules. Their order, hashes, account epoch and bounded local
interval are retained. Route selection is deterministic direct-then-two-hops;
missing targets are not substituted, and a union exceeding three streams fails.
Selected one-sided/crossed/unavailable books or inadequate individual top-book
capacity fail before the market connection. Unselected and unpriced assets stay
in the report and both full native account maps. No priced subtotal becomes equity.

Only the detached state advances to the derived symbols; the startup receipt is
immutable. Route fixation retains the selected initial hash, four account raw
hashes/sequences, metadata and book raw hashes/sequences, fixation time and each
asset's route/exclusion. Both replay and collection derive the same route result
from those bytes. BookTicker remains routing evidence without qualified event
age; local recency is not quote freshness, atomicity or liquidation qualification.

## Durable dispatch and budget handling

Every GET, account WS operation and market connection gets a durable preparation
before dispatch. A response must reference its original operation, selector and
preparation ID. An interrupted or rejected operation cannot be retried. Preparation
also reserves all remaining final-account, clock and unsubscribe costs. Before
route fixation, it reserves the maximum three snapshot costs, not zero snapshots.

For the three-symbol fixture there are **20 prepared operations**: **16 GETs**,
three account WS operations and one market connection. Their documented weight
is **448**, with **two socket connection attempts**. The loopback peer accounts
for each request and returns raw REST weight headers / WS rate-limit counters.
Missing, regressing, stale or exhausted usage and changed limits stop the scope.
The runner also reserves both connection attempts against a fixture count/limit.
It refuses a one-minute weight or five-minute connection-window change; it does
not invent a reset or refresh an old usage sample.

These counters exercise the dispatch gate, not actual Binance shared-IP admission.
The initial budget sample is explicitly labelled `loopback_peer_shared_usage_fixture`.
Its 6,000/minute and 300/five-minute bounds are fixture inputs, not measurements of
other clients or proof that the two Binance endpoint families share one connection
ledger. A real source and per-endpoint connection-limit interpretation remain to
be qualified before an actual capture contract.

## Transport and failure behavior

`portfolio_joint_transport.py` uses Nautilus's Ed25519 signer and Rust native
WebSocket client, with no heartbeat or reconnect. The public local connection
uses the actual combined-stream URL derived from the frozen routes. Account raw
frames are persisted before distinguishing acknowledgements from business events;
request IDs, status, subscription identity and raw rate-limit fields are checked.
A reply and an immediate first account event in the same peer write are covered.
Each connection has its own payload-echo pong counter and control-rate limit.

The HTTP leg uses one bounded stdlib connection per GET, restricted to local
peers, with no redirect or proxy handling. It reuses the Nautilus Ed25519 signer
for the eight private reads. Original unsigned selectors and response bytes are
retained; API key, private key and outbound signatures are not put in the archive
or result logs. This is native WS/signing acceptance, not native HTTP-adapter or
actual exchange TLS acceptance.

Both transports feed the existing shared 16 MiB / 4,096-receipt budget and 64 MiB
archive. Durable dispatch times still gate processing age. Market callbacks can
arrive inside a full-account collection; an account business callback during that
collection still invalidates it. Unsupported funding/lock/fee/termination events
remain raw evidence followed by refusal. No balance patch, settlement or order
component is introduced.

A watchdog checks native socket activity, reconnect/disconnect state and journal
health. Source drift, budget refusal, unknown events, a dropped connection, disk
failure, buffer exhaustion or cancellation fails the whole interval without retry.
Both successful closes are initiated together within one five-second allowance;
failure cleanup also shares one five-second allowance and never repeats a close
already dispatched. No seal is produced after a failed close or unfinished action.
Synchronous fsync and an already-running HTTP worker are not preemptible; a timed
out worker may finish its single bounded GET, but cannot start another request.

## Verification and replay

New route/dispatch and native transport tests cover original selection/hash
refusals, direct/two-hop route fixation, missing/one-sided/insufficient-depth paths,
complete asset retention, independent budget reservations, expired/window-changing
usage, consumed preparations, foreign selectors and explicit profile separation.

The native peer acceptance verifies all **nine Ed25519 signatures** independently
with OpenSSL (eight account GETs and one subscription). Successful captures contain
**seven quotes** in the normal case and **304 quotes** with a 300-frame bootstrap
burst; four additional quotes arrive while the second account collection runs.
Both account and market pongs echo their peer payloads. Failure cases cover either
socket dropping, unknown balance events, a shared-weight jump, bootstrap pressure,
failed fsync and cancellation, without a second connection or order method.
These are bounded fixture tests, not a throughput benchmark or a real source test.

Two fresh CLI processes reproduce identical reports from a selected loopback
archive. Native quote reconstruction and both complete CASH maps run from original
bytes; the report remains private and the archive is unchanged:

```bash
.venv/bin/python -m apps.ops.portfolio_joint_observation --loopback-profile \
  --archive data/SELECTED-LOOPBACK-JOINT.jsonl \
  --archive-sha256 SELECTED-ORIGINAL-SHA256 \
  --report data/NEW-LOOPBACK-REPLAY.json
```

Omitting `--loopback-profile` retains the original synthetic profile and rejects
a loopback archive. The old fixture generated independently with `a9b4104` and
with this implementation has identical SHA256
`4a3ced9b9aab7ffd0ce5b5d97baa31a87c11d35e3cd607984f69d528cffcbb0a`.
Existing BTC depth v1/v2 behavior is unchanged.

**40 new tests** were added. Full offline regression: **2,911 passed, 12 deselected
in 276.00 seconds** (`-m 'not network and not postgres'`); the Postgres integration
cases lack a dedicated test DSN. Final closure/replay refinements also pass **91
focused tests** and a subsequent **nine native scenarios**, including two fresh
CLI replays of the actual local-peer capture. Ruff for apps/tests/notebooks,
changed-file formatting and the research registry check pass. Current results
and next steps are recorded in `docs/project-status.md`.

## Remaining actual-capture work

Next define how current shared-IP usage, per-endpoint connection-attempt usage
and identity will be obtained and bound for a real bounded testnet capture. Design
a separate testnet profile/contract with raw handshake and endpoint provenance,
current source checks and an explicit single-attempt scope before enabling or
running it. The loopback profile cannot serve as that run authorization. The
consumed public v1/v2 probes and fixed ADR-017 session must not be repeated.

Full-account/UTC/flow/reset qualification, actual fills/fees/cleanup and strict
continuity **0/14** remain blocked. All six qualification flags stay false;
qualified current/day-open/peak equity and losses stay null. No SourcePolicy,
SignalEvent, risk rule, execution runner, schedule or upstream code was changed.

Changed files: `apps/strategies_nautilus/portfolio_joint_routes.py`,
`apps/strategies_nautilus/portfolio_joint_transport.py`,
`apps/strategies_nautilus/portfolio_joint_observation.py`,
`apps/ops/portfolio_joint_observation.py`,
`tests/strategies_nautilus/test_portfolio_joint_routes.py`,
`tests/strategies_nautilus/test_portfolio_joint_transport.py`,
`apps/strategies_nautilus/README.md`, `apps/ops/README.md`,
`docs/agent-reading-list.md`, `docs/project-status.md`, and this report.

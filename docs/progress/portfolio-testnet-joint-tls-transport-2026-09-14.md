# Local joint TLS transport acceptance — 2026-09-14

The joint account/market collector now records local TLS provenance through the
complete bounded JSON WebSocket lifecycle, and detached replay reconstructs its
messages from original received bytes before native account/quote mapping. This
completes the local transport integration following the
[handshake primitive](portfolio-testnet-tls-provenance-2026-09-14.md).

The new profile is `portfolio.loopback_tls_joint_observation.v1`. It remains
separate from the synthetic journal, original native/plain loopback profile and
unimplemented real `portfolio.testnet_joint_observation.v1` draft. The
[real capture contract](portfolio-testnet-joint-capture-contract-2026-09-14.json)
is unchanged at SHA256
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
No actual exchange capture, first-request exception or new probe is enabled.
The public v1/v2 probes and ADR-017 one-BUY scope remain consumed.

## Transport and original-byte binding

`portfolio_joint_tls_transport.py` implements asyncio/OpenSSL TLS using the Python
standard library. It shares the existing joint lifecycle in
`portfolio_joint_transport.py`, including operation preparation, route fixation,
account subscriptions, GET signing, budgets and failure cleanup. Nautilus provides
Ed25519 signing and native account/quote reconstruction. TLS and frame processing
are project-owned; they are not the installed native Rust WebSocket transport,
whose interface still lacks the required provenance accessors. No upstream or
dependency change is needed.

The caller selects a PEM trust digest and exact `http.fixture.invalid`,
`account.fixture.invalid` and `market.fixture.invalid` HTTPS/WSS authorities.
All actual socket connections use literal `127.0.0.1`, with the fixture hostname
for certificate verification. The verifier requires certificate trust, hostname
checks and TLS 1.2 or newer; it is rechecked before each connection. There is no
proxy, DNS fallback, redirect, retry or reconnect. Real authorities fail manifest
validation before network I/O. Fixture certificates and signing keys are generated
only in temporary test directories.

Each connection follows the existing durable operation preparation. The journal
then retains the actual peer, certificate digest, TLS/cipher/verifier settings,
selected trust, unsigned target and Upgrade nonce before request send. Each
decrypted read chunk, at most 4 KiB, is persisted before HTTP or frame parsing.
The journal retains original response header casing, ordering and duplicate fields;
Upgrade validation checks the nonce/accept relation and rejects unrequested
extensions/subprotocols. REST uses bounded Content-Length responses and rejects
duplicate weight counters. Outbound API keys and signature bytes are never archived.

`portfolio_joint_tls_evidence.py` reconstructs messages from those chunks. Account
and market semantic receipts must consume the matching original message in FIFO
order, on the correct connection, after its original receipt sequence. Both UTC
and monotonic ages from message completion to semantic dispatch must be at most
five seconds. Subscription replies cannot predate their operation preparation.
REST semantic status, weight and body must match the completed original HTTP
response. Original chunk receipt, callback receipt and dispatch times remain
distinct; native callback timestamps retain the existing semantics.

`portfolio_ws_frames.py` implements the RFC 6455 text/continuation/control subset:
incremental reads, canonical short/16-bit/64-bit lengths, fragmented UTF-8 and
interleaved ping/pong/close. Server frames must be unmasked; outbound frames use
fresh random masks. Binary, reserved opcodes, RSV extensions, invalid UTF-8,
oversized controls, invalid close codes, nested/orphan fragments and unfinished
messages at close are refused. Aggregate text messages are bounded to one MiB.
This is a deliberate JSON transport subset, not a general WebSocket implementation.

Incoming pings bind matching durable pong preparations before send. Tests exposed
early pings both before subscription acknowledgement and before the native
`connect()` future returned. Both loopback transports now record the observed
socket connection before control processing and wait for its active handle to
send pong; connection-before-subscription does not grant account readiness.
Connection, epoch, closure and five-control-per-second checks remain enforced.

## Lifecycle, bounds and replay

Successful runs consume 16 fixture GETs and 448 fixture weight, with one account
and one market WebSocket. There are **18 TLS connections**: 16 individual HTTPS
requests and two WebSockets. The separate real draft remains 17 GETs / 468
documented weight because it adds an early metadata request. Local fixture usage
samples cannot stand in for authenticated pre-existing real usage.

Both sockets share the existing 120-second capture and one five-second shutdown
allowance. Close preparation, peer close and TLS closure must all be recorded;
unsolicited closes and truncated fragments fail. Stream reader failures wake
pending reply/bootstrap waits, and cancellation closes available clients without
retry. Successful completion requires drained frame/control queues, consumed HTTP
responses and all connections closed. Wire buffers, fragments and queued messages
count toward the existing shared 16 MiB / 4,096-event bounds; the 64 MiB archive
and incident reserve remain unchanged. Async deadlines do not preempt synchronous
filesystem operations. Failed or unsealed runs cannot be selected as successes.

The offline CLI explicitly selects the new profile:

```bash
.venv/bin/python -m apps.ops.portfolio_joint_observation \
  --tls-loopback-profile \
  --archive data/SELECTED-LOCAL-JOINT-TLS.jsonl \
  --archive-sha256 SELECTED-ORIGINAL-SHA256 \
  --report data/NEW-JOINT-TLS-REPLAY.json
```

`--tls-loopback-profile` and `--loopback-profile` are mutually exclusive. The
default synthetic profile is unchanged. The CLI has no capture or credential
options and writes a new private report. Two fresh processes reproduce identical
reports from each successful normal archive, including both full native CASH
snapshots and all three independent native quote streams. Replay verifies selected
original bytes; it does not repeat TLS authentication or authenticate a fabricated
archive. Local trust does not prove exchange identity or complete shared egress.

## Verification and remaining work

The focused suite passes **118 tests**, including **78 added cases**: 46 framing
cases, 14 source/binding cases, two account control lifecycle cases and 16 added
end-to-end scenarios. The shared peer harness now covers 25 scenarios across the
original native/plain and TLS transports. Independent peers verify nine signatures,
masked pongs and closes; normal/fragmented runs produce seven native quotes and
burst runs 304, including four quotes interleaved with the final account reads.
Failure cases include invalid trust, duplicate weight headers, masked server
frames, incomplete fragmentation, unsolicited close, socket loss, unknown events,
budget/buffer exhaustion, disk failure and cancellation.

Six additional tampering checks rehash the entire journal after substituting
account/market/REST bytes, changing endpoint/trust fields or removing a close
preparation. They fail on semantic source/closure checks rather than outer hash
integrity. The old synthetic archive remains byte-identical at SHA256
`4a3ced9b9aab7ffd0ce5b5d97baa31a87c11d35e3cd607984f69d528cffcbb0a`.
Full offline regression passes **3,093 tests, 12 deselected in 308.86 seconds**
(`-m 'not network and not postgres'`). The 12 Postgres integration cases lack a
dedicated test DSN. Ruff for apps/tests/notebooks, all 11 changed Python files'
formatting, the research registry, new progress links and diff checks pass.
`docs/project-status.md` records the same verification.

Next implement actual source/rate/complete-egress admission and the separate
durable real one-shot profile. Missing authenticated initial usage and complete
shared-egress records still block the first external request under the draft;
local transport acceptance does not supply those records. No credentials were
rediscovered and no actual venue request was made in this increment.

All six qualification flags remain false; qualified equity/loss fields and the
common account/market revision remain null. Strict continuity remains **0/14**.
No upstream, live order path, SourcePolicy, runtime schedule, dependency, risk
policy or selected private artifact changed. Project status, the reading list
and both app READMEs are updated.

Changed files: the new strategy modules `portfolio_joint_tls_transport.py`,
`portfolio_joint_tls_evidence.py`, `portfolio_ws_frames.py`; shared
`portfolio_joint_transport.py`, `portfolio_joint_routes.py`; ops
`portfolio_joint_observation.py`; five strategy test files for joint transport,
TLS evidence, frame parsing, routes and TLS provenance; both app READMEs,
`docs/agent-reading-list.md`, `docs/project-status.md`, and this report.

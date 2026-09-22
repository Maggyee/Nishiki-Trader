# Installed signed account WebSocket and partial native event receipt

Date: 2026-09-22. Phase: disposable local acceptance only.
Base commit: `a6358b8`; exact source and artifact pins are in the
[verification report](portfolio-installed-signed-ws-2026-09-22.json).

The installed gateway now signs and sends one fixed account subscription while its
original-derived market WebSocket remains open. A dedicated isolated Nautilus child
creates the Ed25519 signature. Root owns both TLS sockets and preserves subscription
response and account event bytes before interpreting them. After both sockets close
and the kernel permission is revoked, the same child constructs exact native
AccountBalance objects and acknowledges the bound payload. This extends the
[concurrent Upgrade/control milestone](portfolio-installed-concurrent-ws-2026-09-19.md).

## Contract and boundaries

`--signed-ws-fixture` and the disposable wrapper's `--signed-ws-profile` select the
new `gateway_account_ws.py` extension. Supplemental manifest v12 pins nineteen
sources. The base installation v2 bundle is unchanged. The consumed six-read route
parent owns a separate `signed-account-ws-v1` child scope; a fresh controller cannot
reuse either scope. The old control-only profile retains its explicit reader.

The signer uses the public RFC 8032 fixture key and fixed
`userDataStream.subscribe.signature` selector (`fixture-2`, recvWindow 5000).
Its identity is verified through the credential-checked Unix channel and pinned
runtime. Replay binds its executable, runtime, UID/GID, capabilities and non-network
namespaces to the final native route-read process; its IP namespace differs from
root's. Root imports no native package and gives the child no socket descriptors.
No caller-selected destination, credentials, order selector or retry is exposed.

Both connection intents persist before one unrenewable five-second kernel permit.
The existing four-second shared transport deadline starts before grant. After both
channels complete their ping/pong exchange, root challenges the native signer,
checks the selected envelope and Ed25519 signature with system OpenSSL, and
persists the challenge, original signed envelope, receive clocks and masked frame
before writing it. Signature verification, authority checks and persistence spend
the original signing window; root rechecks both clocks immediately before write.
The documented subscription weight is two; provider usage and market connection
charges remain unknown.

The fixed peer returns subscription ID zero and one `outboundAccountPosition`
envelope. Replay verifies the request ID/status, integer subscription ID, exact
message order and original frames, including a fragmented text event. It rejects
ambiguous JSON keys, extra events, market text, mismatched IDs, unexpected shapes
and precision loss. Original response/event receipt clocks come from the first
TLS chunk completing each message, not from interpretation, delivery or replay.
The account sequence is ping, subscription response, partial update, close.

`outboundAccountPosition` is a **partial update**. The fixture updates BTC only;
no missing assets are fabricated or zeroed, and no REST/full-account snapshot or
UID is inferred. Native Currency/Money/AccountBalance construction must preserve
all free/locked/total decimals at the fixed fixture precision of eight. Event E/u
are retained as provider fields; no event freshness, atomic revision, account
stream fence, complete coverage or qualified equity follows from this event.

After both peer close frames, the controller closes its sockets and records kernel
revocation before preparing the native transfer. A bounded 512-byte packet protocol
allows at most 8,192 payload bytes and five seconds total. Both sides recheck the
remaining transfer budget, including time spent parsing and waiting for IPC. The
native acknowledgement binds the exact payload and mapped result; completion is
refused without that acknowledgement. A stopped/dead child, failed persistence or
controller crash cannot synthesize a receipt or restore consumed permission.
Sibling cancellation and unconditional revocation attempts remain in the shared
transport. Cleanup kills/reaps a stopped child. Journal prefixes remain incomplete
and nonresumable even when a later offline mapper can reconstruct the same values.

## Verification

**1,184 tests pass** in 176.80 seconds with no warnings across 29 files, including
**33 new cases**. All **39 current-source disposable scenarios pass**. Two original
replays agree across 39 sets; two frozen-native replays agree across 34 sets and
147 regenerated request envelopes. Four partial results reconstruct offline, but
only the two successful scenarios retain original native acknowledgements. The
maximum sampled descriptor count is **850**, leaving **174** under the unchanged
1,024 limit. The pinned JSON records source/artifact hashes and replay outputs.
The namespace suite includes nine signed-WS cases, eight control-only cases,
ten route cases, seven signed-account cases and five echo cases. New signed cases
cover direct/two-hop route success, a bad response ID, wrong event subscription,
precision loss, an extra event, a stopped native consumer, source drift and SIGKILL.
All fixture peers use disposable namespaces; host observations must remain unchanged.

Tests also mutate fully rehashed archives to exercise the signed selector, signature,
masked wire bytes, original signing window, signer identity/runtime/namespace,
message clocks/order, revoke-before-delivery, missing/duplicate/late native receipts,
partial-event ambiguity and exact native mapping. Every proper archive prefix is
checked as incomplete with restart disabled. System Python 3.10 runs the root
controller; the child and detached native replay use frozen Python 3.12 and
Nautilus 1.226.0. The inherited descriptor limit stays 1,024 with at least 64 spare
required at sampled acceptance points; samples are not a continuous peak measure.

Selected originals and executable copies live under ignored
`data/installed-signed-ws-2026-09-22/`. Independent replay forbids socket creation,
verifies selected hashes and reconstructs the six-read prerequisites and WS state.
Frozen-native replay regenerates the same signed envelopes and balance mappings
while preserving whether the original process acknowledged delivery. Earlier
concurrent/route/descriptor evidence remains immutable.

## Next entrypoint

Integrate the remaining market/depth events and concurrent REST/depth operations
with native receipts and per-operation consumption in this installed boundary.
This fixture accepts one partial account event; it does not implement the complete
native joint collector, continuous account stream or stream fences. Real authority,
caller coverage, provider limits/clocks, host rollout and live admission remain
blocked. No upstream source, execution runner, credentials, service or real venue
request is changed, and consumed bootstrap/depth/ADR-017 scopes stay closed.

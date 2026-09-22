# Installed account and market increment native receipts

Date: 2026-09-22. Phase: disposable local acceptance only.
Base commit: `5ce3da2`; exact sources, artifacts and verification results are in the
[pinned report](portfolio-installed-market-ws-2026-09-22.json).

The installed gateway now receives combined-stream depth increments concurrently
with its native signed account subscription. Each original-derived route symbol
contributes two bounded depth events. After both channels close and kernel egress
permission is revoked, the isolated native child acknowledges the account update
and exact OrderBookDelta batches together. This extends the
[signed account receipt](portfolio-installed-signed-ws-2026-09-22.md) without claiming
a snapshot-backed order book or quote observation.

## Implementation and boundaries

`gateway_market_ws.py` adds an explicit `--market-ws-fixture` profile and disposable
`--market-ws-profile` wrapper. Supplemental manifest v13 pins twenty sources. The
base installation bundle remains v2 and unchanged. A consumed six-read route parent
owns a separate `account-market-ws-v1` scope; failed or uncertain attempts cannot
resume. Legacy account-only and control-only profiles remain explicit.

Selection first replays all six original metadata/account/order/book bundles. The
market extension reconstructs metadata from the original HTTPS chunks and binds its
archive hash, selected symbols and fixed fixture decimal representations into the
joint journal. The fixture uses eight-place Price and Quantity representations,
consistent with its original asset precision fields. This does not validate venue
PRICE_FILTER/LOT_SIZE constraints. The market URL uses the same original-derived
symbol union, including the accepted two-hop conversion case.

The existing two gateway-owned TLS sockets share one unrenewable five-second kernel
permit and a four-second total transport deadline starting before grant. Both fixed
connection intents persist before grant. The account path still challenges the
isolated native signer, verifies its fixed Ed25519 subscription with OpenSSL and
persists the exact masked request before write. Root stays stdlib-only and the child
receives no IP socket or descriptors. Once both channels finish ping/pong, account
and market receive tasks run concurrently. Each must finish its bounded events
before either channel prepares close. Failure cancels the sibling and attempts
revocation even when persistence fails.

The market reader preserves raw TLS chunks before parsing text/continuation frames.
It binds every accepted event to the original chunk completing that message and
retains both UTC and monotonic receipt clocks. Combined-stream name, data symbol,
event type, update IDs and finite decimal levels must agree with the selection.
Each side has at most four levels, no duplicate prices and no rounding. Provider E
and U/u remain original fields; no current freshness is inferred. Per-symbol event
time cannot decrease. The second update must cover `previous_u + 1` and advance u;
a bounded overlap is allowed, while gaps, stale/duplicate ranges and missing symbols
are refused. All selected symbols require exactly two events; extra frames cannot
silently become an accepted complete transcript.

These are **unanchored depth segments**. The first update has no REST snapshot
anchor. An UPDATE uses the provider's absolute size; zero size maps to DELETE.
The child creates actual native Price, Quantity, BookOrder, OrderBookDelta and
OrderBookDeltas objects, verifies exact dictionary round-trips and marks only the
last delta in each event with F_LAST. The update's u becomes sequence; E becomes
ts_event and the original root receive UTC becomes ts_init. No OrderBook or
QuoteTick is constructed. Snapshot linkage, synchronized-book, stream-fence,
qualified-equity and execution flags remain false.

A single receipt payload binds the original account partial update, metadata
selection and market events. Both sockets must have original peer-close evidence
and root-recorded revocation before delivery. The existing 8,192-byte / 512-byte
packet / five-second IPC limits remain. Root and child recheck transfer time,
including parse time; the final acknowledgement covers both exact native results
and payload bytes. Offline mapping never fills a missing original acknowledgement.
Stopped children are killed/reaped, and no attempt or kernel window is renewed.

## Verification

**1,216 tests pass** in 185.39 seconds without warnings across 30 files, including
**32 new cases**. All **51 current-source disposable scenarios pass**. Two original
replays agree across 51 sets; two frozen-native replays agree across 46 sets and
217 regenerated request envelopes. Five market results / twenty native delta
batches reconstruct offline; only three retain original native acknowledgements.
The maximum sampled descriptor count is **852**, leaving **172** under the unchanged
1,024 limit. The linked JSON pins exact sources, artifacts and independent outputs.
The twelve new actual scenarios cover direct/two-hop/overlap success, a gap,
duplicate update, wrong stream, precision loss, a missing symbol, an extra market
event, stopped native consumer, source drift and controller SIGKILL. Local peer
threads exchange fragmented market/account text frames and require both event
senders to finish before accepting close. Regression retains the nine signed
account WS, eight control-only, ten route, seven account GET and five echo cases.

Tests exercise native UPDATE/DELETE mapping, batch flags and original times;
fully rehashed archive mutations; per-symbol ranges and independent clocks;
wrong symbols/streams, ambiguous keys, integer overflow, missing symbols,
precision loss, extra events, absent revocation and missing native receipts.
Every proper joint-journal prefix remains incomplete and nonresumable.
The root controller uses system Python 3.10; native work uses frozen Python 3.12 /
Nautilus 1.226.0. The inherited descriptor limit remains 1,024, with at least 64
spare required at sampled acceptance points. No continuous peak claim follows.

Evidence is retained under ignored `data/installed-market-ws-2026-09-22/`.
Independent readers verify protected source and original archive hashes, forbid
socket creation and replay the six-read prerequisites and both channel histories.
Frozen-native readers regenerate signed envelopes and exact account/delta batches,
preserving original acknowledgement status. Prior signed/account/route evidence
and consumed real scopes are unchanged.

## Next entrypoint

Integrate fixed per-symbol REST depth snapshot attempts while the gateway owns the
streams, then link buffered increments to those original snapshot revisions before
constructing native books/quotes. Preserve the shared deadline, descriptor reserve,
per-operation consumption and original clocks. The complete joint collector,
continuous account stream fences, real source authority/caller coverage, provider
limits/clocks, host rollout, qualified equity and trading remain blocked.
No upstream source, execution runner, service, credentials or real venue request
was changed. Bootstrap/depth/ADR-017 one-shot scopes remain consumed.

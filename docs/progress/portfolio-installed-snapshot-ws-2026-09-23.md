# Installed fixture depth snapshot revision linkage

Date: 2026-09-23. Phase: disposable local acceptance only. The machine-readable
[acceptance summary](portfolio-installed-snapshot-ws-2026-09-23.json) pins the
ignored original report and runtime bundle. No real venue endpoint was contacted.

## Scope and result

The separately consumed `account-market-snapshot-v1` scope extends the existing
six-read route parent and concurrent account/market WebSocket fixture. Before
the single five-second kernel grant, the gateway records one fixed REST depth
connection attempt for each original-selected symbol. It establishes checked
`rest.fixture.invalid` TLS sockets while both WebSockets are live, persists each
exact GET before write and every HTTPS chunk with original UTC/monotonic receipt
clocks. Request/response failures consume the scope; no reconnect or retry occurs.
All sockets close and the kernel permit is revoked before the isolated native
child acknowledges the combined account, market and snapshot payload.

Manifest v14 pins twenty-one protected sources; the base installation bundle,
1,024-descriptor limit and existing v13 market-only scope remain distinct. The
root controller remains stdlib-only. The child reconstructs exact native
AccountBalance and OrderBookDelta batches, and the new receipt binds each
snapshot's HTTP original hash, `lastUpdateId` and eligible event hashes. The
first buffered `U` must not exceed `lastUpdateId`; the first retained event
must cover `lastUpdateId + 1`, and subsequent events must cover the previous
`u + 1`. Events with `u <= lastUpdateId` are explicitly obsolete.
The fixture's two events per symbol and four eight-place assets are bounded;
one linked revision segment does not establish persistent depth continuity.

The local four-scenario acceptance passed. Direct and two-hop routes each
linked two snapshots at revision 101 to their next original events through
revision 103, leaving one obsolete event per symbol. A snapshot at revision
104 lacked a covering event and remained incomplete; a malformed revision was
refused before snapshot acceptance. All four scopes are consumed. The report
records 98/98/94/94 scenario checks, unchanged host observations, zero venue
requests and at most 854 sampled controller descriptors, leaving 170 under the
unchanged limit. The retained report and frozen runtime live under ignored
`data/installed-snapshot-ws-2026-09-23/` and are selected by SHA256 in the
linked JSON; they are not committed or reusable dispatch authority.

Focused tests check too-old/missing/obsolete/gapped revisions, exact requests, duplicated
HTTP/JSON fields, incorrect lengths, crossed/unsorted/rounded levels, altered
chunk hashes, early close, missing or altered native acknowledgement and every
journal prefix. The new and existing WebSocket, installation and source-custody
suite passes 151 tests. The prior v13 evidence remains immutable.
The existing market-only entry also passes all 12 disposable scenarios using the
new source inventory; its separate report is pinned in the linked JSON. This
regression does not modify or replay the prior v13 originals.

## Boundaries and next entrypoint

This fixture links revisions but does not construct a synchronized native
OrderBook or QuoteTick. It has no account stream fence, event-time freshness
qualification, complete full-account joint collection or proven global caller
coverage. The response weight counter is a fixture value; provider charges,
actual limits/clock/usage, signer/source authority and qualified full-account
valuation remain unknown. Neither local replay nor sampled descriptor headroom
admits a real testnet joint attempt or trading. Consumed ADR-017/bootstrap/depth
one-shot scopes and production order runners are unchanged.

Next connect the complete native joint collector to this installed per-dispatch
gateway, then separately prove synchronized per-symbol books and native quote
construction with original snapshot/update timing. Obtain qualified real source
authority, complete egress records and fresh provider budget evidence before any
new real one-shot admission review. Reboot/power-loss and storage rollback also
remain unqualified.

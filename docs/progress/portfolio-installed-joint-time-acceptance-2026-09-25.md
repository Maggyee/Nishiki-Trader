# Installed linked second-clock acceptance

Date: 2026-09-25. Phase: disposable local fixture only. The
[machine-readable summary](portfolio-installed-joint-time-acceptance-2026-09-25.json)
pins eight ignored original reports under `data/`, with their SHA256 values.
No host installation, real venue request, production key or trading permission
was used.

Manifest `portfolio.installed_gateway_fixture.v24` pins 26 project-owned
sources. All eight reports use the same source hashes; each pinned source hash
matches the checkout. Under one distinct `portfolio.installed_joint_linked_time.v1`
parent, the dedicated UID accepts 13/19 ordered operations. The account and
market WebSockets stay open while the root captures four bounded original
market increments (two per selected symbol), then two route-bound depth-100
snapshots for `BNBUSDT` and `BTCUSDT`. Replay links both revision anchors to
their increments. Operation 12 is a second fixed `/api/v3/time` GET after both
snapshots. Its original TLS clock and native receipt bind to the two snapshot
TLS hashes. The clock is checked against the buffered market events and UTC
day; this does not qualify a provider clock.

The successful `--joint-time-profile` scenario prepares and accepts 13 steps.
The bad-clock scenario prepares 13, accepts only 12 and leaves index 12 pending
without native clock acknowledgement; the parent cannot resume. Success peaks
at 917/1,024 sampled descriptors and bad clock at 915/1,024. The three
`--joint-linked-profile` regressions accept 12 steps on success, stop at 9 for
an increment gap, and stop at 11 for a crossed second book. Depth, reads,
clock, account WS, unsubscribe and market WS regressions also pass under the
same v24 source inventory: 31 isolated scenarios in all. The 122 directly
related Python tests and Ruff checks pass.

Only the 13/19 ordered fixture prefix is accepted. The remaining planned
operations are a second four-GET account pass, a final clock GET and account
WebSocket unsubscribe in a fresh parent. No complete before/after account
interval, synchronized OrderBook, QuoteTick or stream fence is established.
Complete caller coverage, real gateway authority, provider charge/clock
qualification, qualified equity and any real trading admission remain blocked.
Preserve all consumed fixture scopes; historical v22/v23 reports do not
certify this v24 inventory.

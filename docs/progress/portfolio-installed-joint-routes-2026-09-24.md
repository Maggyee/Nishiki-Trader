# Installed same-parent route fixation

Date: 2026-09-24. Phase: disposable local fixture only. The
[machine-readable summary](portfolio-installed-joint-routes-2026-09-24.json)
pins ignored original reports under `data/`. No host installation, real venue
request, production key or trading permission was used.

Manifest v20 pins 24 project-owned sources and a distinct v2 disposable parent.
One account WebSocket remains open across the native initial clock, Upgrade,
signed subscription, the first account/orders/orders/account GET pass, and two
new GETs: fixed index 7 `/api/v3/exchangeInfo` and index 8
`/api/v3/ticker/bookTicker`. Each GET has a dedicated UID request selector,
single-use ledger scope, original TLS receive clocks and chunks, kernel
revocation, and exact native receipt before parent acceptance. Metadata has
its own `exchange_info` classification; the original rate fields are parsed,
with connection/RAW_REQUESTS usage still unknown. The parent binds metadata
precision to the four fixture account assets and derives a bounded route from
the same parent's original metadata, first account and books. The successful
selection is `BNBUSDT` and `BTCUSDT`; zero ETH stays explicit. No bookTicker
event time is fabricated.

Four isolated scenarios pass. Success prepares and accepts nine ordered steps;
changed orders prepares six and accepts five, changed balances prepares seven
and accepts six, insufficient BTC top-book quantity prepares nine and accepts
eight. Each failure leaves its scope consumed with kernel permission revoked.
The successful peak is 881/1,024 sampled descriptors. Three older account WS,
two clock and two unsubscribe scenarios pass against the v20 source inventory.
Related egress/ledger pytest runs pass 1,012 tests, with 20 snapshot tests
passing separately due to the existing fixture registration order.

Only **9/19 planned operations** have joined this parent. The fixture has four
known account assets, no market/depth/time segment, second four-GET account
pass, complete before/after interval or stream fence. Older separate route and
unsubscribe fixtures cannot extend these originals. Next integrate market
connection, bounded depth snapshots and linked clock in this same parent, then
the second four-GET pass, final clock and account unsubscribe. Provider clock
qualification, real authority and shared egress coverage, host rollout,
qualified equity and trading remain blocked. Consumed scopes never reopen.

To repeat with a new disposable path:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --joint-reads-profile --report data/NEW-JOINT-ROUTES.json
```

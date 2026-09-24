# Installed same-parent market connection

Date: 2026-09-24. Phase: disposable local fixture only. The
[machine-readable summary](portfolio-installed-joint-market-connect-2026-09-24.json)
pins ignored original reports under `data/`. No host installation, venue
request, production key or trading permission was used.

Manifest v21 pins 24 project-owned sources. A distinct v3 disposable parent
accepts the first nine native/WS/REST operations, then fixes a market WebSocket
request from the original metadata, first account and bookTicker receipts. The
account WebSocket stays open while the root connects to the selected
`BNBUSDT`/`BTCUSDT` combined-depth URL. The tenth step durably records the
market intent before kernel grant, validates the TLS peer/SNI and exact Upgrade
request, preserves original response chunks and receive clocks, verifies the
Upgrade, revokes the permit, then accepts. Route and predecessor bundle hashes
are bound to the step. No socket is passed to the native child.

Five isolated scenarios pass. The success prepares and accepts ten steps. Old
order/balance/top-book refusals accept five/six/eight. A malformed market Upgrade
prepares ten but accepts only nine; the scope is consumed and kernel permission
is revoked. The successful peak is 881/1,024 sampled descriptors. Three older
account WS, two clock and two unsubscribe scenarios pass against the v21 source
inventory. Related egress/ledger pytest runs pass 1,019 tests, with 20 snapshot
tests passing separately due to the existing fixture registration order.

Only **10/19 planned operations** have joined this parent. The success closes
both sockets after its tenth accepted step; it records no market increment,
depth snapshot, linked time, second four-GET account pass, final clock or
unsubscribe. Neither stream fence nor complete before/after account interval
exists. Later independent fixtures cannot extend these originals. The next
entrypoint is a fresh disposable parent that keeps both channels alive while
receiving bounded market increments and fixed REST depth anchors, then samples
linked time before the second account pass. Provider charge/clock authority,
complete shared egress coverage, host rollout, qualified equity and all real
trading remain blocked. Consumed scopes stay closed.

To repeat with a new disposable path:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --joint-reads-profile --report data/NEW-JOINT-MARKET.json
```

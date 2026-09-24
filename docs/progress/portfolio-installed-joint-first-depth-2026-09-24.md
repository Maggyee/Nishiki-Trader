# Installed first route-bound depth anchor

Date: 2026-09-24. Phase: disposable local fixture only. The
[machine-readable summary](portfolio-installed-joint-first-depth-2026-09-24.json)
pins ignored original reports under `data/`. No host installation, real venue
request, production key or trading permission was used.

Manifest v22 pins 26 project-owned sources. A distinct v1 parent retains the
first ten ordered operations from the v3 market-connection parent, then replays
the original route receipts to select the sorted two-symbol set
`BNBUSDT`/`BTCUSDT`. The native child receives that set and its original route
hash through the installed, dedicated-UID launcher. Its separate 19-step
selector fixes index 10 to unsigned `BNBUSDT` depth 100. The root validates
the selected request and captures original HTTPS chunks and receive clocks.
Both account and market WebSocket sockets remain open during the GET. Native
Price/Quantity precision checks and the exact snapshot body bind the receipt
after kernel revocation. The older 20-step, three-symbol fixture remains intact.

Two isolated scenarios pass. Success prepares and accepts 11 steps; the native
receipt contains revision 100 and the exact one-level bid/ask, with no claimed
increment linkage. A crossed book prepares 11 but accepts only 10: the depth
ledger remains pending, no native receipt is acknowledged, kernel permission
is revoked, and fresh-process replay refuses to reopen the consumed parent.
The successful peak is 899/1,024 sampled descriptors. The five v3 joint-read
scenarios and older clock, account-WS and unsubscribe scenarios pass under
the v22 source inventory. Related tests pass 451 checks: 199 focused
request/replay/ledger checks, 232 shared regressions and 20 separate snapshot
checks (kept separate due to the existing fixture registration order).

Only **11/19 planned operations** have joined this parent. No market depth
increment is recorded or linked to the first snapshot; the second `BTCUSDT`
snapshot, linked time, second four-GET account pass, final clock and unsubscribe
are absent. No synchronized OrderBook, QuoteTick, complete account interval or
stream fence exists. Prior independent fixtures do not extend these originals.
Provider charge/clock authority, complete shared egress coverage, host rollout,
qualified equity and all real trading remain blocked. Consumed scopes stay
closed. The next entrypoint is a new disposable parent retaining both sockets
while anchoring the second symbol and receiving bounded original increments.

To repeat with a new disposable path:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --joint-depth-profile --report data/NEW-JOINT-DEPTH.json
```

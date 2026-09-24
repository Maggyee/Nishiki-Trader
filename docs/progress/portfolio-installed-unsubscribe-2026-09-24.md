# Installed fixture account unsubscribe receipt

Date: 2026-09-24. Phase: disposable local fixture acceptance only. The
[machine-readable result](portfolio-installed-unsubscribe-2026-09-24.json)
pins the ignored report and native runtime hashes. Manifest v16 pins the same
22 project sources as v15, now with an independent route parent and WS child
scope. No host installation or real venue permission changed.

The dedicated UID produces the fixed `userDataStream.unsubscribe` request for
subscription ID 0. Root verifies its selector and the exact masked WS frame,
persists preparation before send, and retains the raw reply and receipt clocks.
Unsubscribe follows the original partial account update and both accepted
depth snapshots. The account connection closes only after the exact ID/status/
empty-result acknowledgement. Both sockets then close and kernel permission is
revoked before the dedicated UID acknowledges the original partial account
event and two Nautilus L2/QuoteTicks. The receipt explicitly records that the
account event covers one asset only; it is not a complete snapshot or stream
fence. The selected route parent still has six GETs, followed by two depth
GETs in the WS child.

Two installed scenarios pass their expected outcomes: `unsub_success` has a
complete receipt (103 checks, two native quotes), while `unsub_bad_ack` ends
`incomplete_no_resume` (97 checks, no native receipt). Both consume the parent
scope; neither permits restart. The maximum sampled controller descriptor count
is 856 of 1,024. Separate v16 runs pass all three prior quote scenarios and
all nine prior signed-account WS scenarios, including their failure paths.
One hundred nine focused tests cover account, market, snapshot, quote, v14
handoff and unsubscribe behavior; the original v14 report still hashes to
`7b0e035ddaddd907bb46678a4e55012c94b7c2de9c56df562738ca94a6b68547`.

This adds one fixed WS API operation to a separate fixture, but does not
complete the 19-operation joint plan. Three `/time`, two `/account` and two
`/openOrders` GETs remain missing, and the installed operations are not yet
in the plan's order. No complete account interval or ordered joint operation
is accepted. Real source authority, shared-egress coverage, provider charges,
fresh limits/clocks and all trading remain blocked. The next entrypoint is a
new ordered installed parent that executes both complete four-GET account
reads with time samples and derives selected route symbols before market
bootstrap, then binds the fixed unsubscribe to that same epoch.

To repeat local acceptance use a fresh disposable report path:

```bash
/usr/bin/python3 -I infra/egress-guard/installed_gateway_selftest.py \
  --unsub-ws-profile --report data/NEW-UNSUB-WS.json
```

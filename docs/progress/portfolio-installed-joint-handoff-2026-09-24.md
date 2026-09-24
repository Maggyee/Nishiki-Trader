# Installed fixture to joint collector handoff audit

Date: 2026-09-24. Phase: offline comparison only. The
[machine-readable result](portfolio-installed-joint-handoff-2026-09-24.json)
points to the ignored original report and hashes; no new collection, socket,
credential, native runtime or venue request was used.

## Evidence and result

`apps.ops.portfolio_installed_joint_handoff` selects the installed v14 fixture
report by its full SHA256 and pins its protected source inventory against current
project-owned source bytes. It independently replays the six-read route archive
and the concurrent signed-account/market/snapshot archive for the direct and
two-hop successes. Original route selection, closure, revocation and exact native
account/delta acknowledgement must match the recorded results. Both successes
passed twice in fresh project processes, with identical reports and no change to
the selected source report's SHA256.

For two selected symbols, the fixture has six route GETs and two REST depth GETs:
eight total. The full ordinary-process joint collector's fixed request plan
requires 15 GETs plus three account WS operations and one market connection:
19 operations. The absent GETs are three `/time`, two `/account` and two
`/openOrders`; account `userDataStream.unsubscribe` is also absent. Even matching
selector names are not a joint operation prefix: the installed six reads follow
their own route/scope/order, not the collector's two full four-GET account passes.
Thus **zero ordered joint operations and zero complete account intervals** are
accepted. The fixture subscription acknowledgement does not authenticate a real
account. Snapshot revisions link to native depth-delta receipts, but no synchronized
OrderBook, QuoteTick or stream fence is established.

The audit is read-only; its output `blocked_incomplete_joint_collector` does not
authorize a collection, real gateway budget, testnet probe or trading. Focused
tests cover current source pins, changed/missing/extra source inventories, the
two-symbol budget, depth-plan drift and malformed/unselected input. The two
installed successes provide the full original-byte replay evidence; synthetic route fixtures lack
the installed signed-process namespace metadata and are not used to assert an
equivalent complete installed run.

## Next entrypoint

Implement the fixed missing operations and original-byte receipts within the
installed per-dispatch gateway, and bind a complete native joint collector to
that gateway under an explicitly separate disposable fixture scope. Verify the
two complete account reads on one signed epoch, time sampling, WS unsubscribe,
ordered budget consumption and cleanup, then separately qualify synchronized
per-symbol books and native quotes. Source authority, actual provider limits and
shared egress coverage remain independent prerequisites for any new real attempt.
The consumed prior scopes, testnet BUY allowance and live order path are unchanged.

To reproduce the offline audit against the retained report:

```bash
.venv/bin/python -m apps.ops.portfolio_installed_joint_handoff \
  --report data/installed-snapshot-ws-2026-09-23/final.json \
  --report-sha256 7b0e035ddaddd907bb46678a4e55012c94b7c2de9c56df562738ca94a6b68547 \
  --scenario snapshot_success
```

Use `--scenario snapshot_two_hops` for the second selected original route.

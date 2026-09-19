# Installed repeated open orders and account locks

Started: 2026-09-18. Verification completed: 2026-09-19. Phase: disposable local fixture integration. This extends the
[three-read sequence](portfolio-installed-read-sequence-2026-09-18.md) with an
explicit five-read profile. Exact selected sources, originals and verification
results are pinned in the matching JSON.

## Result and boundaries

One root controller now performs `exchangeInfo → account → openOrders → openOrders
→ account`. Each step launches a fresh isolated dedicated-UID native consumer,
uses one expiring permission, revokes it before response delivery, and closes its
ledger before the next preparation. The separate parent scope is
`fixture-order-sequence-v1`; the old three-read profile remains distinct. The
supplemental installation manifest is v9 with fifteen protected sources.

The new `gateway_native_orders.py` specializes the existing signed account exchange
for the fixed openOrders selector. Nautilus signs each original challenge in the
child; root checks its exact request, signature and original five-second window
before connecting/writing to the local TLS peer. The request digest binds the
single-attempt order ledger and outcome. Root never imports Nautilus.

From each original response, the child constructs actual native OrderStatusReport
objects with account/instrument/order/client IDs, side, LIMIT/GTC, accepted or
partially-filled status, original accepted/update times and receipt initialization
time. Native Quantity/Price values must equal the original decimal values exactly;
rounding is refused. Native-generated random report UUIDs are excluded from the
deterministic receipt. Every selected exchange field, including cumulative quote
quantity, is retained without inferring trade, fill or fee history.

This fixture supports at most sixteen open orders in BTCUSDT/ETHUSDT/BNBUSDT,
positive prices and quantities, NEW or PARTIALLY_FILLED status, and no iceberg,
stop, list or quote-quantity orders. Duplicate exchange/client IDs, conflicting
status/quantities and invalid original timestamps are refused. Precision is fixed
at eight places and must agree with the acknowledged four-asset metadata. These
are local contract limits, not qualification of arbitrary venue order types.

The two sorted order sets must agree across all retained fields, comparing decimal
amounts numerically. Remaining BUY quantity times limit price reserves USDT;
remaining SELL quantity reserves the base asset. Decimal arithmetic with precision
80 sums these amounts against every original account lock, including zeros.
Both endpoint account reads must also have identical UID/free/locked/total values.
Empty open orders only reconcile with zero locked balances.

The nonempty fixture contains a BTC BUY reserving 12.5 USDT, a partially filled
BNB SELL reserving 0.1 BNB, and a BTC SELL reserving 0.001 BTC; ETH has zero locks.
These checks establish consistency of linked endpoint observations. They do not
establish an atomic snapshot, continuous stream fence, absence of intervening
changes, historical commissions or qualified equity.

The five requests cost 220 documented fixture weight: metadata 20, two accounts
at 20 each, and two openOrders reads at 80 each. Synthetic response counter samples
remain original evidence and are not aggregate usage or quota qualification.
Account/order responses do not acquire inferred metadata rate limits. The ordinary
20-operation collector and real 17-GET / 468-weight draft remain unchanged.

Public RFC 8032 test keys and synthetic accounts confer no actual source authority.
No real venue request, host installation, service, credential change, upstream
modification or live-path change occurred. Bootstrap, public-depth and ADR-017
scopes remain consumed.

## Failure and replay behavior

Parent preparations and acceptances retain the existing durable prefix linkage,
clock ordering, held originals and permanent drift invalidation. Reconciliation
can refuse a parent even when an individual order read completed and acknowledged.
Native precision failure and stopped consumers preserve missing acknowledgements;
malformed duplicate orders never acquire a native receipt. SIGKILL after the first
accepted order read retains its predecessors without fabricating completion.
Source drift prevents the next preparation. Every parent scope remains consumed;
no restart, replay or restored file bytes renew authority.

The existing kernel, signing, TLS and receipt deadlines remain unchanged. Held
paths reuse descriptors; the observed five-step peak is 990 under the inherited
1,024 limit. No resource limit was raised. Power-loss/rollback durability, hostile
root races and qualification of arbitrary runtime libraries remain outside this
acceptance.

## Verification

**47 new / 841 focused Python tests pass**, without warnings, in 53.53 seconds.
**53 current-source disposable scenarios pass**: nine new order cases, seven old
sequence, seven signed account, seven native metadata, seven native request,
eleven stdlib receipt and five echo. Two original replays match across all 53
scenario sets; two frozen-runtime native replays match across 37 sets and
regenerate 120 request envelopes. The new order scenarios contain 33 actual read
steps and 24 signed requests. The matching JSON pins every result. The new tests cover all parent prefixes, actual native partial-order reports, precise
amounts, unsupported fields, duplicate/empty sets, original/signature/receipt
splicing, repeated-order drift and exact BUY/SELL locks.

Nine new actual scenarios cover nonempty success, empty success, repeated order
change, precision refusal, duplicates, lock mismatch, stopped consumer, controller
SIGKILL and source drift. Current-source regressions also exercise the original
three-read, signed account, native metadata, native request, stdlib receipt and echo
modes. Python regression covers the unchanged pure TLS and IPC boundaries.

Retained originals live in `data/installed-order-sequence-2026-09-18/`; raw reports,
runtime binaries and source copies remain ignored and pinned, not committed.
The earlier 33-scenario selection, all retained originals and fourteen source
copies were hash-checked unchanged. Replays disable socket creation and DNS, verify
the selected original hashes and preserve original clocks and missing receipts.
Native replays use the frozen ordinary-user runtime and regenerate original signed
requests and mapped reports; they cannot repair a refused parent.

```bash
/usr/bin/python3 -I data/installed-order-sequence-2026-09-18/replay.py
data/installed-order-sequence-2026-09-18/offline-runtime/bin/python3.12 -I -B data/installed-order-sequence-2026-09-18/native-replay.py
```

## Next implementation entrypoint

Derive market routes from same-run book/metadata/account originals, then integrate
concurrent gateway-owned TLS/WS with the installed native collector. Preserve the
per-operation consumption, native acknowledgements and original clocks. Actual
authority/coverage, provider limits/clocks/unknown charges, host rollout, full equity
and UTC baselines, and trading admission remain blocked. No new ADR or service is
required for the next local implementation.

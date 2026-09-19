# Installed original book routes after native account reconciliation

Date: 2026-09-19. Phase: disposable fixture integration. This extends the
[five-read order sequence](portfolio-installed-order-sequence-2026-09-18.md)
with a separate six-read route profile. Exact sources, reports, runtime and replay
pins are recorded in the matching JSON.

## Result

The fixed sequence is `exchangeInfo → account → openOrders → openOrders → account
→ bookTicker`. The separate `fixture-route-sequence-v1` parent retains the existing
single-use ordering, native acknowledgements, original clocks and no-resume rule.
Earlier three/five-read profiles remain distinct. Manifest v10 pins sixteen sources.

`gateway_book_routes.py` adds the fixed unsigned GET selector at index 8, transported
through the existing credential channel from the native child. It sends no API key
or signature. Root validates the exact selector and challenge window, records its
request hash in the separate one-attempt books ledger, owns the TLS socket, and
revokes kernel permission before delivering the original response to the child.
There is no arbitrary endpoint or payload parameter.

The dedicated UID constructs native Price and Quantity objects from all bid/ask
prices and quantities, and refuses silent eight-place rounding. Only bounded,
nonnegative decimal strings and unique symbol rows are accepted. Zero or crossed
sides remain original evidence and are excluded from route edges as applicable.
REST bookTicker has no event timestamp: no QuoteTick or fabricated event time is
created. Root imports only standard-library code.

After the sixth receipt, root reparses the exact first metadata TLS payload and
uses the acknowledged final account and book results. All three inputs belong to
the same parent preparation chain and installation. Metadata definitions require
known fixture assets and eight-place precision; book rows must bind to unique
metadata symbols. A TRADING symbol with spot enabled offers a bid edge from base
to quote and an inverse-ask edge from quote to base when that side has positive
price and quantity. Missing, disabled, crossed and empty sides stay explicit.

Every account asset stays in the output. USDT needs no market leg; a zero balance
also needs no route. Each nonzero other asset needs a direct USDT path, or otherwise
a two-hop path through one of the other fixed fixture assets. Selection uses
shortest-path then lexical destination/symbol/side identity, never the best price
or an opportunistic deeper path. The policy is an explicit bounded fixture variant
of the ordinary collector's direct-then-two-hop policy, with only BNB/BTC/ETH/USDT.
It does not substitute for the full-account valuation planner.

For each chosen leg, the entire free-plus-locked balance must fit the original
side's top-book capacity. Bid capacity is base quantity; inverse-ask capacity is
ask quantity times ask price. Exact rational arithmetic carries the amount across
legs without rounding or changing capacity at inverse rates. Insufficient capacity
refuses the route step even if its individual native book receipt succeeded.
Capacity is checked separately for each asset; shared legs do not become pooled
liquidation capacity or reserved order depth. There is no resulting equity value
or order-sizing authority.

The route union is capped at three symbols. The successful fixture selects
BNBUSDT and BTCUSDT; zero ETH stays explicit without a stream selection. The actual
two-hop fixture disables direct BNBUSDT and selects BNBBTC plus BTCUSDT instead.
This demonstrates response-derived selection rather than reuse of the old fixed
three-symbol request envelope. The route summary binds original metadata payload,
metadata/account/book TLS digests and the original final receipt clock.

The original metadata-header to book-body interval must fit 60 seconds in one UTC
day, and UTC/monotonic elapsed time must agree within 50 ms. This bounded input
interval does not qualify individual quote age or refresh evidence during replay.
Repeated balances/orders and all account locks must still reconcile before books.
All six child ledgers close and revoke before another preparation or completion.

The budget is six GETs / 224 documented fixture weight, including bookTicker weight
4. Synthetic original counter samples do not measure aggregate usage or quota.
The new books response does not acquire rate limits from metadata. Prior local
20-operation and real 17-GET / 468-weight contracts remain unchanged.

## Verification and retained evidence

**47 new / 888 focused tests pass**, without warnings, in 59.90 seconds.
**63 current-source disposable scenarios pass**: ten route, nine five-read order,
seven three-read sequence, seven signed account, seven native metadata, seven
native request, eleven stdlib receipt and five echo cases. Two original replays
match across all 63 sets; two frozen-runtime native replays match across 47 sets
and regenerate 168 request envelopes. The route cases contain 58 read steps,
40 signed private requests and eight unsigned book requests. Five book receipts
are native-acknowledged; only the two successful parents qualify route completion.
The matching JSON pins all results. New tests exercise six actual
native receipts over credential-framed channels, every parent prefix, direct and
inverse/two-hop routes, exact capacity boundaries, zero balances, malformed or
unbound books, metadata/precision/spot-status refusals, original splicing, stale
intervals and UTC boundaries. Old profiles refuse the new parent schema.

Ten new namespace scenarios cover direct success, two-hop success, missing books,
insufficient depth, native precision refusal, duplicate books, disabled metadata,
SIGSTOP of the final consumer, controller SIGKILL after the second account, and
source drift before the book preparation. A completed child cannot repair a refused
parent. Stopped consumers are killed/reaped under the existing timeout; interrupted
parents remain consumed with missing acknowledgements intact. Source drift remains
permanently invalidating. No deadline or resource limit is increased. Observed controller descriptor peak
is 1,009 under the inherited 1,024 limit; later integration must respect that
remaining margin rather than adding unbounded held inputs.

Selected source copies, original report/journal bundles, frozen native runtime and
replay drivers live under `data/installed-route-sequence-2026-09-19/`. They remain
ignored and are hash-pinned by tracked evidence. Earlier retained evidence is
immutable. Original replays disable socket creation and DNS. Native replays use
the frozen ordinary-user runtime to regenerate exact request envelopes and native
mappings, preserving original times, missing receipts and parent refusals.

```bash
/usr/bin/python3 -I data/installed-route-sequence-2026-09-19/replay.py
data/installed-route-sequence-2026-09-19/offline-runtime/bin/python3.12 -I -B data/installed-route-sequence-2026-09-19/native-replay.py
```

## Boundaries and next entrypoint

This is bounded local read-only route selection. No real venue requests, operator
keys, upstream modifications, host installation, service or live order-path changes
occurred. LLMs do not enter execution. Full equity, event-time freshness, atomic
snapshots, user-stream fences, source authority, caller coverage and real admission
remain unqualified. Consumed bootstrap, public-depth and ADR-017 scopes stay closed.
Power-loss/rollback and hostile root races retain the prior acceptance limits.

Next integrate concurrent gateway-owned TLS/WS with the installed collector,
consuming this original-derived symbol union while retaining per-operation durable
accounting, native receipts and original clocks. Full collector source/runtime
custody must continue to fit inherited resource limits. No new ADR or service is
needed for the next disposable implementation.
